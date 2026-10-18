# Installer assets

`tools/build_installer.py --output dist/installer` builds a wheel using the declared
build backend, then packages the consumer skill, its offline references, host
manifests and Python bootstrap in `devsift-install.zip`. It also emits a SHA256
file and Windows/POSIX install and update scripts. It does not publish anything.
Use a trusted checkout and provision `setuptools==83.0.0` and `wheel` first.
The consumer guides must be synchronized and all selected inputs tracked in Git.
Only the explicit consumer-skill allowlist and named plugin manifest files enter
the installer; unrelated files under `skills/` are excluded.

The manually dispatched `installer-assets.yml` workflow produces downloadable
build artifacts. After release authorization and the existing release checks,
attach all six generated files to the selected GitHub release. The public `/releases/latest/download/` commands use those release assets.
The owner selected and authorized release `0.1.13`; the project license remains
unselected and no signature claim is made.

`tools/install.py` creates a private venv, installs the wheel offline, verifies
help, then switches the launcher. Installation never runs target-project code.
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
The owner authorized version 0.1.13 and GitHub publication.

The development download-feedback rule is in [AGENTS.md](../../AGENTS.md) and
[DEVELOPMENT.md](../../DEVELOPMENT.md); it applies to schema and native setup too.
