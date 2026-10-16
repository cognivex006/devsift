# First wave — DevSift v6

**Historical initial frontier: `T000` only.** Current state is in `plan/ledger.json` and `docs/evidence/G000.md`. Remote is observed empty as of 2026-10-16; recheck immediately before work. Do not launch five workers for one initial bootstrap task.

- Controller exclusively assigns **T000**; prepare exact file manifest, audit contents, publish the approved scaffold in one initial main commit and update GitHub Description.
- Distinct reviewer independently examines evidence and the remote SHA. Set `in_review` before `accepted`; no downstream unlock until accepted.
- After T000 accepted, `T076` (bootstrap verification) and T001/T002/T004/T005/T007/T008 become DAG-eligible; they may run before G000 fully completes, subject to locks.
- Start up to four disjoint writers + one reviewer when tasks and slots actually exist. Refill each freed slot as soon as acceptance and locks allow; never batch synchronize.
- When `G000` is fully accepted, normal scoped feature branches + PR workflow applies; the initial direct main commit is the only exception and must not be repeated.

Generating the original kit performed no GitHub mutation. G000 has since been published and independently accepted; consult the canonical execution ledger.
