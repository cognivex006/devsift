# Real cross-language contract E2E

`test_e2e_backend.py` (T049) runs the public CLI through real trusted Roslyn and
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

## Frontend / SQL companion suite (T050)

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
skip is not native acceptance evidence. T051 release-wide composition remains a
separate gated task; these suites do not implement it.
