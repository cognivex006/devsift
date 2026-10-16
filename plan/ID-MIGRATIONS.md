# Execution ID and canonical ID migrations

Canonical IDs `G001`–`G025` and `T001`–`T075` from v5 are preserved. v6 adds `G000`, `T000`, and `T076`. Root-task dependencies T001/T002/T004/T005/T007/T008 now require T000 acceptance. **The full G000 goal is not a gate** to these six entries; only the accepted T000 is required.

Recompute the execution IDs from the actual DAG using `python tools/planctl.py classify`. Original G001–G025 structural classes are unchanged by this partial-goal dependency addition. New G000 maps to GA000. If future graph changes cause any class transition, record the old and new aliases, graph fingerprints and affected task/job/PR/savepoint links in the register below.

|Date|Canonical|Old alias|New alias|Graph hash before/after|Linked artifacts|Reviewer|Evidence|
|---|---|---|---|---|---|---|---|
|2026-10-16|G000|none|GA000|new goal in v6|plan/goals/G000.md, T000, T076|planned|plan ledger only|

Old execution aliases may be used for historical citations but must not replace canonical goal IDs. An `accepted` state requires actual reviewed evidence, never migration text.
