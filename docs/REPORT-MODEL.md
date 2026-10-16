# Source-reproved report model

`assemble_report(scan_record, repo_root=..., policy=None, redactor=None,
trusted_lifecycles=False, repository_urls=())` builds an immutable `Report`.
Inputs are actual scanner envelopes; serialized input is not a certificate of
execution or source attribution. Source records are re-extracted from immutable
Git blobs. Missing or mismatched evidence becomes SOURCE_UNRESOLVED without a
physical location or navigation. Runtime text cannot manufacture source proof.

Persisted lifecycle claims default to UNKNOWN, including claimed NEW/block
findings. Only an explicitly trusted in-process provenance integration can set
`trusted_lifecycles=True`; file imports must not do this implicitly. Severity,
enforcement and security escalation are recomputed from the supplied policy and
source proof. A failed scan stays incomplete, even if some cases block. Unresolved
source or UNKNOWN attribution forces incomplete (2). Independent legacy security
review remains separate from quality blocking.

Each case contains full source evidence, static catalog explanation, an explicit
unknown invalidating exception, pending AFTER (PROPOSAL), alternatives, both
unknown impact/risk assessments, unknown consumer/test scope, review constraints,
verification and rollback guidance. Unknown production frequency, exploitability
or consumer impact is disclosed, never replaced with an invented metric, patch,
source symbol, runnable test command or deployment claim. Proposals are not fixes;
implement prompts require explicit case approval and never execute remediation.

Credential, config-secret and sensitive-log evidence withholds the complete
verified region. Raw-content identity is separate from masked display; if a
fingerprint cannot be proved it remains null. Input detector messages and raw
error text are not reproduced. Caller-known secrets must be supplied through the
same Redactor for supplemental text. Redaction is defensive, not proof that
arbitrary unknown sensitive data has been identified.

Navigation is absent unless the caller supplies an explicit trusted repository
label-to-GitHub-HTTPS mapping. Links use the proven full commit and URL-encoded
relative path; repository labels alone never generate links. Working-tree state
is not asserted equal to an old immutable source snapshot.

The envelope, individual case shapes, counts and booleans are checked. Duplicate
IDs, nonfinite/cyclic/oversized input, inconsistent exit status and unsupported
fields fail with a constant ReportError. Limits are 1,000 cases/errors and 4 MB
serialized input/output. Reports and cases cannot be directly constructed from
wire claims. `to_dict` returns fresh independent trees; `find_case` exposes only
an exact existing ID. No source, Git metadata, baseline or report file is written.

This task supplies assembly and schema. Markdown, SARIF/JSON export, substantive
baseline/risk integration and CLI/report consumption are separate reviewed tasks.
