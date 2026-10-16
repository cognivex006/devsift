---
name: development-quality-lint
description: Shift-left quality checks for code, config, comments, security and regressions.
---
# Development Quality Lint

## When to invoke
Before and during any feature, bugfix, refactor, configuration change, PR review or release task.

## Required procedure
1. Read AGENTS.md, DEVELOPMENT.md and SPEC.md. Detect stack and installed tools.
2. Identify affected modules, config contracts, public APIs and tests.
3. Reuse existing central configuration, typed constants, helpers and shared components.
4. Run available fast linters and secret checks against touched files as work progresses.
5. Review hardcoded environment values, unexplained magic numbers, commented-out code, TODOs, unsafe logs and swallowed exceptions.
6. Run relevant tests after each behavior-affecting fix; do not batch cleanup until release.
7. Before completion, report findings, tests, exceptions, residual risk and rollback.

## Rules of engagement
- Deterministic tools, not LLM judgment alone, decide blocking findings.
- No indiscriminate comment deletion or string extraction.
- No silent suppression, baseline refresh or auto-fix of behavior-affecting settings.
- A failing tool is not a passing scan; report it as unavailable or blocked.
- For parallel agents, each worker scans its own worktree and the integration owner reruns authoritative checks after merge.

## Output
Summary with scanned scope, rule IDs, severity, files, fix status, test evidence and unresolved findings.


## v3 override (normative)
Read `V3-POLICY.md` before scanning. Scan is read-only. Legacy findings are case-based recommendations only; each finding MUST have full `REPORT-TEMPLATE.md` fields and two independent prompts. No global legacy auto-fix.

## v4 override (normative)
Read `SOURCE-DIAGNOSTICS-CONTRACT.md`. Every case must show verified exact source location, BEFORE excerpt, proposed AFTER, two effect assessments and two prompts; otherwise mark SOURCE_UNRESOLVED, never fabricate code or line numbers. Produce complete standalone Markdown plus JSON and SARIF.
