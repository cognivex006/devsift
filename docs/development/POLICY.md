# Policy v1 producer contract

`devsift.policy` supplies a local, standard-library-only policy library for Python
3.12+. This is policy metadata and enforcement evaluation, not a scanner or Git
classifier. The CLI does not consume this policy yet. No source, configuration,
baseline, report or other file is written by these functions.

`policy/schema.json` is the normative JSON Schema for each partial input layer;
`policy/defaults.json` records the complete defaults. The runtime enforces the
same structure without a JSON Schema dependency. `resolve_policy(repo=None,
overlay=None)` validates every supplied layer before recursively merging
defaults, repository policy, then an explicit caller overlay. Objects merge,
arrays replace, inputs are preserved and results do not share mutable defaults.
An omitted field inherits its prior value; `{}` is valid. `None` means absent at
this Python API boundary only. `load_policy(path, overlay=None)` reads one explicit
UTF-8 JSON file without discovery. JSON null, duplicate keys, non-finite constants,
invalid types, unsupported versions/severities and unknown keys at every depth
raise `PolicyError`. Callers must report configuration failure, never a clean scan.

The only v1 keys are `schema_version` (string `"1"`), `legacy_mode` (only
`"recommend"`), `quality_gate.block_on` (unique Critical/Error array, default both),
and `rules.<registered ID>.severity`. An empty `block_on` disables introduced
finding blocking, but cannot disable independent security escalation. Lowercase
historical `advisory` is not a valid v1 severity. Suppressions, baselines, excludes,
analyzer settings and arbitrary rule disabling are outside this schema and must
be added through a reviewed versioned contract.

```python
from devsift.policy import resolve_policy, decide

policy = resolve_policy(
    {"rules": {"HC001": {"severity": "Warning"}}},
    {"quality_gate": {"block_on": ["Critical"]}},
)
decision = decide("HC001", "NEW", source_verified=True, policy=policy)
assert decision.enforcement == "advisory"
```

`devsift.registry.RULES` is an immutable ordered registry of the 23 historical
IDs in [historical rule specification](https://github.com/cognivex006/devsift-specs/blob/main/reference/v4/SPEC.md); it retains their default severity and security
classification. Historical COM003/ARC002 `advisory` becomes `Suggestion` under the
v6 Critical/Error/Warning/Suggestion vocabulary. Rule presence means policy
metadata exists; it does not mean detection is implemented. Applicability and
exceptions remain in the reference catalog pending analyzer implementation.
No external registry files are required at runtime or in installed packages.

`decide(rule_id, lifecycle_class, *, source_verified, policy=None)` accepts only
upstream-proven inputs. `source_verified` must be an actual boolean, whose truth
means immutable source evidence was verified by the caller. This library cannot
establish that fact. It returns a frozen `Decision` with rule ID, effective
severity, lifecycle, enforcement and a separate `security_escalation` flag.

| Supplied lifecycle/evidence | Enforcement |
| --- | --- |
| UNKNOWN, or any unverified source | `incomplete` |
| Verified NEW/MODIFIED_INTRODUCED with configured blocking severity | `block` |
| Other verified NEW/MODIFIED_INTRODUCED | `advisory` |
| Verified MODIFIED_PREEXISTING/LEGACY_UNCHANGED | `advisory` |
| Verified preexisting/legacy critical security issue | `security_review` |

Unknown lifecycle strings, ambiguous `MODIFIED` and unknown rule IDs are errors.
UNKNOWN never becomes NEW or a passing finding. Independently verified critical
security evidence also sets the escalation flag for UNKNOWN, preserving incomplete
provenance. For security rules, catalog Critical is an escalation floor even when
an override lowers effective severity. Escalation is independent review, not an
automatic quality block on legacy and never remediation authorization.

`gate_result(decisions)` summarizes finding enforcement with precedence `block`,
`incomplete`, `security_review`, `pass`. Advisory findings and an empty iterable
return `pass` **only for this finding summary**. Callers must preserve individual
escalation flags and independently account for analyzer failures, unavailable
tools and scan coverage; an empty finding list is not evidence of a successful
scan. This helper does not choose process exit codes or approve source changes.

Producer checks: `python -m unittest discover -s tests -p test_policy.py`.
Independent invariant fixtures verify the policy model separately from producer checks. Rollback is a revert of the scoped producer commit; no consumer
files, schema migrations or runtime data are modified.
