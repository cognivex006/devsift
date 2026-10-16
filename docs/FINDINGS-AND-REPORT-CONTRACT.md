# DevSift Report Contract — normative for implementation

Every authoritative `scan` outputs full standalone Markdown, JSON and SARIF 2.1.0 (unless a target format was explicitly disabled). Markdown summary links to **complete case sections**, not truncated previews. All case data must cite immutable source evidence (commit + relative file + region) or state `SOURCE_UNRESOLVED` with runtime evidence and lookup plan.

## Mandatory per finding

`case_id`, `rule_id`, `severity`, `confidence`, `lifecycle_class`, `enforcement`, `repository`, `source_sha`, `file`, `symbol`, `line:column` start/end or unresolved; local/remote navigation; exact numbered/redacted **BEFORE**; highlighted line(s); **AFTER (PROPOSAL)** code or patch with confidence; related locations; why detector fired and what exception would invalidate it; alternative do-nothing or minimal change; **if unchanged** risk; **if changed** risk (functional, logging consumers, security, performance, contract, deployment, test, rollback); affected scope and high/medium/low/unknown rationale; verification commands, rollback; separate `review` read-only prompt and `implement` approval-gated prompt; approval status; test/consumer evidence.

Secret-bearing code snippets must be masked before rendering, and masking must be consistent in logs/SARIF/JSON/prompts. Do not invent source regions from runtime logs. SARIF results should include accurate `physicalLocation.region`, `relatedLocations`, and partial fingerprints. Never ship unvalidated automatic SARIF fixes for an uncertain case.

## Behavior policy

- NEW / MODIFIED_INTRODUCED => block on configured critical/error (verified with source evidence).
- MODIFIED_PREEXISTING / LEGACY_UNCHANGED => advisory, except verified critical security issues routed to independent escalation.
- UNKNOWN => incomplete/review; never silently classed new, legacy, or clean.
- No mass rewriting `ActionLoggingFilter` and no mandatory upstream timing; first check trace continuity and log consumers. Wording and one bounded log event can be suggested, not auto-applied.
- Scanning never modifies source; per-case remediation requires explicit approval and a separate bounded verification step.

## Example record — illustrative, not actual source

```json
{
  "case_id":"OBS-001", "source_status":"SOURCE_UNRESOLVED",
  "evidence":"INFO Starting: ContentProxy.ProxyInternal ...",
  "human_explanation":"Duplicate start/end events may add noise",
  "before":"SOURCE_NOT_VERIFIED", "after_proposal":"pending source inspection",
  "impact_if_unchanged":{"level":"unknown","reason":"volume/consumers unmeasured"},
  "risk_if_changed":{"level":"unknown","reason":"global action filter consumers not inspected"},
  "lifecycle_class":"UNKNOWN","automatic_fix":false,
  "agent_review_prompt":"Inspect source and all log consumers for this exact case. Do not edit.",
  "agent_implement_prompt":"Only after per-case approval, implement minimal verified change and run regression tests."
}
```
