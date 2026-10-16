# V4 Source-aware Diagnostic Contract (normative)

## Evidence and navigation
Each case MUST provide repository, immutable commit SHA, relative path, symbol, start/end line and column where verified; a permalink pinned to that SHA when repository remote is known; exact source excerpt with numbered lines, caret/marker and surrounding context; related locations (consumer, config, test); rule ID, detector version, confidence, provenance, and evidence type. Never fabricate a path, line, source, or proposed fix. If only logs exist, mark `SOURCE_UNRESOLVED`, show exact log evidence and next source lookup steps. Distinguish verified source from illustrative snippets.

## Before/after
Provide verified BEFORE excerpt and proposed AFTER snippet or unified diff; AFTER must be labeled PROPOSAL, not a tested fix. Include alternatives including no change, trade-offs, prerequisites and confidence. Do not offer an unsafe autofix. Show exact insertion/deletion intent and scope boundary. For a shared filter, do not imply an endpoint-local change if the code change affects all endpoints.

## Two-dimensional effect
1. Impact if left unchanged: diagnostic gap, reliability/security, likelihood/frequency (measured vs unknown), affected paths and business impact.
2. Risk if changed: runtime behavior, logs/alerts/dashboards consumers, cardinality/cost, performance, tracing propagation, regression scope, rollback complexity. Rate each Low/Medium/High/Unknown and give rationale/evidence; Unknown never means Low.

## Finding states
NEW, MODIFIED_INTRODUCED, MODIFIED_PREEXISTING, LEGACY_UNCHANGED, UNKNOWN. Use git merge-base plus finding fingerprints, blame only as supporting evidence. Legacy untouched is advisory only except separately escalated verified security risk. Changed file does not mean every finding is new. `scan` is read-only, `review` read-only, `implement` requires explicit per-case approval.

## Machine outputs
- Full standalone Markdown report, including every finding and both prompts (no truncation; paginate only with an index linking complete case files).
- JSON findings with source regions, before/after, risk dimensions, evidence and decisions.
- SARIF 2.1.0 results with physicalLocation region, relatedLocations, rule metadata, and fix only if validated as safe. Include partialFingerprints and invocation/tool failures.
- IDE links: `file:line:column` for local, immutable commit permalink for remote; no invented URL.

## Gate behavior
Block only verified new/introduced findings that match enabled blocking policy; legacy and unresolved source cases recommend or request review. Analyzer errors fail closed or mark incomplete per explicit CI policy; never report pass from an incomplete scan.

## Safety
Redact secrets, tokens, PII, URL query secrets in all snippets, patches and prompts; preserve line references while masking. Use AST-aware parsers for code, not regex-only localization. Logging recommendations must prioritize existing correlation continuity and minimum necessary change; upstream timing is optional, not a mandatory legacy requirement.
