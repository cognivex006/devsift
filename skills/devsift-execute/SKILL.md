---
name: devsift-execute
description: Execute explicitly authorized DevSift goal/task with rolling five-slot global capacity, independent review and safe ephemeral worktrees.
---

1. Inspect source AGENTS/DEVELOPMENT/approved task, call `planctl validate/frontier`; re-check ledger and accepted evidence; never infer authority from plan artifact.
2. Establish task dependency readiness, locks, exact file ownership, integration base SHA and actual global free slots. Controller plus max five subagents, reviewers count. No nested quota.
3. Group independent tasks by non-overlapping files/contracts, dispatch highest priority downstream-unlocking work to isolated worktrees when supported; serial fallback otherwise. Use packet template; workers cannot merge, approve or clean.
4. On every completion, collect actual commit SHA/tests/changed paths, transition to `in_review` (does NOT unlock), assign independent reviewer in an available slot; controller integrates verified artifact then marks accepted with evidence.
5. Recompute readiness and refill a freed slot immediately without waiting for a goal/batch. B goals with distinct gated entry paths may begin independently when only one gate satisfied.
6. For failed gates/conflicts preserve worktrees and branches; rework in a new job and checkpoint. Never remove unintegrated or dirty worktrees.
7. Update docs and CHANGELOG Unreleased in the same authorized behavioral edit, without bumping releases. Goal complete only after all required tasks accepted. Savepoint on milestone/pause and before moving location.
8. Enforce scan/read-only boundaries; legacy findings are review recommendations, NEVER blanket fixes, and no missing upstream fields mandated across old logs. New blocking findings governed by rule policy.
