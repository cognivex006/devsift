# Evidence contract v1

`requires_source_mask(rule_id, source=None)` withholds HC002/CFG003/SEC001 regions
and preserves an already fully masked source region through overlapping rules.
Scanner, native host and classifier use the same display rule; immutable Git
verification and raw-content fingerprints remain independent. An existing mask
does not grant verification, lifecycle, a waiver or enforcement authority.

`devsift.evidence` provides immutable source/runtime records and separately labeled
illustrative proposals. It does not discover findings, classify Git changes,
authorize remediation, or render complete finding reports. The public wire shapes
are in `schemas/evidence.schema.json`; semantic relationships and actual Git
verification are enforced by the standard-library runtime, without a schema
dependency. All `from_dict` methods reject missing/unknown fields and wrong types.
`to_dict` returns fresh nested dictionaries; no mutable input is retained.

## Immutable source proof

```python
from devsift.evidence import Region, verify_source, SourceEvidence
from devsift.redaction import Redactor

redactor = Redactor(secrets=("sensitive value supplied by caller",))
evidence = verify_source(
    repo_root, "owner/repository", full_commit_sha, "src/example.py",
    Region(10, 1, 12, 5), redactor=redactor,
)
wire = evidence.to_dict()
restored = SourceEvidence.from_dict(wire, repo_root=repo_root, redactor=redactor)
```

`Region(start_line, start_column, end_line, end_column)` uses positive one-based
line numbers and Unicode code-point columns, with an exclusive end. Empty regions
are valid, but reversed regions and boolean coordinates are invalid. A future
SARIF writer must declare `run.columnKind = "unicodeCodePoints"`. Selected
multiline BEFORE text preserves source line endings; line terminators are not
included in the column count. Physical lines follow Git LF boundaries; CRLF is
one terminator, while Unicode LS/PS, VT and form-feed stay within a line. A bare
CR is content, and only the single CR immediately preceding LF is removed from
column bounds. A terminal newline does not introduce a selectable
extra empty line. Source extraction checks both endpoint bounds.

`SourceLocation(repository, source_sha, path, region, symbol=None)` validates the
physical location structure. SHA is a full hexadecimal SHA-1 (40) or SHA-256 (64),
normalized lowercase. A structurally valid SHA is not proof that an object exists.
Paths must be canonical repository-relative forward-slash paths: no traversal,
empty/dot segments, `.git` segment, backslash, colon, absolute path or control
characters. Repository is a bounded caller-supplied identity label, not an
authenticated remote identity. Optional symbol metadata is structurally checked,
not semantically proven. The Git verifier emits `symbol=None` and rejects imported
VERIFIED records asserting a symbol until a symbol-aware proof contract exists.

`verify_source` requires the actual repository root and a commit object. It uses
read-only Git object commands, disables replacement objects and optional locks,
and sets `GIT_NO_LAZY_FETCH=1` on every Git read to prevent partial-clone object
lookups from silently fetching over the network. It never reads source through
the working tree. Only regular Git blobs are
accepted; symlink/submodule/tree modes are unresolved, so neither working-tree
symlinks nor Git symlink contents can escape into host filesystem reads. UTF-8,
NUL-free source up to 2 MB is supported; commands have a 10-second timeout each.
Invalid coordinates/path/SHA structure raises a constant `EvidenceError` without
echoing input. Missing commits/files/tools, unsupported source, invalid source
bounds and mismatched `expected_before` return `SOURCE_UNRESOLVED`.

A VERIFIED `SourceEvidence` contains its physical location and redacted exact
BEFORE. Sensitive spans are found in the complete original blob before slicing;
even a region selecting only part of an assignment value, Bearer credential or
multiline key emits a complete mask for the overlapping sensitive span. Offsets
always refer to original source, so earlier masks cannot shift the selected
region. An unresolved record contains **no physical location or BEFORE**, only a
fixed reason code and bounded lookup plan. Runtime messages cannot fill these
fields. `SourceEvidence()` starts unresolved; normal construction cannot assert
VERIFIED. `SourceEvidence.from_dict` requires `repo_root` for a VERIFIED record
and re-extracts the immutable source, comparing the masked BEFORE. Wire input is
not a verification certificate. This is an in-process correctness boundary, not
protection against hostile Python code altering internals.

`expected_before` compares after masking, so changes solely within masked values
cannot be distinguished by serialized evidence. The immutable SHA and location
remain the source identity. If explicit sensitive values occur in a path, the
verifier returns unresolved instead of emitting an inaccurate masked path. Do
not discard that redactor when rehydrating evidence containing explicitly masked
values: explicit secrets are intentionally never stored in an evidence record.

## Runtime evidence and proposals

`RuntimeEvidence(origin, message, observed_at=None, *, redactor=None)` records a
bounded origin label and message. Optional timestamp is an ISO/RFC3339-style
date/time with timezone (`Z` or numeric offset), seconds, and up to six fractional
digits. Its wire contract has no file, line, symbol or SHA fields; adding any is
an error. Runtime origin is supplied provenance, not authenticated telemetry.

`AfterProposal(code, confidence="unknown", *, redactor=None)` is distinct from
BEFORE and always serializes `label: "AFTER (PROPOSAL)"`. Confidence is
high/medium/low/unknown. The proposal is illustrative and never a verified patch
or an approval. Both records mask text at construction, hide redactor values from
representations, and support strict `from_dict` round trips.

## Bounded masking

`Redactor(secrets=())` freezes a copy of at most 256 caller-specified sensitive
values (each 1–4096 characters). `text` masks those values, common GitHub/AWS key
shapes, PEM private-key blocks, Bearer credentials, password/token/API-key
assignments and HTTP URL user/password credentials. These patterns are bounded
defenses, **not comprehensive secret or PII detection**. Callers must register
known sensitive values; arbitrary business identifiers or custom credential
formats cannot reliably be inferred.

`redact` handles nested JSON-compatible dictionaries/lists/tuples, masks dictionary
keys too, and masks whole values under common sensitive key names. It returns new
containers and rejects cycles, masked-key collisions, unsupported objects,
non-finite numbers, more than 32 levels/20,000 nodes/2 MB of text. `text` accepts
at most 2 MB. Failures use constant `RedactionError` text without inspecting
untrusted object representations. Normal evidence errors and unavailable Git
lookups never include source snippets, Git stderr, raw paths or sensitive values.
Use the same redactor before creating source/runtime/proposal objects and on
other report/log/prompt structures; this module cannot intercept unrelated caller
logging. Already-masked values remain masked consistently.

`Redactor.slice(full_text, start, end)` uses zero-based original Unicode code-point
offsets, with an exclusive end. It returns selected non-sensitive text plus whole
masks for overlapping sensitive spans; an empty selection remains empty. Explicit
secrets containing the mask marker are recognized before preserving ordinary
markers. `SourceEvidence(..., redactor=...)` and unresolved `from_dict` apply that
same redactor to lookup plans, without retaining its sensitive values.

Producer verification: `python -m unittest discover -s tests -p test_evidence.py`
and `python -m unittest discover -s tests -p test_redaction.py`. Tests create real
temporary Git commits, including symlink index entries, compare dirty working
state before/after, and verify source/runtime/proposal masking. The evidence suite acceptance
fixtures are a separate downstream task. Rollback is the scoped producer commit
revert; there are no data migrations or consumer-source modifications.

Explicit sensitive-region verification masks the complete BEFORE range after checking immutable content and any prior display assertion. Existing verified displays can be re-proved and upgraded to full masking; a wrong display remains unresolved. A fully masked wire display re-proves the same immutable region while retaining the mask. The sensitive flag is conservative even for an empty selection; default empty-region behavior is unchanged.
