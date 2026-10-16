# DevSift — open-source development workflow

## Repository bootstrap (one-time)

`orchex006/devsift` was observed public and **empty** on 2026-10-16, with a default `main` name but no committed tree. **T000** is the exclusive authorized bootstrap job: recheck remote emptiness, stage the full approved v6 source/docs kit, make exactly one root `main` commit, push without force, set the professional GitHub Description and verify remote metadata. A distinct reviewer accepts the task only after real evidence. T076 subsequently verifies remote contents and checks. Other original root tasks depend on T000 accepted, not G000 complete.

This single root commit is the **only** direct-main exception; future changes use branch+PR. See [Bootstrap autopilot](docs/BOOTSTRAP-AUTOPILOT.md). Changes to GitHub repository metadata require an authenticated administrator; this specification alone does not modify it.

## Branch strategy

- `main` is the intended protected, release-quality branch after bootstrap; **verify protection in GitHub**, do not infer it from files. No direct pushes after the one T000 initial commit.
- `develop` optional integration branch if the project chooses multi-PR staging; default is **GitHub flow** `feature/*`, `fix/*`, `docs/*`, `chore/*` -> PR -> `main`. Do not create `develop` merely because the reference has one.
- Parallel workers: `feature/<goal>-<task>-<job>` from the controller's **integrated base SHA** in isolated `<repo>.worktrees/<job>` directories. Only one writer per file/contract. One-writer job may use ordinary branch.
- Controller validates branches and merges completed jobs into its integration branch after tests+review; only it cleans up proven-integrated clean worktrees and merged branches. Rework uses a fresh job/worktree based on latest integrated commit.
- PRs are targeted to the policy-selected integration branch; branch protection, required checks, no force push and signed commits (if supported) must be configured *at GitHub*, not presumed from Markdown.

## Commit style — standard Conventional Commits

Examples: `feat(cli): add read-only scan command`, `fix(report): preserve source offsets`, `test(policy): cover legacy baseline`, `docs: explain remediation approvals`, `ci: enforce SARIF validation`, `chore(deps): update pinned analyzer versions`.

Rules: `<type>(optional-scope): imperative subject`; typical types feat, fix, docs, test, refactor, perf, build, ci, chore, revert. Scope is optional; no arbitrary version suffix in every commit. Breaking changes use `!` plus `BREAKING CHANGE:` footer with rationale and migration. Commit one logical change, stage only owned files, include task `Refs: T###` in body, evidence in PR. Do not push/publish based on commit alone.

## Release and changelog

- SemVer from public CLI/rule-contract compatibility, not from number of tasks or a calendar schedule. Rule severity changes can be breaking policy changes, document migrations.
- Use Keep a Changelog: `## [Unreleased]` sections `Added`, `Changed`, `Fixed`, `Security`, `Deprecated`, `Removed`. Do not mutate old release notes.
- Tags `vX.Y.Z` only after approved verified release; preview `vX.Y.Z-rc.N` when deliberately published, never reuse tag. GitHub Release and checksums/SBOM are release deliverables, not assumptions.
- Code/docs/tests in same PR; update Unreleased changelog automatically for meaningful user-facing changes without generating release version bumps.
- Pin native analyzer versions and install manifests; update with CI across Windows/Linux.

## Tests and gates

- Unit: DAG classification, policy, schema validation, CLI, redaction, rules positive/negative.
- Integration: pinned analyzer execution and error propagation, changed vs legacy classification, SARIF schema and Markdown report snapshots.
- E2E: mixed .NET/TS/Go/SQL fixtures with good and bad inputs; verify no DB access.
- Security: redact leaks across logs/patches/errors, prohibit source writes in scan/review, block unintended release.
- Acceptance requires successful targeted tests, source SHA, evidence log, independent reviewer, and controller integration. Only accepted unlocks downstream.
- No automatic legacy cleanup. If change is observability-related, avoid mandatory upstream timing and preserve useful correlation continuity.

## Worktree lifecycle and savepoints

1. Check `git status --short`, base SHA and exclusive ownership. Never silently touch existing dirty worktrees.
2. Controller creates branch+worktree for bounded writer. Job packet records job ID, goal canonical/execution ID, task IDs, base SHA, worktree, owner, locks, acceptance, result format.
3. Worker commits on own branch and returns hashes, tests, changed paths, risks; it never merges or cleans.
4. Reviewer checks independently; controller verifies and integrates with conflict checks.
5. Only after proven integration, clean status and no unresolved review: `git worktree remove <path>` and `git branch -d <branch>` (no force). Audit deletion in ledger.
6. Rework creates new worktree/job; historical job evidence remains immutable.
7. Before pause/move/shutdown or at milestone: `python tools/planctl.py checkpoint` plus human-readable `templates/SAVEPOINT.md`; include uncommitted changes without destroying them. Resume verifies hashes and reality before dispatching tasks.

## Execution IDs

Canonical `G###` stays immutable. `GA###` iff some true entry lacks full predecessor-goal gate; `GB###` iff every true entry has at least one. Compute via transitive closure of tasks, not raw goal order or runtime statuses. A/B alias migration required if graph changes; preserve old alias and evidence reference in `plan/ID-MIGRATIONS.md`.

## Separate permissions

Discussing/planning does not authorize edits. Local implementation authorization does not authorize push, merge PR, publication or touching a consumer repository. Each operation respects explicit scope and host capabilities.
