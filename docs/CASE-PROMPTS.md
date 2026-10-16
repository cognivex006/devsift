# Per-case prompt composer (T046)

`devsift.case_prompts.compose_case_prompt(report, case_id, *, mode, repo_root)`
composes a prompt snapshot for one exact case. It accepts only an actual
in-process `Report`/`ReportCase` produced by `assemble_report`, not a serialized
report/case dictionary, imported prompt text or duck-typed object. Assembly and
composition reprove source against an explicitly supplied local Git repository.
They do not authenticate an arbitrary caller controlling the Python process.

```python
from devsift.case_prompts import compose_case_prompt

# report is the actual immutable assemble_report(...) result.
prompt = compose_case_prompt(report, selected_case_id, mode="review", repo_root=repo_root)
json_payload = prompt.to_dict()
prompt_identity = prompt.digest
```

The returned `CasePrompt` is frozen. `to_dict()` returns a fresh JSON-ready tree;
modifying that tree cannot alter the prompt or the original report. `digest`
identifies its canonical JSON bytes for a future case-specific approval binding;
it is not approval, authentication or a source-write grant. Constructor bypass
or hostile Python/plugin code in the same process is outside this boundary.

## Review and implement boundaries

`mode="review"` produces read-only investigation instructions. It asks for
detector context, counterexamples, unknown effects and relevant verification.
`mode="implement"` produces an implementation *proposal request*, with
`approval_required=true`, `approval_status=pending` and `writes_authorized=false`.
It explicitly requires later per-case approval, consumer/current-source checks,
bounded regression verification and rollback planning before any separately
authorized edit. This composer accepts no approval argument and cannot apply a
patch. Both modes have `automatic_fix=false`, empty commands and no AFTER code.

T047 owns the separate approval boundary; T048 owns subsequent prompt evaluation
fixtures/checklist. This slice neither implements those tasks nor wires a CLI,
installs a skill, executes a model/tool, builds target projects, connects to a
database or edits consumer source. No mass legacy remediation is authorized.

## Source, masks and unknowns

Verified output carries the exact case/rule ID, immutable source SHA, relative
path/region and the report's raw fingerprint when available. Reproof uses the
sealed source's expected BEFORE display and `requires_source_mask`: a complete
`[REDACTED]` region stays completely masked even for a nonsecurity rule overlapping
a sensitive region. If an explicit caller-specific partial mask cannot be
reproduced by the fresh verification context, all source is withheld and marked
unresolved rather than revealing previously hidden bytes.

Missing objects, wrong repository or already unresolved evidence produce
`SOURCE_UNRESOLVED`, a lookup plan, null location/BEFORE/current source SHA and
fingerprint, and no fabricated path, snippet, patch or navigation. Historical
in-process report SHA/fingerprint context may remain under `reported_context`,
explicitly distinguished from current reproof; it grants no authority. An
already unresolved assembled case contains no such location-derived context.

Git proof refers only to the named immutable commit. It does not claim the
working tree still matches that commit; `working_tree_alignment=not_checked`
remains explicit even when the working tree is dirty. Later review/approval must
reconcile actual source and consumers before a separately authorized change.

Confidence, production impact, affected consumers/test evidence and change risk
remain unknown. Unresolved evidence resets lifecycle/enforcement to
UNKNOWN/incomplete; a previous verified decision cannot become current source
authority merely because it was serialized. Sensitive display masking is not a
claim of comprehensive secret detection.

Source snippets/comments/strings are labelled **untrusted evidence data**, never
instructions. The body combines fixed workflow instructions with a distinct
JSON evidence section; embedded text is not copied into the instruction list,
turned into executable commands or used to grant writes. Imported report prompt,
message, proposal or arbitrary explanation text is not used. This textual/data
separation is a downstream instruction boundary, not a claim that every model
will resist prompt injection or that a same-user process is sandboxed.

Invalid report types, wrong case IDs, invalid modes or invalid explicit roots
raise only `CasePromptError("Invalid or unavailable case prompt input")`, without
echoing input identifiers, snippets, exception text or local paths. Encoded
outputs are bounded to four million characters. No filesystem writes occur.

## Verification

```powershell
python -B -m unittest discover -s tests -p test_case_prompts.py -v
python -B -m unittest discover -s tests -p test_report_model.py -v
```

Tests use actual temporary Git commits and sealed assembled reports. They cover
mode separation/no implicit approval, exact source identity, untrusted source
comments, serialized/duck-typed forgery rejection, safe constant errors,
unresolved/wrong-repository evidence, overlapping full masks, custom partial
masks, immutable/fresh output digests and complete source/.git no-write snapshots.
No consumer project, native build, model session or external service is used.
