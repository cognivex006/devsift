"""Explicit runtime correlation observations; contextual advice, never gate rules."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import re

from .evidence import RuntimeEvidence, SourceEvidence
from .redaction import Redactor


class ObservationError(ValueError):
    """Static failure without runtime identifiers, messages or PII."""


def _require(condition):
    if not condition:
        raise ObservationError('Invalid or excessive runtime observation input') from None


def _opaque(value, maximum=256, optional=False):
    if optional and value is None:
        return
    _require(type(value) is str and bool(value.strip()) and len(value) <= maximum
             and not any(ord(character) < 32 for character in value))


@dataclass(frozen=True)
class RuntimeEvent:
    event_id: str = field(repr=False)
    pair_id: str = field(repr=False)
    side: str
    trace_id: str | None = field(default=None, repr=False)
    span_id: str | None = field(default=None, repr=False)
    parent_span_id: str | None = field(default=None, repr=False)
    correlation_id: str | None = field(default=None, repr=False)
    message: str = field(default='', repr=False)
    observed_at: str | None = None
    context_observed: bool = False

    def __post_init__(self):
        _opaque(self.event_id)
        _opaque(self.pair_id)
        _opaque(self.correlation_id, maximum=512, optional=True)
        _require(type(self.side) is str and self.side in {'upstream', 'downstream'})
        _require(type(self.context_observed) is bool)
        for value, length in ((self.trace_id, 32), (self.span_id, 16), (self.parent_span_id, 16)):
            _require(value is None or (type(value) is str and len(value) == length
                     and re.fullmatch('[0-9a-f]+', value) is not None and value != '0' * length))
        _require(type(self.message) is str and len(self.message) <= 8192)
        try:
            RuntimeEvidence('structured-event', '', self.observed_at)
        except ValueError:
            raise ObservationError('Invalid or excessive runtime observation input') from None


@dataclass(frozen=True)
class CorrelationCoverage:
    pair_id: str = field(repr=False)
    upstream_complete: bool
    downstream_complete: bool
    propagation_expected: bool = False

    def __post_init__(self):
        _opaque(self.pair_id)
        _require(all(type(value) is bool for value in (
            self.upstream_complete, self.downstream_complete, self.propagation_expected)))


_RATIONALES = {
    'CONTEXT_CONTINUOUS': 'The observed downstream trace and direct parent agree with the paired upstream span.',
    'NO_COVERAGE': 'No explicit boundary collection coverage was supplied.',
    'INCOMPLETE_COVERAGE': 'Boundary collection is incomplete; absent records cannot prove a missing trace link.',
    'AMBIGUOUS_PAIR': 'Exactly one observed client and one observed server entry span are required.',
    'EVENT_ID_CONFLICT': 'Event identity is repeated or conflicts across the supplied observations.',
    'CONTEXT_NOT_OBSERVED': 'At least one boundary context was not authoritatively observed.',
    'UPSTREAM_CONTEXT_UNAVAILABLE': 'An actual outgoing W3C context is not proven; custom correlation is insufficient.',
    'CONTEXT_INCOMPLETE': 'Only part of the downstream span context was observed.',
    'AMBIGUOUS_CONTEXT': 'Client and server span identity is duplicated; distinct boundary spans are not established.',
    'EXPECTATION_NOT_DECLARED': 'Direct parent propagation was not explicitly required for this boundary.',
    'TRACE_MISMATCH': 'Complete paired boundary observations show different W3C trace identities where continuity was required.',
    'PARENT_MISMATCH': 'Complete paired boundary observations show no expected direct upstream parent link.',
    'DOWNSTREAM_CONTEXT_ABSENT': 'An authoritative downstream boundary observation records absent W3C context despite a required outgoing context.',
}
_MISSING = frozenset({'TRACE_MISMATCH', 'PARENT_MISMATCH', 'DOWNSTREAM_CONTEXT_ABSENT'})
_LOOKUP = ('Locate the paired client/server instrumentation and propagation configuration at an immutable commit; '
           'verify source regions and log/trace consumers before proposing a bounded change. No source path is inferred from runtime data.')
_RECOMMENDATION = ('Review only this explicitly paired context boundary and its verified propagation configuration. '
                   'Confirm source and consumers before proposing one bounded change; do not edit automatically.')


@dataclass(frozen=True)
class ContextualObservation:
    context_id: str
    reason: str
    coverage_complete: bool
    runtime_evidence: tuple[RuntimeEvidence, ...]
    source: SourceEvidence = field(default_factory=lambda: SourceEvidence(lookup_plan=_LOOKUP))
    category: str = field(default='correlation_continuity', init=False)
    enforcement: str = field(default='advisory', init=False)
    lifecycle_class: str = field(default='UNKNOWN', init=False)
    automatic_fix: bool = field(default=False, init=False)

    def __post_init__(self):
        _require(type(self.context_id) is str and re.fullmatch(r'CONTEXT-CORRELATION-[0-9]{4}', self.context_id) is not None)
        _require(type(self.reason) is str and self.reason in _RATIONALES)
        _require(type(self.coverage_complete) is bool)
        _require(self.reason not in _MISSING or self.coverage_complete)
        _require(type(self.runtime_evidence) is tuple and 0 < len(self.runtime_evidence) <= 1001
                 and all(type(item) is RuntimeEvidence for item in self.runtime_evidence))
        _require(type(self.source) is SourceEvidence and self.source.status == 'SOURCE_UNRESOLVED'
                 and self.source.location is None and self.source.before is None and bool(self.source.lookup_plan))

    @property
    def status(self):
        return ('continuous' if self.reason == 'CONTEXT_CONTINUOUS' else
                'proven_missing_link' if self.reason in _MISSING else 'unresolved')

    @property
    def recommendation(self):
        return _RECOMMENDATION if self.reason in _MISSING else None

    def to_dict(self):
        """Fresh fixed-schema JSON; no event/pair/trace IDs or raw log messages."""
        return {'context_id': self.context_id, 'category': self.category, 'status': self.status,
                'reason': self.reason, 'human_explanation': _RATIONALES[self.reason],
                'coverage_complete': self.coverage_complete,
                'runtime_evidence': [item.to_dict() for item in self.runtime_evidence],
                'source': self.source.to_dict(), 'enforcement': self.enforcement,
                'lifecycle_class': self.lifecycle_class, 'automatic_fix': self.automatic_fix,
                'recommendation': self.recommendation, 'approval_status': 'not_requested',
                'volume_status': 'unknown', 'consumer_status': 'unknown',
                'impact_if_unchanged': {'level': 'unknown', 'reason': 'Operational impact and incident frequency have not been measured.'},
                'risk_if_changed': {'level': 'unknown', 'reason': 'Source, shared instrumentation and log/trace consumers have not been verified.'},
                'review_prompt': _LOOKUP + ' Review only; do not edit.',
                'implement_prompt': 'Only after verified source and explicit per-case approval, implement the bounded approved change and verify consumers, traces and rollback.'}


def analyze_correlation(events: tuple[RuntimeEvent, ...], coverage: tuple[CorrelationCoverage, ...],
                        *, redactor: Redactor | None = None) -> tuple[ContextualObservation, ...]:
    """Analyze explicitly paired direct client/server spans, never infer pairing.

    Coverage, boundary authority and propagation expectation are trusted caller
    declarations; this function cannot establish them from absent/sampled logs.
    """
    _require(type(events) is tuple and len(events) <= 1000 and all(type(item) is RuntimeEvent for item in events))
    _require(type(coverage) is tuple and len(coverage) <= 1000 and all(type(item) is CorrelationCoverage for item in coverage))
    _require(redactor is None or type(redactor) is Redactor)
    _require(sum(len(event.event_id) + len(event.pair_id) + len(event.correlation_id or '') + len(event.message)
                 for event in events) <= 1_000_000)
    declarations = {item.pair_id: item for item in coverage}
    _require(len(declarations) == len(coverage))
    identities = Counter(event.event_id for event in events)
    groups = defaultdict(list)
    for event in events:
        groups[event.pair_id].append(event)
    pair_ids = sorted(set(groups) | set(declarations))
    _require(len(pair_ids) <= 1000)
    observations = []
    for ordinal, pair_id in enumerate(pair_ids, 1):
        group = sorted(groups[pair_id], key=lambda item: (item.side, item.event_id))
        declaration = declarations.get(pair_id)
        complete = declaration is not None and declaration.upstream_complete and declaration.downstream_complete
        upstream = [item for item in group if item.side == 'upstream']
        downstream = [item for item in group if item.side == 'downstream']
        if declaration is None:
            reason = 'NO_COVERAGE'
        elif not complete:
            reason = 'INCOMPLETE_COVERAGE'
        elif len(upstream) != 1 or len(downstream) != 1:
            reason = 'AMBIGUOUS_PAIR'
        elif any(identities[item.event_id] != 1 for item in group):
            reason = 'EVENT_ID_CONFLICT'
        elif not upstream[0].context_observed or not downstream[0].context_observed:
            reason = 'CONTEXT_NOT_OBSERVED'
        else:
            before, after = upstream[0], downstream[0]
            if before.trace_id is None or before.span_id is None:
                reason = 'UPSTREAM_CONTEXT_UNAVAILABLE'
            elif ((after.trace_id is None) != (after.span_id is None)
                  or (after.trace_id is None and after.parent_span_id is not None)):
                reason = 'CONTEXT_INCOMPLETE'
            elif (after.trace_id == before.trace_id and after.span_id == before.span_id):
                reason = 'AMBIGUOUS_CONTEXT'
            elif after.trace_id == before.trace_id and after.parent_span_id == before.span_id:
                reason = 'CONTEXT_CONTINUOUS'
            elif not declaration.propagation_expected:
                reason = 'EXPECTATION_NOT_DECLARED'
            elif after.trace_id is None:
                reason = 'DOWNSTREAM_CONTEXT_ABSENT'
            elif after.trace_id != before.trace_id:
                reason = 'TRACE_MISMATCH'
            else:
                reason = 'PARENT_MISMATCH'
        evidence = []
        if declaration is None:
            summary = 'No authoritative collection coverage declaration was supplied.'
        else:
            summary = (f'Declared upstream_complete={str(declaration.upstream_complete).lower()}; '
                       f'downstream_complete={str(declaration.downstream_complete).lower()}; '
                       f'direct_propagation_expected={str(declaration.propagation_expected).lower()}.')
        evidence.append(RuntimeEvidence('declared-correlation-coverage', summary, redactor=redactor))
        if len(upstream) == 1 and len(downstream) == 1:
            before, after = upstream[0], downstream[0]
            trace_relation = ('unavailable' if before.trace_id is None or after.trace_id is None
                              else 'equal' if before.trace_id == after.trace_id else 'different')
            parent_relation = ('unavailable' if before.span_id is None or after.parent_span_id is None
                               else 'equal' if before.span_id == after.parent_span_id else 'different')
            evidence.append(RuntimeEvidence('observed-context-relationship',
                                            f'Observed trace_identity_relation={trace_relation}; '
                                            f'direct_parent_relation={parent_relation}.', redactor=redactor))
        for event in group:
            summary = (f'Observed {event.side} event: authoritative_context={str(event.context_observed).lower()}; '
                       f'trace_present={str(event.trace_id is not None).lower()}; '
                       f'span_present={str(event.span_id is not None).lower()}; '
                       f'parent_present={str(event.parent_span_id is not None).lower()}; '
                       f'custom_correlation_present={str(event.correlation_id is not None).lower()}.')
            evidence.append(RuntimeEvidence('structured-' + event.side + '-event', summary,
                                            event.observed_at, redactor=redactor))
        observations.append(ContextualObservation(f'CONTEXT-CORRELATION-{ordinal:04}', reason,
                                                  complete, tuple(evidence)))
    return tuple(observations)
