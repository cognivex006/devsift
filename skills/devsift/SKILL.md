---
name: devsift
description: Analyze developer code quality using change-aware source-linked findings, risk-aware recommendations and optional case-specific agent remediation. **Planned skill; engine not implemented.**
---

# DevSift — planned user-facing skill (not implemented)

Until product code exists, never claim a `devsift scan` was executed. If working on this repository, read AGENTS.md, DEVELOPMENT.md and relevant planning skills instead. For future consumer use:

1. Scope source and new/modified/legacy classification; do not equate modified file with all new code.
2. Scan read-only; exact source region and commit SHA or `SOURCE_UNRESOLVED`.
3. Emit full Markdown + SARIF findings, before/proposed-after, human explanation, effect if changed/unchanged, risk and context-specific tests.
4. Legacy modifications require per-case authorization; do not auto-refactor existing logging or demand upstream instrumentation without actual trace gap evidence.
5. Separate backend/frontend/SQL adapters and combine results under a single stable user-facing entrypoint.

The v6 task graph builds this functionality; this file is a specification placeholder and is not a functioning quality scanner.
