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


def run_scan(root, *, all_scope=False, legacy_mode="recommend"):
    """Changed scope unions staged, unstaged and untracked file paths.

    This selects candidates, not finding lifecycle attribution. Deleted files
    stay explicit incomplete targets. The coordinator registers no native tools.
    """
    candidates = None
    if not all_scope:
        try:
            origin = Path(root).resolve(strict=True)
            top = Path(_git(origin, "rev-parse", "--show-toplevel").decode("utf-8").strip())
            if top.resolve() != origin:
                raise ValueError("Git root required")
            filter_config = _filter_config(origin)
            diff_options = ("--no-ext-diff", "--no-textconv", "--no-renames", "--name-only", "-z")
            staged = _git(origin, "diff", "--cached", *diff_options, "HEAD", "--", config=filter_config)
            unstaged = _git(origin, "diff", *diff_options, "--", config=filter_config)
            untracked = _git(origin, "ls-files", "--others", "--exclude-standard", "-z")
            candidates = sorted({path.decode("utf-8") for path in
                                 staged.split(b"\0") + unstaged.split(b"\0")
                                 + untracked.split(b"\0") if path})
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            return result("scan", complete=False,
                          errors=[{"code": "GIT_SCOPE_UNAVAILABLE",
                                   "message": "Changed scope requires a Git repository root and readable HEAD."}],
                          data={"scope": "changed", "legacy_mode": legacy_mode,
                                "mode": "incremental", "targets": []})
    record = scan(root, candidates)
    record["data"].update(scope="all" if all_scope else "changed", legacy_mode=legacy_mode)
    return record
