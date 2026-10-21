"""Explicit CI artifact I/O outside source; annotation messages never include code."""
import json
import os
from pathlib import Path

from .report_model import Report


class ArtifactError(ValueError):
    """Safe artifact failure without paths, document contents or OS messages."""


def _require(condition):
    if not condition:
        raise ArtifactError('Report artifacts unavailable') from None


def _escape_command(value):
    return value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A').replace(',', '%2C').replace(':', '%3A')


def annotation_lines(report, *, limit=50):
    """Bounded start-line annotations; the full region/cases remain in reports."""
    _require(type(report) is Report and type(limit) is int and 0 <= limit <= 1000)
    lines = []
    for case in report.cases[:limit]:
        data = case.to_dict()
        level = 'error' if data['enforcement'] == 'block' else 'warning' if data['security_escalation'] or data['enforcement'] == 'incomplete' else 'notice'
        message = f'{case.case_id} {case.rule_id}: {data["severity"]}; {data["enforcement"]}. See the full case report.'
        location = data['source']['location']
        if location is not None:
            properties = 'file=' + _escape_command(location['path']) + ',line=' + str(location['region']['start_line'])
            lines.append('::' + level + ' ' + properties + '::' + _escape_command(message))
        else:
            lines.append('::' + level + '::' + _escape_command(message + ' SOURCE_UNRESOLVED.'))
    return tuple(lines)


def build_reports(scan_record, *, repo_root, policy=None, trusted_lifecycles=False,
                  formats=None, repository_urls=(), source_timeout_seconds=10, language='en', terms_assessment=None):
    """Render all requested formats in memory from one source-reproved model."""
    from .markdown_report import render_markdown
    from .report_export import render_json, render_sarif
    from .report_model import assemble_report
    try:
        _require(language in ('en', 'th'))
        requested = ('json', 'markdown', 'sarif') if formats is None else formats
        _require(type(requested) is tuple and 0 < len(requested) <= 3
                 and all(type(name) is str and name in ('json', 'markdown', 'sarif') for name in requested)
                 and len(set(requested)) == len(requested))
        # Reports consume findings and outcome gates, not the per-file inventory.
        # Keep the bounded untrusted-report model independent of repository size.
        _require(type(scan_record) is dict and type(scan_record.get('data')) is dict)
        report_input = {**scan_record, 'data': {key: scan_record['data'][key]
                       for key in ('source_analysis_complete', 'source_enforced_count')
                       if terms_assessment is not None and key in scan_record['data']}}
        report = assemble_report(report_input, repo_root=repo_root, policy=policy,
                                 trusted_lifecycles=trusted_lifecycles, repository_urls=repository_urls,
                                 source_timeout_seconds=source_timeout_seconds, terms_assessment=terms_assessment)
        documents = {}
        if 'json' in requested:
            documents['json'] = _decode_json(render_json(report))
        if 'markdown' in requested:
            documents['markdown'] = render_markdown(report, language=language)
        if 'sarif' in requested:
            documents['sarif'] = _decode_json(render_sarif(report))
        _require(len(json.dumps(documents, ensure_ascii=True, allow_nan=False).encode()) <= 24_000_000)
        return report, documents
    except (OSError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise ArtifactError('Report artifacts unavailable') from None


def attach_reports(public_record, scan_record, *, repo_root, policy=None,
                   trusted_lifecycles=False, formats=None, terms_assessment=None):
    """Internal CLI integration; preserve every existing failed/incomplete gate."""
    from .output import result
    try:
        public = _decode_json(json.dumps(public_record, ensure_ascii=True, allow_nan=False))
        scan_input = _decode_json(json.dumps(scan_record, ensure_ascii=True, allow_nan=False))
        if public.get('complete') is False:
            scan_input.update(complete=False, status='incomplete', exit_code=2)
        report, documents = build_reports(scan_input, repo_root=repo_root, policy=policy,
                                          trusted_lifecycles=trusted_lifecycles, formats=formats,
                                          terms_assessment=terms_assessment)
        cases = {case.case_id: case.to_dict() for case in report.cases}
        for finding in public['findings']:
            case = cases[finding['case_id']]
            for key in ('source', 'severity', 'lifecycle_class', 'enforcement', 'security_escalation'):
                finding[key] = case[key]
        public['enforced_count'] = report.to_dict()['enforced_count']
        if not public['complete'] or not report.complete:
            public.update(complete=False, status='incomplete', exit_code=2)
        else:
            public.update(complete=True, status='enforced' if public['enforced_count'] else 'clean',
                          exit_code=1 if public['enforced_count'] else 0)
        if terms_assessment is not None:
            public['data']['terms_compliance'] = report.to_dict()['terms_compliance']
        public['data']['reports'] = documents
        return public
    except (OSError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        from .terms import TermsAssessment
        terms = terms_assessment.to_dict() if type(terms_assessment) is TermsAssessment else None
        return result(public_record.get('command') if type(public_record) is dict else None,
                      complete=False, enforced_count=terms['enforced_count'] if terms else 0,
                      data={'terms_gate': {key: terms[key] for key in
                            ('status', 'complete', 'enforced_count', 'decision_required')}} if terms else {},
                      errors=[{'code': 'REPORT_UNAVAILABLE', 'message': 'Full source-reproved reports could not be generated.'}])


def write_report_bundle(report, *, repo_root, destination):
    """Explicit output operation, separate from read-only scan and rendering."""
    from .markdown_report import render_markdown
    from .report_export import render_json, render_sarif
    try:
        _require(type(report) is Report)
        documents = (('report.md', render_markdown(report)), ('findings.json', render_json(report)),
                     ('results.sarif', render_sarif(report)))
        return _write_artifacts(repo_root, destination, documents)
    except (OSError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise ArtifactError('Report artifacts unavailable') from None


def _decode_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result)
            result[key] = value
        return result
    def invalid(_):
        raise ArtifactError('Report artifacts unavailable')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def _write_artifacts(repo_root, destination, artifacts):
    """Internal sink for already-rendered documents; never called by scan.

    Exactly three fixed new files are created in an explicit stable trusted
    output directory outside the source tree. Existing artifacts are not replaced.
    """
    created = []
    try:
        _require(type(artifacts) is tuple and len(artifacts) == 3)
        expected = ('report.md', 'findings.json', 'results.sarif')
        _require(all(type(pair) is tuple and len(pair) == 2 for pair in artifacts))
        _require(tuple(pair[0] for pair in artifacts) == expected)
        _require(all(type(pair[1]) is str and 0 < len(pair[1].encode('utf-8')) <= 16_000_000 for pair in artifacts))
        findings, sarif = _decode_json(artifacts[1][1]), _decode_json(artifacts[2][1])
        _require(type(findings) is dict and findings.get('schema_version') == '1'
                 and type(findings.get('cases')) is list)
        _require(type(sarif) is dict and sarif.get('version') == '2.1.0' and type(sarif.get('runs')) is list)
        source = Path(repo_root).resolve(strict=True)
        _require(source.is_dir())
        directory = Path(destination)
        _require(directory.is_absolute())
        for component in (directory, *directory.parents):
            _require(not component.is_symlink() and not (hasattr(component, 'is_junction') and component.is_junction()))
        directory = directory.resolve()
        _require(not directory.is_relative_to(source))
        directory.mkdir(parents=True, exist_ok=True)
        _require(directory.is_dir() and all(not (directory / name).exists() and not (directory / name).is_symlink() for name in expected))
        for name, text in artifacts:
            target = directory / name
            with target.open('xb') as stream:
                identity = os.fstat(stream.fileno())
                created.append((target, identity.st_dev, identity.st_ino))
                stream.write(text.encode('utf-8'))
                stream.flush()
        return expected
    except (OSError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        for target, device, inode in created:
            try:
                observed = target.stat(follow_symlinks=False)
                if (observed.st_dev, observed.st_ino) == (device, inode):
                    target.unlink()
            except OSError:
                pass
        raise ArtifactError('Report artifacts unavailable') from None
