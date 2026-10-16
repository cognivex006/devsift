# Pinned Roslyn snapshot adapter

The trusted `native/dotnet` helper uses the real Roslyn parser and semantic model
from .NET SDK **9.0.205**, assembly version **4.13.0.0**. Its tool identity is
`devsift-roslyn` version `1.0.0`, language `csharp`, native protocol `1`. It accepts
only `--probe` or `--analyze`; analysis receives one JSON snapshot on stdin and
returns only catalog rule IDs, numeric regions, fixed completeness/reason fields
and empty metadata. No source snippets or arbitrary diagnostic messages leave
the helper. Syntax errors produce incomplete `PARSE_ERROR`; operational errors
produce a fixed incomplete response, never compiler stderr or a fabricated pass.

Build this helper explicitly during trusted setup, never during a scan or from
target project configuration. Run from `native/dotnet` so its `global.json`
selects the exact SDK:

```powershell
dotnet build DevSift.Roslyn.csproj --configuration Release --output ../../.devsift/local/tools/dotnet -p:BaseIntermediateOutputPath=../../.devsift/local/roslyn-obj/ --nologo
```

The project references the SDK's own Roslyn assemblies through `MSBuildSDKsPath`;
it has no NuGet packages. Its local NuGet configuration clears package sources,
and local Directory.Build files stop parent-project build customization discovery.
Only the trusted helper is built. The scanned repository's projects, props,
targets, generators, analyzers and source build scripts are never loaded.
Explicit SDK/runtime setup is separate; missing pinned SDK/framework assets fail
the build rather than silently downloading a substitute or choosing another SDK.

`devsift.dotnet_adapter.make_tool(absolute_dotnet_executable, absolute_artifact_dir)`
returns the accepted `ToolDefinition`. It pins SHA256 of the dotnet host and these
five already-built files:

- `DevSift.Roslyn.dll`
- `DevSift.Roslyn.deps.json`
- `DevSift.Roslyn.runtimeconfig.json`
- `Microsoft.CodeAnalysis.dll`
- `Microsoft.CodeAnalysis.CSharp.dll`

Probing reports the actually loaded Roslyn version; the common host requires the
exact expected engine version and rechecks hashes before executing. Factory calls
never build, install, discover project hooks or silently skip missing artifacts.
Caller-controlled hashes protect against accidental replacement relative to
trusted configuration; they do not authenticate a caller who changes the pins.
The dotnet runtime and its framework libraries remain trusted host dependencies,
not an OS sandbox or a claim that every runtime file is hashed here.

The helper builds an in-memory compilation from the snapshot and trusted runtime
platform libraries only. It does not execute the source or require a successful
target build. Narrow rules currently implemented are:

| Rule | Proven pattern | Deliberate exclusions |
| --- | --- | --- |
| HC001 | Direct HTTP(S) string literal as first endpoint argument of resolved HttpClient Get/GetString/GetByteArray/GetStream/Post/Put/Patch/Delete Async calls, or the second HttpRequestMessage constructor argument | Constants/indirect values, general URI strings, test/config/options paths, `*Tests.cs`, `*.test.cs`, options/settings/configuration types, test-attributed methods |
| LOG002 | Catch clause whose block has no statements | Catching the real OperationCanceledException family; nonempty blocks |
| LOG001 | Resolved System.Console Write/WriteLine invocation | User-defined Console lookalikes, arbitrary logger names and Console.Error/TextWriter calls |

Framework symbols must originate in metadata from the expected framework
assembly, not merely have the same full type name. A source-defined
`System.Console`, `System.Net.Http.HttpClient` or cancellation lookalike cannot
establish or suppress the framework-specific rules. Comments and strings that
contain apparent code do not become AST invocations/catch clauses. The HC001
test/config exclusions apply to that endpoint rule only. These rules do not claim
taint analysis, cross-project resolution, arbitrary logger semantics, every form
of hardcoding, or complete C# quality coverage. Unresolved framework symbols are
outside the narrow proven patterns; parse completion alone is not semantic proof.

Regions come from actual AST spans, converted from Roslyn UTF-16 offsets to
physical LF/CRLF lines and Unicode code-point columns with exclusive end. The
helper does not use logical `#line` coordinates or Roslyn's broader Unicode line
separator interpretation. Emoji before a finding counts as one column; a Unicode
line separator inside a comment does not create a physical Git line. Empty catches
span the catch clause; console diagnostics span the invocation; endpoints span
the literal including its quotes.

The shared `NativeAdapter` performs immutable source verification and whole-blob
snapshot comparison, then emits findings with default UNKNOWN lifecycle. This
module does not duplicate that bridge, infer NEW from a touched file, change the
quality policy, or authorize fixes. Analysis executes through the accepted bounded
runner in an owned temporary cwd with no project environment inheritance.

Opt-in tests require a real built helper: set `DEVSIFT_TEST_NATIVE=1`, optionally
`DEVSIFT_DOTNET_EXECUTABLE` and `DEVSIFT_ROSLYN_ARTIFACT_DIR`, then run
`python -m unittest discover -s tests -p test_dotnet_adapter.py -v`. The default
artifact directory is `.devsift/local/tools/dotnet`. Opt-in setup errors fail;
ordinary discovery skips native cases until explicit setup. Actual tests cover
parser failures, exact spans, shadowed framework types, cancellation, exclusions,
emoji/Unicode separator/CRLF/`#line`, artifact tampering and verified Git evidence
without source/.git writes.
