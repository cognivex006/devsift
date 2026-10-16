# Release-candidate readiness check

`tools/check_release_readiness.py` is a bounded, read-only composition of the
source-bundle verifier and artifact security inspector. It requires an explicit
bundle directory, full source commit SHA and independently trusted SHA256 of
`integrity.json`:

```text
python -B tools/check_release_readiness.py --bundle <absolute-bundle-directory> --source-sha <trusted-commit-sha> --integrity-sha256 <trusted-integrity-sha256>
```

The verifier checks the expected source identity, integrity digest, all bundle
checksums, archive bytes and declared members without extracting them. Each
archive then receives the existing bounded ZIP text/known-shape inspection.
The output distinguishes completed checks from release blockers. Even when all
checks complete, the result says `checks_passed_release_blocked`, keeps
`release_ready` and `publication_authorized` false, and lists owner license
approval, signing evidence, hosted CI evidence and release review as pending.
License approval is currently unresolved; this tool does not select a license
or infer owner approval.

The canonical candidate dependency/input sources are `pyproject.toml`,
`packaging/manifest.json`, and the component-specific native project and lock
files listed in [RELEASE-CHECKLIST.md](RELEASE-CHECKLIST.md). A release-specific
SBOM and license evidence still need to be prepared from the actual candidate;
this readiness check does not generate either. Preserve `NOASSERTION` for a
license value that has not been determined in an SBOM format that supports it.
That value reports uncertainty and does not constitute approval.

The Python project currently declares version `0.0.0.dev0`, no runtime
dependencies, and setuptools `83.0.0` as its build requirement. Those facts do
not represent the native source asset dependency graph. Use the checked-in
NuGet, Go, and npm project/lock inputs for those components rather than copying
dependency versions into this document.

The source SHA identifies Git objects and the expected integrity digest binds
bundle bytes only when both values are independently trusted by the caller.
Checksums do not authenticate an origin, reviewer or publisher. A clean scoped
archive inspection covers supported ZIP text and recognized sensitive shapes;
it does not inspect nested archives, compiled files, license suitability,
signatures, native availability or every release policy. No finding does not
grant approval. This command does not build, install, execute, download, sign,
publish, tag or change a version, and its result grants no publication
authority.

See [RELEASE-DRAFT.md](RELEASE-DRAFT.md) for non-final notes and
[RELEASE-CHECKLIST.md](RELEASE-CHECKLIST.md) for unchecked preparation and
evidence requirements. T070's accepted selected-bundle checks do not establish
four-component dry-run completion; T072 is planned for that work.
