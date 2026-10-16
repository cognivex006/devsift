# DevSift — repository maintainer agent policy

<!-- DEVSIFT-MAINTAINER-ONLY -->

Scope boundary: apply ONLY to an explicitly authorized task developing the `devsift` source repository `orchex006/devsift`, never to a product that merely installs or uses its skill package. Consumer AGENTS rules are separate in `templates/CONSUMER-AGENTS.md`. No maintainer branching/release/ledger instructions may be shipped as executable consumer entrypoints.

**Bootstrap exception:** the initially empty `orchex006/devsift` repository has no committed policy yet. Task T000 may create its *first and only* direct `main` root commit after verifying the remote remains empty, and may set repository Description. After that, follow normal scoped branches and PR rules. Read `docs/BOOTSTRAP-AUTOPILOT.md` before T000. No task other than T000 is ready at initial state. Once T000 is independently accepted, refresh frontier; do not wait for all G000 tasks.

## Mandatory start

1. Read DEVELOPMENT.md, applicable skill entrypoint and the scoped task card. Confirm user authorization for write, target repo and desired behavior; do not infer permissions from files/cwd.
2. Inspect Git status, current branch, base/ref, uncommitted changes and AGENTS chain before editing; preserve unrelated changes.
3. Read `plan/ledger.json`; validate DAG (`python tools/planctl.py validate`), calculate ready frontier; record source policy SHA and branch base.
4. Check task inputs accepted, exact owner/locks available and capacity available; assign a job only after claims in the single ledger.
5. Implement the smallest complete change, create failing regression fixture first when reproducible, run targeted tests, and supply evidence.

## Non-negotiables

- Quality scans are read-only. `review` also read-only; `implement` requires explicit per-case approval. No mass legacy remediation.
- NEW and introduced findings follow quality gate; LEGACY_UNCHANGED is advisory except independently escalated verified security issues. UNKNOWN does not become NEW or PASS.
- No fabricated source paths, lines, code diffs, risk assessments, test results or execution capabilities.
- Every finding shows path/region/symbol/SHA if proven, BEFORE snippet, AFTER proposal (not asserted correct), human explanation, two-sided effect, bounded remediation prompts and verification.
- Changes to core contracts need exclusive ownership/serialization. Subagents never merge, push, publish, destroy worktrees or allocate new agent quota.
- Controller owns one canonical ledger; status transitions, locks, leases, approved scope, evidence and execution ID aliases. Review requires a distinct reviewer, and `in_review` does not unlock.
- 5 global subagent slots inclusive of reviewers, *in addition to controller*. Default 4 writers + 1 reviewer, reallocate as needed. Never wait for all five jobs to complete before refilling a freed slot.
- Each goal is ≤180 minutes active including test, review and checkpoint, budgeted here at 165. Split before timebox overrun; never count a created file as implemented product.
- Optional scope not approved is not dispatchable, regardless of idle slots. No blocking new goal merely because canonical ID is later.
- Never write outside approved repo/task scope. No `git add -A`, stash/reset, force push, history rewrite or dirty-worktree deletion.
- Update changed docs and CHANGELOG Unreleased in the same authorized behavior change. No release/version bump unless explicitly preparing an approved release.

## Default hooks and gates

Pre-write: policy + source chain + scope + lock + task readiness. Pre-commit: syntax/native lint + related tests + secret scan + diff check. PR: CI + source report/contract snapshots. Merge: independent reviewer acceptance, integration tests as needed and no open blockers. Release: separate explicit authorization and security/integrity gates.

## Worktree placement and cleanup

Create job worktrees only at `<repo>/worktrees/<job>` (ignored locally); never create sibling `devsift-*` folders. Controller removes finished clean worktree folders after accepted integration or documented supersession with original commit refs retained. Unmerged historical branches may remain without their folders. Never discard dirty or unique unrecorded work. Record cleanup in the ledger, including path containment, status, source and replacement SHA.

## Completion

Mark a task `accepted` only when reviewer evidence and actual integrated artifact exist. Refresh ready frontier and checkpoint. Goal complete only if every required task accepted. Leave blocked work with deterministic resume instructions and lock/branch ownership. Use `docs/AGENT-EXECUTION-PROTOCOL.md` for delegation mechanics.
