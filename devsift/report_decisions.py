"""Read-only baseline-aware finding decisions; source origin is not business impact."""
from dataclasses import dataclass, replace
from datetime import datetime

from .baseline import BaselineSnapshot, capture_entry
from .evidence import SourceEvidence, verify_source
from .git_changes import Classification, classify
from .policy import Decision, decide
from .suppressions import Suppression


class AssessmentError(ValueError):
    """Constant safe failure; do not print untrusted evidence or configuration."""


def _require(condition):
    if not condition:
        raise AssessmentError('Invalid or unavailable decision evidence') from None


@dataclass(frozen=True)
class FindingAssessment:
    proof: Classification
    decision: Decision
    baseline_status: str
    suppressed: bool

    def to_dict(self):
        return {
            'rule_id': self.decision.rule_id,
            'severity': self.decision.severity.value,
            'lifecycle_class': self.decision.lifecycle_class,
            'enforcement': self.decision.enforcement,
            'security_escalation': self.decision.security_escalation,
            'provenance': self.proof.to_dict(),
            'baseline_status': self.baseline_status,
            'suppressed': self.suppressed,
            'rationale': 'Decision follows verified immutable source origin and configured policy; baseline membership alone is not rule-absence evidence.',
            'impact_if_unchanged': {
                'level': 'unknown',
                'reason': 'Production frequency, exploitability and consumers have not been measured.',
                'evidence': [],
            },
            'risk_if_changed': {
                'level': 'unknown',
                'reason': 'Behavioral, contract, logging, security, performance and deployment effects need case-specific review.',
                'evidence': [],
            },
            'automatic_fix': False,
        }


def assess_finding(repo_root, base_ref, head_ref, rule_id, source, *, rule_version,
                   snapshot=None, observation=None, tool_version=None,
                   rule_catalog_version=None, suppressions=(), as_of=None, policy=None):
    """Combine actual Git proof with policy and an optional trusted baseline.

    Load persisted snapshots with baseline.load_snapshot and an independently
    trusted digest before calling. Snapshot absence never proves rule absence.
    Explicit in-process BaselineObservation is needed for changed-region rule
    absence; classify reproves its immutable locations. No files are written.
    """
    try:
        _require(type(source) is SourceEvidence and type(rule_version) is str
                 and 0 < len(rule_version) <= 256)
        _require(type(suppressions) is tuple and len(suppressions) <= 1000
                 and all(type(item) is Suppression for item in suppressions))
        proof = classify(repo_root, base_ref, head_ref, rule_id, source, baseline=observation)
        baseline_status = 'not_supplied'
        if snapshot is not None:
            _require(type(snapshot) is BaselineSnapshot
                     and snapshot.tool_version == tool_version
                     and snapshot.rule_catalog_version == rule_catalog_version
                     and snapshot.source_sha == proof.merge_base_sha)
            if proof.head_location is not None:
                _require(snapshot.repository == proof.head_location.repository)
            _require(all(entry.rule_version == rule_version for entry in snapshot.entries
                         if entry.rule_id == rule_id))
            matches = [entry for entry in snapshot.entries
                       if entry.rule_id == rule_id and entry.fingerprint == proof.fingerprint]
            baseline_status = 'not_recorded'
            for entry in matches:
                location = entry.location
                baseline_source = verify_source(repo_root, location.repository, location.source_sha,
                                                location.path, location.region)
                reproduced = capture_entry(repo_root, rule_id, rule_version, baseline_source)
                _require(reproduced.fingerprint == entry.fingerprint)
                baseline_status = 'matched'
        decision = decide(rule_id, proof.lifecycle_class,
                          source_verified=proof.head_location is not None
                          and source.status == 'VERIFIED', policy=policy)
        suppressed = False
        if suppressions:
            _require(type(as_of) is datetime and as_of.tzinfo is not None)
            for waiver in suppressions:
                waiver.valid_at(as_of)
                if (decision.enforcement not in ('incomplete', 'security_review')
                        and not decision.security_escalation
                        and waiver.matches(rule_id, proof.fingerprint, as_of=as_of)):
                    suppressed = True
            if suppressed:
                decision = replace(decision, enforcement='advisory')
        return FindingAssessment(proof, decision, baseline_status, suppressed)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise AssessmentError('Invalid or unavailable decision evidence') from None
