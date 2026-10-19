# Installer assets

## Lint-ready setup contract (0.1.16 candidate)

The new normal installer is responsible for deploying a verified version/platform
analyzer companion and registering user-level native trust before declaring
analysis ready. Python 3.12+ is an installation prerequisite; actual immutable
source proof also needs trusted Git. Companion runtimes avoid separate .NET SDK,
Go and Node/npm toolchain setup on the consumer machine. Do not claim support for
platform/architecture assets that have not actually been built and validated.

When not embedded, the installer downloads the version-pinned
`devsift-analyzers-PLATFORM-ARCH.zip` and its `.sha256` during authorized setup,
not during scan. Verify bytes/layout/pins before rebasing accepted paths into an
owned installation. Preserve the prior CLI if native preflight fails. Explicit
`--core-only` must report analysis not configured rather than unqualified Ready.

CLI `setup` registers a reviewed manifest/digest once or installs an explicitly
trusted offline analyzer bundle. The fixed user registry is
`~/.local/share/devsift/analyzers.json`; no target search or project configuration
creates native trust. Default scan/doctor/ci resolve this registration; explicit
paired flags validate first and override it without mutating it. `setup --status`
is read-only readiness metadata. Installation, registry changes and companion
updates remain separate from target analysis and never authorize target builds.

Human report generation adds `--report-language en|th` and the direct
`data.report_bundle.report` path to session-root `REPORT.md`. Keep every case and
all proof/UNKNOWN states; a folder or JSON alone is not the user-facing lint
deliverable. Candidate metadata targets 0.1.16; it does not itself authorize
publication or assert that pending platform/release gates passed. See the
[candidate notes](RELEASE-DRAFT.md) and [release checklist](RELEASE-CHECKLIST.md).

The platform release plan includes Windows/Linux/macOS x64 and arm64 ZIPs and
checksums. Only actually built/validated assets may be published as supported;
record cross-build versus native-run evidence separately. The fresh normal
Windows installation acceptance passed real four-language analysis and full Thai
report delivery without SDK PATH entries or repeated native flags. It does not
stand in for the pending final platform matrix and candidate artifact audit.

`tools/build_installer.py --output dist/installer` builds a wheel using the declared
build backend, then packages the consumer skill, its offline references, host
manifests and Python bootstrap in `devsift-install.zip`. It also emits a SHA256
file and Windows/POSIX install and update scripts. It does not publish anything.
Use a trusted checkout and provision `setuptools==83.0.0` and `wheel` first.
The consumer guides must be synchronized and all selected inputs tracked in Git.

## Physical paths and interrupted report ownership

Canonicalize trusted temporary staging roots and every manifest path slot before
checking companion containment. macOS `/var` aliases and Windows 8.3 temporary
names can otherwise make a physically contained executable appear external after
`ProcessSpec` resolves its path. Retain the physical inside-payload check and
frozen hashes; accepting lexical prefixes or weakening the check is unsafe.
Companion smoke checks must still execute all four helpers and verify exact AST
rules and source spans. Keep bounded, masked build diagnostics for failed CI jobs.

Windows report storage can exceed MAX_PATH even for an ordinary user home. Use
the extended filesystem namespace for deep owned sessions, normalize both source
and destination namespaces for containment, and encode native SQLite filenames
correctly in read-only URIs. Never enable system-wide policy or allow a short
explicit `\\?\` destination to bypass the source read-only boundary.

Commit the old/new human-report ownership journal before replacing `REPORT.md`.
Recovery may adopt only its exact known hashes on a regular single-link file;
foreign edits, symlinks and hardlinks remain errors. Test interruption on both
sides of journal creation, replacement and final metadata publication.
Only the explicit consumer-skill allowlist and named plugin manifest files enter
the installer; unrelated files under `skills/` are excluded.

The manually dispatched `installer-assets.yml` workflow produces downloadable
build artifacts. After release authorization and the existing release checks,
attach all six generated files to the selected GitHub release. The public `/releases/latest/download/` commands use those release assets.
The maintainer selected candidate patch `0.1.16` under the owner's continuing GitHub
publication instruction: “ดำเนินการ released ขึ้น github เลยทันที”. The owner did
not explicitly select that exact version. The project license remains
unselected and no signature claim is made.

`tools/install.py` creates a private venv, installs the wheel offline, verifies
help and required native readiness, then switches the launcher. Explicit setup
uses a finite cold-runtime preflight; normal readiness/Doctor probes remain
short and finite. Installation never runs target-project code.
The launcher internally uses isolated Python with bytecode disabled; users and
skills invoke `devsift`. User skill installation and plugin import are distinct:
skills are copied to documented host paths; plugin bundles are staged for explicit
host import and never silently registered in a marketplace.

Failed pip/help checks preserve the old launcher. Environment directories are
retained for operator rollback. Skill/plugin copying and PATH changes are not a
multi-directory transaction; a filesystem failure during host directory replacement can
leave a partial host update while preserving the previous launcher. Re-run after correcting the error. Installer release
checksums detect corruption but do not authenticate a publisher independently.

Shell bootstraps own exactly two in-place rows. The top row labels measured
transfer percentage separately from overall setup milestones; the bottom row
shows spinner/current stage and transfer bytes when available. The verified
Python child emits the existing JSON-lines protocol and never writes UI frames.
Non-TTY output uses sparse bounded stages plus a final outcome.

Authoritative install templates and shared renderers are expanded by
tools/build_installer.py into all four scripts, including update. Checked-in
update templates are removed to prevent drift. See
[terminal implementation and native PTY checks](TERMINAL-UX.md).
GitHub publication continues under that owner instruction; final candidate review
and artifact verification still precede publication.

The development download-feedback rule is in [AGENTS.md](../../AGENTS.md) and
[DEVELOPMENT.md](../../DEVELOPMENT.md); it applies to schema and native setup too.
