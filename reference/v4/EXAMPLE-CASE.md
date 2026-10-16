# Illustrative report case — NOT a verified source finding

## OBS-001: Redundant Action Logging
Status: `LEGACY_UNCHANGED` (illustrative) | Severity: Suggestion | Source: `SOURCE_UNRESOLVED` | Approval: Required

**Observed log evidence:** `INFO Starting: ContentProxy.ProxyInternal` and `INFO Ended: ContentProxy.ProxyInternal (23 ms)` coexist with a response event containing status and duration. These logs alone do not identify the filter implementation or its line numbers.

**BEFORE source:** NOT AVAILABLE — repository source has not been inspected.

**AFTER source:** NOT AVAILABLE — a safe patch cannot be specified without examining filter implementation, configured sinks and consumers.

**Illustrative direction only:** If verified source shows per-action INFO start/end logging and there are no audit/alert dependencies, consider narrowing levels or wording for selected actions. A shared filter change may affect all routes; do not assume a route-local edit is possible.

**Impact if unchanged:** diagnostic signal-to-noise may remain low (Medium, inference); functional impact not demonstrated (Unknown); measured log volume Unknown.

**Risk if changed:** shared-filter blast radius potentially High; downstream log consumers Unknown; trace continuity must be verified; functional risk Unknown pending source review.

**Review prompt:** Inspect the actual ActionLoggingFilter, logging configuration and consumers for `ContentProxy.ProxyInternal`. Locate exact lines, show numbered BEFORE code and minimal proposed AFTER diff, check cross-service correlation, and assess downstream effects. Do not edit code or introduce mandatory upstream instrumentation.

**Implementation prompt:** Only after case approval, implement the exact approved minimal diff, preserve trace and audit behavior, test affected routes and rollback; stop if shared scope is larger than approved.
