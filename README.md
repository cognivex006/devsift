# DevSift

**Language-agnostic developer quality intelligence — early implementation.**

DevSift aims to detect code-quality and security issues as changes are developed, link findings to verified source locations, explain human-readable risk and provide narrowly scoped agent remediation prompts. New code can be gated; existing legacy code is recommendation-first. Code scanning never silently refactors production services.

**Repository:** https://github.com/orchex006/devsift  
**Stage:** bootstrap accepted; policy and CLI foundation in development. No analyzer engine or published package yet.
**Specifications:** https://github.com/orchex006/devsift-specs  
**Independence:** usable in arbitrary projects; AgriMap, Axiom and Drevqon are optional integrations, not architectural dependencies.

## Planned interface (not yet executable)

```bash
devsift scan --changed
devsift scan --all --legacy-mode recommend
devsift report --latest
devsift explain OBS-001
devsift prompt OBS-001 --mode review
devsift doctor
```

## Development progress

G000 bootstrap is independently accepted: the approved 160-file scaffold is published,
repository description verified, and Windows/Linux CI passes. Evidence is in
[`docs/evidence/G000.md`](docs/evidence/G000.md). Current execution state is maintained
in [`plan/ledger.json`](plan/ledger.json); the specifications repository preserves the
original design snapshot. All further code changes use reviewed pull requests.

```bash
python tools/planctl.py validate
python tools/planctl.py frontier
python tools/validate_kit.py
python -m unittest discover -s tests -v
```

These offline commands validate the plan and files; **they do not push commits, install software or scan product code**. All implementation begins at `plan/GOALS.md` and `plan/ledger.json`, following `AGENTS.md` and `DEVELOPMENT.md`.

## Source layout

- `AGENTS.md` / `DEVELOPMENT.md`: repo-only policy, branching, worktrees, agent orchestration, review and savepoints
- `plan/`: 26 goal cards, 77 task cards, one canonical ledger, A/B entry-path decisions and first-frontier dispatch
- `skills/`: development planning/execution/checkpoint plus planned `$devsift` consumer entrypoint
- `docs/`: bootstrap runbook, repository identity, report contract, open-source process, source study and checklists
- `reference/v4/`: frozen historical source-aware lint specification; **not installed as functional engine**
- `.github/workflows/`: starter plan/test validation only; other planned quality gates come from implementation tasks

## License and maturity

Public visibility does not grant an open-source license. The repository owner has not selected a license; do not claim OSI-approved licensing, publish a package or tag a release without proper authorization and verification. See `CONTRIBUTING.md` and `SECURITY.md`.
