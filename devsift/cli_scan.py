"""Read-only CLI scope selection; analysis requires registered native adapters."""
import os
from pathlib import Path
import subprocess

from .output import result
from .scanner import scan


def _git(root, *arguments):
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1",
                       GIT_NO_LAZY_FETCH="1", GIT_LITERAL_PATHSPECS="1",
                       GIT_TERMINAL_PROMPT="0")
    process = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root),
         *arguments], env=environment, capture_output=True, timeout=10,
    )
    if process.returncode or len(process.stdout) > 2_000_000:
        raise ValueError("Git scope unavailable")
    return process.stdout


def run_scan(root, *, all_scope=False, legacy_mode="recommend"):
    """Changed scope is tracked differences from HEAD plus untracked file paths.

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
            tracked = _git(origin, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                           "--name-only", "-z", "HEAD", "--")
            untracked = _git(origin, "ls-files", "--others", "--exclude-standard", "-z")
            candidates = sorted({path.decode("utf-8") for path in
                                 tracked.split(b"\0") + untracked.split(b"\0") if path})
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            return result("scan", complete=False,
                          errors=[{"code": "GIT_SCOPE_UNAVAILABLE",
                                   "message": "Changed scope requires a Git repository root and readable HEAD."}],
                          data={"scope": "changed", "legacy_mode": legacy_mode,
                                "mode": "incremental", "targets": []})
    record = scan(root, candidates)
    record["data"].update(scope="all" if all_scope else "changed", legacy_mode=legacy_mode)
    return record
