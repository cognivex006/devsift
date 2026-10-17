# Real cross-language contract E2E

`test_e2e_backend.py` runs the public CLI through real trusted Roslyn and
Go parsers, NativeAdapter, immutable source verification, scanner and policy.
Its synthetic committed consumer repositories exercise mixed findings, completed
clean parsers, actual grammar failure, and changed-scope stale whole snapshots.
No consumer project is built, dependencies installed, target source executed,
or baseline silently refreshed. Before/after SHA256 inventories cover all
consumer files and `.git` objects/index/config plus external fixture manifest
and baseline bytes. Fixture setup commits and explicit reviewed baseline writes
are separate from these read-only assertions.

Opt-in is deliberate. Without `DEVSIFT_TEST_NATIVE=1`, these integration tests
are labelled skipped. With it, absent/changed/unprobed tools fail the tests,
never silently skip or claim a native pass. Build only DevSift's own explicitly
trusted checkout with `tools/build_native.py` as documented in NATIVE-SETUP.md;
tests never invoke that builder or target-project commands.

In a worktree, explicitly select the existing reviewed setup artifacts. Example
from the authorized worktree, using the separately trusted primary setup:

```powershell
$env:DEVSIFT_TEST_NATIVE = '1'
$env:DEVSIFT_ROSLYN_ARTIFACT_DIR = 'D:/SP-Billy/devsift-dev/devsift/.devsift/local/tools/dotnet'
$env:DEVSIFT_GO_ARTIFACT = 'D:/SP-Billy/devsift-dev/devsift/.devsift/local/tools/go/devsift-go.exe'
python -B -m unittest discover -s tests -p test_e2e_backend.py -v
```

Runtime overrides `DEVSIFT_DOTNET_EXECUTABLE` and `DEVSIFT_NODE_EXECUTABLE` are
supported. Helper factories pin actual executable/artifact hashes during this
explicitly trusted test setup; every CLI invocation receives an absolute frozen
manifest and its exact SHA256. CLI scans neither discover tools nor re-pin them.
The trust decision is not authenticated merely by computing a digest, and these
process controls are not an OS/network sandbox.

The backend baseline test captures real verified source findings with the actual
baseline library, writes a synthetic reviewed snapshot explicitly, digest-loads
it, compares identities, and invokes real Git provenance and policy. Proven
unchanged legacy is advisory in that *explicit library composition*. Loading a
baseline does not wire provenance into today's CLI: source-verified native
findings remain `UNKNOWN`, `incomplete`, exit 2 and enforced_count 0. The tests
assert this limitation, rather than making a legacy-mode flag look like lifecycle
classification. Generic core rule detection is not invented; the real core path
here is evidence, Git, baseline, scanner and policy.

These are contract E2E tests, not comprehensive rule coverage or release-ready
security certification. All sources, reviewer identities, endpoints and Git
repositories are disposable synthetic fixtures, not consumer project edits.

## Frontend / SQL companion suite

`test_e2e_frontend_sql.py` is the separately committed companion scope. It uses
the same core/public-envelope assertions with real pinned ESLint/TypeScript and
ScriptDom, including both explicit `tsql150`/`tsql160`, verified UNKNOWN security
findings, redaction, dirty source proof, parser incompleteness and target-config
side-effect canaries. SQL is parsed as text only: no DB service, credentials,
connection driver, SQL client command or target build is required or invoked.
Read-only snapshots and unexecuted project/config canaries do not claim an OS
network sandbox against arbitrary trusted native programs.

```powershell
$env:DEVSIFT_TEST_NATIVE = '1'
$env:DEVSIFT_FRONTEND_PACKAGE = 'D:/SP-Billy/devsift-dev/devsift/native/frontend'
$env:DEVSIFT_SQL_ARTIFACT_DIR = 'D:/SP-Billy/devsift-dev/devsift/.devsift/local/tools/sql'
python -B -m unittest discover -s tests -p test_e2e_frontend_sql.py -v
```

After both scoped commits, retain all four absolute artifact overrides above to
run `python -B -m unittest discover -s tests -p test_e2e_*.py -v`. An opted-out
skip is not native acceptance evidence. The end-to-end suite's separate release-wide composition
is described below; the companion suites alone do not establish that gate.

## Full mixed repository gate

`test_e2e_full_gate.py` combines the accepted real providers in one committed
consumer fixture: Roslyn/C#, Go, TypeScript (including a known synthetic secret)
and ScriptDom/SQL. It reuses `e2e_support` repository/manifest/snapshot/setup
helpers, without replacing analyzers or manually fabricating source proof.
Opted-in unavailable providers fail instead of becoming skips. Frontend setup
source/lock files must match the selected checkout; every actual configured
provider must pass its exact pinned native protocol/version probe.

The suite also requires `DEVSIFT_TEST_SCHEMA=1`, accepted validation dependencies
and the exact pinned official offline SARIF schema. `DEVSIFT_SARIF_SCHEMA_PATH`
may explicitly select an existing reviewed schema cache outside the worktree;
bytes/length are checked against `tools.setup_validation` pins before validation.
No schema download, pip/npm installation or helper build runs inside these tests.
An empty or wrong schema cache and missing URI format validators fail setup.

Example on this Windows setup, after separately approved helper/validation setup:

```powershell
$env:PYTHONPATH = '/absolute/trusted-validation-python'
$env:DEVSIFT_TEST_NATIVE = '1'
$env:DEVSIFT_TEST_SCHEMA = '1'
$env:DEVSIFT_DOTNET_EXECUTABLE = 'C:/Program Files/dotnet/dotnet.exe'
$env:DEVSIFT_NODE_EXECUTABLE = 'C:/Program Files/nodejs/node.exe'
$env:DEVSIFT_ROSLYN_ARTIFACT_DIR = 'D:/SP-Billy/devsift-dev/devsift/.devsift/local/tools/dotnet'
$env:DEVSIFT_GO_ARTIFACT = 'D:/SP-Billy/devsift-dev/devsift/.devsift/local/tools/go/devsift-go.exe'
$env:DEVSIFT_SQL_ARTIFACT_DIR = 'D:/SP-Billy/devsift-dev/devsift/.devsift/local/tools/sql'
$env:DEVSIFT_FRONTEND_PACKAGE = 'D:/SP-Billy/devsift-dev/devsift/native/frontend'
$env:DEVSIFT_SARIF_SCHEMA_PATH = 'D:/SP-Billy/devsift-dev/devsift/.devsift/local/schemas/sarif-2.1.0.json'
python -B -m unittest discover -s tests -p test_e2e_full_gate.py -v
```

The validation directory above is an existing pinned flat package target from
`requirements-dev.txt`, not a virtualenv executable or a new dependency install.
Choose absolute reviewed artifacts for the actual machine; do not copy these
paths as proof that another host was tested. The source CLI subprocess harness
uses the Python source-test harness with safe-path and bytecode writes disabled, and explicit trusted checkout PYTHONPATH from
`e2e_support.environment`; installed consumer invocations use their separately
documented `-I -B` entry. This test does not modify the shared helper or CLI.

Three combined acceptance groups establish these distinct gates:

1. Actual mixed native CI CLI scans five files, classifies same-commit findings
   as legacy and keeps quality advisory/security-review semantics. Its protected
   security-review hold remains exit 2. JSON/Markdown/SARIF are produced together
   from source-reproved cases, JSON/SARIF validate against local schemas, SARIF
   full properties equal JSON cases, and invocation completeness/exit matches CI.
   Known secret bytes are masked in every format. The actual underlying scanner
   envelope is deliberately written as external disposable prompt-input setup;
   actual prompt CLI calls require a real operator binding, reject another case,
   and keep even an exact match review-required/manual-planning-only. All writes,
   execution and automatic fixes remain unauthorized. This checks the preceding
   CI hold, separate approval authority boundary and unchanged source snapshots;
   it does not perform a fresh CI scan after approval.
2. A completed clean four-language repository returns 0. After deliberate fixture
   setup adds and commits a new TypeScript path, its actual absent-at-base proof
   produces NEW/HC001/block and exit 1. All exports preserve the same gate and
   exact current source identity. No touched-file guess or fake baseline absence
   is used to promote findings.
3. An actual partial SQL parse keeps CI and every report incomplete/2 while other
   native findings remain visible; no SQL finding/location is invented. A
   deliberately wrong manifest trust pin also stays incomplete/2, emits no cases
   in any format and exposes no manifest path. Neither failure becomes green
   merely because an exporter can serialize its result.

Snapshots cover consumer source, Git objects/index/config and all fixture-parent
files before/after each read-only phase. Native manifest, actual scan-input and
operator approval JSON are created only as separately labeled disposable fixture
setup; tests never refresh them while scanning or mutate consumer source to pass.
No target build, dependency installation, database execution, source import,
report/cache write, remediation, remote upload or release runs. Native processes
are explicitly trusted code under the accepted runner, not an OS sandbox.

This is a local contract/release-gate acceptance test for configured rules and
artifacts, not comprehensive language analysis, automatic approval, a completed
GitHub Actions run or release authorization. A skipped opt-out, valid report
schema or matching manual-planning input alone is insufficient evidence. Goal
acceptance still requires independent review of the actual integrated source and
recorded native/schema test results; other host/platform runs remain unverified
until executed.
