# Developing DevSift

DevSift is a consumer skill backed by Python and optional native analyzers. Requirements, plans and execution coordination live in [devsift-specs](https://github.com/orchex006/devsift-specs).

Use Python 3.12+. Install with `python -m pip install .`. Run `python -m unittest discover -s tests -v` and `git diff --check`. Installed CLI checks use `DEVSIFT_TEST_INSTALLED=1` with `test_cli_platform.py` after installation. Native tests require [trusted setup](docs/NATIVE-SETUP.md), `python tools/build_native.py` and `DEVSIFT_TEST_NATIVE=1`. Setup builds DevSift helpers, never target-project code.

Use Conventional Commits, scoped branches and independently reviewed PRs. Update runtime docs and CHANGELOG.md for behavior changes. Releases require separate authorization. Do not copy specification plans, bootstrap tooling or maintainer skills here.

The consumer entrypoint is skills/devsift/SKILL.md. It invokes installed `devsift` from the target Git root. Keep commands consistent with CLI help, incomplete results and unavailable backends.

Create isolated jobs only inside this repository's ignored `worktrees/<job>`:

```sh
git worktree add worktrees/example -b feature/example HEAD
```

Keep each writer on owned paths and obtain independent review before integration.
After a job is accepted, verify its worktree is clean and its commit is an
ancestor of the integration branch (or record an independently reviewed
replacement). Remove the finished folder with `git worktree remove worktrees/example`; preserve its branch/commit references and cleanup evidence in
the canonical specs ledger. Preserve active, dirty and unique worktrees. Do not
create sibling checkout folders or restore snapshots as task checkpoints.

For the explicit packaging input audit, provision the declared build backend
first, then run `DEVSIFT_TEST_PACKAGE=1` with `test_package_manifest.py` (set the
environment variable using your shell's syntax). Its opt-in exercises actual
wheel/sdist construction in disposable fixtures. Archive reproducibility and
release readiness are separate checks; a passing scan does not publish anything.

Start with [the developer documentation map](docs/development/README.md). Keep user guides in `docs/`, consumer contracts in `docs/reference/`, and implementation/testing/release details in `docs/development/`. Run `python tools/sync_skill_docs.py` after consumer-guide changes.

## Download and setup feedback

Every owned download must show a live bar and percentage from actual received
bytes and a known content length or pinned expected size. If neither is known,
show an indeterminate transfer, bytes received and `size unknown`; timers must
not manufacture percentages. Setup percentages may advance at completed stages,
but must be labelled as overall setup progress, separate from transfer percent.

Reuse `tools/install_progress.py` for Python setup progress. Shell bootstraps
render download feedback before trusting/extracting the bundle, then relay the
Python installer's structured progress into that same display. Long local work
uses a spinner and actual elapsed time while its percentage remains at the last
completed stage. Normal output ends with version, CLI location, installed hosts
and the next action. Do not dump pip/native build output or repeated status logs.
On failure, clear the live indicator and retain the failed stage and reason.

Apply this to CLI/skill updates, schema/setup downloads and future downloads.
For delegated package-manager downloads, preserve native transfer feedback when
available; otherwise identify the dependency-download stage and unknown size.
Headless consumers may use structured progress; human-facing redirected output
must remain readable without carriage-return or ANSI noise. Tests must cover
real byte increments, unknown totals, interrupted transfers, checksum refusal,
quiet successful output and an unchanged existing launcher on preflight failure.
