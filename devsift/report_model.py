"""Bounded source-reproved report assembly; serialized findings are not authority."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

from .evidence import SourceEvidence, requires_source_mask, verify_source
from .git_changes import classify
from .policy import decide
from .redaction import Redactor
from .registry import RULES

_SEAL = object()
_LIFECYCLES = frozenset({'NEW', 'MODIFIED_INTRODUCED', 'MODIFIED_PREEXISTING', 'LEGACY_UNCHANGED', 'UNKNOWN'})
_ENFORCEMENTS = frozenset({'block', 'incomplete', 'advisory', 'security_review'})
_SAFE_ERRORS = frozenset({'GIT_SCOPE_UNAVAILABLE', 'NATIVE_MANIFEST_UNAVAILABLE', 'NATIVE_TOOL_UNAVAILABLE',
                         'INVALID_SCAN_INPUT', 'NO_AVAILABLE_ANALYZER', 'ANALYZER_UNAVAILABLE',
                         'SOURCE_INCOMPLETE', 'ADAPTER_FAILED', 'ADAPTER_INCOMPLETE',
                         'DUPLICATE_CASE_ID', 'FINDING_UNRESOLVED', 'REDACTION_FAILED'})


class ReportError(ValueError):
    """Safe constant failures; never include report inputs or source content."""


def _require(condition):
    if not condition:
        raise ReportError('Invalid or unavailable report input') from None


def _fields(value, keys):
    _require(type(value) is dict and set(value) == set(keys))


def _encode(value):
    try:
        raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
        _require(len(raw) <= 4_000_000)
        return raw
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise ReportError('Invalid or unavailable report input') from None


@dataclass(frozen=True, init=False)
class ReportCase:
    case_id: str
    rule_id: str
    source: SourceEvidence = field(repr=False)
    _payload: str = field(repr=False)

    def __init__(self, case_id, rule_id, source, payload, *, _seal=None):
        _require(_seal is _SEAL)
        for name, value in [('case_id', case_id), ('rule_id', rule_id), ('source', source), ('_payload', payload)]:
            object.__setattr__(self, name, value)

    def to_dict(self):
        return json.loads(self._payload)


@dataclass(frozen=True, init=False)
class Report:
    cases: tuple[ReportCase, ...]
    complete: bool
    exit_code: int
    _payload: str = field(repr=False)

    def __init__(self, cases, complete, exit_code, payload, *, _seal=None):
        _require(_seal is _SEAL)
        for name, value in [('cases', cases), ('complete', complete), ('exit_code', exit_code), ('_payload', payload)]:
            object.__setattr__(self, name, value)

    def to_dict(self):
        return json.loads(self._payload)

    def find_case(self, case_id):
        _require(type(case_id) is str)
        for case in self.cases:
            if case.case_id == case_id:
                return case
        raise ReportError('Case unavailable') from None


def _repository_urls(mapping):
    _require(type(mapping) is tuple and len(mapping) <= 32)
    result = {}
    for pair in mapping:
        _require(type(pair) is tuple and len(pair) == 2 and all(type(v) is str for v in pair))
        label, url = pair
        _require(not any(ord(char) <= 32 or ord(char) == 127 for char in url))
        parsed = urlsplit(url)
        _require(label not in result and parsed.scheme == 'https' and parsed.netloc == 'github.com'
                 and not parsed.query and not parsed.fragment
                 and re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', parsed.path) is not None)
        result[label] = url
    return result


def _source(item, root, redactor, source_timeout_seconds=10):
    try:
        imported = SourceEvidence.from_dict(item['source'], repo_root=root, redactor=redactor,
                                           source_timeout_seconds=source_timeout_seconds)
        if imported.status != 'VERIFIED':
            return SourceEvidence(reason=imported.reason)
        location = imported.location
        if location.path != item['path']:
            return SourceEvidence(reason='SOURCE_MISMATCH')
        return verify_source(root, location.repository, location.source_sha, location.path, location.region,
                             redactor=redactor, sensitive=requires_source_mask(item['rule_id'], imported),
                             source_timeout_seconds=source_timeout_seconds)
    except (OSError, ValueError, TypeError, KeyError):
        return SourceEvidence(reason='SOURCE_UNAVAILABLE')


def assemble_report(scan_record, *, repo_root, policy=None, redactor=None,
                    trusted_lifecycles=False, repository_urls=(), source_timeout_seconds=10):
    """Reprove immutable source and recompute policy; never trust wire assertions.

    The caller supplies an actual scan result, not an authenticated certificate.
    Persisted/untrusted lifecycle claims default to UNKNOWN. Setting the explicit
    trusted flag is for in-process provenance integration only, never auto-import.
    Unknown impact/consumers are valid disclosed limits, not evidence of safety.
    """
    try:
        _require(type(trusted_lifecycles) is bool and (redactor is None or type(redactor) is Redactor))
        redactor = redactor or Redactor()
        root = Path(repo_root).resolve(strict=True)
        _require(root.is_dir())
        _encode(scan_record)
        _fields(scan_record, ('schema_version', 'command', 'status', 'exit_code', 'complete',
                              'enforced_count', 'findings', 'errors', 'data'))
        _require(scan_record['schema_version'] == '1.0' and scan_record['command'] == 'scan'
                 and type(scan_record['complete']) is bool and type(scan_record['exit_code']) is int
                 and type(scan_record['enforced_count']) is int and scan_record['enforced_count'] >= 0
                 and type(scan_record['findings']) is list and len(scan_record['findings']) <= 1000
                 and type(scan_record['errors']) is list and len(scan_record['errors']) <= 1000
                 and type(scan_record['data']) is dict)
        expected_exit = 2 if not scan_record['complete'] else 1 if scan_record['enforced_count'] else 0
        _require(scan_record['exit_code'] == expected_exit
                 and scan_record['status'] == {0: 'clean', 1: 'enforced', 2: 'incomplete'}[expected_exit])
        errors = []
        for error in scan_record['errors']:
            _fields(error, ('code', 'message'))
            _require(type(error['code']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,127}', error['code']) is not None
                     and type(error['message']) is str)
            code = error['code'] if error['code'] in _SAFE_ERRORS and redactor.text(error['code']) == error['code'] else 'SCAN_INCOMPLETE'
            errors.append({'code': code, 'message': 'Scan work was incomplete; inspect declared capabilities and evidence.'})
        _require(not (scan_record['complete'] and errors))
        urls = _repository_urls(repository_urls)
        cases, seen = [], set()
        complete, enforced, original_blocks = scan_record['complete'], 0, 0
        for item in scan_record['findings']:
            _fields(item, ('case_id', 'rule_id', 'message', 'path', 'source', 'severity',
                           'lifecycle_class', 'enforcement', 'security_escalation'))
            identity = item['case_id']
            _require(type(identity) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', identity) is not None
                     and identity not in seen and type(item['rule_id']) is str and item['rule_id'] in RULES
                     and type(item['message']) is str and type(item['path']) is str
                     and item['lifecycle_class'] in _LIFECYCLES and item['enforcement'] in _ENFORCEMENTS
                     and type(item['security_escalation']) is bool
                     and item['severity'] in ('Critical', 'Error', 'Warning', 'Suggestion'))
            seen.add(identity)
            _require(redactor.text(identity) == identity)
            _fields(item['source'], ('status', 'location', 'before', 'reason', 'lookup_plan'))
            if item['source']['status'] == 'VERIFIED':
                _fields(item['source']['location'], ('repository', 'source_sha', 'path', 'region', 'symbol'))
                _fields(item['source']['location']['region'], ('start_line', 'start_column', 'end_line', 'end_column'))
            original_blocks += item['enforcement'] == 'block'
            source = _source(item, root, redactor, source_timeout_seconds)
            lifecycle = item['lifecycle_class'] if trusted_lifecycles and source.status == 'VERIFIED' else 'UNKNOWN'
            decision = decide(item['rule_id'], lifecycle, source_verified=source.status == 'VERIFIED', policy=policy)
            if source.status != 'VERIFIED' or decision.enforcement == 'incomplete':
                complete = False
            enforced += decision.enforcement == 'block'
            location = source.location
            fingerprint = None
            navigation = None
            if location is not None:
                # Raw identity is separate from masked display; absence stays explicit.
                fingerprint = classify(root, location.source_sha, location.source_sha,
                                       item['rule_id'], source, redactor=redactor).fingerprint
                if location.repository in urls:
                    region = location.region
                    navigation = (urls[location.repository] + '/blob/' + location.source_sha + '/'
                                  + quote(location.path, safe='/') + f'#L{region.start_line}-L{region.end_line}')
                if fingerprint is not None and redactor.text(fingerprint) != fingerprint:
                    fingerprint = None
                if navigation is not None and redactor.text(navigation) != navigation:
                    navigation = None
            label = RULES[item['rule_id']].title
            payload = {
                'case_id': identity, 'rule_id': item['rule_id'], 'title': label,
                'severity': decision.severity.value, 'confidence': 'unknown',
                'lifecycle_class': decision.lifecycle_class, 'enforcement': decision.enforcement,
                'security_escalation': decision.security_escalation, 'source': source.to_dict(),
                'fingerprint': fingerprint, 'navigation': navigation, 'related_locations': [],
                'runtime_evidence': [], 'human_explanation': label,
                'why_detector_fired': 'The configured detector reported this rule at the supplied region; inspect its documented limits.',
                'invalidating_exception': 'Unknown until the exact detector context and counterexamples are checked.',
                'after_proposal': {'label': 'AFTER (PROPOSAL)', 'code': None, 'confidence': 'unknown',
                                   'status': 'pending source and consumer inspection'},
                'alternatives': ['Leave behavior unchanged while collecting evidence.', 'Propose one bounded change after review.'],
                'impact_if_unchanged': {'level': 'unknown', 'reason': 'Production frequency, exploitability and consumers are unmeasured.', 'evidence': []},
                'risk_if_changed': {'level': 'unknown', 'reason': 'Functional, contract, logging, security, performance and deployment effects are unverified.', 'evidence': []},
                'affected_scope': {'status': 'unknown', 'consumers': [], 'test_evidence': []},
                'verification': ['Inspect the immutable source and actual consumers; select relevant regression checks before editing.'],
                'rollback': 'No source change has been applied. Define a scoped rollback before implementation.',
                'approval_status': 'pending', 'automatic_fix': False,
                'review_prompt': f'Review case {identity} ({item["rule_id"]}) and its immutable evidence and unknowns. Read only; do not edit source.',
                'implement_prompt': f'Case {identity} ({item["rule_id"]}) requires explicit per-case approval. After approval, propose the smallest change, verify consumers/tests and rollback; never perform mass legacy remediation.',
            }
            # Every nonconstant value above is source-reproved/redacted or
            # identity-checked. Never feed protocol keys/enums to a value masker:
            # caller-known values may coincide with reserved words like unknown.
            cases.append(ReportCase(identity, item['rule_id'], source, _encode(payload), _seal=_SEAL))
        _require(original_blocks == scan_record['enforced_count'])
        cases.sort(key=lambda case: (case.to_dict()['source']['location']['path'] if case.source.location else '', case.case_id))
        exit_code = 2 if not complete else 1 if enforced else 0
        wire = {'schema_version': '1', 'tool': 'devsift', 'complete': complete,
                'status': {0: 'clean', 1: 'enforced', 2: 'incomplete'}[exit_code],
                'exit_code': exit_code, 'enforced_count': enforced, 'cases': [case.to_dict() for case in cases],
                'errors': errors, 'contextual_recommendations': []}
        return Report(tuple(cases), complete, exit_code, _encode(wire), _seal=_SEAL)
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise ReportError('Invalid or unavailable report input') from None
