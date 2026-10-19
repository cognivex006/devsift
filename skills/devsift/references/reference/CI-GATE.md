# Fresh authoritative CI entry

`devsift ci` runs an actual read-only scan now; it never gates an arbitrary saved
JSON record, auto-loads target configuration, builds target projects, installs
dependencies or applies remediation. Setup is a separate trusted operation.

DevSift 0.1.16 adds CLI user-registration and report language. After authorized
installation or one-time `devsift setup`, CI uses that user-level manifest/digest
without requiring native flags again. No project manifest is discovered. Check
installed help when using releases through 0.1.15, which still require the pair.

The CLI starting in 0.1.15 uses the same resumable disk-backed execution and complete
paged reports as [complete scans](../COMPLETE-SCANS.md), including `--summary`,
`--report-dir` and `--resume`. Every resume rechecks current pinned-provider
readiness before reusing byte-identical completed source. Report completeness
does not override source attribution, security review or an incomplete gate.

```text
devsift ci --all --base TRUSTED_BASE_REF --summary --report-language th
devsift ci --paths src/module.py --security --base TRUSTED_BASE_REF --summary --report-language en
```

User registration supplies the trusted native pair by default; explicit paired
flags override it for that invocation and validate before execution.
An invalid explicit pair is rejected, never silently replaced with other trust.
Every entry validates before any probe. A missing or changed configured
tool keeps CI incomplete even if no selected file uses that language. `--security`
opts into the bounded built-in credential detector and composes it with native
providers; otherwise unregistered languages are not silently analyzed. Coverage
means the documented configured rules, not comprehensive language quality.

`--all`, `--changed` (default) and `--paths` are mutually exclusive. Paths are exact
repository-relative file paths, not directory expansion; the resulting scope is
explicit in output. Changed CI scope requires `--base` and unions the immutable
merge-base-to-HEAD committed delta with existing filter-free staged, unstaged and
untracked Git selection. A missing/ambiguous base cannot turn an empty worktree
diff into a successful PR scan. The ordinary `scan --changed` command retains its
working-tree selection semantics. Every actual analyzed snapshot must match immutable HEAD,
including clean snapshots: dirty or untracked clean text cannot hide a finding
in committed source. Unresolved, parse-failed or unavailable work remains 2.

`--base` resolves a real immutable base for the accepted Git source classifier.
Classification happens on actual findings before policy/scan completeness is
computed. Proven absent new paths can be NEW; exact old regions retain legacy or
preexisting origin. Changed-region introduction without complete same-rule
baseline absence remains UNKNOWN. A touched file never becomes wholly NEW.
Without a base, findings remain UNKNOWN and incomplete. Empty/no-finding analyzed
snapshots may complete; this never establishes comprehensive semantic coverage.

`--minimum-severity Error` (default) blocks verified introduced Critical/Error.
`Critical` blocks only introduced Critical quality findings. These are the existing
policy's supported thresholds; Warning/Suggestion are not silently promoted to
blocking rules. Verified legacy security flags remain independently escalated;
the public CI entry returns 2 with SECURITY_REVIEW_REQUIRED when quality analysis
would otherwise return 0 but independent security review is still required.
There is no public waiver for that review: GateConfig rejects a false
require_security_review value too. Invalid arguments return 3 safely.

The library API is `run_ci(root, native_manifest=..., native_manifest_digest=...,
base_ref=None, all_scope=False, paths=None, security=False, config=GateConfig())`.
It returns a frozen `CiRun` whose `scan_record()` and `to_dict()` return fresh
trees. The former is the actual scanner envelope; the latter is the CI envelope
with command `ci`, explicit threshold/scope and security-review status. A scan
failure cannot be turned into success by a gate threshold. Known failures never
echo manifest values, ref arguments, source, tool stderr or credentials.

The CI gate tests use an explicit trusted Python AST fixture program launched through
the real process/native protocol, actual immutable Git histories and actual CLI
subprocesses. They prove new/legacy/unknown distinctions, thresholds, dirty clean
snapshot rejection, failure precedence, protected review flags and no source/Git
writes. This is CI coordination evidence, not a claim that this fixture ships as
a production language adapter. Native/report upload integration is separately
reviewed in the CI gate.

## Workflow integration entrypoint

`python tools/run_quality_ci.py --output ABSOLUTE_OUTSIDE_DIRECTORY` uses this
trusted kit as the default Git source root. `--repo` explicitly selects another
Git root for integration testing without importing its package or executing its
source. The fixed kit `.devsift/local/native-manifest.json` and `.sha256` must
already exist from explicit setup. This entrypoint never installs or builds.

Scope is exactly tracked top-level production `devsift/*.py` files, selected from
Git and filtered without wildcard shell expansion. Test/helper/nested/untracked
files are not implied coverage. The Python security rulepack is enabled and all
configured native probes must succeed; this does not claim whole-repository or
every-native-language rule coverage. The trusted runtime/package is imported from
the kit location, never from the optional target checkout.

`--base` overrides DEVSIFT_BASE_SHA; either must be a full nonzero 40-hex commit.
Without a base, findings retain UNKNOWN and incomplete rather than becoming NEW.
Actual CI exits 1/2 remain failed, and report reproof incompleteness takes priority.
Independent security-review incompleteness is also reflected in generated reports,
not hidden behind a scan that completed without blocking quality violations.

The wrapper assembles source-reproved complete Markdown/JSON/SARIF and explicitly
writes only `report.md`, `findings.json`, `results.sarif` outside the source tree.
Existing report files are never overwritten. Invalid arguments/output locations
return static 3; unavailable setup/source/report work returns static incomplete 2.
Only accepted safe annotations and a scope-count notice reach stdout; no source,
credentials, raw subprocess errors or target command execution is printed.

`test_quality_pipeline.py` copies a controlled kit, supplies a real trusted Python
AST helper through its fixed cache, and invokes the actual wrapper subprocess
against immutable temporary Git histories. It verifies clean/error/UNKNOWN and
legacy-security review exits, all three artifacts, whole credential masks,
source/Git preservation, no target-package execution and output collision safety.
The helper fixture is not a production native Python adapter claim. Actual
GitHub Actions/artifact/service results require the integrated workflow run.
