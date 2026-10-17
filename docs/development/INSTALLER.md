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
The owner selected and authorized release `0.1.12`; the project license remains
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

Shell bootstraps own one overall setup bar. Download ranges reflect actual
received bytes/Content-Length and expose a separate transfer percentage; unknown
lengths show bytes and `size unknown`. The verified Python bootstrap emits a
private JSON-lines progress protocol with stage/percent/elapsed events, a final
state, or an error. Shells consume these records without showing them as logs.
`tools/install_progress.py` also renders one-line progress for direct Python setup
and keeps pip output captured. No timer increases a percentage: heartbeat updates
only the spinner and elapsed time. Redirected human output contains a concise
final summary; structured protocol output is for the shell relay.

The development download-feedback rule is in [AGENTS.md](../../AGENTS.md) and
[DEVELOPMENT.md](../../DEVELOPMENT.md); it applies to schema and native setup too.
