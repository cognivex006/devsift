# DevSift 0.1.14 release notes

Version `0.1.14` is selected and publication authorized by the project owner.
The tag is `v0.1.14`. Package and agent plugin manifests use the same version.

## Changes

- Fix REDACTION_FAILED on large scan inventories while preserving bounded masking
  and fail-closed serialization. Generic/untrusted redaction keeps its default.
- Retain all per-file coverage/counts and deduplicate fixed error categories.
- Keep incomplete results usable for reports; no analyzer availability or source
  verification is fabricated and no target code is built or modified.
- Fix skill reference resolution and clarify direct read-only execution, actual
  exit2 envelopes, report language and large-output handling.

## Distribution and limitations

Python 3.12 or newer is required. Native analyzer binaries are not bundled;
trusted native setup is separate. Persisted `report --latest` and `explain`
storage remain unavailable. Live loading in every AI host has not been verified.

The owner authorized publication without selecting a project license. No new
license is declared and artifact inventory records `NOASSERTION`. SHA256 files
provide integrity checks; this release does not claim cryptographic signatures.
Release assets include the installer bundle/scripts, wheel, source distribution,
consumer/source components and source/integrity records.
