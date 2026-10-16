# ScriptDom SQL parser adapter (T028)

The explicit trusted helper `native/sql/DevSift.Sql.csproj` parses SQL snapshots
with Microsoft's actual ScriptDom AST parser. SQL input is never executed. There
are no database drivers, connections, deployment operations, sqlcmd calls, target
project builds, SQL project loading, or source-file writes. The helper reads one
bounded JSON object from stdin, parses its source with `StringReader`, and writes
only the frozen native protocol v1 on stdout. It never opens the supplied path.

`tsql150` selects `TSql150Parser`; `tsql160` selects `TSql160Parser`, both with
quoted identifiers enabled. Dialect is mandatory and explicit. Missing, PostgreSQL,
MySQL, or other dialect values return `UNSUPPORTED_DIALECT`; malformed T-SQL
returns `PARSE_ERROR`. No fallback parser or string heuristics claim success.
Parse errors and exceptions produce no source, identifiers, SQL strings or raw
diagnostic messages in output. Invalid/duplicate/unknown JSON keys fail closed.

T028 supplies parser integration and AST metadata, **not unsafe-SQL rules**.
Successful analysis currently returns zero rule diagnostics. Parser success means
syntactic parsing completed, not that a query is safe, semantically correct,
fully analyzed, authorized for execution or suitable for a clean quality gate.
T029 adds separately reviewed rules; T030 supplies downstream acceptance fixtures.

Metadata reports the explicit dialect, count of AST `NamedTableReference` nodes
whose names have one identifier, and supported DDL AST-node counts. Unqualified
counts are syntactic table references, including CTE/temp names where the parser
represents them that way; there is no catalog/schema resolution. Supported DDL
counts cover create/drop table, create/alter/drop view, procedure and function,
create/drop index, and create/drop schema. Other DDL statements may parse without
being included in this deliberately bounded metadata count. No SQL text, object
names, values or connection information are emitted.

## Explicit trusted setup

The project pins SDK `9.0.205` in its own `global.json` and exact NuGet range
`[161.8901.0]` for `Microsoft.SqlServer.TransactSql.ScriptDom`, with the committed
content-hashed `packages.lock.json`. `NuGet.Config` selects the official feed
without changing user/global settings. Setup is an authorized network/build
operation on this trusted project only; scan execution never restores/builds or
searches customer `.sqlproj`/MSBuild files.

Run from `native/sql` so the project SDK pin is effective. For example, with
`<repo>` replaced by the source repository's absolute path:

```text
dotnet --version
dotnet restore DevSift.Sql.csproj --locked-mode --configfile NuGet.Config --packages <repo>/.devsift/local/nuget
dotnet publish DevSift.Sql.csproj -c Release --no-restore -o <repo>/.devsift/local/tools/sql
```

The package cache and published toolhome stay under ignored `.devsift/local`;
`bin`/`obj` build outputs are ignored. Build artifacts are not committed. The real
Windows producer restore/build used SDK 9.0.205 and the pinned package. The loaded
ScriptDom assembly is checked for assembly version `16.1.0.0` and actual file
version `16.1.8901.0` before probe/parse. The Python factory also verifies the exact
package version in the published dependency graph; it does not rely solely on a
self-reported engine version string.

## Factory and execution

`devsift.sql_adapter.make_tool(dotnet_executable, artifact_dir)` requires explicit
absolute paths. It creates the accepted `ToolDefinition` for tool `devsift-sql`
version `1.0.0`, language `sql`, engine `scriptdom=161.8901.0`. The runtime executable
and four required artifacts receive caller-trusted SHA-256 pins:

- `DevSift.Sql.dll`
- `DevSift.Sql.deps.json`
- `DevSift.Sql.runtimeconfig.json`
- `Microsoft.SqlServer.TransactSql.ScriptDom.dll`

`NativeAdapter`/`analyze_snapshot` own bounded process execution, per-call integrity
checks, strict report normalization and default UNKNOWN source lifecycle. Native
AST positions alone do not establish Git source proof; findings, once introduced,
must pass common immutable snapshot/source verification. The helper includes a
UTF-16 offset converter using physical LF lines and Unicode code-point columns,
exclusive end; U+2028/PS/VT remain within a physical line. There are no added
protocol fields or verification modes. T029 actual rule diagnostics will exercise
that coordinate conversion end to end.

Pins protect setup relative to caller-trusted expected bytes, not against a
caller replacing both artifacts and trusted hashes. .NET runtime libraries and
trusted helper dependencies are not an OS sandbox. Scans do not intentionally
access the network, install tools or execute SQL; a trusted helper process still
runs under the host process permissions described in `NATIVE-PROTOCOL.md`.

## Validation

`python -m unittest discover -s tests -p test_sql_adapter.py` runs setup-boundary
tests without native installation. Set `DEVSIFT_TEST_NATIVE=1` to run real parser
tests after setup. `DEVSIFT_DOTNET` and `DEVSIFT_SQL_ARTIFACTS` can select the explicit
runtime/toolhome; otherwise the test resolves dotnet once and uses repository-local
`.devsift/local/tools/sql`. When native tests are requested, missing runtime/helper
is a failure, not a skip or parser substitute.

Real tests exercise both dialect parsers, AST metadata, syntax errors, Unicode
literals/CRLF, strict/duplicate JSON and unsupported dialects. Dynamic execution
statements are parsed as syntax only: a temporary filesystem-marker test proves
`xp_cmdshell` text is not executed. No database is contacted. Rollback is the
scoped producer commit revert; no consumer SQL or database state was modified.
