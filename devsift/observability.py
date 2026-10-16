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
    boundary_id: str | None = field(default=None, repr=False)
    event_kind: str = 'unknown'
    emission_role: str = 'unknown'

    def __post_init__(self):
        _opaque(self.event_id)
        _opaque(self.pair_id)
        _opaque(self.correlation_id, maximum=512, optional=True)
        _opaque(self.boundary_id, optional=True)
        _require(type(self.side) is str and self.side in {'upstream', 'downstream'})
        _require(type(self.event_kind) is str and self.event_kind in {
            'unknown', 'routine_success', 'audit', 'security', 'auth_rejection'})
        _require(type(self.emission_role) is str and self.emission_role in {'unknown', 'start', 'completion'})
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


@dataclass(frozen=True)
class NoiseMeasurement:
    boundary_id: str = field(repr=False)
    coverage_complete: bool
    equivalent_emissions: bool = False
    window_seconds: int | float | None = None
    consumers_reviewed: bool = False

    def __post_init__(self):
        _opaque(self.boundary_id)
        _require(all(type(value) is bool for value in (
            self.coverage_complete, self.equivalent_emissions, self.consumers_reviewed)))
        _require(self.window_seconds is None or (type(self.window_seconds) in (int, float)
                 and 0 < self.window_seconds <= 31_536_000))


_NOISE_REASONS = {
    'BOUNDARY_UNSPECIFIED': 'No actual emitter boundary identity was supplied.',
    'NO_NOISE_COVERAGE': 'No measurement coverage was declared for this boundary.',
    'INCOMPLETE_NOISE_COVERAGE': 'The supplied operation sample is incomplete; no redundancy recommendation is established.',
    'EVENT_ID_CONFLICT': 'Repeated observation identity may represent ingestion duplication, not separate emissions.',
    'PROTECTED_EVENT': 'The same operation/boundary contains audit, security or authentication-rejection records; preserve them.',
    'UNKNOWN_EVENT_KIND': 'The operation/boundary has unclassified records; their audit/security role is unknown.',
    'UNSUPPORTED_ROLE': 'Equivalent routine completion emissions are not established for this role.',
    'EQUIVALENCE_UNDECLARED': 'The caller has not established semantic equivalence of these completion emissions.',
    'SINGLE_EMISSION': 'Only one routine completion emission was observed in this operation/boundary/side/role group.',
    'DUPLICATE_COMPLETION': 'Multiple distinct, explicitly equivalent routine completion emissions were observed for one operation/boundary/side/role.',
}
_NOISE_LOOKUP = ('Locate the exact emitters and retention configuration at an immutable source commit; '
                 'verify log consumers, audit/security obligations and bounded regression/rollback before proposing a change.')
_NOISE_RECOMMENDATION = ('Review only the equivalent routine completions for this measured operation and boundary. '
                         'Assess retention and consumers before proposing one bounded wording/level change, or retain them. '
                         'Preserve audit/security events; do not rewrite a shared filter automatically.')


@dataclass(frozen=True)
class NoiseObservation:
    context_id: str
    reason: str
    observed_event_count: int
    coverage_complete: bool
    equivalence_declared: bool
    window_seconds: int | float | None
    consumer_review_declared: bool
    runtime_evidence: tuple[RuntimeEvidence, ...]
    source: SourceEvidence = field(default_factory=lambda: SourceEvidence(lookup_plan=_NOISE_LOOKUP))
    category: str = field(default='runtime_noise', init=False)
    enforcement: str = field(default='advisory', init=False)
    lifecycle_class: str = field(default='UNKNOWN', init=False)
    automatic_fix: bool = field(default=False, init=False)

    def __post_init__(self):
        _require(type(self.context_id) is str and re.fullmatch(r'CONTEXT-NOISE-[0-9]{4}', self.context_id) is not None)
        _require(type(self.reason) is str and self.reason in _NOISE_REASONS)
        _require(type(self.observed_event_count) is int and 1 <= self.observed_event_count <= 1000)
        _require(all(type(value) is bool for value in (
            self.coverage_complete, self.equivalence_declared, self.consumer_review_declared)))
        _require(self.window_seconds is None or (type(self.window_seconds) in (int, float)
                 and 0 < self.window_seconds <= 31_536_000))
        _require(self.reason != 'DUPLICATE_COMPLETION' or
                 (self.observed_event_count >= 2 and self.coverage_complete and self.equivalence_declared))
        _require(type(self.runtime_evidence) is tuple and 0 < len(self.runtime_evidence) <= 4
                 and all(type(item) is RuntimeEvidence for item in self.runtime_evidence))
        _require(type(self.source) is SourceEvidence and self.source.status == 'SOURCE_UNRESOLVED'
                 and self.source.location is None and self.source.before is None and bool(self.source.lookup_plan))

    @property
    def status(self):
        return ('duplicate_observed' if self.reason == 'DUPLICATE_COMPLETION' else
                'preserve_protected' if self.reason == 'PROTECTED_EVENT' else
                'no_duplicate' if self.reason == 'SINGLE_EMISSION' else 'unresolved')

    @property
    def recommendation(self):
        return _NOISE_RECOMMENDATION if self.reason == 'DUPLICATE_COMPLETION' else None

    def to_dict(self):
        return {'context_id': self.context_id, 'category': self.category, 'status': self.status,
                'reason': self.reason, 'human_explanation': _NOISE_REASONS[self.reason],
                'coverage_complete': self.coverage_complete, 'equivalence_declared': self.equivalence_declared,
                'runtime_evidence': [item.to_dict() for item in self.runtime_evidence],
                'source': self.source.to_dict(), 'enforcement': self.enforcement,
                'lifecycle_class': self.lifecycle_class, 'automatic_fix': self.automatic_fix,
                'recommendation': self.recommendation, 'approval_status': 'not_requested',
                'measurement': {'observed_event_count': self.observed_event_count,
                                'window_seconds': self.window_seconds, 'scope': 'supplied_operation_sample'},
                'volume_status': 'measured_sample' if self.window_seconds is not None and self.coverage_complete else 'unknown',
                'consumer_status': 'unknown', 'consumer_review_declared': self.consumer_review_declared,
                'impact_if_unchanged': {'level': 'unknown', 'reason': 'Production volume, incident impact and actual log consumption have not been established.'},
                'risk_if_changed': {'level': 'unknown', 'reason': 'Source, shared-filter scope, consumers and audit/security obligations require verification.'},
                'review_prompt': _NOISE_LOOKUP + ' Review only; do not edit.',
                'implement_prompt': 'Only after verified source and explicit per-case approval, implement the bounded approved change; preserve audit/security, verify consumers and provide rollback.'}


def analyze_noise(events: tuple[RuntimeEvent, ...], measurements: tuple[NoiseMeasurement, ...],
                  *, redactor: Redactor | None = None) -> tuple[NoiseObservation, ...]:
    """Count distinct actual emissions; never guess equivalence from free text.

    pair_id must identify one particular request/hop operation, not a route,
    service, shared trace or correlation identifier reused across requests.
    """
    _require(type(events) is tuple and len(events) <= 1000 and all(type(item) is RuntimeEvent for item in events))
    _require(type(measurements) is tuple and len(measurements) <= 1000
             and all(type(item) is NoiseMeasurement for item in measurements))
    _require(redactor is None or type(redactor) is Redactor)
    _require(sum(len(item.event_id) + len(item.pair_id) + len(item.boundary_id or '')
                 + len(item.correlation_id or '') + len(item.message) for item in events) <= 1_000_000)
    declarations = {item.boundary_id: item for item in measurements}
    _require(len(declarations) == len(measurements))
    identities = Counter(item.event_id for item in events)
    groups, operations = defaultdict(list), defaultdict(list)
    for item in events:
        boundary = item.boundary_id or ''
        groups[(boundary, item.pair_id, item.side, item.emission_role)].append(item)
        operations[(boundary, item.pair_id)].append(item)
    observations = []
    for ordinal, (key, group) in enumerate(sorted(groups.items()), 1):
        boundary, pair, side, role = key
        declaration = declarations.get(boundary)
        complete = declaration is not None and declaration.coverage_complete
        equivalent = declaration is not None and declaration.equivalent_emissions
        reviewed = declaration is not None and declaration.consumers_reviewed
        window = None if declaration is None else declaration.window_seconds
        operation = operations[(boundary, pair)]
        if any(item.event_kind in {'audit', 'security', 'auth_rejection'} for item in operation):
            reason = 'PROTECTED_EVENT'
        elif any(item.event_kind == 'unknown' for item in operation):
            reason = 'UNKNOWN_EVENT_KIND'
        elif not boundary:
            reason = 'BOUNDARY_UNSPECIFIED'
        elif declaration is None:
            reason = 'NO_NOISE_COVERAGE'
        elif not complete:
            reason = 'INCOMPLETE_NOISE_COVERAGE'
        elif any(identities[item.event_id] != 1 for item in group):
            reason = 'EVENT_ID_CONFLICT'
        elif role != 'completion':
            reason = 'UNSUPPORTED_ROLE'
        elif not equivalent:
            reason = 'EQUIVALENCE_UNDECLARED'
        elif len(group) < 2:
            reason = 'SINGLE_EMISSION'
        else:
            reason = 'DUPLICATE_COMPLETION'
        summary = (f'Observed {len(group)} structured event records for one operation/boundary/side/role group; '
                   f'coverage_complete={str(complete).lower()}; equivalence_declared={str(equivalent).lower()}; '
                   f'consumer_review_declared={str(reviewed).lower()}. No production volume or consumer list inferred.')
        evidence = (RuntimeEvidence('measured-operation-emissions', summary, redactor=redactor),)
        observations.append(NoiseObservation(f'CONTEXT-NOISE-{ordinal:04}', reason, len(group), complete,
                                             equivalent, window, reviewed, evidence))
    return tuple(observations)
