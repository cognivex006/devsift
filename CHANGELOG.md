# Changelog

All notable user-facing changes to DevSift will be documented here. This follows Keep a Changelog conventions; Specification v6 is **not** a released software version.

## [Unreleased]

### Added
- DevSift brand, canonical repository URL, scoped maintainer and consumer skill identities.
- T000 first-run autopilot to publish the complete v6 scaffold to the initially empty repository and set its professional GitHub Description.
- Independent bootstrap verification T076, offline kit validator, Linux/Windows plan-validation workflow, README/Contributing/Security scaffolding.
- G000 bootstrap goal with partial-task dependency gates, preserving 25 prior goal IDs and 75 prior task IDs.

### Changed
- Root task entry paths require T000 acceptance, not full G000 completion; 26 goals and 77 tasks with exact A/B reclassification.
- Documentation, task ownership, paths and prompts now consistently reference `orchex006/devsift` rather than a generic quality-lint repository.
- Brand-independent adapters: integration with AgriMap, Drevqon, Axiom is optional, not mandatory.

### Security
- Initial remote bootstrap prohibits force push, secret publication, unreviewed license selection and writes to non-target repositories.
