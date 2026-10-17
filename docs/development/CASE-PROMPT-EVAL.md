# Per-case prompt fixture evaluation

This is a fixture-based evaluation of the case prompt composer and explicit
manual-planning approval boundary. It adds tests/data/docs only. It does not
invoke a model, apply a patch, install a skill, wire CLI options or grant consumer
write permission. Task/goal acceptance remains the controller/reviewer's decision.

## Reproduce the current fixture evidence

From the selected code checkout:

```text
python -B -m unittest discover -s tests -p test_case_prompt_fixtures.py -v
git diff --check
```

Four focused groups exercise six golden decision scenarios, canonical JSON
stability, source-as-data separation and four external malformed inputs.
The pipeline is the actual public implementation:

```text
fresh temporary Git commit
  → trusted deterministic fixture detector + scan(...)
  → assemble_report(...), immutable source reproof and policy
  → compose_case_prompt(...), separate review/implement snapshots
  → ImplementationApproval.from_dict(...) when explicitly supplied
  → evaluate_case_approval(...), selected current-file/index/HEAD checks
  → stable canonical JSON with no source-write authority
```

The fixture callback only supplies deterministic candidate findings; it is not a
real TypeScript parser/rule detector. Git source proof, scan coordination, report
assembly, policy, composer and approval decisions are real code paths. No serialized
report is treated as a sealed report or authentic approval without validation.

The fixed `tests/fixtures/case_prompts/client.ts` source is copied into a newly
initialized disposable Git repository. Only fixture setup commits it with
command-local synthetic identity and a fixed commit time; hooks/conversions and
automatic maintenance are disabled in the fixture. Source SHA, location proof,
fingerprint and implement/review prompt digests are generated from actual Git and
APIs at runtime. No fake SHA or hardcoded proof is stored in fixtures. The actual
same-commit Git classifier supplies verified legacy attribution; unknown cases
remain explicitly unknown. No source commit is made to a consumer repository.

The test snapshots the entire fixture source and `.git` file bytes before/after
evaluation. Read-only APIs must preserve them, including index/config/refs. They
do not install dependencies, execute source-language code, run embedded commands,
build targets, connect to databases, create reports/cache files or edit source.
The only filesystem writes are deliberate disposable fixture setup/cleanup.

## Golden scenario contract

`cases.json` stores editable semantic expectations rather than a copy of the whole
current implementation output. `$fixture_line` means the selected committed fixture
line; real proof hashes are asserted separately against actual Git/API results.

| Fixture | Expected result from the actual pipeline |
| --- | --- |
| unverified | Scan/report incomplete; prompt location/BEFORE/current SHA/fingerprint null, lookup plan present, no inferred file or patch; approval denied SOURCE_UNRESOLVED |
| legacy-advisory | Real immutable proof and same-commit legacy attribution; advisory policy; exact matching operator input allows manual planning only, remains review_required with unknown effects |
| masked-secret | Synthetic bearer text is actually present in the committed source but absent from scan/report/prompts/decision; BEFORE stays `[REDACTED]`; legacy security escalation remains visible |
| wrong-case | Approval keeps actual source/fingerprint/digest but names another case; denied binding mismatch, no manual handoff or write authority |
| wrong-prompt-binding | Approval uses the actual review prompt digest instead of the selected implement digest; denied binding mismatch without a fabricated proof hash |
| source-as-data | Verified comment canary stays in the distinct JSON evidence section, never in workflow instructions/commands; lifecycle/effects remain unknown, no approval or write authority inferred |

All review/implement prompts keep commands empty, AFTER code null, automatic_fix
false, affected consumers empty and effects/risk unknown. Review does not request
implementation approval; implement requests a later explicit approval. Every
approval decision keeps execution_authorized/writes_authorized/automatic_fix false,
including the matching manual-planning case. A diagnostic scan/report exit 0 for
the controlled legacy fixture is not implementation permission or a claim of
comprehensive detector/source safety.

The full serialized outputs contain no synthetic secret. Source-unverified prompt
and decision JSON do not disclose even the known candidate `client.ts` path as if
it were proven. The source instruction canary is deliberately retained as evidence
data; imported detector-message canaries are not promoted to generated prompt text.
Repeated fresh reproof of one unchanged actual commit produces byte-identical
canonical JSON and prompt digests. This is deterministic serialization evidence,
not cross-model evaluation or a cryptographic approval/authentication scheme.

## External malformed fixtures

`malformed/*.json` names a real scan-record/approval boundary, a JSON key path and
a replacement value. Tests first create a valid actual pipeline input, copy it,
then apply that data-only mutation before the public validator. Nothing is eval'd,
executed or loaded as an approval from project configuration.

- Extra imported report implement-prompt field → constant ReportError.
- Invalid report severity → constant ReportError.
- Extra unrestricted approval scope → constant CaseApprovalError.
- Nonboolean `approved` value → constant CaseApprovalError.

Errors must match the fixed public messages and never echo the supplied canary.
To extend a fixture, keep its source synthetic, declare the expected state and
authority boundary, and add reviewable scenario coverage rather than copying a
newly observed output wholesale. Re-run immutable-source/mask/binding/no-write
assertions. New case IDs/proof/attribution/approval modes require a deliberate
fixture/test update; unknown modes are rejected by the fixture harness.

## Evaluation checklist and limits

Current automated fixture evidence (on the host where the recorded command ran):

- [x] Real Git→scan→sealed report→composer→approval pipeline exercised.
- [x] Unverified source withholds file/region/snippet/patch and provides lookup.
- [x] Verified legacy remains advisory and unknown effects remain unknown.
- [x] Known synthetic sensitive bytes stay masked through every public stage.
- [x] Wrong case and different actual prompt binding cannot authorize planning.
- [x] Source canary remains data; command list and write authority stay empty/false.
- [x] External malformed inputs fail safely and immutable JSON reproof stays stable.
- [x] Source and `.git` byte snapshots stay unchanged during evaluation.

Future/manual evaluation, **not run or proven by these string tests**:

- [ ] Independently reproduce on every supported OS and pinned runtime/tool setup.
- [ ] Inspect real parser-produced cases and their source/mask/attribution limits.
- [ ] Run controller-owned actual CLI/skill integration once its shared entry is ready.
- [ ] If a downstream LLM is evaluated, pin model/client/settings, retain curated
  inputs and actual responses, and independently score unauthorized-command/edit
  attempts, invented paths/patches, masking and uncertainty disclosure.
- [ ] Expand source/report injection canaries and counterexamples without treating
  data labeling as proof that every model will obey it.
- [ ] Review actual consumers, production effects, tests and rollback before any
  separately authorized consumer edit; manual-planning match is insufficient.

No LLM call, real consumer remediation, OS sandbox, universal secret detector or
protection against a hostile same-user process is claimed. The prompt evaluation does not complete
CLI wiring, runtime functionality or another goal by generating this document.
