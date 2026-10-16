# Pinned native tool protocol v1

`native_host.ToolDefinition` holds an explicit absolute `ProcessSpec`, external
SHA256 of the executable and at least one trusted artifact, exact tool version,
language tuple and exact engine-version pairs. Probing rechecks hashes before
executing `argv + ('--probe',)` through the bounded process runner. This is caller
configuration integrity, not authentication against a caller who changes both
code and trusted hashes. Runtime/dependency installation is an explicit setup
operation; scans never install tools, search project hooks or build target code.

Probe output is exactly:

```json
{"protocol_version":"1","tool_id":"example","tool_version":"1.0.0","languages":["typescript"],"engine_versions":{"parser":"1.0.0"}}
```

Analysis receives a single UTF-8 JSON object on stdin with `protocol_version`,
canonical relative `path`, `language`, original `source` and `dialect` (null except
explicit SQL dialects). It executes `argv + ('--analyze',)` from a runner-owned
temporary directory. The output is exactly:

```json
{"protocol_version":"1","tool_id":"example","tool_version":"1.0.0","complete":true,"diagnostics":[{"rule_id":"LOG002","region":{"start_line":1,"start_column":1,"end_line":1,"end_column":8}}],"reason":"COMPLETED","metadata":{}}
```

Allowed failure reasons: PARSE_ERROR, UNSUPPORTED_DIALECT, ANALYSIS_FAILED,
UNSUPPORTED_SOURCE. Unknown keys, duplicate JSON keys, non-finite JSON, invalid
versions/booleans/rules/regions, duplicate diagnostics and oversized output fail
closed. Coordinates are physical LF/CRLF lines, one-based Unicode code-point
columns, exclusive end; AST runtimes must convert their UTF-16/byte offsets.
No source snippet or arbitrary diagnostic message is accepted from a tool:
messages come from the canonical rule registry. Optional metadata contains only
`dialect` (tsql150/tsql160) and bounded unqualified-reference/DDL counts, not SQL
text, identifiers or connections.

`analyze_snapshot` returns a frozen `NativeReport` of parsed snapshot positions.
Those positions alone are not immutable Git proof. `NativeAdapter` re-verifies
each finding against the configured immutable source SHA and whole snapshot blob
before producing `ScanFinding`. Missing/stale source remains unresolved, and
default lifecycle attribution is UNKNOWN. Parser success is not semantic rule
proof or complete language coverage. The scanner retains all incomplete gates.

Tools are explicitly trusted programs and runtime dependencies on a stable host;
this protocol/runner is not an OS filesystem/network/memory sandbox. Pins and
hashes prevent accidental replacement relative to caller-trusted expectations;
they do not authenticate arbitrary caller configuration. Partial/timeout/invalid
output never becomes a clean result. No baseline or source writes occur here.
