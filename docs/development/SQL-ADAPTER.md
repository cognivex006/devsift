# ScriptDom SQL adapter

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

The SQL adapter supplies parser integration, AST metadata and bounded AST rule
`SEC003` for executed SQL strings assembled from grounded SQL literals and direct
input-variable values. Parser/rule completion is not proof that a query is safe,
semantically correct, fully analyzed, authorized for execution or suitable for a
clean quality gate. Downstream acceptance fixtures verify those boundaries.

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
version `1.1.0`, language `sql`, engine `scriptdom=161.8901.0`. The internal tool
protocol/rulepack version changed from 1.0.0 because the SQL adapter adds real detectors;
this is not a DevSift project release, package publication or Git tag.
The runtime executable
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
exclusive end; U+2028/PS/VT remain within a physical line. Actual rule diagnostics
exercise conversion from ScriptDom AST execution-statement spans, including
emoji before a diagnostic on the same line, LS, LF and CRLF. There are no added
protocol fields or verification modes.

## Bounded dynamic SQL rule

Straight-line `DECLARE`, `SET`, `+=`, parentheses, literal concatenation and local
aliases are tracked into actual `EXEC(string)` and recognized unqualified or
`sys.sp_executesql` AST execution sinks. Direct variables without a known local
value represent potential external inputs. Stored-procedure parameters are
input values in a separate local scope; batches reset variable state. Literal
SQL grounding comes from ScriptDom keyword tokens, not matching raw comments or
strings for executable-looking text. Merely formatting a string without executing
it does not trigger SEC003. SQL strings, identifiers and input values stay internal.

Grounded literal SQL concatenated with direct input-variable parts at execution
emits SEC003 at the exact execution-statement AST span. Known constant SQL and
constant-only concatenations pass this rule. `sp_executesql` parameter values
remain separate from statement text: constant statement text with bound `@id`/
`@name` placeholders passes. Parameterization cannot undo taint already inserted
into the SQL text. Duplicate/ambiguous statement arguments remain incomplete.

`QUOTENAME` is not a universal value sanitizer. Only the built-in call (default,
`[` or double-quote delimiters) is eligible. The assembled skeleton must re-parse
and every placeholder must occur as an actual table-reference identifier; quoted
string/value positions, partial identifiers and unsupported contexts remain
incomplete. This is bounded syntactic context proof, not catalog resolution,
permission validation or assurance that the target object exists.

Quoted-identifier proof is preserved through local storage only when the target
is explicitly `nvarchar(max)`. Finite `nvarchar` (including `sysname`), `varchar`
conversion, and unknown storage capacity discard that proof and remain incomplete
at execution: a truncated closing delimiter can make apparently quoted input
unsafe. Both DECLARE initialization and subsequent SET/+= assignments apply this
check, including aliases; finite-capacity worst-case length analysis is outside
the bounded rule except a conservative guard that rejects literal/quoted-identifier
assembly whose UTF-16 worst-case length exceeds 4,000 (258 per QUOTENAME result).
Assigning to `nvarchar(max)` does not by itself prevent finite intermediate
concatenation truncation. Direct QUOTENAME expressions without intervening storage still
require the same parsed table-identifier context proof.

Unknown SQL execution provenance, arbitrary transformations/functions, unknown
procedure execution, remote/context execution, query-based variable assignment,
cursor mutation, and unsupported control flow return `complete=false` with a
fixed `ANALYSIS_FAILED` reason. IF/WHILE/TRY-CATCH/GOTO/RETURN invalidate convenient
local values, as do standalone EXECUTE AS/REVERT context switches. Function/trigger
bodies are not treated as analyzed procedure
scopes. Incomplete reports may retain independently detected diagnostics, but
must never become a clean scan. No arbitrary expression/dataflow analysis,
numeric conversion safety, interprocedural taint, runtime reachability, SQL
catalog binding, or whole-program security guarantee is claimed.

The local flow domain is limited to 256 concatenation parts and 32 expression
levels; excess becomes unknown/incomplete at execution. At most 1,000 diagnostics
are emitted. SEC003 here identifies a bounded static hazard, not proof of actual
user exploitability. Common host immutable-source verification and default
UNKNOWN lifecycle remain required; parsing a dangerous-looking string does not
authorize source edits or make legacy findings introduced.

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
`xp_cmdshell` text is not executed. No database is contacted.
The SQL adapter tests additionally verify unsafe execution, safe bound parameters, aliases,
procedure input scopes, QUOTENAME context limits, unknown-flow incompleteness,
ambiguous statement arguments and exact diagnostic coordinates in both dialects.
Run `python -m unittest discover -s tests -p test_sql_rules.py` with native testing
enabled. `xp_cmdshell` is an unknown procedure to the bounded rulepack and remains
incomplete while its text is still never executed. Rollback is the
scoped producer commit revert; no consumer SQL or database state was modified.
