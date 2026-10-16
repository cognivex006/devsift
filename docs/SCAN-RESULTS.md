# Trusted scan coordination and failure aggregation

`devsift.scanner.scan(root, candidates=None, *, adapters=(), policy=None,
redactor=None)` returns the version `1.0` machine envelope from `output.result`.
It inventories the full repository or exactly the supplied incremental file paths,
negotiates one declared capability per ready source, executes the selected trusted
adapter, verifies findings and applies the accepted policy. No native analyzer is
registered by default. Without an available registered analyzer, even an empty
scope returns incomplete (2), never a fabricated clean result.

```python
from devsift.adapters import AdapterCapability
from devsift.scanner import AdapterOutcome, scan

class TrustedFixture:
    capability = AdapterCapability('fixture-python', '1', ('python',), True)

    def analyze(self, target):
        # A real adapter must actually analyze target.content before declaring
        # completeness. This fixture demonstrates only the call contract.
        return AdapterOutcome(complete=True)

record = scan('/path/to/repository', ['src/example.py'], adapters=(TrustedFixture(),))
```

`Adapter` is a structural protocol exposing `capability` and
`analyze(SourceTarget) -> AdapterOutcome`. The source snapshot is frozen and
contains immutable bytes. Capability identities must be unique and capabilities
must be real `AdapterCapability` instances. Adapter input collections and findings
are tuples. Negotiation selects an available match before unavailable matches,
then sorts by stable identity/version; targets are visited by canonical path.
Findings sort by path, case ID and rule ID. An adapter returning a dictionary,
foreign outcome, nonboolean completeness, mutable findings, or throwing an
exception is incomplete. Exceptions, stderr and arbitrary object representations
are never included in public errors.
Accidental Python stdout/stderr emitted during `analyze` is discarded without
retaining a buffer. This synchronous coordinator redirects process-global Python
streams, so callers must serialize scan execution with other stream-sensitive
work. This is output hygiene, not isolation of file descriptors or subprocesses.

`AdapterOutcome(complete, findings=())` is frozen and requires an actual boolean.
`ScanFinding(case_id, rule_id, source, message='', lifecycle_class='UNKNOWN')` is
frozen, validates the catalog rule and requires a real `SourceEvidence`. The
message and evidence are omitted from its debug representation. Lifecycle
attribution is a trusted upstream caller/adapter assertion, not something the
coordinator infers from a touched file. The future Git classifier can supply
region-aware attribution; this coordinator does not implement a baseline or
reclassify an entire changed file as NEW. UNKNOWN remains incomplete.

For every claimed verified finding, the coordinator checks its path matches the
actual target, re-runs immutable commit/region verification with the scan's
Redactor, and compares the **entire raw source snapshot** against the immutable
Git blob ID. Git SHA-1 and SHA-256 object formats are supported. It also inventories
the file again after adapter execution to detect changes since capture. A stale
commit with different file bytes, unresolved source, missing current file, or
wrong target cannot block or pass. CRLF conversion or any other raw-byte
difference intentionally yields incomplete until consistent source is supplied.
Only the freshly verified source object is serialized; adapter-provided excerpts
are not trusted. Masked BEFORE excerpts are never compared to raw snippet hashes:
verification retains the accepted full-context redaction behavior, including a
selected region overlapping just part of a secret.

Policy decisions use that source verification result. Verified introduced findings
can block, verified legacy remains advisory or security review, and unknown or
unverified findings remain incomplete. Even if some findings block, any failed
adapter, unavailable language, unresolved finding, source error, or incomplete
outcome makes the final exit code 2. Independently proven blocking findings remain
visible in `enforced_count`. Completed analysis with only advisory findings or no
findings returns 0; completed analysis with blocking findings returns 1.

Public `data.targets` exposes `path`, inventory `status`, `language`, `byte_count`,
`execution_status`, `adapter_id`, and `adapter_version`, never raw source bytes.
Execution statuses distinguish `executed`, `skipped`, `unavailable`, and
`incomplete`. `data.counts` reports those categories: `executed` counts adapters
that returned valid outcomes, including valid incomplete outcomes; `incomplete`
counts unresolved/failed targets, so these two counters can overlap. Explicit
unsupported, binary and excluded inventory entries are skipped. Errors carry
fixed codes/messages. The scan Redactor masks untrusted target paths, adapter
identities, case IDs and messages; verified excerpts were masked in full source
context using that same Redactor. Protocol keys and fixed status values retain
their machine meaning. A final bounded default redaction pass validates the tree.
If safe redaction itself fails, the output is a minimal static incomplete error.
This is a coordination result, not the full later Markdown/SARIF report contract.

The coordinator's filesystem operations are read-only and Git lookups disable
optional locks/replacement objects. Injected Python adapters are trusted code:
they can still write files, access the network, hang or terminate the process.
Immutable inputs and source-drift detection cannot sandbox arbitrary callbacks or
undo their side effects. Process isolation, resource limits and native adapter
integrity belong to later analyzer-host work. Tests use controlled injected
fixtures, real temporary Git repositories and directory/file snapshots. For cold
package-tree no-write guarantees, retain the CLI's documented Python `-B` or
`PYTHONDONTWRITEBYTECODE=1` launch setting.

## Exit zero and independent security review

Exit 0 means the run completed with no **enforced gate violations**. It does not mean no findings or no urgent follow-up. A verified unchanged legacy Critical security finding remains nonblocking while retaining `enforcement: security_review` and `security_escalation: true` in its finding. Consumers must route that explicit flag to the independent security-review workflow; scanning does not authorize a fix. Any unresolved evidence/tool failure still takes precedence as incomplete 2.

## CLI integration

The `scan` command invokes this coordinator with no registered native adapters. `--all` inventories the working directory; `--changed` requires the Git root and inventories the union of staged differences from HEAD, unstaged differences from the index, and untracked paths (Git ignore rules apply to untracked files). Selected paths are analyzed from their current working-tree bytes, not staged blobs. A staged change canceled by an unstaged revert is still selected. This selection is not immutable finding classification. Deleted paths are explicit missing/incomplete targets. Missing HEAD, non-root/non-Git scope or unavailable Git yields `GIT_SCOPE_UNAVAILABLE`, never a fabricated empty clean scan. No branch baseline or policy configuration is silently discovered or written.

Git candidate selection disables external diff, textconv, fsmonitor, optional locks, replacement objects and lazy fetching, with bounded output and timeouts. Source snippets/byte contents and Git stderr are never serialized into the target inventory. Native providers, complete Markdown/JSON/SARIF reports and per-case remediation remain later tasks.

Git diff may invoke clean or process conversion filters even when external diff
and textconv are disabled. Before querying candidates, the CLI reads effective
configuration with `git config --includes --null --list`, including system,
global, repository/worktree, included and environment command scopes. It extracts
only driver names, preserving case, and passes explicit subprocess argument
overrides disabling every discovered driver's clean/process/smudge commands and
setting required=false on both staged and unstaged diff queries. Configuration
values and Git stderr are never echoed. This does not modify Git configuration,
the index or the source tree. Failure to read valid bounded configuration yields
incomplete scope rather than running an unprotected diff. Configuration and
environment must remain stable for the duration of the query; this is not a
sandbox against concurrent hostile Git-config replacement. Disabling conversions
can conservatively overselect LFS/normalized files, while downstream inventory
continues to read exact current working-tree bytes. Tests use real hostile clean
and process commands with required=true across local, environment and globally
included scopes, and compare directory entries plus full source/.git bytes.
