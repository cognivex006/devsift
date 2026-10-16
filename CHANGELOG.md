# Changelog

All notable user-facing changes to DevSift will be documented here. This follows Keep a Changelog conventions; Specification v6 is **not** a released software version.

## [Unreleased]

### Added
- Explicit pinned native helper setup and Windows/Linux CI running actual Roslyn, Go AST, ESLint/TypeScript and ScriptDom tests.
- Immutable Git merge-base/fingerprint/rename-region provenance with explicit UNKNOWN for ambiguous history or origin.
- Trusted adapter execution and conservative aggregation connected to CLI inventory, including filter-free staged/unstaged/untracked scope selection.
- Immutable Git-backed source evidence, distinct runtime/proposal contracts, strict wire schemas and full-context snippet redaction.
- Deterministic read-only source inventory and explicit adapter capability negotiation; unavailable analyzers never imply clean analysis.
- Installable Python CLI shell with strict commands, JSON error envelopes and exit codes 0/1/2/3; unavailable analyzer/report capabilities remain incomplete.
- Strict policy v1 overlays and immutable 23-rule severity registry, with evidence-aware legacy/unknown enforcement and independent critical-security review.
- DevSift brand, canonical repository URL, scoped maintainer and consumer skill identities.
- T000 first-run autopilot to publish the complete v6 scaffold to the initially empty repository and set its professional GitHub Description.
- Independent bootstrap verification T076, offline kit validator, Linux/Windows plan-validation workflow, README/Contributing/Security scaffolding.
- G000 bootstrap goal with partial-task dependency gates, preserving 25 prior goal IDs and 75 prior task IDs.

### Changed
- Development jobs use ignored `worktrees/<job>` inside the source repository; finished integrated or superseded folders are removed while preserving commit refs and cleanup evidence.
- Published and independently verified the initial 160-file scaffold; historical planner tests now tolerate execution progress.
- Root task entry paths require T000 acceptance, not full G000 completion; 26 goals and 77 tasks with exact A/B reclassification.
- Documentation, task ownership, paths and prompts now consistently reference `orchex006/devsift` rather than a generic quality-lint repository.
- Brand-independent adapters: integration with AgriMap, Drevqon, Axiom is optional, not mandatory.

### Security
- Initial remote bootstrap prohibits force push, secret publication, unreviewed license selection and writes to non-target repositories.
