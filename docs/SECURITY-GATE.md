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
