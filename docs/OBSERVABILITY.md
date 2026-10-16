# Explicit correlation continuity observations

`devsift.observability` analyzes explicitly supplied structured boundary events.
It reads no logs/files, contacts no service, invents no source locations and writes
nothing. This is contextual runtime advice, separate from catalog ScanFinding
rules. Historical OBS identifiers are not new policy rules or quality gates.
Duplicate/noise and authentication/CORS guidance are separate later tasks.

```python
observations = analyze_correlation(events, coverage)
wire = [observation.to_dict() for observation in observations]
```

`RuntimeEvent` is frozen. Required fields are `event_id`, `pair_id`, and `side`
(`upstream` or `downstream`). Optional fields are `trace_id`, `span_id`,
`parent_span_id`, `correlation_id`, `message`, `observed_at`, and
`context_observed` (default false). Trace IDs are actual lowercase nonzero
32-character W3C hex values; span/parent IDs are nonzero 16-character hex values.
Missing fields remain None, never fabricated. Timestamp validation uses the
accepted RuntimeEvidence timestamp contract.
ID lengths, lowercase encoding and nonzero constraints follow the
[W3C Trace Context field definitions](https://www.w3.org/TR/trace-context/#traceparent-header-field-values).

Pair IDs are explicit trusted caller attribution for the same actual direct
client/server hop. They are not guessed from equal cookies, custom correlation
IDs, route strings, timestamps or log ordering. An upstream event describes the
outgoing client span; its downstream counterpart describes the actual server
entry span. This contract is for a direct W3C parent edge, not asynchronous span
links, arbitrary nested server spans, or a graph inferred from sampled logs.

`CorrelationCoverage(pair_id, upstream_complete, downstream_complete,
propagation_expected=False)` is frozen and requires actual booleans. Completeness
and propagation expectation are explicit trusted collection/architecture facts,
not conclusions this analyzer can establish from log absence. An event's
`context_observed=True` means the actual boundary span/context was authoritatively
inspected, including an explicitly observed absence. It must not be set merely
because a log field was missing. Callers that cannot establish these facts leave
the defaults/coverage incomplete and receive unresolved observations.

`analyze_correlation(events: tuple, coverage: tuple, *, redactor=None)` returns a
tuple of frozen `ContextualObservation` records. Batches allow at most 1000 events,
1000 coverage declarations, 1000 distinct pairs, and 1,000,000 total characters of
event IDs/pair IDs/correlation IDs/messages. Opaque IDs are bounded to 256
characters, custom correlation to 512, messages to 8192. Duplicate coverage is an
input error. Multiple candidate events, repeated/conflicting event IDs, partial
contexts, unknown outgoing context or incomplete coverage remain unresolved.
Input errors are static and contain no original values.

With exactly one authoritative event per side and complete declared coverage:

- Matching trace ID and direct downstream parent equal to the outgoing span show
  `continuous`, with no recommendation. Custom IDs may differ or be absent.
- A mismatch does not recommend changes unless direct propagation was explicitly
  expected. Intentional new-root or trust boundaries must not be assumed defective.
- When propagation was required, different actual traces, a missing/different
  direct parent, or an explicitly observed wholly absent downstream context yield
  `proven_missing_link`. Partial fields remain unresolved.
- Missing events/logs never prove a trace break, even under a complete-coverage
  declaration. Null custom cookies, OPTIONS messages, or correlation IDs alone
  do not establish or disprove W3C continuity. No upstream duration is required.

`ContextualObservation` exposes `context_id`, `reason`, `coverage_complete`,
`runtime_evidence`, `source`, `status`, and `recommendation`. Category is
`correlation_continuity`; enforcement is always advisory, lifecycle UNKNOWN and
automatic_fix false. Only a proven missing-link status carries the fixed bounded
review recommendation. All source evidence stays SOURCE_UNRESOLVED with an
explicit immutable-source/instrumentation/consumer lookup plan; no file, line,
BEFORE snippet or source SHA is inferred from runtime messages. Volume, consumers,
impact if unchanged and risk if changed remain unknown because this contract
contains no measurements or consumer/source review.

`to_dict()` returns a fresh fixed-schema JSON tree with those fields, static human
explanation, runtime evidence, unknown impact/risk, review/approval-gated bounded
implementation prompts and approval_status not_requested. Context IDs are
batch-local ordinal labels sorted by the private pair keys, not stable source
fingerprints or catalog rule IDs. A continuous observation is not a quality-gate
pass; unresolved observations are not introduced defects.

Privacy is structural: raw event/pair/trace/span/correlation IDs and log messages
are omitted from public observations, not merely shortened or hashed. Raw input
fields are also omitted from event/coverage repr. RuntimeEvidence contains actual
side/context-presence facts and equality/difference relations synthesized from
the supplied observations, plus real optional timestamps. Its origin labels are
static observation roles, never invented code paths. The optional accepted
Redactor also masks these summaries; arbitrary metadata keys are not supported.
Use observation.to_dict for reporting, not dataclasses.asdict on raw input events.

These assertions depend on the caller supplying actual boundary observations and
correct pairing/coverage facts. They do not authenticate telemetry or establish
source correctness, production incident frequency or permission to change global
logging filters. Review instrumentation and consumers, then seek explicit bounded
case approval before any implementation. Existing trace/audit behavior and HTTP
semantics must be verified; blanket legacy remediation remains unauthorized.
