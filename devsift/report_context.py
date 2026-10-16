"""Source-linked candidate context; source facts never prove consumers or impact."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import re

from .baseline import BaselineSnapshot
from .evidence import SourceEvidence, requires_source_mask, verify_source
from .git_changes import BaselineObservation
from .policy import decide
from .report_decisions import assess_finding
from . import report_model
from .report_model import Report, ReportCase


class ContextError(ValueError):
    """Fixed failure without private paths, source or caller-controlled text."""


def _require(condition):
    if not condition:
        raise ContextError('Invalid or unavailable report context') from None


def _case_id(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', value) is not None


@dataclass(frozen=True)
class CandidateContext:
    case_id: str
    role: str
    source: SourceEvidence = field(repr=False)

    def __post_init__(self):
        _require(_case_id(self.case_id) and type(self.role) is str
                 and self.role in {'consumer', 'test'} and type(self.source) is SourceEvidence)


@dataclass(frozen=True)
class CaseProvenance:
    case_id: str
    rule_version: str
    observation: BaselineObservation | None = field(default=None, repr=False)

    def __post_init__(self):
        _require(_case_id(self.case_id) and type(self.rule_version) is str
                 and 0 < len(self.rule_version) <= 256
                 and not any(ord(c) < 32 or ord(c) == 127 for c in self.rule_version)
                 and (self.observation is None or type(self.observation) is BaselineObservation))


def _encode(value):
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
    _require(len(encoded) <= 4_000_000)
    return encoded


def _primary(case, root):
    if case.source.status != 'VERIFIED':
        return SourceEvidence(reason=case.source.reason)
    location = case.source.location
    return verify_source(root, location.repository, location.source_sha, location.path, location.region,
                         expected_before=case.source.before, sensitive=requires_source_mask(case.rule_id, case.source))


def _candidate(candidate, source, root):
    claimed = candidate.source
    if source.status != 'VERIFIED' or claimed.status != 'VERIFIED':
        return SourceEvidence(reason='SOURCE_UNAVAILABLE')
    primary, location = source.location, claimed.location
    if (location.repository, location.source_sha) != (primary.repository, primary.source_sha):
        return SourceEvidence(reason='SOURCE_MISMATCH')
    # Position is reproved; a caller's symbol/relationship is not. All text is
    # withheld, including opaque secrets that generic patterns cannot detect.
    return verify_source(root, primary.repository, primary.source_sha, location.path, location.region, sensitive=True)


def _description(role, source):
    label = 'Candidate consumer' if role == 'consumer' else 'Candidate test source (not executed; no pass evidence)'
    if source.status != 'VERIFIED':
        return label + ': SOURCE_UNRESOLVED; relationship unknown; inspect the unresolved source lookup plan.'
    location, region = source.location, source.location.region
    return (label + ': ' + location.path + '@' + location.source_sha
            + f' L{region.start_line}:{region.start_column}-L{region.end_line}:{region.end_column}; '
            + 'source position verified only; relationship unproven; symbol unknown.')


def enrich_report_context(report, *, repo_root, candidates=(), base_ref=None, provenance=(),
                          snapshot=None, tool_version=None, rule_catalog_version=None, policy=None):
    """Return a new sealed Report accepted by all existing exporters.

    Candidate positions are not call-graph/test-run/impact proof. When base_ref is
    supplied, explicit CaseProvenance versions feed accepted assess_finding.
    A trusted snapshot is optional and never interpreted as rule-absence proof.
    """
    try:
        _require(type(report) is Report and isinstance(repo_root, (str, Path))
                 and type(candidates) is tuple and len(candidates) <= 256
                 and all(type(item) is CandidateContext for item in candidates)
                 and type(provenance) is tuple and len(provenance) <= 1000
                 and all(type(item) is CaseProvenance for item in provenance))
        root = Path(repo_root).resolve(strict=True)
        _require(root.is_dir())
        original = report.to_dict()
        case_ids = {case.case_id for case in report.cases}
        _require(all(item.case_id in case_ids for item in candidates))
        _require(all(sum(candidate.case_id == identity for candidate in candidates) <= 32 for identity in case_ids))
        inputs = {item.case_id: item for item in provenance}
        _require(len(inputs) == len(provenance))
        if base_ref is None:
            _require(not provenance and snapshot is None and tool_version is None and rule_catalog_version is None)
        else:
            _require(type(base_ref) is str and 0 < len(base_ref) <= 1024
                     and not any(ord(c) < 32 or ord(c) == 127 for c in base_ref)
                     and set(inputs) == case_ids)
            _require(snapshot is None or type(snapshot) is BaselineSnapshot)
            if snapshot is not None:
                _require(type(tool_version) is str and type(rule_catalog_version) is str)
        cases, complete = [], report.complete
        for case in report.cases:
            _require(type(case) is ReportCase and type(case.source) is SourceEvidence)
            item = case.to_dict()
            _require(item['case_id'] == case.case_id and item['rule_id'] == case.rule_id
                     and item['source'] == case.source.to_dict())
            source = _primary(case, root)
            item['source'] = source.to_dict()
            if source.status != 'VERIFIED':
                decision = decide(case.rule_id, 'UNKNOWN', source_verified=False, policy=policy)
                item.update(lifecycle_class='UNKNOWN', enforcement='incomplete', severity=decision.severity.value,
                            security_escalation=False, fingerprint=None, navigation=None)
                complete = False
            elif base_ref is not None:
                context = inputs[case.case_id]
                assessed = assess_finding(root, base_ref, source.location.source_sha, case.rule_id, source,
                                          rule_version=context.rule_version, observation=context.observation,
                                          snapshot=snapshot, tool_version=tool_version,
                                          rule_catalog_version=rule_catalog_version, policy=policy)
                decision = assessed.decision
                item.update(lifecycle_class=decision.lifecycle_class, enforcement=decision.enforcement,
                            severity=decision.severity.value, security_escalation=decision.security_escalation,
                            fingerprint=assessed.proof.fingerprint)
            elif policy is not None:
                decision = decide(case.rule_id, item['lifecycle_class'], source_verified=True, policy=policy)
                item.update(enforcement=decision.enforcement, severity=decision.severity.value,
                            security_escalation=decision.security_escalation)
            # With no new base/policy, retain the previously trusted sealed
            # attribution (including UNKNOWN and legacy security_review).
            related, consumers, tests, evidence = [], [], [], []
            for candidate in candidates:
                if candidate.case_id != case.case_id:
                    continue
                proof = _candidate(candidate, source, root)
                related.append(proof.to_dict())
                description = _description(candidate.role, proof)
                (consumers if candidate.role == 'consumer' else tests).append(description)
                evidence.append({'kind': candidate.role + '_source_context_only',
                                 'relationship': 'candidate_unproven', 'source': proof.to_dict(),
                                 'measurement': 'none; not impact, reachability or test execution evidence'})
                if proof.status != 'VERIFIED':
                    complete = False
            item['related_locations'] = related
            item['affected_scope'] = {'status': 'unknown', 'consumers': consumers, 'test_evidence': tests}
            item['impact_if_unchanged'] = {
                'level': 'unknown', 'reason': 'Source-linked candidates do not measure production frequency, exploitability or affected consumers.',
                'evidence': evidence}
            item['risk_if_changed'] = {
                'level': 'unknown', 'reason': 'Candidate source positions are not call-graph, contract, deployment or regression-result evidence; shared consumer effects remain unknown.',
                'evidence': evidence}
            item['confidence'] = 'unknown'
            item['approval_status'], item['automatic_fix'] = 'pending', False
            item['after_proposal']['code'] = None
            if item['lifecycle_class'] in {'LEGACY_UNCHANGED', 'MODIFIED_PREEXISTING'}:
                item['human_explanation'] += ' Proven preexisting source is a recommendation, not forced legacy remediation; security review remains independent.'
            item['verification'] = list(item['verification']) + [
                'Candidate consumer/test relationships are supplied and unproven. Inspect actual callers, contracts and relevant regression results before any separately approved change.']
            if item['enforcement'] == 'incomplete':
                complete = False
            cases.append(ReportCase(case.case_id, case.rule_id, source, _encode(item), _seal=report_model._SEAL))
        enforced = sum(case.to_dict()['enforcement'] == 'block' for case in cases)
        exit_code = 2 if not complete else 1 if enforced else 0
        original.update(cases=[case.to_dict() for case in cases], complete=complete,
                        enforced_count=enforced, exit_code=exit_code,
                        status={0: 'clean', 1: 'enforced', 2: 'incomplete'}[exit_code])
        _require(original['contextual_recommendations'] == [])
        return Report(tuple(cases), complete, exit_code, _encode(original), _seal=report_model._SEAL)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError, OverflowError):
        raise ContextError('Invalid or unavailable report context') from None
