---
name: devsift-review
description: Independently review bounded source and diagnostic finding changes, with explicit acceptance evidence and per-case remediation policy.
---

Use `templates/REVIEW-CHECKLIST.md`. Inspect exact task, diff SHA, source locations, before/proposed-after, expected behavior, tests, effects of both changing and not changing. Report accepted/rework/blocked with evidence; only Controller writes canonical accepted state after verifying merge/integration. No self-review, no new subagent quota, no unapproved changes or legacy auto-fixes. Runtime log-only findings must remain SOURCE_UNRESOLVED until source proven. Tests and independent review both required for acceptance; neither alone unlocks tasks.
