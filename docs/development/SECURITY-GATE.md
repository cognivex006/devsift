# Fresh bounded security escalation

`devsift.security_gate.run_security_gate(repo_root, *, paths=None, policy=None,
tools=(), config_paths=(), redactor=None)` runs the accepted security detectors
afresh. It accepts no saved report, JSON result, baseline, waiver, threshold,
approval flag or prior gate result as authority. It neither edits source nor
rotates credentials, publishes reports, patches configurations or executes fixes.

```python
from devsift.security_gate import run_security_gate

gate = run_security_gate("/explicit/repository", paths=("src/settings.py",))
if gate.requires_security_review:
    # Independent review remains necessary even when another target is incomplete.
    pass
assert not gate.write_authorized
assert not gate.execution_authorized
```

Scope must be an explicit nonempty tuple of at most 256 canonical relative paths.
Omitted scope returns incomplete `SCOPE_REQUIRED`; it never implies a repository
was analyzed. Aggregate captured source is limited to 2,000,000 bytes, with the
same limit per file. Missing, unsupported, excluded, unsafe, binary, over-limit,
untracked or unresolved selected source cannot produce a complete gate. These
resource limits are not severity thresholds or an approval budget.

The root must be a Git root with readable HEAD and complete, non-promisor history.
Effective included/global/worktree/environment configuration is checked before
object reads. Host Git is selected through the accepted `git_runtime` guard,
outside the consumer repository; project Git lookalikes and relative PATH entries
are not executed. Reads disable lazy fetch, replacements, optional locks and
fsmonitor. No diff, textconv, conversion filters, target build, install or network
command is invoked. Every selected raw snapshot, including one without findings,
must hash to its regular-file HEAD blob. CRLF/filter-normalized working bytes
that differ from the committed blob remain incomplete even if Git status reports
no changes; this module never invokes a converter to make them match.

Accepted `SecurityAdapter` instances run through the accepted scanner. An internal
binding checks that each actual detector receives the initially captured bytes;
scanner independently rechecks snapshots and finding source proof. HEAD, complete
selected snapshots and raw blob identities are checked again at completion.
Findings are rehydrated/reverified from immutable Git source. This is a captured
observation, not a watcher or guarantee against later repository changes.

Security review is independent of quality lifecycle enforcement. Only catalog
`Rule.security=True` findings can require security review. Their canonical
Critical floor cannot be downgraded by policy; configured Critical severity can
also escalate a catalog security rule. Raising an ordinary quality rule such as
LOG001 to Critical does not invent a security finding. An actual detector
observation with verified source and Critical security status sets
`requires_security_review=True`, including a finding that has existed unchanged
for years. File age is not used as provenance: lifecycle remains `UNKNOWN` and
`quality_enforcement` remains the scanner's original value.

UNKNOWN quality attribution alone does not invalidate completed security detector
execution when every observation has verified source and all adapters completed.
The gate may then have `status="security_review"`; it never turns UNKNOWN quality
findings into NEW, legacy, clean or quality-blocking findings. Public
`quality_gate_complete` is always false. Failed adapters, incomplete detectors,
unresolved findings or changing source keep `status="incomplete"`. Independently
proved Critical observations remain visible through `requires_security_review`
even alongside incomplete work. Quality rules, policy and baseline behavior are
not changed by this module.

A complete result with no such observation says only
`no_detected_critical_in_declared_scope`. Built-in version 1.1.0 covers the accepted
narrow credential literal shapes in C#, Go, JavaScript, Python, SQL and TypeScript,
plus accepted Python AST SEC001/SEC002 contexts. It is not comprehensive secret,
PII, taint, TLS or vulnerability analysis. Credential liveness, exploitability and
business impact always remain `unknown`. Source verification proves location and
bytes, not a live credential, exploitable defect or business severity.

Optional `tools` must be explicit accepted `ToolDefinition` objects with pinned
executable/artifact hashes and disjoint languages. They invoke the existing real
`NativeAdapter` probe/analyze protocol and are composed with built-in credential
checks; remaining languages use the built-in profile. No PATH discovery, download,
build or installation of native analyzers occurs. A missing/failed/mismatched tool
keeps execution incomplete; it cannot hide an independently verified built-in
Critical observation. This configuration explicitly trusts native code execution
under the existing process contract, never consumer remediation. The gate tests
exercise the unavailable-provider boundary; they do not simulate successful native
analysis or claim a new native conformance run.

`config_paths` is an explicit subset of selected paths used only for accepted
CFG003 labeling. Secret-bearing excerpts stay fully masked. Optional `Redactor`
values also withhold public case/path/tool references while fixed enum/protocol
fields stay intact. Masked navigation references cannot be treated as a replayable
source-proof wire record. A path explicitly withheld by the redactor remains
unresolved under the accepted evidence contract; the gate cannot assert verified
escalation for it and stays incomplete pending private source inspection.
Outputs contain fixed private error codes, catalog
severity metadata and fresh masked source evidence, never native stderr, raw
exception text or source-bearing error messages. This is bounded redaction, not
comprehensive secret detection or an OS sandbox.

`SecurityGateResult` is frozen and factory-produced, and `to_dict()` returns a
fresh independent structure. Write, execution, rotation and publication authority
are always false. CLI integration and packaging are separate controller work;
this library imports no case-approval, CI-gate or report-model workflow.

Every explicitly configured provider must pass its probe, including providers
whose languages have no selected target. An unavailable provider keeps the result
incomplete while independent verified Critical observations remain visible.


## Independent cross-boundary acceptance

`tests/test_security_acceptance.py` exercises the actual `run_security_gate`
producer independently of its author. It uses real temporary Git repositories,
raw committed source and the built-in SecurityAdapter/scanner/evidence path;
there are no detector mocks or successful native-provider simulations. Source
snippets deliberately contain a marker-creating statement but are parsed as
data, never imported/executed. The missing provider has a trusted external test
helper and a deliberately absent required pin, so it cannot execute.

| Actual fixture | Observable outcome |
| --- | --- |
| Local policy JSON discovered through accepted project-policy API disables quality blocks and resolves HC002 as Suggestion | Real Git-backed credential source still has catalog Critical and requires security_review; its separate quality report remains UNKNOWN/incomplete |
| Explicit unavailable Go provider while only Python is selected | CONFIGURED_PROVIDER_UNAVAILABLE and incomplete, with the independent verified Critical observation retained |
| Missing selected file or changed uncommitted companion source | SNAPSHOT_UNVERIFIED and incomplete; another verified Critical finding cannot disappear |
| Saved old complete result modified with approved/waiver/publication/write claims, followed by a real new source commit | Fresh gate binds the new SHA and detects Critical; saved JSON remains data, unsupported saved-report argument and direct result fabrication are rejected |
| Invalid approval/waiver policy keys | Fixed SECURITY_GATE_UNAVAILABLE_OR_INVALID, no completed gate or authority |
| Complete security observation over an explicitly safe selected file, plus separate archive checks | Clean supported archive gives only scoped known-shape completion; substituted digest fails and credential-bearing source archive requires review, independently of the selected source gate |

The local policy bridge is an explicit test caller: `discover_policy(...).policy()`
is supplied to the gate only after successful resolution. This does not claim
the security-gate API automatically discovers project configuration or consumes
saved reports. Its explicit accepted API remains unchanged.

Every gate observation retains quality_gate_complete=false, UNKNOWN lifecycle
where findings exist, unknown liveness/exploitability/business impact, masked
credential source and false write/execution/rotation/publication authority.
A completed security inspection with requires_security_review=true is not a
successful release gate. A captured old result is not a watcher or reusable
permission after the source changes. Provider/source/config incompleteness
cannot be cured by mutating a report or declaring approval.

Archive fixtures use actual ZIP bytes and separately supplied expected SHA256;
they do not consume the packaging/bundler implementation or assert that an
actual release archive was produced. The packaging allowlist allows source files whose
contents still need confidentiality review. The archive checker only inspects
recognized shapes in supported bounded ZIP text and always retains
release_review_required=true and false publication/write/execution flags.
It computes no release eligibility, authenticity, credential liveness or license
approval. At most a completed scoped inspection is input to a separately
authorized review; it never authorizes artifact publication. An ordinary quality
policy/result does not override a digest failure or secret-review requirement.

Run the focused acceptance suite:

```text
python -B -m unittest discover -s tests -p test_security_acceptance.py -v
```

The tests compare full consumer source/file/directory and .git hashes around
actual gate/report/archive calls, including persisted fake report/config data,
and assert that neither source nor provider marker appears. Known synthetic
credential values and absolute fixture roots must not occur in public gate or
artifact results. These checks establish the stated fixture observations and
no-write boundaries; they are not LLM/host obedience, universal OS isolation,
whole-repository coverage, a new native conformance run or live release proof.
No production API, CLI, consumer remediation or publisher is added by the security gate.
