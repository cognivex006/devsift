# Backend golden acceptance fixtures

`tests/test_backend_golden.py` exercises the actual pinned Roslyn and Go programs
through the accepted native host and process runner. It does not mock parser
results, invoke target projects or execute fixture source. The two producer suites
remain separate; these tests check their shared behavior at the host/scanner
boundary.

`tests/fixtures/backend/expected.json` contains independently specified catalog
rule IDs, severities, exact physical regions and source snippets. Positive C# and
Go sources exercise runtime HTTP endpoints, empty error handling and standard
printing. Negative sources contain framework/package lookalikes, local import
shadowing, strings/comments that resemble code and harmless protocol constants.
Configuration/test cases prove that endpoint exemptions do not suppress unrelated
empty-error or printing diagnostics. The test compares complete diagnostic arrays,
including ordering, rather than checking that one expected warning appeared.

Additional integration cases verify:

- Both parsers return explicit incomplete `PARSE_ERROR` without partial findings.
- CRLF, emoji, Unicode line separators and logical line directives preserve physical
  LF/code-point coordinates and exclusive ends in both engines.
- Real temporary Git commits produce freshly VERIFIED source while default UNKNOWN
  lifecycle keeps the scanner incomplete, never automatically enforcing NEW.
- Appending even an unrelated comment makes the old whole-blob proof stale; those
  findings become SOURCE_UNRESOLVED and cannot block or pass.
- Complete directory/file snapshots, including `.git`, remain unchanged by analysis.
- Source startup/main functions with absolute-file-write traps are parsed but never
  executed; the trap markers remain absent.

Run after explicitly building both trusted helpers:

```text
DEVSIFT_TEST_NATIVE=1 python -m unittest discover -s tests -p test_backend_golden.py -v
```

Set environment variables using the current shell's syntax. Optional absolute
overrides are `DEVSIFT_DOTNET_EXECUTABLE`, `DEVSIFT_ROSLYN_ARTIFACT_DIR` and
`DEVSIFT_GO_ARTIFACT`. Defaults are the setup dotnet host and
`.devsift/local/tools/dotnet` / `.devsift/local/tools/go/devsift-go(.exe)` under the
checkout. Contained worktrees can point those overrides to the source root's built
artifacts. With native testing enabled, missing artifacts, failed probes or wrong
engine versions fail setup; they do not skip or substitute simulated results.
Ordinary discovery skips this suite until native setup is explicitly enabled.

These fixtures verify the documented narrow rules and provenance boundaries.
They do not establish broad semantic/dataflow coverage, target compilation,
cross-project logger correctness or a filesystem/network security sandbox. No
baseline is refreshed, severity policy changed or source remediation authorized.
