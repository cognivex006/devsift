# DevSift 0.1.12 release notes

Version `0.1.12` is selected and publication authorized by the project owner.
The tag is `v0.1.12`. Package and agent plugin manifests use the same version.

## Changes

- Use `devsift --help`, `devsift doctor` and `devsift scan --changed` directly.
- Add Windows PowerShell and macOS/Linux install and update scripts with a
  checksum-verified bundle and a private Python environment.
- Install consumer skills for Codex, Claude Code, Gemini CLI, Antigravity and
  Cursor; bundle offline usage guides and host plugin/extension metadata.
- Separate consumer guides, command reference and developer documentation.
- Keep source analysis read-only and preserve incomplete/UNKNOWN results.

## Distribution and limitations

Python 3.12 or newer is required. Native analyzer binaries are not bundled;
trusted native setup is separate. Persisted `report --latest` and `explain`
storage remain unavailable. Live loading in every AI host has not been verified.

The owner authorized publication without selecting a project license. No new
license is declared and artifact inventory records `NOASSERTION`. SHA256 files
provide integrity checks; this release does not claim cryptographic signatures.
Release assets include the installer bundle/scripts, wheel, source distribution,
consumer/source components and source/integrity records.
