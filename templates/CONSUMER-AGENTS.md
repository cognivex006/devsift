# Consumer application — DevSift usage only

This file is a **template** for projects that choose to use DevSift. It does not authorize editing the devsift source package, changing branches, publishing packages or applying provider-specific maintainer workflow.

For authorized application code changes: run changed-only lint during development and CI. Treat verified new/introduced policy violations at configured gate severity as blocking. Report unchanged legacy as recommendations; never bulk-apply legacy fixes. Never make a source edit during `scan` or `review`. For remediation, obtain per-case explicit approval with before/after, two-sided effect assessment and tests. No speculative source location. Prioritize correlation continuity and existing log semantics. Read the project-local governance first; do not override its release, branch or approval policy.
