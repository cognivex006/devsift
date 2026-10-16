# DevSift v6 — Implementation checklist

## Before product implementation: T000 first-run repo bootstrap

- [ ] Confirm `orchex006/devsift` is still empty, public and under authorized account.
- [ ] Validate exact v6 source file manifest; no secrets or machine-local files.
- [ ] Publish all approved scaffold source/docs/skills/goals/tasks/tests/CI into the initial `main` commit with conventional commit message.
- [ ] Set professional GitHub Description and read it back from the remote API.
- [ ] Record remote commit SHA, file hashes, CLI output, CI statuses and independent reviewer decision.
- [ ] Mark T000 accepted only with evidence; then recompute frontier and dispatch with locks/capacity.
- [ ] Complete T076 independent remote verification; do not confuse its completion with product implementation.

# Master implementation checklist

## Preflight
- [ ] New source repository selected and authorized; do not modify AgriMap repository.
- [ ] Read repository AGENTS chain, license, CI, package configuration and user-selected priorities.
- [ ] Validate task graph, confirm A/B classifications and per-entry gates.
- [ ] Confirm model runtime supports subagents/worktrees; otherwise serial fallback.
- [ ] Review five-slot global capacity and independent reviewer availability.

## Every goal
- [ ] Outcome, canonical ID, GA/GB alias, prerequisites/gates and locks resolved.
- [ ] Start within bounded 165-minute active goal budget; split if needed.
- [ ] Each task accepted with reviewer distinct from author, integrated SHA and test evidence.
- [ ] No downstream unlocked by `in_review` or completion claim without evidence.
- [ ] Changelog Unreleased updated for user-visible behavior.
- [ ] Savepoint updated at each accepted task and before pause.

## Every PR and integration
- [ ] Scoped commits, Conventional Commits, reviewed tests and lint.
- [ ] Source snippets/patches privacy-safe, expected findings matched.
- [ ] Existing legacy unchanged by auto-fixes and no accidental upstream instrumentation mandate.
- [ ] No shared contracts changed without consumer verification.
- [ ] No dirty/unmerged worktree removed; reviewer/integrator verified target SHA.
- [ ] Release remains separate explicit action; no auto tag/publish.

## Ready-to-ship product
- [ ] CLI real, not just shell files; command help and exit codes accurate.
- [ ] Positive+negative adapters tested in target languages.
- [ ] Source-aware Markdown/JSON/SARIF complete; SOURCE_UNRESOLVED truthful.
- [ ] New enforced, legacy advisory, critical legacy escalation reviewed.
- [ ] Security redaction tested, no source edits during scan/review.
- [ ] Windows/Linux CI and clean install/rollback tested with evidence.
