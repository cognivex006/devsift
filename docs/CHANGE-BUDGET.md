# Change-budget planning

`devsift.change_budget` compares declared change estimates with explicit operator
limits. It performs no filesystem, Git, configuration, process or source writes;
it does not execute a proposal. No decision grants editing or execution authority.
Scan findings, report severity, urgent security review and budget labels cannot
replace explicit case authorization, source proof, tests and independent review.

```python
from devsift.change_budget import BudgetLimits, ChangeEstimate, ChangePlan, assess_plan

plan = ChangePlan(("case-1",), "MODIFIED_PREEXISTING", ChangeEstimate(1, 8, 3),
                  refactor=False, risk_if_changed="moderate", consumer_impact="bounded")
decision = assess_plan(plan, BudgetLimits(max_files=1, max_added_lines=10,
                                         max_removed_lines=5))
assert decision.status == "bounded_plan_review"
assert decision.legacy_advisory
assert not decision.write_authorized
assert not decision.execution_authorized
assert decision.verification_pending
```

All lifecycle, risk and consumer-impact labels are **caller declarations**. They
do not establish Git provenance, prove consumers are unaffected, or override the
actual quality gate. In particular, `legacy_advisory` describes planning treatment
only: known preexisting/unchanged legacy stays a recommendation, while independent
verified Critical security escalation remains intact. No blanket legacy cleanup
or mandatory timing instrumentation follows from a planning result.

Limits have no numeric defaults. Each missing limit or count, unknown lifecycle,
unknown change risk, or unknown consumer impact produces `incomplete`; unknown is
never interpreted as low risk, unlimited budget, or a passing plan. Equality with
an explicitly chosen limit is within that declared limit; exceeding any limit
requires separate approval. Refactoring, multiple case IDs, high declared change
risk and broad consumer impact also require separate explicit approval. If unknowns
coexist with these conditions, status stays `incomplete` and
`separate_approval_required` remains true. The requirement is unfulfilled: this
module accepts no approval flag, token or waiver. Every result still requires
actual case authorization and verification. `bounded_plan_review` means only that
the declared estimate fits those declared limits and needs review.

`ChangeEstimate` is always a declared estimate, even when its values happen to
match a real diff. `counts_basis` is always `declared_estimate`, and
`verification_pending` is always true. Actual immutable-source counts, before/after
diagnostics, behavior comparisons, regression results and rollback evidence remain
separate verification work. This module neither measures them nor invents them;
it does not import or implement case-approval workflows.

Inputs are frozen models with immutable nested estimates and copied case-ID tuples.
`ChangePlan.from_dict`, `BudgetLimits.from_dict` and `ChangeEstimate.from_dict`
require exactly their documented keys. `ChangePlan.to_dict()` includes schema
version `"1"`; `load_plan(text)` accepts JSON text, never a path, and rejects
duplicates at every nesting level, unknown fields, non-finite numbers and invalid
versions. Outputs are fresh dictionaries/lists. Counts and limits require exact
integers in `[0, 2**63)` or `None`; booleans are invalid counts. These bounds are
representation limits, not policy thresholds. JSON input is limited to 65,536
code points, and plans to 1,000 unique case IDs of 1–128 ASCII identifier characters.
IDs altered by the existing bounded Redactor are rejected, and IDs are hidden
from model repr. This is not comprehensive secret detection. Failure messages are
fixed and contain no supplied keys, IDs, source, values or exception details.

Regression tests exercise all five declared lifecycles, missing measurements and
limits, large/refactor/batch plans, strict JSON and constructor types, immutable
fresh outputs, private errors, and an actual temporary Git repository whose source
and Git files remain byte-identical. A verified legacy Critical security decision
is checked independently before and after budget assessment.
