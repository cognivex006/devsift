# Quality Lint v2 — Observability & Actionable Diagnostics

Status: Proposed. This document extends v1; no engine or analyzer has been implemented.

## Enforcement
Skill instructs; deterministic language adapters and CI enforce. Critical/Error new findings block protected merges; Warning reports; Suggestion is advisory. Existing debt uses reviewed, expiring baseline. Rule exceptions need owner, reason, ticket and expiry; secrets cannot be broadly suppressed.

## Finding contract
Every finding emits: rule_id, severity, confidence, file/line, human_explanation_th, why_it_matters, evidence_redacted, expected_outcome, remediation_steps, regression_risk, verification, agent_prompt, fingerprint. Only high-confidence deterministic findings can block; contextual recommendations require review.

## Log and observability rules
- OBS001 (warning): repetitive action start/end logs duplicating HTTP completion events; prefer spans and metrics, debug level or sampling.
- OBS002 (warning): high-volume successful HTTP requests at INFO without sampling/route exclusion. Never drop operational audit records.
- OBS003 (error for designated critical paths): missing trace context propagation across gateway and downstream HTTP/queue calls; verify W3C traceparent and baggage policies. Do not assume absent custom cookie trace ID implies broken tracing.
- OBS004 (warning): response log lacks route template, service name, status, duration, outcome and deploy version. Avoid high-cardinality labels.
- OBS005 (warning): dependency calls without latency/outcome instrumentation; recommend OpenTelemetry spans and HTTP/DB metrics.
- OBS006 (error): logging request/response bodies or secrets without explicit allowlist, redaction, size limit, retention review.
- OBS007 (warning): expected 401/404 validation/auth failure emitted as unhandled Error; map expected outcomes while preserving suspicious-activity security monitoring.
- OBS008 (warning): catch/rethrow logging same exception at multiple layers; log once at boundary and attach trace context.
- OBS009 (warning): auth middleware logs verbose configuration/skip paths per request; debug-only and startup summary, inspect duplicate path entries.
- OBS010 (warning): custom request IDs used without consistent correlation; document distinct roles of request_id, correlation_id, W3C trace_id and application session ID.
- OBS011 (suggestion): operational events lack action/outcome/reason/dependency and troubleshooting runbook reference.
- OBS012 (suggestion): instrument meaningful domain milestones, cache hit/miss, retry, timeout, queue delay, downstream failure, and circuit breaker transitions without logging sensitive data.
- OBS013 (warning): dynamic unbounded route/user/trace identifiers as metric labels; use bounded dimensions and keep IDs in trace/log fields.
- OBS014 (error): audit/security events disabled by generic success-log sampling or suppression.

## Case review: supplied AgriMap logs
1. ContentProxy.ProxyInternal generates start/forward/end/response for each request, while HTTP 304 and timings are already logged. Consider consolidating success event or replacing start/end with span; do not assume 304 is an error.
2. `agm_trace_id=null` for some requests, including OPTIONS, is not proof of broken distributed tracing. Check W3C traceparent propagation independently and document whether cookie trace is optional.
3. `AuthorizationMiddleware` repeatedly prints SkipPaths; one sample shows duplicated entries. Inspect configuration registration and middleware invocation before changing behavior.
4. Invalid credentials is an expected 401, but sample logs an Unhandled Exception stack as Error. Use typed auth outcome or exception mapping; ensure abuse monitoring persists.
5. Request body logging includes username; password masking exists, but allowlist/redaction and privacy review are needed.
6. Proxy timings should distinguish total latency from upstream latency and indicate upstream status, retry and cache behavior when actually available.

## Example desired event (illustrative, not observed)
```json
{"event":"proxy.request.completed","level":"Information","service":"agmws-gateway","route":"content.proxy","http.method":"GET","http.status_code":304,"duration_ms":53,"upstream.service":"agmws-content","upstream.duration_ms":41,"retry_count":0,"outcome":"not_modified","trace_id":"example","span_id":"example","deployment.version":"example"}
```
Keep routine successes in metrics/traces, sampled debug or selectively retained completion events. Emit abnormal events at useful levels; measure log volume, cardinality and query effectiveness.

## Domain-specific adapters
One orchestration skill; separate deterministic rule packs for backend-dotnet, backend-go, frontend-ts, sql, infra, cross-cutting security and observability. Discover repo manifests and file extensions; parse via language-specific AST/semantic tooling, not one regex/LLM analyzer. Merge findings into one SARIF report; cross-layer checks consume declared contracts.

## Example finding
**OBS001 — Repetitive low-signal action logging (Warning, contextual)**
Human: `ActionLoggingFilter` emits Starting/Ended for every action and a response completion record already includes duration. On high-volume paths this can increase storage and make failures harder to find. Consider Debug sampling or Activity spans, retaining security/audit events and slow/error summaries.
Agent prompt: `Inspect ActionLoggingFilter, HTTP response middleware and existing OpenTelemetry setup. Identify duplicate routine success logs; propose the smallest change to reduce INFO noise without removing audit/security logs or changing HTTP behavior. Add route-aware thresholds/sampling, correlation propagation checks and regression tests. Report before/after log volume and example traces; do not edit until test impact is assessed.`

## Acceptance tests
- Critical/Error new deterministic findings fail CI with stable exit code and SARIF.
- Each finding has Thai human guidance and a copyable scoped agent prompt, including test plan and constraints.
- Frontend/SQL/backend rule packs run separately with deterministic file routing.
- Fixture cases: 304 success, OPTIONS without cookie, invalid credentials 401, secret in body, duplicate auth skip paths, successful proxy and slow upstream.
- Tests prove audit/security events remain available and that behavior, status codes, propagation and error handling are unchanged after remediation.
