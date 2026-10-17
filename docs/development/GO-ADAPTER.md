# Pinned Go AST snapshot adapter

The trusted `native/go` program uses the real Go standard-library parser and AST
from **go1.21.3**. Its tool identity is `devsift-go` version `1.0.0`, language
`go`, native protocol `1`. Probe reports actual `runtime.Version()`; the accepted
host requires exactly `go1.21.3`. Analysis also fails closed on another compiler
runtime version. The module has no external dependencies.

Build only this trusted module during explicit setup, from `native/go`, with
`GOTOOLCHAIN=local`, `GOPROXY=off`, `GOSUMDB=off`, `CGO_ENABLED=0`, and `GOWORK=off`:

```text
go build -trimpath -buildvcs=false -o ../../.devsift/local/tools/go/devsift-go .
```

Use `devsift-go.exe` on Windows and create the output directory before building.
These flags prevent toolchain downloading, module proxy/network resolution,
workspace discovery, CGO and VCS stamping. They do not build or inspect a scanned
project. This explicit setup requires the pinned local Go installation and may
write its normal compiler cache plus the requested ignored artifact directory.
Scanning never runs `go build`, `go test`, `go run`, module installation, target
build hooks or target imports.

`devsift.go_adapter.make_tool(absolute_executable)` pins SHA256 of the already-built
binary as both executable and trusted artifact. It returns the accepted
`ToolDefinition`; no PATH search, build or installation occurs. Integrity is
rechecked by the host before execution, relative to trusted caller expectations.
It does not authenticate a caller who changes both the program and hash.

The helper accepts only `--probe` and `--analyze`. Analysis reads bounded UTF-8
JSON from stdin, rejects duplicate/unknown fields and uses `go/parser.ParseFile`
with supplied source bytes. It never opens the request path. There is no
`go/importer`, target type loading, module resolution, execution or network I/O.
Results contain only catalog IDs and numeric AST regions; messages/snippets are
not accepted native output. Syntax errors yield incomplete `PARSE_ERROR`; fixed
failure reasons replace raw parser errors, paths and source. More than 1000
diagnostics or other analysis failures produce incomplete output.

Current narrow patterns are:

| Rule | Grounded AST pattern | Deliberate exclusions |
| --- | --- | --- |
| HC001 | HTTP(S) direct string literal endpoint in imported standard `net/http.Get` or `Post` | Nonstandard package paths, shadowed aliases, indirect constants/values, `_test.go`, test/testdata/fixtures/config/configuration paths |
| LOG001 | Imported standard `fmt.Print` or `Println` call | Nonstandard package paths, shadowed aliases, arbitrary logger methods, dot imports |
| LOG002 | Empty `if value != nil` error branch | Pointer/interface/non-error parameters, `== nil` branches, nonempty bodies and ungrounded variable names |

Imports may use aliases. The parser's lexical object bindings reject local
variables, parameters or package declarations shadowing those aliases; duplicate
alias declarations are not trusted. This proves the intended standard import and
syntactic scope, not a whole-project semantic model. No external packages are
loaded. An empty error branch requires a builtin `error`-typed parameter/variable
or a directly inferred standard `errors.New`/`fmt.Errorf` result. A user-defined
`error` type, a shadowed errors/fmt receiver, or an explicitly generic interface
variable does not establish that proof. There is no variable-name-only `err`
heuristic or speculative cross-function/taint/dataflow claim. Unresolved constructs
fall outside these patterns. Parse completion does not prove target compilation
or comprehensive Go rule coverage. Test/config exclusions apply to HC001 only;
standard print diagnostics identify printing, not the author's business intent.

Coordinates convert actual AST byte offsets to physical LF/CRLF lines and
one-based Unicode code-point columns, with exclusive end. They do not use Go's
byte columns or logical `//line` directives. Emoji counts as one column and a
Unicode line separator inside a comment does not create a physical Git line.
HTTP diagnostics cover the quoted/raw string literal; printing covers the call;
empty-error diagnostics cover the if statement. Comments, strings and protocol
constants containing apparent code do not become AST call/branch findings.

The shared `NativeAdapter` supplies immutable Git proof and default UNKNOWN
lifecycle attribution; this adapter does not duplicate the bridge or label a
touched file NEW. Execution uses the accepted bounded runner and owned temporary
cwd. Host runtimes/executables remain trusted; this is not an OS filesystem,
network, CPU or memory sandbox. No scan source/config/baseline writes are made.

Set `DEVSIFT_TEST_NATIVE=1` after building and run
`python -m unittest discover -s tests -p test_go_adapter.py -v` for actual native
fixtures. `DEVSIFT_GO_ARTIFACT` overrides the default
`.devsift/local/tools/go/devsift-go(.exe)`. Opt-in missing tools, artifacts or pin
mismatches fail instead of skipping or substituting fake native results. Fixtures
cover aliases/shadowing, exact rule spans, grounded error types, comments/strings,
test/config exclusions, malformed syntax, physical Unicode/CRLF/directive
coordinates and changed-binary rejection.
