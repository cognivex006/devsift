# Agent remediation workflow (proposed)
1. Read governance and applicable language rule pack.
2. Run changed-file scanner and collect redacted findings.
3. For each finding output: Thai human explanation, evidence, confidence, risk, recommended fix, copyable agent prompt, test plan.
4. Prioritize Critical/Error; no auto-fix of logging, security or configuration semantics without review.
5. For observability: compare current logs, metrics, traces and audit obligations; distinguish missing context from intentional omission.
6. Implement smallest safe change in isolated worktree; run targeted tests, contract tests, redaction tests and sampled production-like log replay.
7. Re-run scanner; present before/after diagnostic value and log volume, and require reviewer approval before merge.
