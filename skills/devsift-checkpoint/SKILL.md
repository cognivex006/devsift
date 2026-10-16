---
name: devsift-checkpoint
description: Save and resume exact task/goal/subagent state without losing worktrees, uncommitted files or evidence.
---

When asked to checkpoint, pause, resume, shutdown, or move: re-read ledger and source control state; snapshot task statuses, actor/reviewer, accepted evidence+integration SHA, global 5-slot capacity, locks/leases, branch/worktree paths, dirty/untracked files, graph SHA and GA/GB mapping, blockers, priority, next frontier. Use `python tools/planctl.py checkpoint` and `templates/SAVEPOINT.md`; output path and next safe action. Resume rechecks source SHA, status, lease and branch/worktree reality; do not assume old ownership or re-dispatch a previously running job. New rework gets new worktree.
