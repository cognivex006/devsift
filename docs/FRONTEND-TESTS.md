# Frontend acceptance and bounded workload (T027)

`tests/test_frontend_acceptance.py` uses the actual pinned ESLint/TypeScript ESTree
helper, tool version 1.1.0. Set `DEVSIFT_TEST_NATIVE=1` after explicit setup; optional
`DEVSIFT_NODE_EXECUTABLE` and `DEVSIFT_FRONTEND_PACKAGE` select the trusted installed
runtime/package directory. Requested native tests fail if tools/dependencies are
unavailable or their probe does not match. Without opt-in the native suite skips;
a skip does not establish analyzer coverage.

```text
python -m unittest discover -s tests -p test_frontend_acceptance.py
```

Static fixtures cover Angular decorators and environment-driven configuration,
Next/TSX markup URLs, centralized config/spec/fixture endpoint exclusions, lexical
shadowing, non-axios imports, explicit placeholders, actual runtime fetch
positives, and credential findings that remain active in test paths. Every case
invokes real AST analysis; severity is never inferred by a test-side regex.

The changed-scope integration fixture creates a real Git history with unchanged
legacy, staged config, unstaged runtime code and untracked TSX. It calls the actual
`run_scan` Git candidate selector. A test-only scanner seam supplies a recording
wrapper around **real NativeAdapter execution**, since the inventory CLI does not
register native tools by default. Neither the candidate selection nor analyzer
outcomes are mocked. Spies confirm that Python source inventory reads and native
analysis touch exactly the three changed candidates, never unchanged legacy.
This does not assert that Git avoids reading index/stat metadata. Dirty findings
retain UNKNOWN/unresolved proof and exit 2 with zero enforced findings, so selecting
a changed file never makes it wholly NEW or falsely blocking.

A second real-Git fixture commits a credential assignment, runs the common
coordinator/native adapter, and checks immutable source verification, fully masked
BEFORE, UNKNOWN lifecycle, independent critical-security escalation and zero
automatic quality blocking. The public JSON must not contain the fixture value.
No source or index writes are authorized by these scans.

The bounded workload generates 3,500 unique typed exported declarations (127,280
UTF-8 bytes) in memory and requires real AST completion with no findings. The
configured native process budget is 30 seconds; the test permits 90 seconds of
overall wall time to account for host contention and integrity checks. This is a
bounded smoke fixture, not a portable throughput benchmark or performance SLA.
The producer run on Windows recorded **2.077 seconds** for this sample; all five
acceptance methods completed in 39.319 seconds before the additional direct-cwd
hook assertion. The test prints actual elapsed seconds for subsequent evidence.
An excessive snapshot beyond the 2 MB native input budget must return incomplete
without diagnostics; rejected input is never a successful empty scan.

No target JavaScript is executed. Filesystem-marker tests supply executable-looking
imports and ESLint config plus invalid tsconfig data, then verify no marker or
byte changes. The helper is also invoked directly from that customer directory
to ensure config/import execution is not avoided solely by the common runner's
temporary cwd. Parser/host source code remains untouched by this task.

These tests exercise bounded syntax/context rules, not complete language/type,
taint, live-secret validity or exploitability analysis. The common host is not an
OS sandbox, and trusted runtime/dependency assumptions remain those documented in
`NATIVE-PROTOCOL.md`. Read-only fixture evidence cannot authorize remediation.
Rollback is the test-only commit revert; no production code, shared task ledger,
release artifacts or consumer source was modified.
