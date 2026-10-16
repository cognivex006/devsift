"""Select host Git explicitly; never execute a consumer project's Git lookalike."""
from functools import lru_cache
import os
from pathlib import Path


class GitRuntimeError(ValueError):
    """Constant failure; never expose host PATH or repository locations."""


def _outside(path, root):
    return not path.is_relative_to(root)


@lru_cache(maxsize=128)
def _discover(search_path, root_text):
    root=Path(root_text)
    if len(search_path)>32768 or len(search_path.split(os.pathsep))>512:
        raise GitRuntimeError('Trusted host Git is unavailable') from None
    name='git.exe' if os.name=='nt' else 'git'
    for item in search_path.split(os.pathsep):
        directory=Path(item.strip().strip('"')) if item.strip() else None
        if directory is None or not directory.is_absolute():
            continue
        try:
            candidate=directory/name
            if not _outside(candidate,root):
                continue
            executable=candidate.resolve(strict=True)
            if (_outside(executable,root) and executable.is_file()
                    and os.access(executable,os.X_OK)):
                return str(executable)
        except (OSError,ValueError,RuntimeError):
            continue
    raise GitRuntimeError('Trusted host Git is unavailable') from None


def git_executable(repo_root):
    """Use operator-configured absolute host PATH entries outside this repository.

    Empty/relative entries and resolved repository aliases are excluded. No PATH
    program is probed during discovery. This trusts the host installation, not
    executable bytes or hostile concurrent host changes; it is not a sandbox.
    """
    try:
        root=Path(repo_root).resolve(strict=True)
        selected=Path(_discover(os.environ.get('PATH',''),str(root))).resolve(strict=True)
        if not _outside(selected,root) or not selected.is_file():
            raise GitRuntimeError('Trusted host Git is unavailable')
        return str(selected)
    except (OSError,ValueError,TypeError,RuntimeError):
        raise GitRuntimeError('Trusted host Git is unavailable') from None
