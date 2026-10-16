# DevSift

**Language-agnostic developer quality intelligence — planned, not yet implemented.**

DevSift aims to detect code-quality and security issues as changes are developed, link findings to verified source locations, explain human-readable risk and provide narrowly scoped agent remediation prompts. New code can be gated; existing legacy code is recommendation-first. Code scanning never silently refactors production services.

**Repository:** https://github.com/orchex006/devsift  
**Stage:** v6 development specification and repository bootstrap kit (no working lint engine, CLI or published package yet).  
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

## First implementation task

The repository was verified empty on **2026-10-16**. `G000/T000` is the sole initially ready task: autopilot publish **all** approved v6 scaffold files, configure the repository Description, and verify remote SHA. Read [`docs/BOOTSTRAP-AUTOPILOT.md`](docs/BOOTSTRAP-AUTOPILOT.md) or the complete [v6 product specification](docs/SPEC-V6.md). All other task work must wait for T000 to be independently accepted — not necessarily all of G000. `T076` independently verifies bootstrap completion.

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
