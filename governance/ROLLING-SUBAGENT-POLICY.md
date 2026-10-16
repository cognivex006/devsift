# Portable rolling agent execution policy

1 Controller owns the canonical ledger and global task/lock/worker allocation. Up to five active subagents including reviewers, excluding Controller. Assign four writers + one reviewer by default, rebalance within the same cap. No nested spawning outside allocation.

Ready frontier = tasks whose **all transitive and direct predecessors** are `accepted`; prioritize selected user milestone > critical path / downstream unblock score > least conflicting ready work. Source permission and locks are separate preconditions.

Each bounded job has owner, exact repo/files/contracts, branch+base SHA, isolated worktree if parallel writers, budget, tests and return artifact. Reserve locks atomically and verify visibility. Parallelism requires non-overlapping writers and finalized upstream contracts. If no supported agent provider/isolation, use serial ready frontier; do not invent subagents.

Worker reports results with evidence -> `in_review`, releases writer execution slot for reassignment where safe but retains resources until integration. Reviewer is independent, consumes a global slot, checks tests/diff/contract. Controller merges verified work and records integrated SHA before `accepted`. Only then release contract locks and unlock downstream, calculate frontier and immediately refill available capacity. Never wait for all agents or all goals in a batch.

Dirty/conflicting/unverified worktree => preserve, record blocker; no cleanup. Accepted+integrated+clean+merge ancestry proven => Controller removes ephemeral worktree and normal-deletes branch. Rework always gets a fresh job/worktree. Savepoint at milestone and before stop with leases/locks/status/accepted references, code SHA, pending review, next frontier and dirty/untracked file inventory. No unselected optional work to keep slots busy.

Worktree convention: create only `<repo>/worktrees/<job>` (ignored). At job completion remove clean integrated or documented superseded folders after preserving commit refs/replacement evidence. Keep historical branches without retaining finished folders. Never discard dirty or unique unrecorded work. Controller audits cleanup and leaves no finished job directories at session completion. This convention supersedes older wording that required retaining the folder for every unmerged superseded branch.
