---
name: rolling-goal-execution
description: Reusable five-slot controller/subagent execution with independent review, continuous ready-frontier refill, isolated worktrees and safe savepoints.
---

Read `governance/ROLLING-SUBAGENT-POLICY.md` and `governance/AB-GOAL-PLANNING.md`. Only for explicitly authorized source implementation. Controller holds one canonical ledger, max five global subagents including reviewer, no nested quota. On any free slot calculate task readiness from *accepted* predecessors plus resource locks and permissions; dispatch independent nonconflicting tasks immediately, no wave barrier. Each worker owns a bounded branch/worktree and submits evidence to independent review, but cannot mark accepted, integrate, push, publish or cleanup. Controller integrates reviewed code before marking accepted and unlocking downstream. On failures keep worktrees and savepoint; rework gets fresh job. On resume reconcile reality. Follow project branch/commit/release policy instead of copying package-specific conventions.
