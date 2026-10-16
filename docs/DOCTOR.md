# Doctor provider discovery

`devsift.doctor.run_doctor` provides a read-only provider-discovery result.
The CLI calls it through `python -m devsift doctor`. Explicit trusted probes use
`--native-manifest <absolute-path>` and `--native-manifest-digest <trusted-sha256>`.
Cache/config diagnostics and the later degraded-environment matrix are separate tasks.

```python
from devsift.doctor import run_doctor

record = run_doctor()  # Metadata only; no external command is executed.

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

## Default discovery executes nothing

The running Python interpreter's version is read from `sys.version_info`; Python
3.12 or newer is required. Git, dotnet, Go, Node and npm are checked only through
bounded PATH **metadata** discovery. A found filename is `discovered_unverified`,
not a trusted/runnable installation, and its version is explicitly null. Missing
tools are `missing`; unavailable/excessive PATH metadata is `discovery_unavailable`.
Each record has a fixed explanation and actionable separate-setup guidance.
No `--version`, package manager, Git/project command, hook or executable from
PATH is run, even if the current project shadows its name.

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

Without both manifest arguments, all unconfigured providers remain unavailable
and the result is incomplete, exit 2. A missing partner, unreadable/relative path,
bad digest, malformed later tool or invalid SQL dialect also returns incomplete
with a static error and starts no native probe. No manifest is auto-discovered
from project configuration or ignored setup directories.

Supplying the pair explicitly authorizes the configured native programs, just
as described in [NATIVE-SETUP.md](NATIVE-SETUP.md). The entire bounded manifest
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

Complete/exit 0 is possible only when the current Python runtime is supported
and **all six language provider checks** succeed. It means the declared provider
discovery scope completed, not that host PATH tool versions, scan rule coverage,
report/case-prompt backends or source quality passed. `reports` and `case_prompts`
remain false in this module; the separate CLI owner must describe future backend
integration accurately. Missing/partial/changed/unverified native providers always
yield incomplete/2. No tools are automatically installed to make that status green.

## Read-only verification

From the code checkout, `python -B -m unittest discover -s tests -p test_doctor.py -v`
checks the default no-process boundary with an executable-name shadow, missing
tools, actual trusted bounded protocol probes, partial and complete synthetic
coverage, whole-manifest validation before any probe, changed artifacts, reduced
process limits and unsupported Python. Test helpers/manifests live only in fresh
temporary fixtures. Byte snapshots confirm diagnostics preserve the fixture tree;
changed-artifact tests prove no execution or automatic pin update happens.

Use `python -B` or `PYTHONDONTWRITEBYTECODE=1` for strict cold source/package-tree
no-bytecode execution, as explained in [CLI.md](CLI.md). Doctor itself writes no
project files, installs nothing and has no target command runner. Test fixture
creation and build/install operations are separate from read-only diagnostics.
