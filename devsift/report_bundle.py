"""Bounded source-reproved report pages with unbounded disk-backed coverage indexes."""
import hashlib
import json
import os
import re
from urllib.parse import quote
from pathlib import Path
import uuid

from .ci_artifacts import build_reports, ArtifactError
from .output import result
from .evidence import SourceEvidence
from .scan_store import _mkdir_private, _private_file, _safe_path
from .redaction import Redactor
from .markdown_report import render_markdown, rule_guidance, _text

_FORMAT_NAMES = {'json': 'findings.json', 'markdown': 'report.md', 'sarif': 'results.sarif'}


def _dump(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))


def _write(directory, name, text):
    path = directory / name
    with _private_file(path, 'xb') as stream:
        stream.write(text.encode('utf-8'))
        stream.flush()
    return {'file': name, 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'bytes': len(text.encode('utf-8'))}


def _digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def build_bundle(stored, *, formats=None, policy=None, trusted_lifecycles=False, language='en'):
    if language not in ('en', 'th'):
        raise ArtifactError('Report artifacts unavailable')
    requested = ('json', 'markdown', 'sarif') if formats is None else formats
    if (type(requested) is not tuple or not requested or len(set(requested)) != len(requested)
            or any(name not in _FORMAT_NAMES for name in requested)):
        raise ArtifactError('Report artifacts unavailable')
    connection = stored.connection
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS report_pages(id INTEGER PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS report_cases(finding INTEGER PRIMARY KEY,page INTEGER NOT NULL);
        DELETE FROM report_pages;
        DELETE FROM report_cases;
    ''')
    directory = stored.directory / ('reports-' + uuid.uuid4().hex)
    _mkdir_private(directory)
    scan_summary = stored.summary()
    source_summary = scan_summary
    terms = getattr(stored, 'terms_assessment', None)
    if terms is not None:
        from .terms_gate import source_record
        source_summary = source_record(scan_summary, terms)
    all_complete = scan_summary['complete']
    source_complete = source_summary['complete']
    reports_rendered = True
    page_number = 0
    case_count = 0

    def render(items):
        nonlocal page_number, case_count, all_complete, source_complete, reports_rendered
        findings = [json.loads(payload) for _, payload in items]
        record = result('scan', complete=source_summary['complete'],
                        enforced_count=sum(item['enforcement'] == 'block' for item in findings),
                        findings=findings, errors=source_summary['errors'])
        try:
            report, documents = build_reports(record, repo_root=stored.root, formats=requested,
                                             policy=policy, trusted_lifecycles=trusted_lifecycles,
                                             source_timeout_seconds=None, language=language)
            if set(documents) != set(requested):
                raise ArtifactError('Report artifacts unavailable')
            human_document = documents.get('markdown')
            if human_document is None:
                human_document = render_markdown(report, language=language)
            by_case = {case.case_id: case.to_dict() for case in report.cases}
            aligned = []
            for original in findings:
                reproved = by_case[original['case_id']]
                updated = dict(original)
                for key in ('source', 'severity', 'lifecycle_class', 'enforcement', 'security_escalation'):
                    updated[key] = reproved[key]
                aligned.append(updated)
            page_record = result('scan', complete=report.complete,
                                 enforced_count=sum(item['enforcement'] == 'block' for item in aligned),
                                 findings=aligned, errors=source_summary['errors'])
            if len(_dump(page_record)) > 4_000_000:
                raise ArtifactError('Report artifacts unavailable')
        except (ValueError, TypeError, OSError):
            if len(items) > 1:
                midpoint = len(items) // 2
                render(items[:midpoint])
                render(items[midpoint:])
                return
            all_complete = False
            source_complete = False
            reports_rendered = False
            stored.error('REPORT_UNAVAILABLE')
            # A failed case is indexed explicitly and never represented as a rendered report.
            documents = {}
            report = None
            fallback = [{**item, 'source': SourceEvidence(reason='SOURCE_UNAVAILABLE').to_dict(),
                         'lifecycle_class': 'UNKNOWN', 'enforcement': 'incomplete'} for item in findings]
            page_record = result('scan', complete=False, findings=fallback, errors=stored.errors())
            if len(_dump(page_record)) > 4_000_000:
                # A failed proof never exports oversized source or a made-up location.
                for item in fallback:
                    item['path'] = '[UNAVAILABLE]'
            if len(_dump(page_record)) > 4_000_000:
                raise ArtifactError('Report artifacts unavailable')
        page_number += 1
        stem = f'page-{page_number:08d}'
        page_dir = directory / stem
        _mkdir_private(page_dir)
        scan_descriptor = _write(page_dir, 'scan.json', _dump(page_record))
        scan_descriptor['file'] = stem + '/' + scan_descriptor['file']
        files = [scan_descriptor]
        for name, document in documents.items():
            text = document if type(document) is str else _dump(document)
            descriptor = _write(page_dir, _FORMAT_NAMES[name], text)
            descriptor['file'] = stem + '/' + descriptor['file']
            files.append(descriptor)
        if report is None:
            descriptor = _write(page_dir, 'ERROR.md', '# Report unavailable\n\nSource-reproved rendering failed for this case. The scan is incomplete.\n')
            descriptor['file'] = stem + '/' + descriptor['file']
            files.append(descriptor)
        else:
            all_complete = all_complete and report.complete
            source_complete = source_complete and report.complete
            # Keep public finding assertions aligned with the re-proved report.
            with connection:
                for (identity, _), updated in zip(items, aligned):
                    connection.execute('UPDATE findings SET payload=? WHERE id=?', (_dump(updated), identity))
                    reproved = updated
                    if reproved['enforcement'] == 'incomplete' or reproved['source']['status'] != 'VERIFIED':
                        connection.execute('UPDATE targets SET complete=0 WHERE identity=(SELECT target FROM findings WHERE id=?)', (identity,))
        human_file = next((item['file'] for item in files if item['file'].endswith('/report.md')), None)
        if report is not None and human_file is None:
            descriptor = _write(page_dir, 'human.md', human_document)
            descriptor['file'] = stem + '/' + descriptor['file']
            files.append(descriptor)
            human_file = descriptor['file']
        anchors = {} if report is None else {case.case_id: f'case-{ordinal:04d}'
                                            for ordinal, case in enumerate(report.cases, 1)}
        page = {'page': page_number, 'case_count': len(items),
                'case_ids': [item['case_id'] for item in findings], 'files': files,
                'rendered': report is not None, 'complete': report is not None and report.complete,
                'human_file': human_file, 'case_anchors': anchors}
        with connection:
            connection.execute('INSERT INTO report_pages VALUES (?,?)', (page_number, _dump(page)))
            connection.executemany('INSERT INTO report_cases VALUES (?,?)',
                                   ((identity, page_number) for identity, _ in items))
        case_count += len(items)

    page = []
    for identity, payload in stored.iter_findings():
        page.append((identity, payload))
        if len(page) == 32:
            render(page)
            page = []
    if page or page_number == 0:
        render(page)
    terms_files = []
    terms_count = 0
    if terms is not None:
        terms_count = len(terms.to_dict()['cases'])
        try:
            terms_files = _build_terms(stored, directory, requested, language)
            if 'TERMS_OUTPUT_LIMIT' in terms.to_dict()['errors']:
                reports_rendered = False
        except (ValueError, TypeError, OSError, KeyError):
            reports_rendered = False
            all_complete = False
            stored.error('REPORT_UNAVAILABLE')
    bundle = {'index': str(directory / 'index.json'), 'markdown_index': str(directory / 'README.md'),
              'page_count': page_number, 'case_count': case_count, 'complete': bool(all_complete),
              'reports_complete': reports_rendered, 'analysis_complete': bool(all_complete),
              'formats': requested, 'language': language}
    bundle['source_analysis_complete'] = bool(source_complete)
    if terms is not None:
        bundle.update(terms_files=terms_files, terms_case_count=terms_count,
                      total_case_count=case_count + terms_count, terms_binding=terms.binding_digest)
    pages_valid = _verify_pages(stored, bundle) and _verify_terms(stored, bundle)
    bundle['reports_complete'] = bool(reports_rendered and pages_valid)
    bundle.update(_write_frontdoor(stored, bundle, language))
    # Index arrays stream directly from the database, independent of case count.
    index = directory / 'index.json'
    with _private_file(index, 'x', encoding='utf-8', newline='\n') as stream:
        metadata = {'schema_version': '1', 'complete': bool(all_complete),
                    'reports_complete': bundle['reports_complete'], 'analysis_complete': bool(all_complete),
                    'report': '../REPORT.md', 'report_sha256': bundle['report_sha256'],
                    'target_count': scan_summary['data']['target_count'], 'case_count': case_count,
                    'execution': scan_summary['data']['execution'],
                    'quality_gate': scan_summary['data'].get('quality_gate', {}),
                    'page_count': page_number, 'formats': requested, 'language': language, 'errors': stored.errors()}
        if terms is not None:
            metadata.update(terms_files=terms_files, terms_case_count=terms_count,
                            total_case_count=case_count + terms_count, terms_binding=terms.binding_digest,
                            source_analysis_complete=bool(source_complete),
                            terms_gate=scan_summary['data']['terms_gate'])
        stream.write(_dump(metadata)[:-1] + ',"pages":[')
        separator = ''
        for (payload,) in connection.execute('SELECT payload FROM report_pages ORDER BY id'):
            stream.write(separator + payload)
            separator = ','
        stream.write(']}\n')
    markdown = directory / 'README.md'
    with _private_file(markdown, 'x', encoding='utf-8', newline='\n') as stream:
        stream.write(('# ดัชนีรายงาน DevSift ทุกส่วน\n\n' if language == 'th' else '# DevSift complete report index\n\n') +
                     f'Analysis: {"complete" if all_complete else "incomplete"}. '
                     f'Report artifacts: {"complete" if bundle["reports_complete"] else "incomplete"}. '
                     f'Cases: {case_count}. Pages: {page_number}.\n\n')
        stream.write('[REPORT.md](../REPORT.md)\n\n')
        if terms is not None:
            stream.write(('ข้อกำหนดบุคคลที่สาม' if language == 'th' else 'Third-party terms') +
                         f': {terms_count} cases; ' + ', '.join(
                             f'[{item["file"]}]({item["file"]})' for item in terms_files) + '\n\n')
        for (payload,) in connection.execute('SELECT payload FROM report_pages ORDER BY id'):
            page = json.loads(payload)
            stream.write(f'- Page {page["page"]}: {page["case_count"]} cases; ')
            stream.write(', '.join(f'[{Path(item["file"]).name}]({item["file"]})' for item in page['files']))
            stream.write('\n')
    bundle.update(index_sha256=_digest(index), markdown_sha256=_digest(markdown))
    if not verify_bundle(stored, bundle):
        stored.error('REPORT_UNAVAILABLE')
        bundle['complete'] = False
        bundle['reports_complete'] = False
    return bundle


def _build_terms(stored, directory, requested, language):
    """One independent, complete terms channel, even for zero source findings."""
    from .markdown_report import render_terms_markdown
    assessment = stored.terms_assessment
    record = result('scan', complete=True, data={'scope': 'terms_only'})
    _, documents = build_reports(record, repo_root=stored.root, formats=requested,
                                 language=language, terms_assessment=assessment)
    # The human artifact is a section, suitable for the full REPORT.md front door.
    documents['markdown'] = render_terms_markdown(assessment, language=language)
    names = {'json': 'terms.json', 'markdown': 'terms.md', 'sarif': 'terms.sarif'}
    return [_write(directory, names[name], text if type(text) is str else _dump(text))
            for name, text in documents.items()]


def _verify_terms(stored, bundle):
    assessment = getattr(stored, 'terms_assessment', None)
    if assessment is None:
        return 'terms_files' not in bundle
    try:
        if (bundle.get('terms_binding') != assessment.binding_digest or
                bundle.get('terms_case_count') != len(assessment.to_dict()['cases'])):
            return False
        names = {'json': 'terms.json', 'markdown': 'terms.md', 'sarif': 'terms.sarif'}
        required = {names[name] for name in bundle['formats']} | {'terms.md'}
        descriptors = bundle['terms_files']
        if len(descriptors) != len(required) or {item['file'] for item in descriptors} != required:
            return False
        for item in descriptors:
            path = Path(bundle['index']).parent / item['file']
            _safe_path(path)
            if path.stat().st_size != item['bytes'] or _digest(path) != item['sha256']:
                return False
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def _verify_pages(stored, bundle):
    """Check exact case coverage and every artifact digest without loading the index."""
    try:
        connection = stored.connection
        expected = connection.execute('''SELECT count(*) FROM findings f JOIN targets t
            ON t.identity=f.target WHERE t.generation=?''', (stored.generation,)).fetchone()[0]
        covered = connection.execute('SELECT count(*) FROM report_cases').fetchone()[0]
        if expected != covered or expected != bundle['case_count']:
            return False
        missing = connection.execute('''SELECT 1 FROM findings f JOIN targets t ON t.identity=f.target
            LEFT JOIN report_cases c ON c.finding=f.id WHERE t.generation=? AND c.finding IS NULL LIMIT 1''',
            (stored.generation,)).fetchone()
        orphan = connection.execute('SELECT 1 FROM report_cases c LEFT JOIN report_pages p ON p.id=c.page WHERE p.id IS NULL LIMIT 1').fetchone()
        if missing or orphan:
            return False
        page_count = 0
        for (payload,) in connection.execute('SELECT payload FROM report_pages ORDER BY id'):
            page = json.loads(payload)
            page_count += 1
            if not page['rendered']:
                return False
            required = {_FORMAT_NAMES[name] for name in bundle['formats']} | {'scan.json'}
            if 'markdown' not in bundle['formats']:
                required.add('human.md')
            if {Path(item['file']).name for item in page['files']} != required:
                return False
            anchors = page.get('case_anchors')
            if (type(anchors) is not dict or set(anchors) != set(page['case_ids'])
                    or any(re.fullmatch(r'case-[0-9]{4,}', anchor) is None for anchor in anchors.values())
                    or len(set(anchors.values())) != len(anchors)):
                return False
            actual = connection.execute('SELECT count(*) FROM report_cases WHERE page=?', (page['page'],)).fetchone()[0]
            identities = [row[0] for row in connection.execute('SELECT f.case_id FROM findings f JOIN report_cases c ON c.finding=f.id WHERE c.page=? ORDER BY f.case_id', (page['page'],))]
            if actual != page['case_count'] or identities != sorted(page['case_ids']):
                return False
            for descriptor in page['files']:
                artifact = Path(bundle['index']).parent / descriptor['file']
                from .scan_store import _safe_path
                _safe_path(artifact)
                if not artifact.resolve().is_relative_to(Path(bundle['index']).parent.resolve()):
                    return False
                digest = hashlib.sha256()
                size = 0
                with artifact.open('rb') as stream:
                    while chunk := stream.read(65536):
                        digest.update(chunk)
                        size += len(chunk)
                if digest.hexdigest() != descriptor['sha256'] or size != descriptor['bytes']:
                    return False
        if page_count != bundle['page_count']:
            return False
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def verify_bundle(stored, bundle):
    """Coverage, all page files, indexes and the owned human front door must agree."""
    try:
        if not _verify_pages(stored, bundle) or not _verify_terms(stored, bundle):
            return False
        if Path(bundle['report']) != stored.directory / 'REPORT.md':
            return False
        for name, key in (('index', 'index_sha256'), ('markdown_index', 'markdown_sha256'),
                          ('report', 'report_sha256')):
            path = Path(bundle[name])
            _safe_path(path)
            if _digest(path) != bundle[key]:
                return False
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def _page_human(directory, page):
    name = page.get('human_file')
    if not page.get('rendered') or type(name) is not str:
        return None
    for descriptor in page['files']:
        if descriptor['file'] == name:
            path = directory / name
            _safe_path(path)
            if (not path.resolve().is_relative_to(directory.resolve())
                    or path.stat().st_size != descriptor['bytes'] or _digest(path) != descriptor['sha256']):
                return None
            return path
    return None


def _source_link(stored, finding):
    source = finding['source']
    if source['status'] != 'VERIFIED' or source['location'] is None:
        return None
    location = source['location']
    path = stored.root / location['path']
    label = _text(location['path']) + ':' + str(location['region']['start_line'])
    if Redactor().text(str(path)) != str(path):
        # Keep the verified relative location; a redacted absolute ancestor
        # cannot safely become a navigable destination.
        return label, None
    try:
        href = quote(Path(os.path.relpath(path, stored.directory)).as_posix(), safe='/')
    except ValueError:  # Cross-drive Windows working-copy navigation.
        href = path.as_uri()
    return label, href + '#L' + str(location['region']['start_line'])


def _copy_human_page(source, output, page_number):
    """Namespace generated navigation in the copy; leave sealed files/code intact."""
    fence = None
    with source.open('r', encoding='utf-8', newline='') as stream:
        for line in stream:
            marker = re.fullmatch(r'(`{3,})(?:text)?\r?\n', line)
            if marker:
                if fence is None:
                    fence = marker[1]
                elif marker[1] == fence:
                    fence = None
                output.write(line)
                continue
            if fence is None:
                if re.fullmatch(r'<a id="case-[0-9]+(?:-(?:review|implement))?"></a>\r?\n', line):
                    line = line.replace('id="case-', f'id="page-{page_number:08d}-case-', 1)
                elif line.startswith(('| [', '[Review prompt]')):
                    line = re.sub(r'\]\(#case-([0-9]+(?:-(?:review|implement))?)\)',
                                  lambda match: f'](#page-{page_number:08d}-case-{match[1]})', line)
            output.write(line)



def _recover_frontdoor(stored, report_path):
    """Resolve only a committed old/new hash journal; never adopt foreign bytes."""
    _safe_path(report_path)
    connection = stored.connection
    row = connection.execute("SELECT value FROM metadata WHERE key='human_report_pending'").fetchone()
    if row is None:
        return
    journal = json.loads(row[0])
    valid_hash = lambda value: type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None
    if (type(journal) is not dict or set(journal) != {'previous', 'next'}
            or not valid_hash(journal['next'])
            or (journal['previous'] is not None and not valid_hash(journal['previous']))):
        raise ArtifactError('Report artifacts unavailable')
    committed = connection.execute("SELECT value FROM metadata WHERE key='human_report_sha256'").fetchone()
    known = {journal['previous'], journal['next']}
    if (None if committed is None else committed[0]) not in known:
        raise ArtifactError('Report artifacts unavailable')
    current = _digest(report_path) if report_path.exists() else None
    if current is not None and current not in known:
        raise ArtifactError('Report artifacts unavailable')
    with connection:
        if current is not None:
            stored._set('human_report_sha256', current)
        connection.execute("DELETE FROM metadata WHERE key='human_report_pending'")



def _check_frontdoor_destination(path, original, previous):
    _safe_path(path)
    if original is None:
        if path.exists():
            raise ArtifactError('Report artifacts unavailable')
    else:
        observed = path.stat(follow_symlinks=False)
        if ((observed.st_dev, observed.st_ino) != (original.st_dev, original.st_ino)
                or _digest(path) != previous[0]):
            raise ArtifactError('Report artifacts unavailable')


def _write_frontdoor(stored, bundle, language):
    """Stream the full human report and atomically replace only our prior artifact."""
    thai = language == 'th'
    def tr(english, translated):
        return translated if thai else english
    summary = stored.summary()
    counts = summary['data']['counts']
    directory = Path(bundle['index']).parent
    connection = stored.connection
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS report_frontdoor_pages(page INTEGER PRIMARY KEY,valid INTEGER NOT NULL);
        DELETE FROM report_frontdoor_pages;
    """)
    for identity, payload in connection.execute('SELECT id,payload FROM report_pages ORDER BY id'):
        page = json.loads(payload)
        try:
            valid = _page_human(directory, page) is not None
        except (OSError, ValueError, TypeError, KeyError):
            valid = False
        connection.execute('INSERT INTO report_frontdoor_pages VALUES (?,?)', (identity, int(valid)))
    connection.commit()
    report_path = stored.directory / 'REPORT.md'
    _recover_frontdoor(stored, report_path)
    previous = connection.execute("SELECT value FROM metadata WHERE key='human_report_sha256'").fetchone()
    if report_path.exists() and (previous is None or _digest(report_path) != previous[0]):
        raise ArtifactError('Report artifacts unavailable')
    original = None if not report_path.exists() else report_path.stat(follow_symlinks=False)
    temporary = stored.directory / ('REPORT-' + uuid.uuid4().hex + '.pending')
    created = None
    try:
        with _private_file(temporary, 'x', encoding='utf-8', newline='\n') as output:
            created = os.fstat(output.fileno())
            def add(value=''):
                output.write(value + '\n')
            add(tr('# DevSift report', '# รายงาน DevSift'))
            add()
            add(tr('Read this first: scope, actual coverage, problems and next actions.',
                   'เริ่มอ่านที่นี่: ตรวจส่วนไหน วิเคราะห์จริงเท่าไร พบอะไร และควรทำอะไรต่อ'))
            add()
            add(tr('Next: inspect the verified case and callers before proposing a change. If no analyzer ran, follow setup diagnosis below.',
                   'ทำต่อ: ตรวจกรณีที่ยืนยันและผู้เรียกก่อนเสนอแก้ไข หาก analyzer ยังไม่ทำงาน ให้ทำตามขั้นตอนตั้งค่าด้านล่าง'))
            add()
            add('| ' + tr('Item | Result', 'รายการ | ผล') + ' |')
            add('| --- | --- |')
            data = summary['data']
            rows = [
                (tr('Repository', 'Repository'), _text(Redactor().text(str(stored.root)))),
                (tr('Scope', 'ขอบเขต'), _text(str(data.get('scope', data.get('mode', 'UNKNOWN'))))),
                (tr('Status / exit', 'สถานะ / exit'), summary['status'] + ' / ' + str(summary['exit_code'])),
                (tr('Inventory targets', 'รายการใน inventory'), str(data['target_count'])),
                (tr('Executed / incomplete / skipped / unavailable', 'เรียก analyzer / ไม่ครบ / ข้าม / ไม่พร้อม'),
                 ' / '.join(str(counts[name]) for name in ('executed', 'incomplete', 'skipped', 'unavailable'))),
                (tr('Cases', 'กรณีทั้งหมด'), str(data['finding_count'])),
                ('reports_complete / analysis_complete',
                 str(bundle['reports_complete']).lower() + ' / ' + str(bundle['analysis_complete']).lower()),
            ]
            if getattr(stored, 'terms_assessment', None) is not None:
                gate = data['terms_gate']
                rows.extend([
                    (tr('Source / terms / total cases', 'กรณี source / ข้อกำหนด / รวม'),
                     f"{data['finding_count']} / {data['terms_case_count']} / {data['total_case_count']}"),
                    (tr('Terms gate / serious blocks', 'Gate ข้อกำหนด / Block ร้ายแรง'),
                     gate['status'] + ' / ' + str(gate['enforced_count'])),
                    (tr('Owner decision required', 'ต้องขอการตัดสินใจจาก Owner'),
                     str(gate['decision_required']).lower()),
                ])
            for label, value in rows:
                add(f'| {label} | {value} |')
            add()
            add(tr('## Diagnosis and next actions', '## ผลวินิจฉัยและขั้นตอนถัดไป'))
            add()
            codes = {item['code'] for item in summary['errors']}
            terms_only = data.get('scope') == 'terms_only'
            if terms_only:
                add(tr('This is a terms-only assessment. No source analyzer was requested; code quality is not certified.',
                       'นี่เป็นการประเมินข้อกำหนดเท่านั้น ไม่ได้ขอเรียก source analyzer จึงไม่รับรองคุณภาพโค้ด'))
            elif data['target_count'] == 0:
                if data.get('scope') == 'changed' or data.get('mode') == 'incremental':
                    add(tr('No targets were selected in changed scope. This does not analyze the whole project; use `devsift scan --all` for that scope.',
                           'ขอบเขต changed เลือกได้ 0 ไฟล์ จึงยังไม่ได้ตรวจทั้งโปรเจกต์ หากต้องการตรวจทั้งหมดใช้ `devsift scan --all`'))
                else:
                    add(tr('Inventory returned no targets. Confirm the repository root and explicit scope; no source analysis can be inferred.',
                           'inventory ไม่พบรายการ ต้องตรวจ repository root และ scope ที่เลือก ยังสรุปว่ามีการวิเคราะห์ source ไม่ได้'))
            if counts['executed'] == 0 and not terms_only:
                add(tr('No analyzer executed. Zero findings here is not evidence of analyzed clean code.',
                       'ยังไม่มีการเรียก analyzer จริง ผล 0 findings จึงไม่ใช่หลักฐานว่าโค้ดที่วิเคราะห์แล้วผ่าน'))
            missing = codes & {'NO_AVAILABLE_ANALYZER', 'ANALYZER_UNAVAILABLE', 'NATIVE_TOOL_UNAVAILABLE',
                               'NATIVE_MANIFEST_UNAVAILABLE', 'NATIVE_CONFIGURATION_UNAVAILABLE',
                               'NATIVE_SETUP_REQUIRED', 'REGISTERED_ANALYZER_UNAVAILABLE',
                               'REGISTERED_ANALYZERS_UNAVAILABLE', 'ANALYZER_SETUP_REQUIRED'}
            if missing or any('SETUP' in code or 'NATIVE_CONFIG' in code for code in codes):
                add(tr('Configured analyzers are missing, untrusted or unavailable. Run `devsift setup --status` and `devsift doctor`; neither command installs tools.',
                       'analyzer ยังไม่ได้ตั้งค่า ไม่ผ่าน trust หรือไม่พร้อมใช้งาน ให้ตรวจ `devsift setup --status` และ `devsift doctor` ซึ่งไม่ติดตั้งเครื่องมือ'))
                add(tr('Rerun the official DevSift updater to prepare its verified analyzers, or register an independently approved existing manifest once:',
                       'รันตัวอัปเดต DevSift ทางการเพื่อเตรียม analyzer ที่ผ่านการตรวจ หรือ register manifest เดิมที่ผู้ดูแลอนุมัติแล้วเพียงครั้งเดียว:'))
                add('```text\ndevsift setup --native-manifest ABSOLUTE_MANIFEST --native-manifest-digest TRUSTED_SHA256\n```')
                add(tr('Never discover a manifest in the project and calculate a digest to approve it yourself. Then rerun the intended scan scope.',
                       'ห้ามหยิบ manifest จากโปรเจกต์แล้วคำนวณ digest เพื่ออนุมัติเอง จากนั้นรัน scan ใน scope ที่ต้องการอีกครั้ง'))
            if counts['incomplete'] or 'FINDING_UNRESOLVED' in codes:
                add(tr('Some analysis/source proof is incomplete. Read the declared errors and unresolved cases; do not treat missing evidence as a pass.',
                       'บางส่วนวิเคราะห์หรือยืนยัน source ไม่ครบ ให้อ่าน error และกรณี SOURCE_UNRESOLVED โดยไม่แปลว่าหลักฐานที่ขาดคือผ่าน'))
            if not bundle['reports_complete']:
                add(tr('REPORT INCOMPLETE: a requested case/page/artifact could not be verified. This file does not claim every full case was rendered.',
                       'รายงานไม่ครบ: มีกรณี หน้า หรือไฟล์ที่ตรวจยืนยันไม่ได้ ไฟล์นี้ไม่อ้างว่าแสดงรายละเอียดครบทุกกรณี'))
            if data['finding_count'] == 0 and counts['executed'] and summary['complete']:
                add(tr('No findings were returned by the analyzers that executed within this declared scope; this is not a claim about unimplemented rules or unselected files.',
                       'analyzer ที่เรียกใน scope นี้ไม่คืน findings ไม่ใช่การรับรองกฎที่ยังไม่รองรับหรือไฟล์ที่ไม่ได้เลือก'))
            for error in summary['errors']:
                add('- ' + _text(error['code']) + ': ' + _text(error['message']))
            add()
            index_link = quote(os.path.relpath(directory / 'index.json', stored.directory).replace('\\', '/'), safe='/')
            add('[' + tr('Complete page/checksum index', 'ดัชนีทุกหน้าและ checksums') + '](' + index_link + ')')
            add()
            if getattr(stored, 'terms_assessment', None) is not None:
                add('<a id="third-party-terms"></a>')
                if _verify_terms(stored, bundle):
                    with (directory / 'terms.md').open(encoding='utf-8') as terms_stream:
                        for line in terms_stream:
                            output.write(line)
                    add()
                else:
                    add(tr('## Third-party terms report unavailable', '## รายงานข้อกำหนดบุคคลที่สามไม่พร้อมใช้งาน'))
                    add(tr('The terms gate remains in force; evidence delivery is incomplete. Reassess before acting.',
                           'Gate ข้อกำหนดยังคงมีผล แต่ส่งหลักฐานไม่ครบ ต้องประเมินใหม่ก่อนดำเนินการ'))
                    add()
            add(tr('## Problem priority and verified files', '## ลำดับปัญหาและไฟล์ที่ยืนยันแล้ว'))
            add()
            add('| ' + tr('Case | Severity / rule | Verified file | What to inspect / next action',
                         'กรณี | ความรุนแรง / กฎ | ไฟล์ที่ยืนยัน | ปัญหาและแนวทางตรวจแก้') + ' |')
            add('| --- | --- | --- | --- |')
            query = """SELECT f.payload,p.payload,v.valid FROM findings f JOIN targets t ON t.identity=f.target
                JOIN report_cases c ON c.finding=f.id JOIN report_pages p ON p.id=c.page
                JOIN report_frontdoor_pages v ON v.page=p.id WHERE t.generation=?
                ORDER BY CASE json_extract(f.payload,'$.severity') WHEN 'Critical' THEN 0 WHEN 'Error' THEN 1
                         WHEN 'Warning' THEN 2 ELSE 3 END,f.case_id,f.id"""
            for payload, page_raw, valid in connection.execute(query, (stored.generation,)):
                finding, page = json.loads(payload), json.loads(page_raw)
                if valid:
                    relative = quote(os.path.relpath(directory / page['human_file'], stored.directory).replace('\\', '/'), safe='/')
                    case_link = '[' + _text(finding['case_id']) + '](' + relative + '#' + page['case_anchors'][finding['case_id']] + ')'
                else:
                    case_link = _text(finding['case_id'])
                source = _source_link(stored, finding) if valid else None
                location = (('[' + source[0] + '](' + source[1] + ')') if source and source[1]
                            else source[0] if source else 'SOURCE_UNRESOLVED / UNKNOWN')
                explanation, action = rule_guidance(finding['rule_id'], language)
                add(f'| {case_link} | {finding["severity"]} / {finding["rule_id"]} | {location} | {_text(explanation)}; {_text(action)} |')
            add()
            add(tr('## All case details', '## รายละเอียดทุกกรณี'))
            add()
            add(tr('Source links navigate the working copy; immutable SHA and exact verified regions remain in each case. Review advice is not an approved patch or automatic edit authority.',
                   'ลิงก์ไฟล์เปิด working copy; แต่ละกรณีคง Git SHA และพิกัดที่ยืนยันแล้ว แนวทางทบทวนไม่ใช่ patch ที่อนุมัติหรือสิทธิ์แก้ source อัตโนมัติ'))
            add()
            for identity, payload in connection.execute('SELECT id,payload FROM report_pages ORDER BY id'):
                page = json.loads(payload)
                add('## ' + tr('Report part ', 'ส่วนรายงานที่ ') + str(identity))
                add()
                try:
                    human = _page_human(directory, page)
                except (OSError, ValueError, TypeError, KeyError):
                    human = None
                if human is None:
                    add(tr('Full source-reproved case report unavailable; no source location or BEFORE is asserted for: ',
                           'ยังไม่มีรายงานกรณีฉบับเต็มที่ยืนยันได้ จึงไม่อ้าง source location หรือ BEFORE ของ: ')
                        + ', '.join(_text(case) for case in page['case_ids']))
                else:
                    _copy_human_page(human, output, identity)
                add()
            output.flush()
            os.fsync(output.fileno())
        _check_frontdoor_destination(report_path, original, previous)
        _safe_path(temporary)
        digest = _digest(temporary)
        # Commit ownership of both possible atomic-replace outcomes before the
        # filesystem changes. Cancellation at any later point is recoverable.
        with connection:
            stored._set('human_report_pending', _dump({
                'previous': None if previous is None else previous[0], 'next': digest}))
        _check_frontdoor_destination(report_path, original, previous)
        os.replace(temporary, report_path)
        with connection:
            stored._set('human_report_sha256', digest)
            connection.execute("DELETE FROM metadata WHERE key='human_report_pending'")
        return {'report': str(report_path), 'report_sha256': digest}
    finally:
        if created is not None:
            try:
                observed = temporary.stat(follow_symlinks=False)
                if (observed.st_dev, observed.st_ino) == (created.st_dev, created.st_ino):
                    temporary.unlink()
            except OSError:
                pass
