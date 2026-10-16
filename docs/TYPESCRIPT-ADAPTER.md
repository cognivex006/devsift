# Pinned ESLint / TypeScript AST adapter

`typescript_adapter.make_tool(node_executable, package_dir)` is an explicit trusted
setup factory. The source helper is `native/frontend/analyze.cjs`. Install its exact
lockfile with `npm ci --ignore-scripts --no-audit --no-fund` before setup. Scans never
install packages or load target ESLint configuration, plugins, tsconfig projects,
project services, imports, scripts or inline disable directives.

Pins: ESLint 10.12.0, @typescript-eslint/parser 8.71.2 and TypeScript 6.0.3. TypeScript
7 is outside this parser's declared compatibility range, so it is not selected.
The helper reports actual dependency versions and common host probing verifies
them, plus runtime and helper/manifest/lockfile digests. This is trusted setup
integrity, not authentication against a hostile caller/host changing both pins
and code. The Node runtime must satisfy ESLint's supported engine range.

T025 uses the real ESLint `Linter.verify` and TypeScript ESTree parser on in-memory
source. Its initial rule is LOG002 for syntactically empty catch blocks. Comments
and fake code in literals are not AST catches; nonempty handling is not flagged.
Angular decorators, Next/TSX and JSX are parsed without target project resolution.
Syntax errors stay incomplete and no source-bearing parser messages are emitted.
This is syntax-aware bounded analysis, not whole-program type or taint analysis.

Coordinates derive from original AST UTF16 offsets, converted to physical LF/CRLF
line numbers and Unicode code-point columns with exclusive ends. Logical LS/PS
inside comments does not shift Git line references. Native helpers accept stdin
JSON only and output rule IDs/regions; source proof and UNKNOWN default lifecycle
are handled by the shared native adapter. Hardcode/secret context rules are a
separate T026 task after T025 acceptance.

Actual tests require `DEVSIFT_TEST_NATIVE=1`; missing configured runtime or pinned
packages fail the opt-in suite. Optional overrides: `DEVSIFT_NODE_EXECUTABLE` and
`DEVSIFT_FRONTEND_PACKAGE`. No native coverage claim is inferred from a skipped
test. Native programs and dependencies remain trusted code, not an OS sandbox.

References: [ESLint Linter API](https://eslint.org/docs/latest/integrate/nodejs-api#linter),
[TypeScript parser options](https://typescript-eslint.io/packages/parser/).

The native request boundary rejects duplicate JSON keys (including escaped aliases), invalid UTF-8, and trailing data before parsing source. Malformed requests return fixed incomplete output without echoing input.

## Runtime context rules (T026)

Tool protocol version 1.1.0 adds actual ESTree-based HC001/HC002. HC001 covers
literal HTTP(S) endpoints passed directly to unshadowed global fetch or default
imports from axios (including aliases). Other imports, lexical shadows, arbitrary
strings, indirect values, test/fixture paths and centralized environment/config
paths are excluded from this narrow endpoint detector. No target imports execute.
HC002 covers explicit credential-named variable, assignment, object-property and
class-field string literals. Dynamic computed names, environment reads, empty
values and explicit example/dummy/YOUR_* placeholders are not verified secrets.
Credential literals remain findings in tests and configuration; a directory name
cannot waive security. These bounded syntactic patterns do not establish that a
credential is live or provide interprocedural taint analysis. The host emits fixed
registry text and source-safe regions, never the credential literal.
