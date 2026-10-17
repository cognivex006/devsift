# DevSift repository maintainer scope

These instructions govern work on the DevSift runtime repository itself. They
are not consumer-project instructions. Invoking the installed DevSift skill or
CLI against another repository does not adopt DevSift's branch, commit, review,
release or task-management conventions. Follow that target's applicable
instructions and the user's authorized scope. See [agent scope](docs/development/AGENT-SCOPE.md).

This repo owns the consumer skill, Python CLI, native analyzers, schemas, runtime
tests, build/CI and usage docs. Specifications, task cards, the single execution
ledger, maintainer skills, governance templates and review evidence belong to
https://github.com/orchex006/devsift-specs . Do not copy them here or install them
with the consumer skill. Use specs only for explicitly authorized DevSift
maintenance coordination; consumers need no specs checkout or ledger access.

For authorized changes to DevSift, read DEVELOPMENT.md and relevant runtime
docs; inspect status and preserve unrelated work. Use scoped branches and
reviewed PRs, no direct main writes or force push. Stage only owned files. Run
relevant tests and diff checks and obtain independent review before merge.
Releases require separate authorization.

All explicit download workflows must provide live progress bars and transfer
percentages based on received bytes and a known total (server length or a trusted
expected size). This is a development rule for new and changed download code.
When the total is unavailable, show an indeterminate bar/spinner, received bytes
and "size unknown"; never invent a transfer percentage. Distinguish overall
setup-stage progress from transfer progress. Update the same console indicator
instead of printing periodic log lines, keep a concise completion/failure summary,
and support structured/noninteractive output without terminal control noise.
Test known-size, unknown-size, interruption and checksum-failure behavior. This
rule does not authorize network activity during read-only scans.

Scans and reviews are read-only. Native execution requires an explicitly trusted
manifest and digest. No target builds, automatic dependency installation or mass
remediation. Consumer edits require user authorization and applicable target
rules. Report prompts and approval labels do not independently authorize edits.
Never claim pending capabilities work.

For DevSift maintenance, use ignored worktrees/<job> for parallel work. Preserve
dirty or unique work; remove completed worktrees only after integration or
documented supersession. Specs owns coordination. A pause handoff records
unfinished work and next actions when pausing; Git preserves committed history.
These coordination requirements do not create tasks or goals from ordinary
consumer questions or read-only scan requests.
