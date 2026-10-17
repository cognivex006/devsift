# Artifact, provenance and source-as-data threat model

DevSift separates input identity, archive-content review, output redaction and
execution authorization. None substitutes for the others. This document and
`tools/check_artifact_security.py` add a bounded maintainer inspection, not a
release, signing service, sandbox or universal secret certificate.

## Boundaries and attackers

| Boundary | Untrusted material | Required trust and remaining limits |
| --- | --- | --- |
| Source provenance | changed files, supplied lifecycle labels, stale paths, baseline or manifest claims | Reprove immutable source through accepted runtime contracts; UNKNOWN remains unresolved. A SHA identifies bytes/objects, not author identity or approval. |
| Packaging allowlist | local caches, unselected configs, workspace/governance files | The explicit component inventory excludes unselected files. Allowed tracked source can still contain credentials; file inclusion is not confidentiality proof. |
| Archive identity | substituted ZIP/wheel, hashes bundled beside it | An independently trusted expected SHA256 is mandatory. Hash and parser use the same bounded captured bytes. Deriving a new expected hash from untrusted input does not establish trust. |
| Archive confidentiality | credential/private-key shapes, private filenames, nested/compiled/encoded content | This checker reports recognized shapes without echoing contents or member names. Unsupported content remains incomplete; unknown secrets and liveness require separate review. |
| Human/machine report display | source snippets, filenames, messages, proposal text | Accepted redaction and safe renderers govern output. A redacted report does not sanitize the original archive or authorize edits. |
| Execution/write/publication | report snippets, comments, case prompts, package scripts or scan requests | Treat source/report snippets as data. Execution, installation, consumer edits, publication and releases require their own authorization and trusted setup. No archive is extracted/imported/executed by this checker. |

Trust the selected reviewed DevSift tool checkout, Python/stdlib and accepted
public Redactor implementation, the independently obtained digest, and the
operator's stable local filesystem. Malicious archive bytes/member names are
untrusted. A hostile administrator, altered interpreter/toolkit, concurrent
hostile filesystem owner, compromised trust channel or authorized maintainer
changing the checker is outside this boundary. Read-only path checks are not
an OS sandbox, publisher authentication, revocation or a signature mechanism.

## Bounded archive inspection

Run the trusted maintainer script explicitly, separately from a consumer scan:

```text
python -I -B <trusted-checkout>/tools/check_artifact_security.py --archive <absolute-file> --expected-sha256 <independently-trusted-lowercase-sha256>
```

`inspect_archive(path, expected_sha256=...)` returns a fresh JSON-safe record.
The script imports the public Redactor only from its explicit trusted source
checkout, never the inspected archive or caller's current directory. It needs
no bundler, archive extractor, build backend, native compiler, dependency
installer, network or publication credentials. This is not a runtime CLI feature.

The archive is captured once (maximum 8,000,000 bytes), SHA256 checked, then that
same immutable byte string is parsed. A changing/unavailable/oversized file,
relative path, symlink/junction/reparse path or incorrect/missing digest remains
incomplete. The result describes captured bytes, not a guarantee that the path
will contain them forever after inspection.

ZIP structure is bounded before constructing a member list: at most 256 actual
central records, no ZIP64/multidisk/self-extracting/trailing structures, at most
1,000,000 uncompressed bytes per member, 4,000,000 total and a maximum expansion
ratio of 100. Only stored and deflated UTF-8 text members are inspected. Every
supported payload is validated directly from its complete captured raw
compressed span. Stored data must have identical compressed/actual/declared
lengths and matching CRC. Raw deflate produces at most declared_size+1 bytes
within existing resource limits, must reach EOF with no unused_data or
unconsumed_tail, and must match the exact declared length and CRC. Truncated,
over-expanding, trailing-junk or concatenated streams remain incomplete; the
checker does not trust ZipFile's potentially truncated declared-size prefix.
Empty archives can complete
this narrow zero-member inspection; they prove no source coverage or release
readiness. A .whl filename is inspected as ZIP content, not certified as an
installable or policy-compliant Python distribution.

Traversal/absolute/drive/backslash/control/device aliases, duplicate/casefold
and normalized-name collisions, file/directory prefix conflicts, encrypted,
linked/special or inconsistent entries fail closed. Original stored filenames
are checked before ZipInfo's platform normalization can hide an unsafe name.
Local header names/flags/sizes must match central entries. Local/central extra
fields, comments and unaccounted bytes are uninspected metadata and cannot yield
complete. Windows COM/LPT aliases include the six superscript-digit forms
COMยน/COMยฒ/COMยณ and LPTยน/LPTยฒ/LPTยณ, with optional extensions, as documented by
[Microsoft's naming rules](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file).
This is a bounded reserved-name rule, not general Unicode homoglyph detection.
No name is used as an output/extraction path.

Private filename families include .env variants, common package/auth dotfiles,
SSH key names, credentials/secrets filenames, private-key container suffixes,
Git/cloud credential directories and .devsift/local. They are conservative review
signals, not proof of a live credential. Known compiled/binary or nested archive
extensions/magic, invalid UTF-8/control bytes and unsupported structured JSON
remain incomplete rather than being silently skipped into a clean result.

Detection uses public `Redactor.text` on names/text and `Redactor.redact` on
bounded parsed JSON, plus fixed private-key BEGIN delimiters so truncated and
encrypted private-key shapes also require review. No private Redactor regex
internals are imported. Protocol keys/enums are constants, not passed through a
value masker. Duplicate JSON keys or excessive structured redaction input cannot
hide behind a successful inspection. Known shapes may be examples or false
positives; no provider API is queried and credential liveness is never inferred.

## Result meaning and operator obligations

The only successful status is `no_detected_shapes_in_declared_archive` with
`complete: true`: supported bounded ZIP text/known-shape inspection completed.
It does not mean safe, secret-free, malware-free or approved to publish.
Recognized shapes/private names return review_required/incomplete. Unsupported,
partial, malformed or untrusted work returns incomplete. Exit 0 means that
narrow inspection completed; exit 2 means review/incomplete work, never a bypass.
Every result retains release_review_required=true and publication_authorized,
writes_authorized and execution_authorized=false. Public records contain only
fixed issue codes, scope flags and counts; no archive path/member name/source,
secret, raw stderr or exception representation is emitted.

The checker does not rewrite/redact an archive, rotate a credential, delete
source, extract members or execute report/source code. Review inclusion against
the accepted component allowlist, inspect real contents/relationships, establish
publisher/provenance/licensing/dependency trust and independently approve any
release. Encrypted/nested/binary/encoded secrets, steganography, novel provider
formats, fragmented values and arbitrary PII are not comprehensively detected.
A text member's declaration/UTF-8 decoding does not prove its semantic safety.
Compressed-stream internals are not a general-purpose forensic scan. Reports
and archive snippets never become commands merely because they look executable.

## Actual verification and limits

`python -B -m unittest discover -s tests -p test_artifact_security.py -v` creates
actual ZIP/wheel-shaped bytes for clean text, marker-creating Python/report
snippets retained as inert data, known credential/key canaries and private names.
It covers original stored-name aliases, traversal/collision/type/encryption,
unsupported nested/binary/metadata/JSON, digest tampering, actual size/count/
ratio limits, forged local+central sizes/CRC, exact deflate EOF and trailing/
concatenated streams, superscript aliases, malformed ZIP, safe isolated script
JSON, source/file/directory symlinks and an actual Windows junction when the host permits creation.

The captured-snapshot fixture swaps the on-disk archive after capture to prove
hashing/parsing use the same bytes. Other fixtures compare archive/consumer/.git
and original source/index/HEAD bytes around read-only inspection; no marker is
created by source snippets. These tests prove executable/filesystem boundaries,
not LLM/host obedience, every OS's sandbox, archive authenticity, all-secret
absence, production liveness or a successful external publication. The security acceptance suite provides
separate independent gate verification. Deterministic bundles, reproducible
wheels/native binaries and installation/rollback are outside this task.
