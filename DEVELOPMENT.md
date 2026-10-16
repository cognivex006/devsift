# Developing DevSift

DevSift is a consumer skill backed by Python and optional native analyzers. Requirements, plans and execution coordination live in [devsift-specs](https://github.com/orchex006/devsift-specs).

Use Python 3.12+. Install with `python -m pip install .`. Run `python -m unittest discover -s tests -v` and `git diff --check`. Installed CLI checks use `DEVSIFT_TEST_INSTALLED=1` with `test_cli_platform.py` after installation. Native tests require [trusted setup](docs/NATIVE-SETUP.md), `python tools/build_native.py` and `DEVSIFT_TEST_NATIVE=1`. Setup builds DevSift helpers, never target-project code.

Use Conventional Commits, scoped branches and independently reviewed PRs. Update runtime docs and CHANGELOG.md for behavior changes. Releases require separate authorization. Do not copy specification plans, bootstrap tooling or maintainer skills here.

The consumer entrypoint is skills/devsift/SKILL.md. It invokes installed `python -I -B -m devsift` from the target Git root. Keep commands consistent with CLI help, incomplete results and unavailable backends.

Create isolated jobs only inside this repository's ignored `worktrees/<job>`:

```sh
git worktree add worktrees/example -b feature/example HEAD
```

Keep each writer on owned paths and obtain independent review before integration.
After a job is accepted, verify its worktree is clean and its commit is an
ancestor of the integration branch (or record an independently reviewed
replacement). Remove the finished folder with `git worktree remove
worktrees/example`; preserve its branch/commit references and cleanup evidence in
the canonical specs ledger. Preserve active, dirty and unique worktrees. Do not
create sibling checkout folders or restore snapshots as task checkpoints.

For the explicit packaging input audit, provision the declared build backend
first, then run `DEVSIFT_TEST_PACKAGE=1` with `test_package_manifest.py` (set the
environment variable using your shell's syntax). Its opt-in exercises actual
wheel/sdist construction in disposable fixtures. Archive reproducibility and
release readiness are separate checks; a passing scan does not publish anything.
