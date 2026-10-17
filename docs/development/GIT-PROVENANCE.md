# Immutable Git source provenance

`devsift.git_changes.classify(repo_root, base_ref, head_ref, rule_id, evidence,
baseline=None, redactor=None)` provides source-origin attribution for a verified
finding region. It is a local library, not a scan command, semantic analyzer,
baseline store or remediation mechanism. `baseline` and `redactor` are keyword-only.

The immutable `Classification` contains `lifecycle_class`, a fixed safe `reason`,
resolved `head_sha`, unique `merge_base_sha`, content `fingerprint`, and proven
`head_location`/`base_location` when available. `to_dict` produces fresh structures.
UNKNOWN may retain verified head provenance/fingerprint while lacking baseline
mapping; it never becomes passing or introduced by default.

The caller supplies an accepted `SourceEvidence` object. VERIFIED wire claims are
not sufficient; the library re-verifies the exact immutable head source through
the evidence helper. The claimed source SHA must equal the resolved head commit.
Use the same explicit `Redactor` that produced the evidence, if applicable. Source
coordinates follow the accepted LF/CRLF, one-based Unicode code-point, exclusive-end
contract in `docs/development/EVIDENCE.md`. Dirty working-copy/index contents are ignored.

## Classification rules

| Proof | Source-origin result |
| --- | --- |
| Identical old/head file bytes and verified region | LEGACY_UNCHANGED |
| Changed file, complete selected physical-line chunk occurs exactly once in each immutable file, with exact old-region proof | MODIFIED_PREEXISTING |
| Changed region without exact old mapping; complete scoped baseline analysis reports no findings for that rule | MODIFIED_INTRODUCED |
| Absent old path, no deleted old paths, selected original content occurs in no old regular blob within limits | NEW |
| New path with exactly one removed predecessor, identical file bytes, unique selected content and destination, verified old region | LEGACY_UNCHANGED |
| Same unique predecessor/destination proof with changed file bytes and uniquely mapped unchanged physical-line chunk | MODIFIED_PREEXISTING |
| Missing/ambiguous provenance, insufficient baseline analysis, possible copy/rename, duplicate region mapping | UNKNOWN |

An unchanged selected region is not automatically new because another part of
its file changed. Exact unique source mapping is about source origin, **not rule
validity**: an unchanged call can acquire a new semantic issue when dependencies
or configuration change. A later semantic analyzer must supply that evidence;
this library does not assert that mapped findings were previously diagnosed.
It does not prove whether a changed finding worsened an old defect.

`BaselineObservation(rule_id, source_sha, path, findings, complete, analyzer_id)`
freezes a copy of supplied `SourceEvidence` findings. `source_sha` must identify
the actual unique merge-base, and rule/path must match. Nonempty finding source
claims are re-verified against Git. `complete=True` and analyzer identity are
**caller-trusted observation inputs**, not independent proof that a native
analyzer ran or that its negative result is correct. No analyzer executes here.
Only a complete, same-rule, same-path observation with zero baseline findings can
establish MODIFIED_INTRODUCED in changed regions. Existing baseline findings whose
relation to the changed region is uncertain keep UNKNOWN. No baseline is written
or silently refreshed, and an incomplete observation never proves absence.

For absent old paths, selected original content is checked against every old
regular blob within limits. NEW requires no old content match and no removed
path that might represent a changed rename. A rename can instead retain legacy
origin only with exactly one candidate old path, removal of that predecessor,
one occurrence of the selected original content in both files, and no other head
path containing that content (including previously existing changed paths).
The complete selected physical-line chunk
must map uniquely into the old blob, and its old region is independently verified.
Identical blobs retain LEGACY_UNCHANGED; renamed changed blobs retain
MODIFIED_PREEXISTING only for that proven unchanged region. The result includes
the actual old path/region and immutable SHA. Original-content fingerprints stay
stable through the rename and positional drift.

Multiple candidate old paths, repeated/overlapping selected content, repeated
physical-line chunks, multiple new destinations, and copies with the old path
retained remain UNKNOWN. Edited copies and partial-file moves cannot be called
NEW merely because their destination path is absent in the old tree. Unsupported
or oversized blobs also prevent convenient origin claims. This deliberately
favors UNKNOWN for common snippets and large repositories. These are exact
bounded source-content mappings, not heuristic similarity scores or Git's
configurable rename detector, and do not establish semantic rule validity.

## Git safety and limits

Refs resolve with `rev-parse --verify --end-of-options` to full commit hashes;
no ref is interpolated into shell code. `merge-base --all` must return exactly one
commit. Shallow repositories are always UNKNOWN, even if two available refs
appear connected. Missing/unrelated refs, multiple merge bases and unavailable
Git never pick a convenient fallback. Git stderr and source text are never copied
into public errors/results.

Operations use `rev-parse`, `merge-base`, `ls-tree`, and `cat-file`, without diff
drivers, external diff, textconv, network, index/source writes or ref updates.
Replacement objects, optional locks, fsmonitor and terminal prompting are disabled.
Lazy fetching is disabled for Git commands, and partial/promisor repositories are
rejected before source verification to prevent missing-object network retrieval.
The guard inspects effective Git configuration with includes, covering system,
global, local, worktree and environment scopes; local-only inspection is insufficient.
The actual repository root must be supplied. Only regular immutable blobs are
read; symlink/submodule source is unsupported. Limits: 1,000 tree entries, 2 MB
per blob, 5 MB total comparison bytes for absent-path origin/rename candidates, 5,000 physical lines per
file for changed-region matching, and 10 seconds per Git command. Exceeding limits
produces UNKNOWN rather than partial confidence. Git stdout is checked against
5 MB after command completion; this is not a hardened hostile-process sandbox.

The SHA-256 fingerprint hashes a version tag, rule ID, and **original unmasked
selected source content**, encoded deterministically. It is independent of SHA,
path and line drift; changing only a sensitive value changes the hash despite
identical masked display. Original content remains internal and is never stored
in Classification, errors, `repr`, or serialized result. Hashes are identity
signals, not encryption or proof that the rule is valid. Rule IDs must be in the
accepted registry.

Producer checks: `python -m unittest discover -s tests -p test_git_changes.py`
and `python -m unittest discover -s tests -p test_git_rename.py`.
Fixtures create real temporary histories for all five lifecycles, complete and
incomplete observations, copied/possibly renamed paths, dirty state, shifted and
duplicate regions, masked-content fingerprints, shallow clones and unrelated
histories. The Git provenance fixtures additionally cover exact and changed renames with drift,
old-path proof, duplicate origins/occurrences, retained copies and multiple
destinations. Integration coverage is documented with the scan and report suites.
Rollback is a revert of this scoped library/tests/documentation commit; no
consumer sources or runtime state are modified.
