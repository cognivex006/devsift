# Quality Lint v3 — Change-aware, legacy-safe policy

## Normative invariants
1. `scan` and `report` MUST be read-only; never modify source, config, baselines, or documentation during scans.
2. A finding is classified NEW, MODIFIED, LEGACY_UNCHANGED, or UNKNOWN using merge-base, changed lines, symbol context and approved baseline. A touched file is NOT entirely new. Renames and moved code retain origin when confidently mapped. Ambiguity => UNKNOWN.
3. NEW: enforce deterministic critical/error rules in CI. MODIFIED: enforce introduced violations and demonstrable worsened violations; pre-existing adjacent debt remains report-only. LEGACY_UNCHANGED: recommend only, except confirmed severe security exposure escalates to an incident/review queue, not automatic refactoring. UNKNOWN: review, no automatic edits; avoid falsely blocking based on uncertain attribution unless independent security gate confirms a critical issue.
4. No remediation is authorized by a scan. Each case requires explicit approval, scoped implementation, tests, and rollback. Never aggregate all legacy recommendations into a single auto-fix command.
5. Logging: preserve correlation propagation, event consumers, and audit requirements. Recommend minimal wording/field improvements only where evidence shows diagnostic gaps. Do NOT require upstream timing or replacing existing logging if downstream correlation and timelines already work. Optional improvements are suggestions.
6. For cross-service correlation distinguish request_id, correlation_id, W3C trace_id and application trace/session id; do not assume equal semantics. A missing custom id is not automatically a trace failure.
7. For every finding report both *impact if left unchanged* and *risk of implementing the proposed fix*, separately. If evidence is insufficient mark Unknown, never invent certainty.
8. Rule packs: backend, frontend, SQL, infrastructure, observability and cross-cutting. Common orchestrator, language-native analysis, common report schema.
9. Reports must be self-contained Markdown, with one case per finding or grouped identical findings sharing the same scope and risk. No dependency on dashboard or external chat context.
10. Stable case IDs, code location, redacted evidence, change provenance, detection confidence, severity, applicability, human explanation, recommended minimal change, alternative/no-change option, impact scope, dependency and consumer risks, test plan, rollback plan, approval status, and a complete standalone copy-paste agent prompt are mandatory.

## Quality gate
- Scan exit codes: 0=no blocking new findings, 1=confirmed new blocking finding, 2=scan/config failure. Legacy suggestions do not change exit code. Critical security findings also enter a separate security review workflow regardless of age.
- SARIF for CI; Markdown for human-readable report; machine-readable JSON for orchestration. All outputs share case IDs.
- Baseline is reviewed, versioned and immutable within scan. New baseline generation is an explicitly approved separate operation.

## Reporting workflow
`quality scan --changed --read-only --report reports/quality/2026-10-16.md`
`quality scan --all --read-only --legacy-mode recommend --report reports/quality/full.md`
`quality explain OBS-CASE-001`
`quality prompt OBS-CASE-001 --mode review` (default)
`quality prompt OBS-CASE-001 --mode implement` (only after explicit approval; prompts must scope to one case)

These are proposed CLI contracts, not currently implemented commands.
