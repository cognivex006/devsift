# Structured observability acceptance fixtures

`tests/test_observability_acceptance.py` checks the accepted correlation/noise
interfaces against external JSON records in `tests/fixtures/observability`.
Expected statuses, reasons, recommendation flags and measured record counts are
written independently in those fixtures; tests compare exact results rather than
reimplementing the detector. No production implementation changes are made by
this acceptance suite.

These are controlled collector observations with concrete W3C/OTel-compatible
trace/span/parent values and explicit operation/boundary attribution. They are
not a claim of live OpenTelemetry SDK capture, authenticated production telemetry
or verified source. HTTP metadata documents the scenario; the analyzer receives
the supplied structured RuntimeEvent classifications and explicit coverage. It
does not infer status, handled authentication or CORS behavior by parsing text.

The correlation fixtures cover:

- OPTIONS with a null custom cookie but a valid actual direct trace-parent edge.
- A 304 response whose existing context is continuous without extra timing fields.
- OPTIONS with no authoritative span context, which remains unresolved.
- A missing downstream log, partial capture and different explicit operation keys,
  none of which establish a broken trace.
- A concrete required trace mismatch under complete authoritative pairing,
  yielding only contextual advisory review with unresolved source.

The noise fixtures cover equivalent filter/middleware completion observations,
unknown consumers, and two legitimate requests sharing a boundary/free text.
The latter remain separate single emissions. A handled 401 scenario retains five
records across client, server, auth, audit and security roles: all three output
groups remain protected, without sampling/removal recommendations or a default
critical gate. Partial capture cannot recommend a change. A review boolean alone
does not establish consumers or low change risk. Optional sample windows report
only the supplied record count and window, never extrapolated production rates.

Every output is checked for the fixed contextual schema, advisory enforcement,
UNKNOWN lifecycle, automatic_fix false, no requested approval, source location
and BEFORE absent, explicit source lookup, unknown impact/consumer/change risk,
and conditional implementation prompts. RuntimeEvidence contains supplied facts
summarized with static roles; it never masquerades as a source path or a source
verification. Historical OBS labels do not become catalog rule IDs.

Privacy tests reject raw event/pair/boundary/correlation/trace/span values, dummy
PII and dummy secrets in public evidence. A custom Redactor containing reserved
schema words checks that JSON keys and status/reason/enforcement enums remain
stable even when summaries are further masked. Read-only tests compare complete
fixture bytes before/after and block file opens, subprocess creation, network
connections and database connections during analysis. No native tool, network,
database, source execution or upstream duration is needed.

Run the acceptance suite alone, or with its producer tests:

```text
python -m unittest discover -s tests -p test_observability_acceptance.py -v
python -m unittest discover -s tests -p "test_observability*.py" -v
```

These tests establish behavior for the supplied declarations and records. They do
not authenticate collector completeness, discover consumers, estimate incident
volume or authorize shared logging-filter edits. Source verification, consumer
review and explicit bounded approval remain necessary before implementation.
