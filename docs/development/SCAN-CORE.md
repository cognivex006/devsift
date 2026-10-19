# Read-only source inventory and adapter capability interface

Inventory interfaces enumerate source and negotiate capabilities. Enumeration
alone does not execute analysis or establish findings. Inventory completeness
is never a quality-gate pass. The scan coordinator runs
trusted adapters. Library calls require explicit configured adapters; the new
source CLI resolves already registered user trust by default. Only explicit
installer/setup actions create that registration; no scan discovers target
manifests or performs network setup. See [native protocol](NATIVE-PROTOCOL.md)
for execution boundaries.

Registry resolution and human report language are Unreleased. Ordinary skill
project-check intent selects full scope, while changed scope requires an explicit
changes request. Output must distinguish readiness, actual analyzed coverage and
human report delivery: zero executed files is not a completed lint. Sessions keep
all cases; `data.report_bundle.report` names the direct human REPORT.md and
`reports_complete` does not promote incomplete analysis or unresolved evidence.

Generated scanner output masks each target and finding independently, with a
separate bounded envelope. Repository cardinality does not consume a cumulative
redaction budget. Each item retains the generic 20,000-node, 2,000,000-character,
depth 32, cycle/type, sensitive-key and key-collision checks. Failed individual
redaction never returns raw data. Error categories are deduplicated in first-seen
order while per-target statuses and exact outcome counts remain.

The CLI uses `iter_inventory` / `iter_scan` and the `scan_store` SQLite session,
not the aggregate compatibility API. Each iterator first emits a targetless
current-readiness control envelope; cached results cannot hide current provider
failure. Sources are read one at a time, without a repository-sized content list
or sorted directory materialization. One target's AST/content and diagnostics may
still require per-file memory. Generic `inventory` / `scan` retain their embedded
compatibility snapshot contracts.

The session is outside source, privately created, and locked for one writer.
Only safe records plus hashed raw path/snapshot identities are persisted. A new
generation revalidates root/configuration/current source, retries incomplete or
changed targets, and removes deleted-target coverage only after enumeration.
Cross-target duplicate case IDs remain explicit errors. Per-target transactions
survive cancellation; cached and fresh target counts are separate. Raw source
snapshots are never persisted by this journal.

`report_bundle` consumes safe findings in adaptive pages through the unchanged
bounded untrusted report model/exporters. There is no aggregate case or report
size cap. Every page has requested rendered formats and a bounded `scan.json`
for case prompts; SQLite tracks exact page/case coverage and checksums. Missing
or unrendered artifacts make `reports_complete` false independently of analysis
status. Public JSON arrays stream from SQLite, and the exit code is the exact
one encoded in that output snapshot. `--summary` emits compact counts/index.

Completion-mode file transport and source proof have no source-processing wall
deadline; cancellation, contained-child cleanup and fixed-shape validation remain.
Full source proof retains byte-exact Git identity, strict UTF-8, physical LF/CRLF
coordinates and full-context masks. Huge excerpts become a whole mask, never a
partially truncated credential or a missing case. Generic imported documents
retain finite validation budgets and do not inherit fresh execution authority.

Verification includes synthetic 100,000-target output, real 16,000-path CLI/CI,
all four native helpers above 2 MB / 1,000 diagnostics, 1,205 actual templated
cases across all formats, cancellation/resume/revalidation, provider loss on
all-cache resume, ownership and terminal screen-state checks. These verify
cardinality/retention and explicit rules, not comprehensive language semantics.

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
These inventory/capability APIs do not write files, access a database or transfer
source over a network. CLI session/report I/O is the separate owned storage layer
described above.
