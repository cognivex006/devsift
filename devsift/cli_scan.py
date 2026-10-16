"""Read-only CLI scope selection; analysis requires registered native adapters."""
import os
from pathlib import Path
import subprocess

from .output import result
from .scanner import scan


def _git(root, *arguments, config=()):
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1",
                       GIT_NO_LAZY_FETCH="1", GIT_LITERAL_PATHSPECS="1",
                       GIT_TERMINAL_PROMPT="0")
    process = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root),
         *config, *arguments], env=environment, capture_output=True, timeout=10,
    )
    if process.returncode or len(process.stdout) > 2_000_000:
        raise ValueError("Git scope unavailable")
    return process.stdout


def _filter_config(root):
    """Disable every effective conversion driver, without running any driver.

    Includes, global/worktree config and environment command-scope settings are
    resolved by Git itself. Only keys are interpreted; values never leave this
    helper. Explicit command-line overrides take precedence over those scopes.
    """
    effective = _git(root, 'config', '--includes', '--null', '--list')
    drivers = set()
    for entry in effective.split(b'\0'):
        if not entry:
            continue
        key = entry.split(b'\n', 1)[0].decode('utf-8')
        if key.lower().startswith('filter.') and '.' in key[7:]:
            driver, _ = key[7:].rsplit('.', 1)
            if not driver or any(ord(char) < 32 for char in driver):
                raise ValueError('Git scope unavailable')
            drivers.add(driver)
    return tuple(argument for driver in sorted(drivers)
                 for option, value in (('clean', ''), ('process', ''), ('smudge', ''), ('required', 'false'))
                 for argument in ('-c', f'filter.{driver}.{option}={value}'))


def changed_candidates(root):
    """Read changed Git paths with every conversion/external callback disabled."""
    origin = Path(root).resolve(strict=True)
    top = Path(_git(origin, "rev-parse", "--show-toplevel").decode("utf-8").strip())
    if top.resolve() != origin:
        raise ValueError("Git root required")
    filter_config = _filter_config(origin)
    diff_options = ("--no-ext-diff", "--no-textconv", "--no-renames", "--name-only", "-z")
    staged = _git(origin, "diff", "--cached", *diff_options, "HEAD", "--", config=filter_config)
    unstaged = _git(origin, "diff", *diff_options, "--", config=filter_config)
    untracked = _git(origin, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted({path.decode("utf-8") for path in
                   staged.split(b"\0") + unstaged.split(b"\0") + untracked.split(b"\0") if path})


def run_scan(root, *, all_scope=False, legacy_mode="recommend", native_manifest=None, native_manifest_digest=None,
             security=False):
    """Changed scope unions staged, unstaged and untracked file paths.

    This selects candidates, not finding lifecycle attribution. Deleted files
    stay explicit incomplete targets. Only an explicit trusted manifest enables native tools.
    """
    candidates = None
    if not all_scope:
        try:
            candidates = changed_candidates(root)
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            return result("scan", complete=False,
                          errors=[{"code": "GIT_SCOPE_UNAVAILABLE",
                                   "message": "Changed scope requires a Git repository root and readable HEAD."}],
                          data={"scope": "changed", "legacy_mode": legacy_mode,
                                "mode": "incremental", "targets": []})
    adapters, native = (), ()
    if native_manifest is not None or native_manifest_digest is not None or security:
        from .native_manifest import load_manifest
        from .native_host import NativeAdapter
        try:
            # All entries must validate before the first NativeAdapter probes.
            if type(security) is not bool:
                raise ValueError('Invalid security configuration')
            configured = (load_manifest(native_manifest, native_manifest_digest)
                          if native_manifest is not None or native_manifest_digest is not None else ())
            origin = Path(root).resolve(strict=True)
            top = Path(_git(origin, 'rev-parse', '--show-toplevel').decode('utf-8').strip()).resolve()
            head = _git(origin, 'rev-parse', '--verify', 'HEAD^{commit}').decode('ascii').strip()
            import re
            if top != origin or re.fullmatch('(?:[0-9a-f]{40}|[0-9a-f]{64})', head) is None:
                raise ValueError('Immutable root source required')
            native = tuple(NativeAdapter(entry.tool, repo_root=origin, source_sha=head,
                                           dialect=entry.dialect) for entry in configured)
            adapters = native
            if security:
                from .security_adapter import SecurityAdapter
                from .adapters import AdapterCapability, LANGUAGES
                composed = [SecurityAdapter(delegate, repo_root=origin, source_sha=head) for delegate in native]
                covered = {language for delegate in native for language in delegate.capability.languages}
                missing = tuple(sorted(LANGUAGES - covered))
                if missing:
                    standalone = SecurityAdapter(repo_root=origin, source_sha=head)
                    original = standalone.capability
                    standalone.capability = AdapterCapability(original.adapter_id, original.version, missing, original.available)
                    composed.append(standalone)
                adapters = tuple(composed)
        except (OSError, ValueError, TypeError, UnicodeError, subprocess.SubprocessError):
            return result('scan', complete=False, errors=[{'code': 'NATIVE_MANIFEST_UNAVAILABLE',
                          'message': 'Native manifest or immutable source configuration is unavailable.'}],
                          data={'scope': 'all' if all_scope else 'changed', 'legacy_mode': legacy_mode, 'targets': []})
    record = scan(root, candidates, adapters=adapters)
    if any(not adapter.probe.available for adapter in native):
        record.update(complete=False, status='incomplete', exit_code=2)
        record['errors'].append({'code': 'NATIVE_TOOL_UNAVAILABLE', 'message': 'A configured native tool is unavailable.'})
    record["data"].update(scope="all" if all_scope else "changed", legacy_mode=legacy_mode)
    return record
