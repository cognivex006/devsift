# DevSift — open-source development workflow

## Repository bootstrap (one-time)

`orchex006/devsift` was observed public and **empty** on 2026-10-16, with a default `main` name but no committed tree. **T000** is the exclusive authorized bootstrap job: recheck remote emptiness, stage the full approved v6 source/docs kit, make exactly one root `main` commit, push without force, set the professional GitHub Description and verify remote metadata. A distinct reviewer accepts the task only after real evidence. T076 subsequently verifies remote contents and checks. Other original root tasks depend on T000 accepted, not G000 complete.

This single root commit is the **only** direct-main exception; future changes use branch+PR. See [Bootstrap autopilot](docs/BOOTSTRAP-AUTOPILOT.md). Changes to GitHub repository metadata require an authenticated administrator; this specification alone does not modify it.

## Branch strategy

- `main` is the intended protected, release-quality branch after bootstrap; **verify protection in GitHub**, do not infer it from files. No direct pushes after the one T000 initial commit.
- `develop` optional integration branch if the project chooses multi-PR staging; default is **GitHub flow** `feature/*`, `fix/*`, `docs/*`, `chore/*` -> PR -> `main`. Do not create `develop` merely because the reference has one.
- Parallel workers: `feature/<goal>-<task>-<job>` from the controller's **integrated base SHA** in isolated `<repo>/worktrees/<job>` directories inside the source repository. Only one writer per file/contract. One-writer job may use ordinary branch.
- Controller validates branches and merges completed jobs into its integration branch after tests+review; only it cleans up completed clean worktree folders and merged branches after preserving source/review history. Rework uses a fresh job/worktree based on latest integrated commit.
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

Native setup is explicit: install .NET SDK `9.0.205`, Go `1.21.3`, supported Node
(`24` in CI) and npm, then run `python tools/build_native.py` from this trusted
source checkout. Setup builds only `native/` helpers, restores the locked
ScriptDom package and runs `npm ci --ignore-scripts`. Outputs live under ignored
`.devsift/local/tools/`; frontend dependencies remain in `native/frontend/node_modules`.
Set `DEVSIFT_TEST_NATIVE=1` and run `python -m unittest discover -s tests -v`.
Missing helpers then fail tests; the ordinary suite explicitly skips native tests.
The native CI matrix runs setup and actual analyzers on Windows and Linux.
No scan invokes setup, package installation or target-project builds.

- Unit: DAG classification, policy, schema validation, CLI, redaction, rules positive/negative.
- Integration: pinned analyzer execution and error propagation, changed vs legacy classification, SARIF schema and Markdown report snapshots.
- E2E: mixed .NET/TS/Go/SQL fixtures with good and bad inputs; verify no DB access.
- Security: redact leaks across logs/patches/errors, prohibit source writes in scan/review, block unintended release.
- Acceptance requires successful targeted tests, source SHA, evidence log, independent reviewer, and controller integration. Only accepted unlocks downstream.
- No automatic legacy cleanup. If change is observability-related, avoid mandatory upstream timing and preserve useful correlation continuity.

## Worktree lifecycle and savepoints

1. Check `git status --short`, base SHA and exclusive ownership. Never silently touch existing dirty worktrees.
2. Controller creates branch+worktree for bounded writer at `<repo>/worktrees/<job>` only; never create sibling `devsift-*` directories. Job packet records job ID, goal canonical/execution ID, task IDs, base SHA, worktree, owner, locks, acceptance, result format.
3. Worker commits on own branch and returns hashes, tests, changed paths, risks; it never merges or cleans.
4. Reviewer checks independently; controller verifies and integrates with conflict checks.
5. After task completion, verify absolute path containment within `<repo>/worktrees/`, clean status, and accepted integration/replacement evidence. Remove its folder with `git worktree remove <path>` (no force). Delete a merged branch with `git branch -d`; for a superseded commit without merge ancestry, retain its branch/ref and the reviewed replacement SHA, while removing the clean finished folder. Audit paths, source/replacement hashes and cleanup in the ledger. Never delete unique unrecorded or dirty work.
6. Rework creates a fresh worktree/job under `worktrees/`; once its replacement is accepted, remove the old clean superseded worktree folder while retaining commit refs and immutable evidence. No completed worktree folders remain at session completion.
7. Before pause/move/shutdown or at milestone: `python tools/planctl.py checkpoint` plus human-readable `templates/SAVEPOINT.md`; include uncommitted changes without destroying them. Resume verifies hashes and reality before dispatching tasks.

## Execution IDs

Canonical `G###` stays immutable. `GA###` iff some true entry lacks full predecessor-goal gate; `GB###` iff every true entry has at least one. Compute via transitive closure of tasks, not raw goal order or runtime statuses. A/B alias migration required if graph changes; preserve old alias and evidence reference in `plan/ID-MIGRATIONS.md`.

## Separate permissions

Discussing/planning does not authorize edits. Local implementation authorization does not authorize push, merge PR, publication or touching a consumer repository. Each operation respects explicit scope and host capabilities.

## Worktree directory convention

`worktrees/` is a local ignored container within this source repo, not another GitHub repository. Each child shares the main repository Git objects and remote. Example from the source root:

```powershell
git worktree add -b feature/g006-t016-j01 worktrees/g006-t016-j01 <integrated-sha>
# After independent acceptance, clean-status and integration/ref-preservation checks:
git worktree remove worktrees/g006-t016-j01
```

The container is excluded from Git staging, source inventory, native tool inputs and normal test discovery. On shutdown/resume inspect `git worktree list` plus the ledger. Preserve dirty/unique work with a deterministic resume record; do not leave finished folders merely because a superseded branch is retained. Review-only temporary copies follow the same contained layout and cleanup discipline.
