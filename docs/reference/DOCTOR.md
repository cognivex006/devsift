# Doctor provider discovery

`devsift.doctor.run_doctor` provides read-only provider discovery and optional
cache/config diagnostics.
The CLI calls it through `devsift doctor`. Candidate 0.1.16 user-registration
resolution uses explicit flags to override registered trust, otherwise
the CLI resolves `~/.local/share/devsift/analyzers.json` before calling this library.
`devsift setup --status` reads that registration's readiness separately from lint;
it is not source analysis. No trust is discovered in the target. Releases through
0.1.15 still require explicit native flags. Explicit trusted probes use
`--native-manifest <absolute-path>` and `--native-manifest-digest <trusted-sha256>`.
The CLI also accepts `--policy <explicit-json>` and `--cache-path <explicit-directory>`
for read-only diagnostics. These paths are explicit inputs, not automatically
discovered project configuration. For an installed, isolated invocation:

```text
devsift doctor --policy /absolute/policy.json --cache-path /absolute/cache
```

See [troubleshooting](../TROUBLESHOOTING.md) for first-use symptoms and
[the CLI reference](CLI.md) for result and argument conventions.

```python
from devsift.doctor import run_doctor

record = run_doctor()  # Metadata only; no external command is executed.

# Optional explicit files/directories inside an existing diagnostic root:
record = run_doctor(root=project_root, policy_path="policy.json", cache_path=".cache/devsift")

# Only after independently reviewing and trusting the configured programs:
record = run_doctor(
    native_manifest=absolute_reviewed_manifest_path,
    native_manifest_digest=independently_retained_sha256,
)
```

The result uses the existing `output.result('doctor', ...)` envelope version
`1.0`. It includes `data.runtime.name/version/supported`, compatible capability
booleans, host-tool metadata, configured native tools and explicit provider
records for C#, Go, JavaScript, Python, SQL and TypeScript. `analysis_performed`
is false, findings are empty and scope is `provider_discovery_only`. These are
diagnostic facts, not a scan report or proof that every registered rule works.

## Metadata discovery itself executes nothing

The running Python interpreter's version is read from `sys.version_info`; Python
3.12 or newer is required. Git, dotnet, Go, Node and npm are checked only through
bounded PATH **metadata** discovery. A found filename is `discovered_unverified`,
not a trusted/runnable installation, and its version is explicitly null. Missing
tools are `missing`; unavailable/excessive PATH metadata is `discovery_unavailable`.
Each record has a fixed explanation and actionable separate-setup guidance.
Overall incomplete is not equivalent to zero available analyzers: the standard
four native helpers can be ready for C#/SQL/Go/TS/JS while Python quality coverage
is unavailable. Inspect per-provider readiness and continue an eligible project
scan. Setup `analysis_ready` concerns configured native providers, not all languages.
Metadata discovery runs no `--version`, package manager, Git/project command,
hook or executable from PATH, even if the current project shadows its name.
Separately, the installed CLI may execute its previously registered hash-pinned
providers for bounded probes. The Python `run_doctor()` metadata-only example
above has no implicit user-registry resolution; the CLI supplies resolved trust.

`search_path` optionally supplies the metadata search path for an embedding or
test; it never supplies an executable to launch. The search is nonrecursive and
limited to five known tool names, 32768 path characters and 512 path entries.
Filesystem metadata availability is subject to the host/filesystem; this is not
a timeout guarantee against a stalled remote filesystem in PATH. Absolute paths,
PATH values, arguments and raw OS exceptions are not returned in public output.

Host setup tools are advisory: an already-built Go helper, for example, does not
need a Go SDK on PATH. Their unverified metadata never determines a provider's
`available` flag or verified version. The existing `git_provenance` capability
boolean describes an implemented library capability, not a claim that this
invocation verified a working Git runtime. No source provenance is queried here.

## Explicit native trust and verified versions

Without an explicit pair or valid user registration, unconfigured providers
remain unavailable and the result is incomplete, exit 2. At the CLI boundary, a missing partner,
relative manifest path or incorrectly formatted digest is misuse, exit 3.
An unreadable manifest, well-formed but mismatched digest, malformed tool or invalid
SQL dialect returns incomplete, exit 2, with a static error and starts no native probe. No manifest is auto-discovered
from project configuration or ignored setup directories.

Explicit setup registration authorizes repeated use of the reviewed native
programs; ordinary Doctor does not ask the user to retype their manifest/digest.
Supplying the pair overrides that registration for this invocation, just
as described in [NATIVE-SETUP.md](../NATIVE-SETUP.md). The entire bounded manifest
is validated through `load_manifest` before any probe. Stored expected hashes
are preserved; doctor does not rebuild tools or replace pins. `probe_tool`
rechecks executable/helper artifacts and validates native protocol v1 identity,
languages, exact tool version and exact engine-version pairs. SQL reports the
manifest's explicit `tsql150` or `tsql160`, never an inferred dialect.

Doctor caps each trusted probe at the lower of its configured limit and
5 seconds, 32768 stdout bytes and 16384 stderr bytes, with no meaningful stdin.
There are at most 16 configured tools under the existing manifest contract.
Existing process-runner cleanup adds a bounded wait budget; artifact integrity
hashing has its existing per-file bounds and is not part of the child wall-clock
deadline. Checks run from runner-owned temporary directories, not the project.
No target build, installation, report/config/cache mutation or scan occurs.
Only the runner's owned temporary scratch directory is created/cleaned for an
authorized probe. Like existing native scans, arbitrary trusted programs could
still write outside their cwd: this is explicit code trust, not an OS sandbox.

On success, `version` and `engine_versions` are verified against the stored
expectations. `configured_version` is separately labeled trust metadata. Failed
hash/probe/protocol checks leave version null, availability false and engine
versions empty, with concrete guidance to restore reviewed artifacts, inspect
the bounded helper or correct its pinned protocol/version. No raw stdout/stderr,
manifest commands or environment values are echoed. The existing Redactor also
masks public metadata defensively; this is not universal secret detection.

Every known language stays explicit even when no tool is configured. A valid
manifest containing only one provider does not make omitted languages available.
The bundled native helpers do not currently supply a Python analyzer; that gap
remains unavailable rather than being invented by doctor. Setup cannot be assumed
to add a provider that does not exist.

Complete/exit 0 is possible only when the current Python runtime is supported,
**all six language provider checks** succeed and optional root/config/cache
checks have no errors. It means the declared provider
discovery scope completed, not that host PATH tool versions, scan rule coverage,
report/case-prompt backends or source quality passed. `reports` and `case_prompts`
remain false in this module; the separate CLI owner must describe future backend
integration accurately. Missing/partial/changed/unverified native providers always
yield incomplete/2. No tools are automatically installed to make that status green.

## Optional cache/config checks

`run_doctor(..., root=None, policy_path=None, cache_path=None)` uses the current
directory when root is absent, and inspects only its directory metadata. It never
searches for project YAML/JSON, native manifests or cache locations. With no
explicit policy, `resolve_policy()` produces fresh defaults in memory; no file is
read or created. No native configuration is enabled by policy/cache content.

Stable additive result fields:

- `data.config_checks`: status `default`, `valid` or `incomplete`, fixed reason and
  action, and `policy_schema_version` (`"1"` for valid/default, null on failure).
- `data.cache_checks`: status `not_requested`, `missing`, `present` or `incomplete`,
  fixed reason and action. Missing optional directories are informational and are
  never created. A present cache only establishes directory metadata/access hints;
  child contents, aggregate size and writability are deliberately not checked.

Explicit policy/cache paths may be relative to root or absolute **within** root;
outside-root paths and parent traversal are rejected. All original path components,
including the root's ancestors, are checked before resolving aliases. Symlinks,
junctions and other Windows reparse points are refused, even if they point back
inside root. Cache files/wrong types, inaccessible metadata or access denials are
incomplete; the directory is never enumerated, refreshed, cleared or locked.
`os.access` is only an access hint, not a Windows ACL or cache usability proof.

Legitimate Windows 8.3 short names are supported for the explicit root and
absolute policy/cache paths, including a short temporary-directory prefix such
as `RUNNER~1`. Containment is checked on canonical paths only **after** inspecting
every original component with metadata-only no-link/reparse checks. A lexical
short-name versus long-name mismatch is not an outside-root escape. File suffix
and access checks use the canonical name, so a real `.json` policy's `.JSO` short
alias is still recognized. Original file metadata remains the descriptor identity
reference; all containment/type checks precede content reads. This does not permit
traversal, outside-root files, or junctions pointing back inside the root.

An explicit policy must be a regular readable UTF-8 `.json` file, at most 1 MiB.
The reader uses a bounded descriptor read and regular-file/device/inode/size/mtime
identity checks before/after reading, `O_NOFOLLOW`/`O_NONBLOCK` where supported,
and a final component/path recheck. The file is never reopened for parsing.
Instead of `load_policy`'s unbounded pathname reader, doctor reuses that loader's
exact duplicate-key/non-finite JSON hooks and the public `resolve_policy` validator
on the bounded snapshot. JSON null/arrays, duplicate nested keys, unknown policy
fields/rules, unsupported severities, malformed JSON and non-finite values remain
invalid. No policy.py API/source is changed and no temporary policy file is made.
Nothing from the raw policy or its exception is included in the public result.

Invalid root/policy/cache checks add constant `DOCTOR_ROOT_UNAVAILABLE`,
`DOCTOR_POLICY_UNAVAILABLE` or `DOCTOR_CACHE_UNAVAILABLE` errors and force exit 2.
They also skip explicit native probes until corrected; valid optional configuration
cannot turn absent analyzers into available ones. Doctor's `scope` remains
`provider_discovery_only` for envelope compatibility; these additive checks are
metadata/explicit-JSON diagnostics, not target analysis or broader config execution.

The filesystem must be stable during diagnosis. Checks reduce accidental link
redirection and detect identity drift but are not a hostile concurrent same-user
filesystem sandbox, particularly where ancestor-handle/no-follow APIs are not
available on Windows. Cache child permission/size/integrity checks and remote
filesystem latency are outside this metadata-only scope. Doctor does not infer
them as passing or silently follow project execution configuration.

## Read-only verification

From the code checkout, `python -B -m unittest discover -s tests -p test_doctor.py -v`
checks the default no-process boundary with an executable-name shadow, missing
tools, actual trusted bounded protocol probes, partial and complete synthetic
coverage, whole-manifest validation before any probe, changed artifacts, reduced
process limits and unsupported Python. Test helpers/manifests live only in fresh
temporary fixtures. Byte snapshots confirm diagnostics preserve the fixture tree;
changed-artifact tests prove no execution or automatic pin update happens.

`python -B -m unittest discover -s tests -p test_doctor_config.py -v` checks default
in-memory policy/no autodiscovery, optional missing cache, no child enumeration,
valid policy byte preservation, duplicate/malformed/secret/oversized/nonregular
or unreadable inputs, outside/traversal/root failures, descriptor identity drift,
actual symlink/junction redirection refusal and suppression of native probes on
invalid configuration. Fixtures are disposable and byte/tree snapshots prove no
doctor-created directory, cache clearing, policy repair or content mutation.

Windows regressions call actual `GetShortPathNameW` rather than fabricate aliases.
They cover short/long root and absolute/relative input combinations, full file
aliases, a `-P -B` source-checkout CLI subprocess with trusted PYTHONPATH, missing
cache noncreation, and short-spelled outside/traversal/inside-pointing-junction
rejection before any content open. The normal absolute/relative path regression
runs on every OS; Windows-only cases explicitly skip where short-name support is
unavailable. A successful policy/cache check still cannot make absent native
providers available or turn diagnostics into a clean analysis result.

Use `python -B` or `PYTHONDONTWRITEBYTECODE=1` for strict cold source/package-tree
no-bytecode execution, as explained in [CLI.md](CLI.md). Doctor itself writes no
project files, installs nothing and has no target command runner. Test fixture
creation and build/install operations are separate from read-only diagnostics.

## Degraded/no-tool fixture matrix

Run `python -B -m unittest discover -s tests -p test_doctor_degraded.py -v` for eight
focused groups. The tests compose the existing doctor fixture owner and byte
snapshot helper, rather than duplicate provider implementation or inherit and
rerun another test class. All helper/manifest/project files are owned disposable
fixtures; no dependencies are installed and no target builds or hooks are run.

| Environment or failure | Evidence and required result |
| --- | --- |
| Empty, NUL-containing, overlong or excessive-entry PATH | Metadata-only checks remain explicit missing/unavailable; versions null, actions present; a process-launch tripwire must never fire |
| Actual CLI with empty or executable-shadow PATH and untrusted project config | One incomplete machine JSON record, no manifest autodiscovery or fixture byte changes; PATH presence cannot create trusted providers |
| Missing explicit manifest | Actual CLI native arguments return incomplete/2 without leaking the supplied private path |
| Missing pinned executable/helper artifact | No native process is started; unavailable reason, null verified version and repair action; no rebuilding or pin replacement |
| Wrong tool/engine version or malformed protocol JSON | Real explicitly trusted helper processes fail exact version/protocol validation; private output is not published |
| Nonzero exit, oversized stdout or wall timeout | Real explicitly trusted helper processes remain incomplete with no partial private output; no automatic retry/install |
| Ready Go fixture alongside a version-mismatched SQL fixture | Ready provider keeps its verified version, failed and omitted providers remain unavailable; explicit SQL dialect preserved; overall incomplete/2 |
| Unsupported Python introspection with otherwise verified native probes | Runtime failure still wins over ready provider checks; incomplete/2 and actionable runtime guidance |
| Invalid policy after a provider was actually proven ready | No further native execution; config error cannot be hidden by otherwise valid manifest/provider readiness |

The timeout helper has a 50ms caller-configured process deadline and the output
fixture exceeds the existing doctor stream cap; existing process-runner cleanup
budgets still apply. These tests execute trusted Python fixtures that speak the
native protocol, not real Go/.NET/TypeScript/SQL analyzers. A synthetic all-language
ready result is only a precondition for the invalid-config test, never a claim of
rule coverage or source quality. The unsupported-runtime case patches interpreter
introspection; it does not claim an actual Python 3.11 installation was tested.

CLI subprocesses use an explicitly isolated `-I -B` harness with the trusted code
checkout added to sys.path. This prevents fixture-directory startup behavior from
contaminating the test, not a claim that arbitrary normal Python startup hooks are
sandboxed by DevSift. Only already accepted default/native CLI arguments are used;
optional policy/cache flag integration belongs to the controller's CLI tests.
Before/after hashes ensure the fixture contents, untrusted configs and manifests
are preserved; temporary process scratch cleanup is owned by the accepted runner.
This matrix does not replace real native/parser/installed-CLI or cross-platform
acceptance runs, and does not itself mark a goal accepted or released.

## Installed CLI flags

Use `devsift doctor --policy /absolute/policy.json --cache-path /absolute/cache` for explicit config/cache diagnostics. Native probes use registered user trust or an explicit independently trusted pair. The installed CLI additionally advertises the integrated report-generation and case-prompt capabilities; these are not native-provider readiness or source-analysis results.
