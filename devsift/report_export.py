"""Deterministic stdlib JSON/SARIF serialization of accepted sealed reports."""
import json
from urllib.parse import quote

from .report_model import Report

MAX_OUTPUT_BYTES = 16_000_000
SARIF_SCHEMA_URI = 'https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json'
_LEVELS = {'Critical': 'error', 'Error': 'error', 'Warning': 'warning', 'Suggestion': 'note'}


class ExportError(ValueError):
    """Static failures never include source, paths or report content."""


def _require(condition):
    if not condition:
        raise ExportError('Invalid, unsupported or excessive report export') from None


def _report(report):
    _require(type(report) is Report)
    wire = report.to_dict()
    _require(wire['contextual_recommendations'] == [])
    return wire


def _encode(wire):
    encoded = json.dumps(wire, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + '\n'
    _require(len(encoded.encode('utf-8')) <= MAX_OUTPUT_BYTES)
    return encoded


def render_json(report: Report) -> str:
    """Preserve the complete report model; no reconstruction or new authority."""
    try:
        return _encode(_report(report))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        raise ExportError('Invalid, unsupported or excessive report export') from None


def _physical(source):
    if source['status'] != 'VERIFIED':
        return None
    location = source['location']
    region = location['region']
    return {'artifactLocation': {'uri': quote(location['path'], safe='/'),
                                 'properties': {'repository': location['repository'], 'sourceSha': location['source_sha']}},
            'region': {'startLine': region['start_line'], 'startColumn': region['start_column'],
                       'endLine': region['end_line'], 'endColumn': region['end_column'],
                       'snippet': {'text': source['before']}}}


def render_sarif(report: Report) -> str:
    """SARIF 2.1.0; physical positions require actual immutable source proof."""
    try:
        wire = _report(report)
        cases = [report.find_case(stored.case_id).to_dict() for stored in report.cases]
        rules = {}
        for case in cases:
            rules.setdefault(case['rule_id'], {'id': case['rule_id'],
                                              'shortDescription': {'text': case['title']},
                                              'defaultConfiguration': {'level': _LEVELS[case['severity']]}})
        terms = wire.get('terms_compliance')
        if terms is not None:
            for case in terms['cases']:
                key = 'TERMS/' + case['rule_id']
                rules.setdefault(key, {'id': key, 'shortDescription': {'text': case['title']},
                                      'defaultConfiguration': {'level': _LEVELS[case['severity']]}})
        ordered = [rules[key] for key in sorted(rules)]
        indices = {rule['id']: index for index, rule in enumerate(ordered)}
        results = []
        for case in cases:
            exported = {'ruleId': case['rule_id'], 'ruleIndex': indices[case['rule_id']],
                        'level': _LEVELS[case['severity']],
                        'kind': 'fail' if case['enforcement'] == 'block' else 'review',
                        'message': {'text': case['human_explanation']},
                        # Full accepted case evidence/prompts/unknowns stay visible,
                        # including unresolved lookup and security-review semantics.
                        'properties': case}
            physical = _physical(case['source'])
            if physical is not None:
                exported['locations'] = [{'physicalLocation': physical}]
            related = []
            for identity, source in enumerate(case['related_locations'], 1):
                actual = _physical(source)
                if actual is not None:
                    related.append({'id': identity, 'physicalLocation': actual,
                                    'message': {'text': 'Verified related source evidence.'}})
            if related:
                exported['relatedLocations'] = related
            if case['fingerprint'] is not None:
                exported['partialFingerprints'] = {'devsiftRegion/v1': case['fingerprint']}
            results.append(exported)
        if terms is not None:
            for case in terms['cases']:
                key = 'TERMS/' + case['rule_id']
                results.append({'ruleId': key, 'ruleIndex': indices[key],
                                'level': _LEVELS[case['severity']],
                                'kind': 'fail' if case['enforcement'] == 'block' else 'review',
                                'message': {'text': case['rationale']}, 'properties': case,
                                'partialFingerprints': {'devsiftTerms/v1': case['fingerprint']}})
        invocation = {'executionSuccessful': wire['complete'], 'exitCode': wire['exit_code'],
                      'properties': {'reportStatus': wire['status'], 'enforcedCount': wire['enforced_count']}}
        if wire['errors']:
            invocation['toolExecutionNotifications'] = [
                {'level': 'error', 'descriptor': {'id': error['code']}, 'message': {'text': error['message']}}
                for error in wire['errors']]
        sarif = {'$schema': SARIF_SCHEMA_URI, 'version': '2.1.0', 'runs': [
            {'tool': {'driver': {'name': wire['tool'], 'rules': ordered}},
             'columnKind': 'unicodeCodePoints', 'invocations': [invocation], 'results': results,
             'properties': {'reportSchemaVersion': wire['schema_version'], 'complete': wire['complete'],
                            'status': wire['status'], 'exitCode': wire['exit_code'], 'enforcedCount': wire['enforced_count']}}]}
        if terms is not None:
            sarif['runs'][0]['properties']['terms_compliance'] = terms
        return _encode(sarif)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        raise ExportError('Invalid, unsupported or excessive report export') from None
