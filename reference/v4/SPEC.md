# Development Quality Lint Skill — Specification v1.0

Status: Proposed | Scope: .NET, TypeScript/Next.js/Angular, Go, Python | Owner: Project governance

## 1. Objective
Prevent late-stage hardcode/config/comment cleanups from causing regressions. Enforce quality at implementation, pre-commit, PR and CI stages. A skill instructs agents; deterministic scanners enforce rules.

## 2. Non-goals
Do not prohibit all comments, string literals, numbers or TODOs. Do not automatically rewrite production code. Do not replace security testing, code review or regression tests.

## 3. Architecture
- Governance package: versioned rule catalog, severity, suppressions, policies, documentation.
- Agent skill: inspect repository language, existing linters, scope, config, tests and baselines before edits.
- Adapter runners: ESLint/typescript-eslint, Semgrep, Gitleaks, .NET analyzers, golangci-lint, Ruff, plus custom AST rules only when needed.
- CLI: `quality scan --changed`, `quality scan --all`, `quality explain RULE`, `quality doctor`, `quality baseline`, `quality report --format sarif`.
- Local incremental checks; authoritative CI scan with pinned tool versions.

## 4. Rule Catalog
| ID | Detection | Default | Notes |
|---|---|---|---|
| HC001 | Literal external URL/IP/hostname in runtime code | error | Exempt test fixtures, protocol constants, allowlisted domains |
| HC002 | Credential/API key/token literal | critical | Never print detected value; secret scan required |
| HC003 | Environment-specific branch or production marker in domain logic | error | Explicit typed env adapters allowed |
| HC004 | Unnamed business threshold/magic number | warning | Exempt 0/1, enums, test data and documented protocol constants |
| HC005 | Machine-specific filesystem path | error | Exempt fixtures and build tooling with justification |
| CFG001 | Required configuration lacks validation/schema | error | Typed startup validation preferred |
| CFG002 | Duplicate/unused config key | warning | Requires config inventory; avoid guessing dynamic references |
| CFG003 | Secret in committed config or unsafe fallback | critical | Example files use placeholders only |
| COM001 | Commented-out executable code | error | AST/heuristic detection; exclude examples/docs |
| COM002 | TODO/FIXME/HACK without tracked issue, owner or expiry | warning | Allow timeboxed exception |
| COM003 | Redundant comments narrating obvious code | advisory | Agent review only; no automatic blocking |
| SEC001 | Logging secrets/PII | critical | Dataflow analysis where supported |
| SEC002 | Disabled TLS validation | critical | Allow narrowly scoped test fixture only |
| SEC003 | Dynamic SQL string concatenation with untrusted input | critical | Parameterized SQL preferred |
| ARC001 | Forbidden cross-layer imports | error | Repo-specific architecture map |
| ARC002 | Duplicated business logic | advisory | Review-based, not automatic blocker |
| ARC003 | Unapproved dependencies | error | Repo allow/deny policy |
| API001 | Unreviewed breaking API/schema change | error | Compare against approved baseline |
| API002 | Retry/timeout values embedded in application flow | warning | Explicit defaults in central policy permitted |
| LOG001 | Debug printing in runtime paths | warning | Structured logging exceptions |
| LOG002 | Swallowed exceptions | error | Explicit intentional cancellation handling allowed |
| TST001 | Changed behavior without suitable tests | error | Risk-based coverage policy, not line-count alone |
| TST002 | Skipped test without ticket/expiry | error | Quarantine must be tracked |

## 5. Workflow
1. **Task intake:** Agent reads AGENTS.md and skill, discovers language, config conventions, architecture and applicable rules.
2. **Before coding:** Agent checks existing reusable config/components/constants and identifies contract and test impact.
3. **During coding:** Run fast incremental scans on touched files and nearby dependency boundary; do not defer findings.
4. **Before commit:** Run formatter, native linter, custom policy scan, secret scan, affected unit tests. New critical/error findings block commit in enforced mode.
5. **Pull request:** Run changed-code scan, API contract diff, architecture rules, relevant integration tests, report SARIF and concise Markdown.
6. **CI:** Run authoritative full scan periodically and on protected branches; enforce zero new critical/error violations; compare legacy findings with approved baseline.
7. **Release:** Require green quality gates, approved exceptions and regression evidence. No broad cleanup during release freeze without a separately reviewed change.

## 6. Findings Schema
`rule_id`, `severity`, `message`, `path`, `line`, `fingerprint`, `category`, `evidence_redacted`, `suggested_fix`, `introduced_by_change`, `suppression`, `tool_version`.
Use SARIF 2.1.0 for CI interoperability. Stable fingerprints enable baseline comparisons.

## 7. Baseline & Suppressions
- Existing violations are baseline debt; block *new* violations first.
- Suppressions require rule ID, reason, ticket, owner, expiry; no blanket disable for security-critical rules.
- Baseline refresh must be reviewed and cannot silently hide new findings.
- Rule rollout: observe -> warn -> enforce after false-positive tuning.

## 8. Regression-Safe Remediation
- Classify each finding: pure refactor, behavior-affecting config migration, contract change, security-critical.
- For behavior-affecting changes, capture current behavior via tests first, implement in a separate commit/PR, verify affected unit/integration/contract tests and config matrix.
- Never auto-fix production configuration, URLs, thresholds or public contracts without explicit approval.
- Store evidence: commands, results, changed files, baseline delta, risk and rollback instructions.

## 9. Skill Contract
Trigger on new features, bug fixes, refactors, configuration edits, PR reviews and releases. Always inspect policy and existing conventions. Reuse canonical config and shared abstractions. Never add unexplained TODO, commented-out code, secrets or machine-specific paths. Run applicable scanners and tests before declaring completion. Report blocked findings with rule IDs and evidence. Do not modify unrelated code to satisfy lint.

## 10. Acceptance Criteria
- A new hardcoded endpoint, secret, commented-out code and swallowed exception each produce the expected finding in fixture tests.
- Valid comments, test fixtures and protocol constants avoid false-positive blocking.
- Changed-only scans complete within the team-defined time budget and full CI scans are reproducible.
- Baseline preserves existing debt while blocking new critical/error findings.
- Config extraction requires regression tests and documented rollback.
- Five concurrent agents can scan isolated worktrees without shared mutable state.

## 11. MVP Delivery
Phase 1: Rule catalog, policy schema, skill, CLI interface, secret scan, native lint adapters, SARIF report, fixtures.
Phase 2: AST hardcode/config/comment rules, baseline and suppression lifecycle, PR integration.
Phase 3: API contract diff, architecture dependency checks, incremental dependency-aware scans and dashboard.

## 12. Governance Integration
AGENTS.md references this skill and pinned policy version; DEVELOPMENT.md documents mandatory lifecycle gates; CHANGELOG.md records rule and severity changes. Policy updates require changelog, rule fixtures and migration notes. A centrally versioned policy can be distributed to repos while repo-local overrides are explicit and auditable.
