# DevSift — Product & Engineering Specification v6

**Status:** approved specification baseline. G000–G010 are implemented and independently accepted; see the code execution ledger and acceptance evidence. Native analyzers cover the documented bounded rules; complete report/prompt backends remain pending.
**Canonical repository:** https://github.com/orchex006/devsift  
**Owner:** `orchex006`  
**Product:** `DevSift` · proposed CLI: `devsift` · proposed skill: `$devsift`  
**External dependency:** none mandatory. AgriMap, Axiom and Drevqon are **optional** adapters or consumers.

## 1. Product promise

DevSift is an ecosystem-agnostic code quality and development-risk analysis product that works across repositories and programming languages. It scans source code during implementation, distinguishes new changes from legacy, finds evidence-backed issues, explains risk to humans, proposes bounded code improvements and produces case-specific agent instructions. Its quality gates block introduced defects without automatically refactoring stable legacy code.

## 2. Non-goals

- Rebuild compilers, Roslyn, ESLint, Go linters, SQL parsers, OpenTelemetry or SonarQube wholesale; reuse proven analyzers.
- Demand uniform logging schemas or new upstream instrumentation for every legacy endpoint.
- Change consumers' repositories by running a scan or accepting a report.
- Make Axiom, Drevqon or AgriMap required installation or runtime dependencies.
- Rewrite legacy source files, update database schema, rotate customer credentials or deploy changes automatically.
- Create a software release merely because a planning ZIP has a v6 label.

## 3. Principal capabilities

| ID | Requirement | Intended validation |
|---|---|---|
| DS-P01 | Read-only `scan`, `report`, `explain`, `doctor`; no source edits | filesystem/no-side-effect tests |
| DS-P02 | Deterministic NEW, MODIFIED, LEGACY_UNCHANGED, UNKNOWN; changed *regions*, not full files | Git fixture with accepted baseline |
| DS-P03 | Severity Critical / Error / Warning / Suggestion and configurable Quality Gate | CI fixture: introduced error blocks; untouched legacy advises |
| DS-P04 | Canonical policy registry + backend/frontend/SQL analyzers | independent language-fixture tests |
| DS-P05 | Source-aware primary and related locations; otherwise `SOURCE_UNRESOLVED` | stale SHA and missing-source negative tests |
| DS-P06 | Complete standalone Markdown report + Findings JSON + SARIF 2.1.0 | schemas and link/snapshot tests |
| DS-P07 | For each case: before, proposed after, human explanation, impact of not fixing, effect/risk of fixing, tests, rollback | report case fixture |
| DS-P08 | Separate review-only and authorized case-implementation agent prompts | permission boundary tests |
| DS-P09 | Observability guidance targeted to actual trace discontinuity, diagnostically meaningless logs or proven production uncertainty | legacy source + runtime evidence fixtures |
| DS-P10 | Safe plugin host, pinned analyzers, resource limits and no silent external code transfer | plugin/failure/sandbox tests |
| DS-P11 | CI detection, SARIF upload optional, quality gate stable exit codes | GitHub Actions PR fixture |
| DS-P12 | Resumable accepted-evidence task orchestration with GA/GB transitive classification | `planctl` tests, reviewer separation |
| DS-P13 | Reproducible install/build after real implementation, without releasing fake capabilities | packaging and e2e fixtures |

## 4. CLI and Skill intent (future interface, NOT yet functional)

```text
devsift scan --changed
devsift scan --all --legacy-mode recommend
devsift inspect logging
devsift report --latest
devsift explain OBS-001
devsift prompt OBS-001 --mode review
devsift prompt OBS-001 --mode implement --approved-case OBS-001
devsift doctor
```

The user-facing `$devsift` skill should orchestrate explicit intents, not implement analyzer logic itself; machine Quality Gate results come from actual analyzer execution. Input paths are untrusted. No Agent may mark `accepted` based on generated source files alone.

## 5. Source-aware report contract

Each finding includes: immutable ID and rule ID; severity and status; source location (repo/ref/file/line/column/symbol/base SHA) or `SOURCE_UNRESOLVED`; source BEFORE excerpt; illustrative AFTER that **must not be presented as verified patch**; trigger evidence; human explanation; expected effect of leaving defect unchanged; behavior, contract, logging/observability and regression risks of changing it; confidence and unknowns; affected consumer files; proposed specific test and rollback; `review` and `implement` agent prompts.

A report must be readable from its single Markdown document, not link to an absent dashboard to reveal essential context. SARIF is machine output, not a replacement for human explanation. Examples in `reference/v4` are historical requirements, not confirmed current source locations.

## 6. Legacy-safe enforcement

**New code:** enforce configured Critical and Error gates on introduced source. **Modified code:** assess changed lines and introduced effects; do not automatically label entire historical file NEW. **Legacy unchanged:** recommend and group by case; don't batch-edit or mandate timing instrumentation. **Unknown:** preserve uncertainty and require review, never assume new or passing. Verified severe security issues in legacy become urgent security review; they still do not authorize automatic arbitrary source modifications.

Default scan/read remains read-only. Source modification requires explicit case-level authorization with bounded changes, tests and independent review. Production logs with valid correlation continuity are not inherently defective because they lack upstream duration fields.

## 7. Engineering architecture

A thin cross-language CLI coordinates a stable policy registry, Git change classifier, analyzer adapters, evidence model and report serializers. Adapters can invoke pinned Roslyn/.NET tooling, ESLint/TypeScript, Go analyzers and read-only SQL parsers, but results normalize to a language-independent Finding contract. Security/observability policies sit on top, and optional ecosystem adapters are interfaces rather than hard dependencies. Agent Skill remains a host-facing workflow adapter and must not be the sole Quality Gate enforcer.

## 8. Git and continuous engineering conventions

- Repository: `orchex006/devsift` only; `main` for stable protected integration *after bootstrap*. Work branches `feature/*`, `fix/*`, `docs/*`, `chore/*` and PR reviews by default.
- Conventional Commits, no AgriMap-specific `feature:` / `comment:` / `bump:` prefix scheme and no version in every commit.
- Keep a Changelog `Unreleased`; use Semantic Versioning **only for real approved software releases**.
- Agent Controller controls branches/worktrees/claims; up to five global subagent slots **including reviewers**; refill immediately when genuinely ready.
- Goals have <=165 minute target active budget (hard maximum 180 minutes) including independent review and checkpoint.
- One authoritative `plan/ledger.json`; accepted evidence + independent reviewer is required to unlock downstream; `in_review` does not unlock.
- GA/GB execution aliases derive from transitive task dependencies per true entry path. Structural class does not change as task statuses change.

## 9. First development task — G000 / GA000 / T000

The GitHub repository was observed public, empty, default name `main`, Description `null` on 2026-10-16. **Recheck immediately before execution.** T000 must publish the full approved v6 scaffold into this empty repository with one initial commit, configure GitHub Description exactly and verify remote SHA/files/metadata. Do not merely write a README. Work is autonomous within the authorized repository scope, does not create a software release and may not force push, wipe history, publish secrets or choose a legal license without owner choice.

**Description:**

> DevSift is a language-agnostic code quality toolkit for change-aware analysis, source-linked diagnostics, risk-aware remediation, and automated quality gates.

T076 independently validates remote artifacts and CI checks. Exactly six original implementation root tasks now depend on T000 **accepted**, not on G000 fully accepted: T001, T002, T004, T005, T007, T008. This is an intentional **partial-goal** gate preserving opportunities for parallel development. Full information in `docs/BOOTSTRAP-AUTOPILOT.md`, `plan/tasks/T000.md`, `plan/goals/G000.md`.

## 10. Planning and execution inventory

26 canonical goals `G000..G025` (18 GA, 8 GB), 77 task cards `T000,T001..T076`. Existing canonical IDs and traceability from v5 are retained. Every goal includes outcome, exact owner/lock boundaries, executable entry paths, transitive prerequisites, per-path full-goal gates, acceptance, status/evidence and next action. `plan/ledger.json` is authoritative; generated catalogs are readable projections. Before first remote bootstrap the sole ready task is T000.

On task graph changes, recompute all aliases, record migrations, update cards/savepoints/jobs, and pass planctl tests. A/B is structural; ready frontier is runtime state. No synthetic dependencies merely for number order or parallel appearance.

## 11. Release and legal prerequisites

Public repository visibility is not the same as OSI-compliant licensing. A LICENSE has **not** been selected: record owner decision before claiming open-source rights or publishing stable packages. Bootstrap CI is a starter **plan-validation** workflow, not proof of a production lint engine. Configure repository branch protection in GitHub, then verify enforcement with evidence. Security review, dependency provenance, SBOM/checksums and verified release assets are required before first genuine release; version bump is never publication authority.

## 12. Acceptance for v6 planning deliverable

- [x] Canonical name/repo referenced across current kit and instructions; historical v4 reference preserved without being mistaken for live code.
- [x] Real remote state observed and documented, with explicit refresh-on-execution requirement.
- [x] First task includes full bootstrap, metadata update and acceptance evidence.
- [x] Additional bootstrap verification task and true partial goal gate modeled.
- [x] Updated all current task cards and goal cards from the machine graph, not an assumed order.
- [x] CLI starter plan validator and unit tests included.
- [x] Repository content pushed and independently verified after specification generation; see `docs/evidence/G000.md`.
- [x] GitHub description changed and independently verified after specification generation; see `docs/evidence/G000.md`.
- [ ] Complete product engine/native analyzers/report backends: future tasks. Read-only coordination and Git provenance foundations are accepted in G004/G005.
