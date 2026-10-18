"""Bounded source-reproved report pages with unbounded disk-backed coverage indexes."""
import hashlib
import json
from pathlib import Path
import uuid

from .ci_artifacts import build_reports, ArtifactError
from .output import result

_FORMAT_NAMES = {'json': 'findings.json', 'markdown': 'report.md', 'sarif': 'results.sarif'}


def _dump(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))


def _write(directory, name, text):
    path = directory / name
    with path.open('xb') as stream:
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


def build_bundle(stored, *, formats=None, policy=None, trusted_lifecycles=False):
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
    directory.mkdir()
    scan_summary = stored.summary()
    all_complete = scan_summary['complete']
    page_number = 0
    case_count = 0

    def render(items):
        nonlocal page_number, case_count, all_complete
        findings = [json.loads(payload) for _, payload in items]
        record = result('scan', complete=scan_summary['complete'],
                        enforced_count=sum(item['enforcement'] == 'block' for item in findings),
                        findings=findings, errors=scan_summary['errors'])
        try:
            report, documents = build_reports(record, repo_root=stored.root, formats=requested,
                                             policy=policy, trusted_lifecycles=trusted_lifecycles)
        except (ValueError, TypeError, OSError):
            if len(items) > 1:
                midpoint = len(items) // 2
                render(items[:midpoint])
                render(items[midpoint:])
                return
            all_complete = False
            stored.error('REPORT_UNAVAILABLE')
            # A failed case is indexed explicitly and never represented as a rendered report.
            documents = {}
            report = None
        page_number += 1
        stem = f'page-{page_number:08d}'
        page_dir = directory / stem
        page_dir.mkdir()
        files = []
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
            # Keep public finding assertions aligned with the re-proved report.
            with connection:
                by_case = {case.case_id: case.to_dict() for case in report.cases}
                for (identity, _), original in zip(items, findings):
                    reproved = by_case[original['case_id']]
                    updated = dict(original)
                    for key in ('source', 'severity', 'lifecycle_class', 'enforcement', 'security_escalation'):
                        updated[key] = reproved[key]
                    connection.execute('UPDATE findings SET payload=? WHERE id=?', (_dump(updated), identity))
                    if reproved['enforcement'] == 'incomplete' or reproved['source']['status'] != 'VERIFIED':
                        connection.execute('UPDATE targets SET complete=0 WHERE identity=(SELECT target FROM findings WHERE id=?)', (identity,))
        page = {'page': page_number, 'case_count': len(items),
                'case_ids': [item['case_id'] for item in findings], 'files': files,
                'rendered': report is not None, 'complete': report is not None and report.complete}
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
    # Index arrays stream directly from the database, independent of case count.
    index = directory / 'index.json'
    with index.open('x', encoding='utf-8', newline='\n') as stream:
        metadata = {'schema_version': '1', 'complete': bool(all_complete),
                    'target_count': scan_summary['data']['target_count'], 'case_count': case_count,
                    'page_count': page_number, 'formats': requested, 'errors': stored.errors()}
        stream.write(_dump(metadata)[:-1] + ',"pages":[')
        separator = ''
        for (payload,) in connection.execute('SELECT payload FROM report_pages ORDER BY id'):
            stream.write(separator + payload)
            separator = ','
        stream.write(']}\n')
    markdown = directory / 'README.md'
    with markdown.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('# DevSift complete report index\n\n'
                     f'Status: {"complete" if all_complete else "incomplete"}. '
                     f'Cases: {case_count}. Pages: {page_number}.\n\n')
        for (payload,) in connection.execute('SELECT payload FROM report_pages ORDER BY id'):
            page = json.loads(payload)
            stream.write(f'- Page {page["page"]}: {page["case_count"]} cases; ')
            stream.write(', '.join(f'[{Path(item["file"]).name}]({item["file"]})' for item in page['files']))
            stream.write('\n')
    bundle = {'index': str(index), 'markdown_index': str(markdown), 'page_count': page_number,
              'case_count': case_count, 'complete': bool(all_complete),
              'index_sha256': _digest(index),
              'markdown_sha256': _digest(markdown)}
    if not verify_bundle(stored, bundle):
        stored.error('REPORT_UNAVAILABLE')
        bundle['complete'] = False
    return bundle


def verify_bundle(stored, bundle):
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
        for name, key in (('index', 'index_sha256'), ('markdown_index', 'markdown_sha256')):
            path = Path(bundle[name])
            if path.is_symlink() or path.is_junction():
                return False
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                while chunk := stream.read(65536):
                    digest.update(chunk)
            if digest.hexdigest() != bundle[key]:
                return False
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False
