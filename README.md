# DevSift

**Language-agnostic developer quality intelligence — early implementation.**

DevSift aims to detect code-quality and security issues as changes are developed, link findings to verified source locations, explain human-readable risk and provide narrowly scoped agent remediation prompts. New code can be gated; existing legacy code is recommendation-first. Code scanning never silently refactors production services.

**Repository:** https://github.com/orchex006/devsift  
**Stage:** G000–G010 accepted: foundations, immutable baselines, bounded native host and actual backend/frontend/SQL AST analyzers. Complete report/prompt backends remain pending; no published package.
**Specifications:** https://github.com/orchex006/devsift-specs  
**Independence:** usable in arbitrary projects; AgriMap, Axiom and Drevqon are optional integrations, not architectural dependencies.

## Local command interface

Requires Python 3.12+. Install locally with `python -m pip install .`, then use `devsift --help`.
For a source checkout with strict bytecode-free execution, use `python -B -m devsift --help`.

```bash
devsift scan --changed
devsift scan --all --legacy-mode recommend
devsift report --latest
devsift explain OBS-001
devsift prompt OBS-001 --mode review
devsift doctor
```

The CLI calls the real read-only inventory/coordinator. `--changed` selects staged, unstaged and untracked paths and reads working-tree bytes; `--all` inventories the current directory. Native analyzers require [explicit pinned setup and trusted manifest/digest flags](docs/NATIVE-SETUP.md). Without those flags, scans remain **exit 2 (`incomplete`)**. Source-verified findings retain UNKNOWN lifecycle until separately proven attribution is supplied. An empty findings array is not a successful quality scan. Report/prompt backends remain pending.

Local libraries provide [immutable evidence](docs/EVIDENCE.md), [scan coordination](docs/SCAN-RESULTS.md), [Git source provenance](docs/GIT-PROVENANCE.md) and [policy](docs/POLICY.md). See [CLI behavior](docs/CLI.md) and [accepted progress](plan/EXECUTION-STATUS.md).

## Development progress

G000 bootstrap is independently accepted: the approved 160-file scaffold is published,
repository description verified, and Windows/Linux CI passes. Evidence is in
[`docs/evidence/G000.md`](docs/evidence/G000.md). Current execution state is maintained
in [`plan/ledger.json`](plan/ledger.json); G001 policy is accepted with
[fixture/reviewer evidence](docs/evidence/G001.md); G002 has [installed CLI evidence](docs/evidence/G002.md). The specifications repository preserves the
original design and planning fixture. G003–G010 evidence and all goal/task checklists are linked from the [current progress summary](plan/EXECUTION-STATUS.md). All further code changes use reviewed pull requests.

```bash
python tools/planctl.py validate
python tools/planctl.py frontier
python tools/validate_kit.py
python -m unittest discover -s tests -v
```

These offline commands validate the plan and files; **they do not push commits, install software or scan product code**. All implementation begins at `plan/GOALS.md` and `plan/ledger.json`, following `AGENTS.md` and `DEVELOPMENT.md`.

## Source layout

- `devsift/`, `policy/`, `tests/`: Python command interface, strict policy, immutable evidence, read-only scan coordination, Git provenance and regression fixtures
- `AGENTS.md` / `DEVELOPMENT.md`: repo-only policy, branching, worktrees, agent orchestration, review and savepoints
- `plan/`: 26 goal cards, 77 task cards, one canonical ledger, A/B entry-path decisions and first-frontier dispatch
- `skills/`: development planning/execution/checkpoint plus planned `$devsift` consumer entrypoint
- `docs/`: bootstrap runbook, repository identity, report contract, open-source process, source study and checklists
- `reference/v4/`: frozen historical source-aware lint specification; **not installed as functional engine**
- `.github/workflows/`: plan/test validation and installed CLI contract checks on Windows/Linux; actual pinned native analyzer tests on Windows/Linux

## License and maturity

Public visibility does not grant an open-source license. The repository owner has not selected a license; do not claim OSI-approved licensing, publish a package or tag a release without proper authorization and verification. See `CONTRIBUTING.md` and `SECURITY.md`.
