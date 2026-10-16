# How to reuse A/B planning inside an existing skills repository (proposal; no remote changes)

The inspected AgriMap source tree uses `skills/agrimap-agent-skills/references/goal-rules.md`, `subagents-and-branches.md`, `operations/plan.md`, `operations/execute.md`, `lifecycle-core.md`, and `config/operations.json` with generated adapters. **Do not directly edit generated `operations/plan.md` / `operations/execute.md`**; edit canonical operation definitions and shared reference sources, then run the repository's own `npm run sync` and tests.

Safe patch proposal:

1. Add portable `governance/AB-GOAL-PLANNING.md` as a passive reference, triggered only by real plan/execute/goal scheduling intent, never by ordinary questions.
2. Add per-entry full-gate classifier contract into existing `goal-rules.md` and `subagents-and-branches.md`, preserving more restrictive user/host authority and existing AGENTS chain rules.
3. Update canonical `config/operations.json` plan and execute descriptions/conditional reference routes so generator adds it to `agm-plan` and `agm-exec`; add analyzer/architect hooks only when material goal planning is authorized. Do not duplicate references in all skills indiscriminately.
4. Extend existing tests with toy DAG fixtures: partial A, full B, independent B gates, mixed A, cycle/missing ref rejection, readiness invariance; do not add a second parallel ledger without explicit migration decision.
5. For a product under AgriMap's existing savepoint convention, preserve existing state rather than unconditionally creating task trees. This kit's 75 cards are requested for DevSift development, not a change to AgriMap's consumer task-recording policy.
6. Execute authorized local checks (`npm run sync`, relevant tests, generated-drift check); never bump package version simply to change plan skills; update Unreleased if user-visible and release separately.

Never import AgriMap's project-specific `feature:`/`comment:`/`bump:` commit conventions or version suffix rules into DevSift. Never edit AgriMap GitHub `develop` without explicit authorization for that repository.
