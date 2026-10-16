# Fresh authoritative CI entry

`devsift ci` runs an actual read-only scan now; it never gates an arbitrary saved
JSON record, auto-loads target configuration, builds target projects, installs
dependencies or applies remediation. Setup is a separate trusted operation.

```text
devsift ci --all --base TRUSTED_BASE_REF --native-manifest ABSOLUTE_MANIFEST --native-manifest-digest TRUSTED_SHA256
devsift ci --paths src/module.py --security --base TRUSTED_BASE_REF --native-manifest ABSOLUTE_MANIFEST --native-manifest-digest TRUSTED_SHA256
```

The manifest/digest pair is required and explicitly authorizes its pinned native
programs. Every entry validates before any probe. A missing or changed configured
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

T043 tests use an explicit trusted Python AST fixture program launched through
the real process/native protocol, actual immutable Git histories and actual CLI
subprocesses. They prove new/legacy/unknown distinctions, thresholds, dirty clean
snapshot rejection, failure precedence, protected review flags and no source/Git
writes. This is CI coordination evidence, not a claim that this fixture ships as
a production language adapter. Native/report upload integration is separately
reviewed in T044/T045.
