# Repository-local policy data

`devsift.project_policy.discover_policy(repo_root, *, policy_path=None)` reads one
project JSON data file. Its default path is `.devsift/policy.json` beneath the
explicit repository root. An optional explicit path must be repository-relative,
use forward slashes and end in `.json` (case-insensitive). There is no ancestor,
global, recursive or environment-based policy search. This library does not wire
automatic discovery into the CLI.

```python
from devsift.project_policy import discover_policy
from devsift.policy import decide

resolution = discover_policy("/explicit/project/root")
if resolution.complete:
    policy = resolution.policy()  # fresh full defaults + validated project layer
    decision = decide("HC001", "UNKNOWN", source_verified=False, policy=policy)
    assert decision.enforcement == "incomplete"
```

Only an absent default path uses built-in policy defaults. A present malformed
file, unavailable/unsafe root, explicit missing path, invalid data or rejected
filesystem object produces an incomplete resolution with `policy() is None`.
Such failures must not silently fall back to defaults. A missing parent `.devsift`
directory counts as an absent default; a symlink/reparse parent does not.

`ProjectPolicyResolution` is a frozen factory-produced snapshot. `complete` and
the serialized `resolution_complete` mean **configuration resolution complete**,
never analyzer execution, analysis completeness, quality-gate pass or editing
authority. `write_authorized` and `execution_authorized` are always false.
`policy()` and `to_dict()` return fresh independent structures. A valid captured
file has its canonical repository-relative path and SHA256 of exact raw bytes;
the defaults-only result has neither. Invalid JSON read from a safe file may
retain its relative path and raw hash for diagnosis without exposing its contents.
Hashes are provenance, not authentication or a guarantee that the file remains
current. A private canonical root/file identity binding is retained for future
consumers, but no open descriptor/handle or absolute root is published. Serialization
cannot restore factory proof. Consumers requiring a current policy must resolve
again and compare provenance; this module does not watch files or enforce approval.

JSON must be UTF-8 with no BOM. The accepted G001 duplicate-key/nonfinite hooks
and `resolve_policy` validate the project layer strictly before merging defaults.
Unknown fields, including permission, executable, native provider or command
configuration, are invalid. Policy data never grants executable trust. Limits are
65,536 raw bytes, nested container depth 16 and finite numeric tokens of at most
32 characters within signed-64 magnitude. Numeric values still must satisfy the
existing policy schema, which currently accepts no numeric policy settings.
Booleans cannot masquerade as schema versions, severity names or block lists.
No policy schema, registry or rule-severity semantics are broadened here.

The reader inspects/opens original components before canonicalizing them. It
rejects traversal, absolute/drive/stream forms in policy paths, controls, `.git`
components, symlinks/reparse points, non-regular files and recognized credential
shapes in public relative paths. Canonical containment is checked after guarded
opening, so legitimate Windows 8.3 aliases are normalized rather than rejected by
a lexical comparison against long names. These are bounded shape checks, not
comprehensive secret detection or an OS sandbox.

On Windows, directory handles use `OPEN_REPARSE_POINT` and deny delete sharing,
preventing component rename/replacement while reading. The regular-file handle
also denies write sharing. Every handle is checked for disk type and reparse/
directory attributes. POSIX walks from the filesystem anchor with directory fds
and `O_NOFOLLOW`, then reads the final regular file through its descriptor; final
component identities are checked against the opened objects. File identity,
size and modification time must remain stable across the bounded read. Handles
and descriptors close on success, missing paths, invalid data and resource errors.
Legitimate concurrent writes or incompatible sharing may cause incomplete results.

No process, target code, loader hook, HTTP client, installation, remote fetch,
native-provider discovery, source/index/configuration write or dependency on the
doctor module is involved. An explicitly managed share-mounted root is ordinary
operator-selected filesystem input, not permission to fetch remote configuration.
Failure reasons are fixed codes without supplied paths, values or exception text.

Tests use real files for absent/default/explicit layers, strict invalid JSON,
source preservation, symlink rejection and handle release. Windows tests exercise
the actual handle-sharing reader and short aliases when the filesystem provides
them. The POSIX descriptor race test runs on POSIX; running Windows tests does not
claim POSIX execution. Actual `decide` calls retain legacy advisory, UNKNOWN
incomplete and independent Critical security escalation after project overrides.
