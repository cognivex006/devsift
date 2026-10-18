# Read-only source inventory and adapter capability interface

These producer interfaces enumerate source and negotiate capabilities. They do
not run analyzers, classify Git changes, render findings, or connect to the CLI.
Inventory completeness is never a quality-gate pass. The scan coordinator runs
explicitly configured trusted adapters; no native analyzer is registered by
default. See [native protocol](NATIVE-PROTOCOL.md) for execution boundaries.

Generated scanner output uses a bounded200,000-node redaction profile, sufficient
for large inventories containing many small entries. Generic/untrusted redaction
retains its20,000-node default. Both profiles retain2,000,000 cumulative string
characters, depth32, cycle/type checks, sensitive-key masking and key-collision
refusal. No failed redaction returns raw data. Error categories are deduplicated
in first-seen order while per-target statuses and exact outcome counts remain.

```python
from devsift.inventory import inventory
from devsift.adapters import negotiate

snapshot = inventory('/path/to/repository', ['src/example.ts'])
for target in snapshot.targets:
    decision = negotiate(target)  # recognized source => unavailable
```

`inventory(root, candidates=None, *, max_bytes=4194304)` returns frozen `Inventory`
with `mode` (`all` or `incremental`), a sorted tuple of frozen `SourceTarget`
records, and a derived `complete` property. Targets have `path`, `status`,
`language`, `content` and `reason`. Content is immutable bytes, never a writable
file handle. Ready targets retain original bytes; NUL-containing recognized source
is `binary` with no content. Unsupported extensions are skipped without reading.
Recognized extensions cover C#, TypeScript/TSX, JavaScript/JSX, Go, SQL and Python.
Language detection identifies file type only; it does not prove parser support.
Raw bytes are excluded from dataclass debug representations because source may
contain secrets. Consumers must not serialize raw content into diagnostics;
summary serializers should expose only path/status/language/byte counts. A frozen
snapshot is internal analysis input, not a redacted public report.

Full inventory traverses entries deterministically. Explicit candidates inventory
exactly the deduplicated listed file paths; directories are not expanded. An empty
candidate list is an empty incremental inventory, not a full scan. Paths use
canonical relative POSIX spelling and sort by that spelling. Absolute, drive,
UNC, backslash, traversal, dot, empty, alternate-stream, control-character,
Windows-reserved and other nonportable path forms raise `ValueError` before
candidate reads. A root must be an existing non-link directory. Noncanonical
names encountered during full traversal produce an `unsafe` diagnostic on their
containing directory; `.` denotes a root diagnostic, not a source file location.

Metadata, dependencies, caches and common build output directories are pruned:
`worktrees`, `.git`, `.hg`, `.svn`, `.venv`, `venv`, `node_modules`, `__pycache__`,
`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `build`, `dist`, `coverage`,
`.devsift`, `bin`, `obj`, `target`, `.next`, `.nuxt`, `.angular`, `.gradle`, `.cache`.
The fixed exclusion names compare case-insensitively on all platforms. Each
encountered excluded root has an explicit `excluded` target. Explicit candidates
under an excluded root also return `excluded` without reading them. This fixed
scope is not Git ignore interpretation or a configurable policy yet.

| Target status | Meaning | Inventory complete allowed |
| --- | --- | --- |
| ready | Recognized immutable source bytes available | yes |
| unsupported | Extension has no supported language detection | yes |
| binary | Recognized source contains NUL bytes | yes |
| excluded | Outside declared inventory scope | yes |
| unsafe | Link, junction or noncanonical entry | no |
| unreadable | Enumeration, metadata or content read failed | no |
| missing | Explicit candidate disappeared or does not exist | no |
| not_file | Explicit candidate is a directory or special file | no |
| too_large | Source exceeds the configured per-file byte limit | no |

`complete` means all requested enumeration work resolved or explicitly skipped.
It says nothing about analysis coverage or findings. A supported source with no
analyzer remains unavailable even when enumeration is complete. Missing/deleted
candidates need later Git-aware interpretation; they are not silently ignored.

`AdapterCapability(adapter_id, version, languages, available)` is frozen and
requires nonempty identity/version strings, a nonempty tuple of unique known
languages and an actual boolean availability. These are trusted declarations,
not discovery results. `negotiate(target, capabilities=())` returns frozen
`AdapterDecision(path, language, status, adapter_id, version, reason)`. Duplicate
adapter identities are rejected. Matching available capabilities take precedence,
then identity/version ordering makes selection deterministic. `supported` means
eligible for a future invocation; it never means analyzed, complete or clean.
No matching capability, or a declared unavailable capability, yields
`unavailable`; explicit unsupported/binary/excluded inputs yield `skipped`;
unresolved source yields `incomplete`.

`SourceView` describes the immutable-snapshot input boundary for future adapters.
No Python callback or external executable runs during negotiation. A future
trusted in-process Python adapter can still access the filesystem through Python;
immutable inputs cannot sandbox arbitrary code. Process isolation, resource limits
and analyzer integrity belong to later adapter-host work. Source reads reject
links and junctions, use no-follow/nonblocking opens where the platform provides
them, and reject nonregular files. This is a stable-repository read contract,
not protection against an attacker concurrently replacing ancestor directories.
No command writes files, accesses a database, or transfers source over a network.
