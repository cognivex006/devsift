# Baseline and suppression v1 producer contracts

These standard-library modules are local library foundations. They are not wired
into scan commands and never authorize source remediation. Normal scan/load/diff
operations do not save, refresh or alter baselines or suppressions.

`capture_entry(repo_root, rule_id, rule_version, evidence, *, redactor=None)` uses
the accepted Git classifier at the evidence's immutable commit to re-verify its
source and original-content fingerprint. Unresolved/shallow/unsupported provenance
cannot be captured. The frozen `BaselineEntry` stores stable catalog rule ID,
explicit rule version, fingerprint and `SourceLocation`; no source snippet is
persisted. Use the same explicit redactor that produced the evidence.

`BaselineSnapshot(repository, source_sha, tool_version, rule_catalog_version,
entries)` freezes and deterministically sorts a copy of entries. Every entry must
belong to that repository/commit. Full lowercase SHA-1/SHA-256 commits, lowercase
SHA-256 fingerprints and nonblank bounded version strings are required. Duplicate
rule/fingerprint identities are rejected as ambiguous rather than silently
deduplicated, including repeated identical findings at different locations.
Snapshots hold at most 1,000 entries and one version per rule. `to_dict`, `to_json`,
`from_dict`, `from_json` provide
strict round trips; unknown/missing keys, wrong types/versions, duplicate JSON
keys, non-finite constants and excessive input are rejected with safe errors.
Importing a snapshot structurally validates recorded provenance; it does not
independently re-run analyzers or authenticate arbitrary supplied records.

`diff_snapshots(old, new)` is read-only and returns frozen tuples `added`,
`resolved`, `unchanged`, using rule/fingerprint identity across source drift. The
unchanged entries come from the new snapshot. Repository, tool version and rule
catalog version must agree, and overlapping rule versions must agree; incompatible
analysis is not silently called resolved. These are observation differences,
not proof of semantic correctness, analyzer completeness or quality-gate status.

## Explicit reviewed saves and trusted loads

```python
approval = UpdateApproval(
    actor="requester", reviewer="independent-reviewer", ticket="CHANGE-123",
    approved_digest=snapshot.digest, expected_digest=previous_file_digest,
)
new_file_digest = save_snapshot(
    path, snapshot, approval, expected_digest=previous_file_digest,
)
loaded = load_snapshot(path, expected_digest=new_file_digest)
```

`UpdateApproval` requires distinct trimmed, case-insensitive actor/reviewer labels,
a ticket, exact approved **snapshot payload digest**, and expected predecessor
**file digest**. These labels/evidence are trusted caller inputs, not signatures
or authenticated human identity. Only an explicitly authorized workflow may
construct and use this approval. Ordinary snapshot reads cannot authorize saves.

`save_snapshot` is the only write entrypoint. `expected_digest=None` means
create-only; a supplied SHA-256 means compare-and-swap against the current exact
file bytes. The approval must bind both that predecessor and the new snapshot
payload. A strict envelope persists `schema_version`, `snapshot` and `approval`.
The returned SHA-256 covers the exact serialized envelope, which differs from
`snapshot.digest` because it includes approval evidence.

The parent directory must already exist. Saves reject symlink targets/parents,
create an exclusive sibling `.lock`, check predecessor bytes under the lock,
flush/fsync a same-directory temporary, then atomically replace the destination.
Only owned locks/temporaries are cleaned; a preexisting lock is left untouched.
Failures before replacement preserve the old file. This CAS serializes cooperating
writers; it is not a sandbox against hostile processes ignoring locks or swapping
filesystem directories. Directory fsync/power-loss durability is platform-specific
and not guaranteed. Recovery never silently removes another writer's lock.

`load_snapshot(path, *, expected_digest)` requires an independently trusted exact
file digest, bounds reads to 5 MB, rejects symlink files, verifies bytes before
parsing, validates approval/payload binding, and returns a frozen snapshot. Neither
an embedded unkeyed digest nor editable approval labels authenticate a tampered
file. Protect the trusted expected digest outside attacker-controlled baseline
content (for example, reviewed immutable commit metadata). Stale/tampered files
fail closed; no automatic baseline regeneration occurs.

## Scoped suppression and expiry

`Suppression(rule_id, fingerprint, owner, reason, ticket, expires_at)` requires one
catalog rule and one exact finding fingerprint. Wildcards, blanket legacy modes,
missing owner/reason/ticket, and all catalog Critical security waivers are rejected
in v1, even if policy severity is locally downgraded. Suppressions cannot bypass
the independent security escalation workflow and are not remediation approvals.

`valid_at(as_of)` and `matches(rule_id, fingerprint, *, as_of)` require an explicit
timezone-aware `datetime`; there is no ambient clock. Expiry is a valid ISO/RFC3339
timestamp with timezone, seconds and up to six fractional digits. Expiry at the
exact boundary is already expired. Expired suppressions raise an error rather than
silently applying; a valid suppression only matches the exact rule/fingerprint.
`load_suppressions(json_text, *, as_of)` parses a strict JSON array (maximum 1,000),
rejects duplicate scope/keys, and validates every expiry. Constructors/from_dict
can represent a structurally valid old record for audit; applying/loading it
requires explicit expiry validation. These functions never read or write files.

Schemas describe stored wire structures; semantic commit agreement, duplicate
identities, digest trust, CAS and time comparisons remain runtime checks. Metadata
validation of the baseline schema requires registering the existing evidence
schema resource (`urn:devsift:evidence:1`) locally; no network resolution is needed.
Metadata
uses the shared bounded common-pattern redactor; register/mask any additional
sensitive metadata with the same explicit redactor before constructing records.
Safe errors do not include raw JSON, Git stderr, source snippets or storage paths.

Producer checks: `python -m unittest discover -s tests -p test_baseline.py` and
`python -m unittest discover -s tests -p test_suppressions.py`. Real temporary Git
sources exercise capture; file fixtures exercise approval, CAS, integrity,
read-only load/diff, nonmutation and atomic-failure cleanup. T018 acceptance
fixtures remain a separate downstream task. Rollback is the scoped producer
commit revert; no consumer sources or automatic baseline refreshes occur.
