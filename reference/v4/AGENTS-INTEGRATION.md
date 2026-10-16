# AGENTS.md integration snippet

## Mandatory development quality gate
For any code/config change, load `development-quality-lint/SKILL.md` before implementation. Apply the pinned rule policy, run incremental lint while developing and run affected tests after behavior-changing fixes. Critical/error findings introduced by the change block completion unless an approved time-limited exception exists. Never hide findings by deleting tests, silently refreshing baselines or disabling rules. Report scan and regression evidence in the task handoff.


## v3 mandatory guardrail
Do not edit code as part of a lint scan. Legacy recommendations require explicit per-case authorization. Report must be self-contained, with impact if unchanged, risk if changed, and case-specific review/implementation prompts.
