# Case study — AgriMap logs (observations, not source-code verification)

## OBS-CASE-001: ActionLoggingFilter duplicate routine events
**Classification:** Legacy candidate; confirm with Git baseline. **Severity:** Suggestion. **Evidence:** Starting/Ended events plus HTTP response completion for the same action. **Not proven:** any broken trace. **Impact if unchanged:** log noise and operator search effort (qualitative; no volume baseline). **Change risk:** shared-filter scope could affect many routes and log consumers (unknown until inspected). **Minimal proposal:** review wording/levels on demonstrably noisy routes only, or keep as-is; no global filter deletion. **Validation:** verify event consumers and trace IDs, compare representative requests. **Autofix:** forbidden.

## OBS-CASE-002: Proxy logs lack upstream timing
**Classification:** Legacy candidate. **Severity:** Informational/no finding by default. **Evidence:** Proxy start, forward and response with correlation IDs. **Not proven:** broken downstream trace or need for upstream timing. **Recommendation:** no change unless a specific incident demonstrates inability to isolate delays; inspect downstream logs first. **Autofix:** forbidden.

## OBS-CASE-003: Application trace id absent on some requests
**Classification:** Unknown until route and request type checked. **Severity:** Review. **Evidence:** agm_trace_id=null on proxy events and CORS preflight. **Not proven:** correlation break, because correlation_id remains present. **Recommendation:** test propagation end-to-end on representative business request, distinguish preflight and anonymous flows. **Autofix:** forbidden.

## OBS-CASE-004: Invalid credentials logged as unhandled error
**Classification:** Legacy candidate. **Severity:** Review. **Evidence:** UnauthorizedAccessException with invalid credentials logged as unhandled exception followed by HTTP 401. **Recommendation:** inspect whether invalid credentials are expected control flow; if so, propose narrow mapping to structured authentication failure without stack trace while preserving audit/security detection. **Change risk:** auth/error semantics and monitoring alerts; require targeted tests. **Autofix:** forbidden.

## OBS-CASE-005: SkipPaths repeated in authorization log
**Classification:** Legacy candidate. **Severity:** Suggestion. **Evidence:** duplicated skip-path list in emitted log. **Not proven:** actual configuration duplicates or functional authorization bug. **Recommendation:** inspect config composition and log formatting; do not deduplicate authorization configuration based only on a log string. **Autofix:** forbidden.
