# Controller and five-slot execution protocol

The Controller is NOT a subagent. Maximum total concurrently active subagents **five**, and reviewer agents count against this cap. Default allocation 4 writers + 1 independent reviewer; dynamically rebalance (e.g. 3 writers + 2 reviewers), always globally capped at five across parent/team. Existing agents must never spawn their own nested quota.

## Readiness and ownership loop

1. Load one canonical ledger. Validate all task references, cycles and task ownership; calculate A/B from **transitive task graph**, not numeric order.
2. Check user-selected priority, ready entry tasks, accepted evidence, task locks, base SHA and resource availability. `in_review` is NOT accepted and does not unlock downstream; every task prerequisite must be accepted before claim.
3. Allocate by highest priority milestone, critical path, downstream unlocking value, then age; never dispatch unselected optional tasks to fill slots.
4. Reserve ownership atomically (task-id + repo paths + shared logical contract + lease + worker + base SHA). Revalidate on claim; one writer per overlapping path/shared contract. For contract changes, accept the producer before dispatching consumers.
5. Dispatch immediately when worker slot becomes available. Do NOT wait for all tasks in a goal or wave; full-goal gates are evaluated separately for each true entry path. Eligible G/A and G/B may both run concurrently when their own paths ready.
6. Worker returns commit SHA, source diff, tests/evidence, scope, artifacts and risks, then transitions `running -> in_review`. Reviewer consumes a slot and is distinct from author. If review lacks proof, return `rework` and re-dispatch fresh job/branch.
7. Controller integrates reviewed artifact, proves visibility and tests. Only transition to `accepted` **after integration and independent review evidence**. Then release locks, clean verified merged worktrees, refresh readiness and allocate freed worker immediately.
8. On conflict or dirty worktree: preserve all source and worktree; record blocker, SHA and next action; never mark accepted or cleanup.
9. Goal completes only when **all required task IDs** accepted; optional tasks skipped unless user explicitly selects them.

## Task status machine

`pending -> claimed -> running -> in_review -> accepted`; `in_review -> rework -> claimed`; any active state -> `blocked` or `paused` with recorded reason and durable savepoint. Unknown statuses invalid. `rejected` requires explanation and new job. Claim/status updates must be compare-and-swap or protected by single Controller write lock; no concurrent writer modifications to ledger. Task acceptance requires independent review + actual integrated commit + command/evidence; a green test alone is insufficient.

## Scheduling example (do not conflate class with readiness)

With G001 containing T001 and T002, G002/T003 depends on T001 only: G002 is A and T003 dispatches after T001 *accepted*, without waiting T002. If T003 depends on T001 and T002 and they are all tasks of G001, G002 is B. If B goal has entries X1 gated by P and X2 gated by Q, start X1 after P accepted even if Q incomplete. A mixed goal containing one partial path and another full-gate path remains A; each path keeps its own gate.

## Parallelism and locks

`write:<repo>:<path>` and `contract:<identifier>` are globally unique exclusive locks; claim only if no overlapping directory/file prefix or logical contract owner. Different languages can run concurrently when their contracts are frozen and tests disjoint. Report and policy schema changes use shared exclusive contract lock until accepted. Reviewer may inspect while writers work but cannot become the author of the same task. If subagents or isolation unsupported, execute ready frontier serially and label mode `serial-fallback`.

## Worktree and checkpoint durability

- Branch `feature/<goal>-<task>-<job>` from Controller's latest integrated head; create worktree only for parallel isolated writers, and record base SHA.
- Never remove worktree on `in_review`; Controller owns safe merge+clean cycle after `accepted` eligibility is proven and source clean.
- Rework job always receives a **fresh** worktree based on latest integrated commit; old failed worktree remains until safely archived/disposed with evidence.
- Savepoint on milestone, after accepted task and before shutdown/move: record ledger SHA, accepted evidence links, running/review states, capacity, leases/locks, PR/branches/worktrees, uncommitted changes, blockers, next ready frontier, held decisions and selected scope. Resume validates hashes/actual branches before new claims.

## Limits

No host API available for subagents in this delivered kit. This is a portable orchestration contract, not a live 5-agent system. Goals carry 165 active minute budgets (<180) and must split at an actual deadline or complexity overrun; checkpoint existing work before split. No unsupported time estimate is a user-facing promise.

Worktree convention: create only `<repo>/worktrees/<job>` (ignored). At job completion remove clean integrated or documented superseded folders after preserving commit refs/replacement evidence. Keep historical branches without retaining finished folders. Never discard dirty or unique unrecorded work. Controller audits cleanup and leaves no finished job directories at session completion. This convention supersedes older wording that required retaining the folder for every unmerged superseded branch.
