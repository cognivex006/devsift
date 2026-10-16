# Source-linked report context (T041)

`devsift.report_context.enrich_report_context` returns a new sealed `Report`
consumable by the existing Markdown, full JSON and SARIF exporters. It never
modifies the input, source, Git index/refs or baseline, executes a target, or
discovers consumer projects. There are no exporter/schema/CLI changes here.

```python
from devsift.report_context import CandidateContext, enrich_report_context

# actual_report comes from assemble_report; candidate_source is actual
# SourceEvidence produced by verify_source against an explicit immutable commit.
candidate = CandidateContext(selected_case_id, "consumer", candidate_source)
enriched = enrich_report_context(
    actual_report, repo_root=repo_root, candidates=(candidate,),
)
```

`CandidateContext(case_id, role, source)` is frozen; role is `consumer` or `test`.
Input must contain an actual `SourceEvidence`, not serialized location assertions.
The supplied relationship is a **candidate, unproven relationship**. It is not
an observed call graph, dependency, runtime reachability, exercised test, passing
regression result or measured production impact.

## What is verified and what stays unknown

Primary source is reproved against the explicit Git root. Its existing whole
mask survives, including overlapping nonsecurity rules; an unreproducible custom
partial mask becomes unresolved rather than revealing hidden text. A primary
reproof failure drops current fingerprint/navigation, resets UNKNOWN/incomplete
and cannot lend proof to related candidates.

Each candidate must match the primary case's repository identity and immutable
SHA. Its exact relative path/region is reproved from that commit. Every candidate
BEFORE is **fully masked**, even when the generic secret detector would miss an
opaque value. Supplied symbols are discarded: physical position does not prove
a symbol. Candidate source fields are hidden in the input dataclass repr.
Relative locations and SHA/regions remain useful links; absolute local roots
are never emitted.

Unresolved candidates, mismatched SHA/repository or unavailable source remain
visible as SOURCE_UNRESOLVED placeholders with a lookup plan. No old claimed
path, snippet, symbol or URL is retained for such a placeholder. SARIF therefore
keeps it in the full case properties but emits no physical related location.

Context populates only existing schema fields:

- `related_locations`: verified fully masked SourceEvidence or visible unresolved
  SourceEvidence, not arbitrary source dictionaries.
- `affected_scope`: status remains `unknown`; consumer and test strings clearly
  label supplied/unproven relationships and no executed/passing-test evidence.
- `impact_if_unchanged` / `risk_if_changed`: unknown level and source-only context
  evidence. Positions do not measure frequency, exploitability, consumers,
  functional effects, contracts, deployment or regression results.

No contextual recommendation is appended at the report root; it stays empty so
the accepted three exporters remain compatible. Context fields are replaced
from the explicit candidate tuple on each call, not silently inferred from prior
rendered strings. A requested unresolved candidate makes the result incomplete.
Existing incomplete execution is never promoted to complete, even when later
provenance establishes some findings' origin. Actual enforced violations remain
counted; incomplete exit 2 retains precedence. Approval remains pending,
automatic_fix false and AFTER code absent.

## Optional real provenance and policy

With no new base/policy, existing sealed attribution is preserved after successful
primary reproof, including UNKNOWN and actual legacy security_review. Persisted
wire lifecycle claims still become UNKNOWN through the normal assembler unless
a trusted in-process caller explicitly supplies attribution. Context alone never
infers NEW from a touched file or baseline absence.

For fresh attribution pass an explicit base and one frozen
`CaseProvenance(case_id, rule_version, observation=None)` per report case:

```python
from devsift.report_context import CaseProvenance

enriched = enrich_report_context(
    actual_report, repo_root=repo_root, candidates=(candidate,),
    base_ref=immutable_base_sha,
    provenance=(CaseProvenance(selected_case_id, "1"),),
)
```

This routes through accepted `report_decisions.assess_finding`, actual immutable
Git classification and configured policy. Proven preexisting findings remain
recommendations/advisory, introduced findings use introduced policy, unresolved
origin stays incomplete and critical security review remains independent. It
does not force legacy remediation or claim low business risk.

Optional `snapshot` must be an explicitly trusted `BaselineSnapshot`, normally
loaded with an independently supplied digest, with matching `tool_version` and
`rule_catalog_version`. Explicit rule versions are always required with a base.
Optional typed `BaselineObservation` is caller-supplied baseline analysis input,
not a claim that this context library ran an analyzer. Changed-region rule
absence requires that explicit complete analysis; an empty baseline snapshot is
not absence evidence. Incorrect versions/provenance fail closed. No source/DB
mutation or baseline refresh occurs.

## Input and scope boundaries

Reports/cases must be actual sealed in-process objects; saved JSON and duck-typed
objects are rejected. Candidate/provenance collections are tuples with typed,
frozen entries; case IDs must exist and provenance IDs must be unique and cover
all cases when a base is supplied. Candidate limits are 256 total and 32 per
case. Encoded cases/report are bounded to four million characters. Every failure
uses `ContextError("Invalid or unavailable report context")` without printing
private paths, source or supplied metadata.

Internal reconstruction uses the trusted package report seal; it is not an
authentication boundary against hostile Python code in the same process. A
source position says nothing about the current working tree or runtime callers.
Candidate source comments/strings are never interpreted as instructions; their
display is entirely withheld. Metrics and verified relationships require separate
measured evidence/feature work; this API supplies neither.

## Verification

```powershell
python -B -m unittest discover -s tests -p test_report_context.py -v
```

The schema integration case additionally requires `DEVSIFT_TEST_SCHEMA=1`, the
explicitly trusted validation libraries on PYTHONPATH, and the accepted official
SARIF bytes in the ignored local schema cache. Those bytes are checked against
the pinned length/SHA256; the tests never download/install them. It validates the
unchanged report/evidence schemas and official SARIF schema plus actual Markdown
rendering. Temporary real Git cases cover candidate proof/unknowns/masks, mixed
legacy/new policy, baseline metadata, changed-region absence, immutable outputs
and complete source/.git before/after equality. These are library/export tests,
not runtime impact measurement, call-graph analysis or regression execution.
