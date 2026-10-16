# DevSift runtime and consumer skill

This repo owns the consumer skill, Python CLI, native analyzers, runtime tests and usage docs. Specifications, task cards, the single execution ledger and maintainer orchestration belong to https://github.com/orchex006/devsift-specs . Do not copy them here.

Read DEVELOPMENT.md and relevant runtime docs; inspect status and preserve unrelated work. Use scoped branches and reviewed PRs, no direct main writes or force push. Stage only owned files. Run relevant tests and diff checks and obtain independent review before merge.

Scans and reviews are read-only. Native execution requires an explicitly trusted manifest and digest. No target builds, automatic dependency installation or mass remediation. Consumer edits need authorization. Never claim pending capabilities work.

Use ignored worktrees/<job> for parallel work. Preserve dirty or unique work; remove completed worktrees only after integration or documented supersession. Specs owns coordination. A pause handoff records unfinished work and next actions when pausing; Git preserves committed history.
