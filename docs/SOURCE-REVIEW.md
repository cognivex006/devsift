# Source study — AgriMap agent skills `develop`

Reviewed 2026-10-16 via connected GitHub repository files. Immutable tree commit: `7e0e9f0169a6ee7a6a8e7c2ead542d7da7c237bc`.

|Source|Observed practice|Adopt / adapt / explicitly reject|
|---|---|---|
|[AGENTS.md](https://github.com/orchex006/agrimap-agent-skills/blob/develop/AGENTS.md)|Maintainer-only scope; consumer installs must not inherit maintainer instructions|Adopt scope isolation|
|[DEVELOPMENT.md](https://github.com/orchex006/agrimap-agent-skills/blob/develop/DEVELOPMENT.md)|feature/develop/main release branches, own commit categories and version suffixes|Use as reference for authority boundaries; **reject** proprietary commit types and per-commit version suffix|
|[goal-rules.md](https://github.com/orchex006/agrimap-agent-skills/blob/develop/skills/agrimap-agent-skills/references/goal-rules.md)|Think before coding, simpler changes, bounded scope, evidence gates|Adopt|
|[subagents-and-branches.md](https://github.com/orchex006/agrimap-agent-skills/blob/develop/skills/agrimap-agent-skills/references/subagents-and-branches.md)|Up to 5 subagents, rolling work queues, ephemeral worktrees with controller integration and removal after verification|Adopt with reviewer included in global 5-slot pool and accepted-task based unlock|
|[git-workflow.md](https://github.com/orchex006/agrimap-agent-skills/blob/develop/skills/agrimap-agent-skills/references/git-workflow.md)|Policy-bound branch changes, stage exact files, deterministic delivery|Adopt safe boundaries; **reject** project-specific branch prefixes and Thai team commit syntax|
|[lifecycle-core.md](https://github.com/orchex006/agrimap-agent-skills/blob/develop/skills/agrimap-agent-skills/references/lifecycle-core.md)|Distinguish ordinary chat/read-only vs authorized development, savepoint and evidence|Adopt|
|[memory-and-logs.md](https://github.com/orchex006/agrimap-agent-skills/blob/develop/skills/agrimap-agent-skills/references/memory-and-logs.md)|Savepoint, resume, no duplicated task directories by default|Adapt because owner explicitly requested full durable task/goal cards for THIS plan|
|[operations/plan.md](https://github.com/orchex006/agrimap-agent-skills/blob/develop/skills/agrimap-agent-skills/references/operations/plan.md)|Reverse engineer dependencies before planning, orchestration when multiple units|Adopt and add formal A/B classifier|
|[operations/execute.md](https://github.com/orchex006/agrimap-agent-skills/blob/develop/skills/agrimap-agent-skills/references/operations/execute.md)|Bounded writes, tests, checkpoint, delegation|Adopt with independent acceptance as release prerequisite|

This reference repository is NOT being modified. This kit contains a new proposed policy for the separate `devsift` project, not a representation of current enforcement in AgriMap or GitHub.
