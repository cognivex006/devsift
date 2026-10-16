# Verification evidence preflight

`devsift.verification_plan` measures immutable Git revisions and compares bounded
external diagnostic, regression and rollback records. It is an evidence preflight,
not a remediation engine or verified test runner. Every comparison returns
`status="incomplete"`, `verification_pending=True`, and both
`write_authorized=False` and `execution_authorized=False`. Explicit case approval,
trusted diagnostic/test capture and independent review remain separate. No record
executes consumer commands, test hooks, configuration, builds or rollback actions.

## Actual Git measurements

`verify_revision_pair(repo_root, before_sha, after_sha, expected_paths)` requires
lowercase full 40/64-character commit identities, a canonical repository root and
the exact complete set of changed repository-relative paths. It compares the two
commits directly; it does not infer a merge base, ancestry or case validity.
Hidden changed paths reject the measurement. Working-tree edits are ignored.

The factory returns a frozen `GitMeasurement` with commit identities, changed
paths, file/addition/deletion counts and `scope_digest`. Counts use Git LF numstat
with rename detection disabled: a renamed file is conservatively counted as
deletion/addition across two paths. Counts describe the whole proposed revision
pair, not an analyzer's assertion or a declared estimate. The digest binds the
pair and complete measured scope; it is not authentication. The private canonical
root binds the local proof. JSON output cannot be loaded as a verified object.

`compare_verification(..., repo_root=...)` requires the intended root, rejects a
measurement from another root and remeasures the same immutable pair before use.
Missing objects or newly unsafe repository configuration invalidate prior proof.
Moving HEAD alone does not invalidate immutable commits; the working tree is never
claimed to match either commit. Counts replace estimate uncertainty for budget
assessment only. The surrounding comparison says `counts_basis="verified_git_diff"`;
the nested T061 budget model keeps its original declared-input vocabulary. Risk,
consumer-impact and lifecycle labels remain caller declarations, even with actual
counts. Unknown labels still produce an incomplete budget, and large/refactor
plans still require unfulfilled separate approval.

Reads reuse the existing filter-free Git primitives. Effective included config
is checked for partial/promisor clones before object reads; shallow histories are
rejected. Lazy fetch, replacement objects, optional locks and fsmonitor are
disabled. Diff uses `--no-ext-diff --no-textconv --no-renames`; no hooks, target
builds, filters, network or source/index writes are invoked. Only regular UTF-8
text changes are supported. A regular-file executable-bit-only change counts as
one changed file and zero added/removed text lines. Its mode and behavior effects
remain unverified; comparison stays incomplete and grants no editing authority.
Binary/NUL, symlink/submodule changes or unavailable proof fail closed with a
fixed `VerificationError`.
At most 256 changed paths, 1,000 tree entries per revision and 2 MB aggregate
changed before/after blob content are supported. These are resource bounds, not
operator change-budget thresholds. Paths reject traversal, controls, absolute
forms and credential shapes recognized by the existing bounded Redactor.

## Declared evidence records

`DiagnosticRecord(case_id, source_sha, scope_digest, analyzer_id, analyzer_version,
complete, findings)` stores unique `(catalog_rule_id, sha256_fingerprint)` pairs.
`complete` explicitly describes the external declaration, not a trusted analyzer
execution. Before/after records must use identical analyzer identity/version and
bind the correct respective commits. Only when both declarations are complete
does comparison return sorted added, removed and persisting declared pairs.
Matching fingerprint strings do not prove source-region identity, a semantic fix,
consumer compatibility or business behavior. Incomplete records produce no delta.

`RegressionRecord(case_id, before_sha, after_sha, scope_digest, status)` accepts
`pass`, `fail` or `unknown`; all are external declarations. A declared pass never
becomes proof of a test run. `RollbackRecord(case_id, before_sha, after_sha,
scope_digest, action)` accepts only `restore_before_commit`, a proposed restoration
target for the measured scope. It is never a command, whole-repository reset,
approval, tested rollback or permission to execute anything.

`compare_verification(plan, limits, measurement, before, after, regression,
rollback, *, repo_root)` currently supports one declared case per plan. Each
present record must match that case, revision pair and scope. Mismatches reject;
missing records preserve incomplete status with fixed reasons. Before/after
analysis, regression and rollback records are mandatory evidence categories.
External-only evidence always retains `independent_diagnostic_capture_required`
and `independent_regression_capture_required`, even when every record claims
success. No availability or completeness flag is accepted as source/test proof.
No trusted executable capture factory is implemented here.

`load_record(text)` strictly decodes up to 262,144 JSON code points, rejects
duplicate/unknown keys, invalid version/types/nonfinite values, and never accepts
a filename. Schemas are exactly the frozen record fields plus `schema_version`
(`"1"`) and `kind` (`diagnostic`, `regression`, `rollback`). Diagnostic lists are
limited to 1,000 unique findings. Identifiers are bounded and reject recognized
credential shapes; case IDs are hidden from repr. Errors never echo values,
paths, snippets, private IDs, Git stderr or parse details. `to_dict()` returns
fresh lists and dictionaries; fixed protocol fields are never value-masked.

Tests construct real temporary Git histories, measure actual changed text, prove
dirty source/Git bytes stay unchanged, and reject mismatched identities, hidden
scope, foreign/stale root proof, binary/symlink paths and forged JSON proof flags.
Legacy Critical security escalation is checked independently and remains urgent
security review; planning advisory never changes enforcement or grants edits.

## Unauthorized-remediation acceptance fixtures

`tests/test_remediation_denial.py` uses the external records and planning cases in
`tests/fixtures/remediation/` against real temporary Git histories. The source
proposal deliberately changes a returned price from 10 to 999: measured counts,
an external passing regression record and a declared removed diagnostic still
cannot prove preserved consumer behavior or grant editing authority. Fingerprint
deltas remain declared; no consumer code is executed to manufacture test proof.

The acceptance matrix covers missing before/after/regression/rollback records,
incomplete diagnostic analysis, substituted case/root/revision/scope identities,
forged serialized proof, approval/command fields, unknown risk/consumers, batch
and refactor plans, absent/zero operator budgets, and independent legacy Critical
security review. Every returned verification comparison stays incomplete with
write and execution authority false; invalid identities and hostile schemas reject.

An actual isolated source CLI (`python -I -B` with the explicitly selected trusted
package root) scans the temporary project read-only and exercises review/implement
prompt parsing. Missing or mismatched `--approved-case` is misuse; a matching
case without explicit `--scan-input` still returns `CAPABILITY_UNAVAILABLE`. This
fixture tests the no-input boundary. The separately implemented case workflow
requires explicit scan evidence and reproof; see [case prompts](CASE-PROMPTS.md).
A matching selector alone never constitutes case authorization. SHA256 snapshots
cover every project/Git file and the selected tool's tracked files before and
after invocation. A target package-name shadow and checkout-hook marker remain
unexecuted. These checks establish observed read-only behavior for the tested
commands, not a sandbox or comprehensive non-execution guarantee for arbitrary
trusted adapters.
