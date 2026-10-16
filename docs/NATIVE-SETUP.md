# Explicit native setup and CLI authorization

`python tools/build_native.py` is a separate trusted setup operation. It requires
the pinned .NET SDK, Go and Node/npm installations, builds only DevSift's own
trusted helpers and installs the frontend's locked dependencies with scripts
disabled. It is never called by scanning or target project configuration.

After setup the builder uses the accepted factories to record runtime/helper
hashes, versions, languages and process limits in ignored local files:

```text
.devsift/local/native-manifest.json
.devsift/local/native-manifest.sha256
```

SQL setup selects explicit `tsql160`; `tsql150` can be chosen in an independently
reviewed manifest. There is no inferred SQL dialect. The SHA256 covers the exact
manifest bytes; retain it independently after reviewing the configured programs
and arguments. Regenerating this manifest is an explicit setup/trust update,
never an automatic response to changed executable hashes.

To authorize those programs for one CLI scan, supply both arguments:

```text
devsift scan --all --native-manifest ABSOLUTE_MANIFEST_PATH --native-manifest-digest TRUSTED_LOWERCASE_SHA256
```

`--changed` is also supported. Without this pair the existing inventory-only
behavior remains unchanged; scans do not search for manifests, install/build
dependencies, invoke source-project hooks or silently enable tools. A missing
partner, relative manifest path or malformed digest is CLI misuse (3). Invalid
manifest bytes/schema, unavailable source proof or a failed tool probe is
incomplete (2), never clean. If one configured tool cannot probe, the overall scan
remains incomplete even when no target currently uses that language.

The manifest is executable configuration. Supplying its trusted digest explicitly
authorizes native program execution; it is not an OS filesystem/network sandbox.
Trusting an attacker-provided manifest *and* attacker-provided digest does not
authenticate its programs. No arbitrary manifest values, commands or tool stderr
are echoed in public validation failures. See the process-runner and native
protocol contracts for bounded execution and the stable-host trust boundary.

Manifest schema `1` has exact keys `schema_version` and `tools`. Each tool entry
has `definition` and `dialect`. The definition records all accepted ToolDefinition
fields: identity/version/languages, complete ProcessSpec, executable SHA256,
artifact path/hash pairs and engine-version pairs. ProcessSpec records executable,
argv, timeout, each stream/stdin byte limit and explicit environment pairs.
Paths must be absolute; SQL requires `tsql150`/`tsql160`, other languages require
null. Identities are unique and tool language sets cannot overlap. Duplicate JSON
keys, unknown fields, wrong types, non-finite limits and oversized manifests are
rejected. The whole bounded manifest is validated before the first native probe.

Loading preserves every stored expected hash. It does **not** regenerate hashes
from executables or artifacts found on disk; the native host compares those files
with the stored pins immediately before execution. Setup serialization and loading
do not themselves probe programs. `native_manifest.manifest_bytes` supports an
explicit trusted setup workflow, and `load_manifest` returns frozen ConfiguredTool
records sorted by tool identity.

With native tools enabled, the CLI requires the actual Git root and full immutable
HEAD commit, using the existing read-only Git query path. It passes that root/SHA
to the shared NativeAdapter. Findings are source-verified but retain default
UNKNOWN lifecycle until a separate proven classifier attribution is integrated.
They therefore remain incomplete, not automatically NEW or blocking. Verified
critical security findings preserve `security_escalation: true` alongside that
incomplete gate. A truly completed configured parser with no findings can return
0; parser completion does not claim comprehensive language quality coverage.

Tests in `test_native_manifest.py` cover paired CLI misuse, strict/digest-bound
loading, preservation of expected pins, malformed later entries before *any*
execution, changed artifacts and real CLI invocations. The opt-in real tests need
`DEVSIFT_TEST_NATIVE=1` plus built Go/SQL artifacts (standard absolute overrides
`DEVSIFT_GO_ARTIFACT` and `DEVSIFT_SQL_ARTIFACT_DIR` are supported). A committed
clean Go snapshot completes; a verified SQL security finding stays UNKNOWN and
incomplete while retaining its security flag. Source and `.git` snapshots remain
unchanged by these scans.
