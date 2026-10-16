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

T047's separate manual-planning approval boundary is described below; T048 owns
subsequent prompt evaluation fixtures/checklist. Neither library wires a CLI,
installs a skill, executes a model, builds target projects, connects to a database
or edits consumer source. No mass legacy remediation is authorized.

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

## Explicit per-case approval (T047)

`devsift.case_approval.ImplementationApproval` is a frozen *explicit trusted
operator input*, not an authenticated user identity or a signed capability.
`from_dict()` accepts exactly these nine fields:

| Field | Required meaning |
| --- | --- |
| case_id | Exact case ID from the selected sealed report |
| source_sha | Exact lowercase immutable commit SHA |
| fingerprint | Exact 64-character source/rule fingerprint |
| prompt_digest | Exact 64-character digest of the selected implement CasePrompt |
| mode | Explicit implement approval; review never permits implement planning |
| approved | Boolean true; absent/false/matching case ID alone cannot approve |
| actor | Explicit nonempty bounded operator label; redacted before display |
| issued_at | Timezone-aware ISO timestamp, not later than the evaluation clock |
| expires_at | Timezone-aware ISO timestamp strictly after issue/evaluation |

Unknown keys, missing fields, malformed IDs/hashes/times, naive timestamps,
nonboolean approval and control-bearing/oversized actors fail with a constant
`CaseApprovalError("Invalid or unavailable case approval input")`. Read arbitrary
JSON only through a deliberate bounded/duplicate-rejecting loader before this
conversion; `from_dict()` does not authenticate serialization or discover/read
any file. No project approval file, signature, comment or source directive is
automatically loaded or trusted. Caller/operator trust is explicit.

```python
from devsift.case_approval import ImplementationApproval, evaluate_case_approval

# operator_record is supplied by the explicitly trusted human/operator boundary.
approval = ImplementationApproval.from_dict(operator_record)
decision = evaluate_case_approval(
    report, selected_case_id, prompt=implement_prompt,
    repo_root=repo_root, approval=approval,
)
json_decision = decision.to_dict()
```

Evaluation requires actual in-process Report and CasePrompt objects, composes a
fresh implement prompt and compares its full digest, then checks the binding's
case ID/SHA/fingerprint/digest exactly. A review prompt or review/declined approval
is denied. The current UTC clock is used by default; tests may supply an explicit
aware datetime via `now`. Expired or not-yet-issued records are denied. No record
can grant execution permission simply by matching a case ID.

Current source is separately checked: the explicit root must be the actual Git
root; HEAD must still equal the bound immutable source SHA; the selected stage-0
index entry must match that commit; and the complete raw selected file bytes must
hash to its immutable Git blob. Dirty selected bytes, dirty/conflicted/untracked
selected index entries, changed HEAD, missing files, links/junctions/reparse paths
or unresolved source are denied. HEAD/index are rechecked after the byte read.
No Git conversion/filter, external diff or textconv driver is executed. This is
deliberately byte-exact: transformed checkout bytes may require reconciliation,
not normalization that invents a match. Unrelated untracked files are not a
global gate; approval scope is the one selected path/case only.

The immutable `ApprovalDecision` provides fresh `to_dict()` snapshots:

- No explicit approval: `review_required / EXPLICIT_APPROVAL_REQUIRED`, no manual
  planning handoff.
- Invalid binding, stale/unsafe source, wrong mode or expired approval: `denied`
  with a fixed reason and no handoff. Source failures withhold location/snippet.
- Matching current explicit approval: `review_required /
  UNKNOWN_EFFECTS_REVIEW_REQUIRED`, `approval_matched=true`,
  `manual_planning_allowed=true`, and a handoff bound to the exact case/SHA/
  fingerprint/prompt digest with scope `manual_case_planning_only`.

Current reports disclose unknown impact, change risk and consumers, so a matching
approval never becomes an execution-ready/automatic-fix decision. Every decision
has `execution_authorized=false`, `writes_authorized=false` and
`automatic_fix=false`; no source files, index, baseline or refs are modified.
Existing source masks, including nonsecurity overlaps, remain intact. Operator
labels are not echoed unredacted. There is no patch application engine here.

This is a point-in-time read-only workflow boundary. Decisions are not reusable
authority tokens: repeat all checks if source, HEAD, prompt, approval window or
scope changes. Checks cannot stop a malicious same-user process racing the
filesystem, nor enforce an outside agent's edits. A separate explicit human
decision is still required for any actual consumer change; this API's handoff
permits only case-scoped manual implementation planning while effects are unknown.

```powershell
python -B -m unittest discover -s tests -p test_case_approval.py -v
```

Actual temporary Git tests cover exact/false/missing/wrong/expired approvals,
staged and unstaged selected changes, unrelated versus selected untracked files,
moving HEAD, unresolved source, actual file links when permitted, protected masks,
immutable decisions and before/after source/.git identity. No automatic changes
or approval discovery are tested as successful capabilities.


## Installed command entry

The installed skill calls `python -I -B -m devsift prompt CASE-ID --mode review --scan-input /absolute/scan.json` from the consumer Git root. Isolated Python prevents consumer module/environment shadowing; bytecode is disabled. Development tests use `-P` and an explicitly trusted checkout PYTHONPATH, never an automatically discovered consumer module.

For proposals use `--mode implement --approved-case CASE-ID`; optionally provide the explicit nine-field operator record with `--approval-file`. Matching only the target ID is not approval. The command backend uses the bounded explicit JSON loader, discards imported rendered reports, reassembles/reproves scan findings and invokes the immutable composer/approval guard. No input is auto-discovered. The CLI returns `scope: case_prompt_generation_only` and `analysis_performed: false`; review exit 0 is generation success only, not evidence of a clean scan. Unknown source returns 2; implementation returns 2/review_required and never grants automatic edits, even for a matching record. Missing legacy storage inputs remain incomplete rather than inferred.

Git proofs select an absolute host Git executable from absolute operator PATH entries outside the consumer repository. Empty/relative entries and links resolving into the consumer repository are excluded, so a project `git.exe`/`git` cannot provide source proof. This trusts the host installation; it is not executable hash pinning or a sandbox against concurrent host changes.
