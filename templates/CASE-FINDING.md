# {CASE_ID} — {rule_title}

- Rule / severity / confidence / lifecycle classification / enforcement:
- Verified repo / commit SHA / file / method-symbol / line-column or `SOURCE_UNRESOLVED`:
- Navigation (SHA pinned) and related locations (config, tests, consumer):
- Evidence type, detector version and detection condition:

## BEFORE — exact source excerpt with numbered lines; or UNVERIFIED

```text
[do not fabricate code/lines]
```

## AFTER — PROPOSAL ONLY; include alternative no-change approach

```diff
[no patch until actual source inspected]
```

## Why this matters

Human explanation, exception cases and likely false positives:

## Effect if unchanged

Security/operability/developer impact; frequency measured or unknown; affected users/services:

## Risk if changed

Runtime behavior, consumers/alerts, logging/traces, performance, rollout/regression, rollback difficulty; Low/Medium/High/Unknown with rationale:

## Verification and rollback

Actual commands, test coverage, consumer compatibility, evidence, rollback plan:

## Review-only agent prompt

[Bounded inspect, no edits]

## Implement agent prompt (approval-gated)

[Only after explicit per-case approval and SHA revalidation]

## Approval and review record

Owner decision, independent reviewer, integrated commit SHA, current status:
