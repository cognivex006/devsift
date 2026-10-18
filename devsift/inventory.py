"""Deterministic read-only source snapshots with explicit exclusions and failures."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import stat
from collections.abc import Iterable

from .adapters import LANGUAGES, detect_language

EXCLUDED = frozenset({'worktrees', '.git', '.hg', '.svn', '.venv', 'venv', 'node_modules',
                      '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
                      'build', 'dist', 'coverage', '.devsift', 'bin', 'obj',
                      'target', '.next', '.nuxt', '.angular', '.gradle', '.cache'})
_STATUSES = frozenset({'ready', 'unsupported', 'binary', 'excluded', 'unsafe',
                       'unreadable', 'missing', 'not_file', 'too_large'})
_COMPLETE = frozenset({'ready', 'unsupported', 'binary', 'excluded'})
_RESERVED = {'con', 'prn', 'aux', 'nul', 'conin$', 'conout$'} | {
    f'{s}{n}' for s in ('com', 'lpt') for n in (*range(1, 10), '¹', '²', '³')}


def _canonical(value: str) -> str:
    if (type(value) is not str or not value
            or any(c in value for c in '\\:<>"|?*')
            or any(ord(c) < 32 for c in value)):
        raise ValueError('Candidates must be canonical relative POSIX paths')
    parts = value.split('/')
    if any(part in {'', '.', '..'} or part.endswith((' ', '.'))
           or part.split('.')[0].rstrip(' ').lower() in _RESERVED for part in parts):
        raise ValueError('Candidates must be canonical relative POSIX paths')
    return value


@dataclass(frozen=True)
class SourceTarget:
    path: str
    status: str
    language: str | None
    content: bytes | None = field(repr=False)
    reason: str

    def __post_init__(self):
        if (type(self.status) is not str or self.status not in _STATUSES
                or (self.language is not None and
                    (type(self.language) is not str or self.language not in LANGUAGES))):
            raise ValueError('Invalid source status or language')
        if self.path != '.':
            _canonical(self.path)
        if self.content is not None and type(self.content) is not bytes:
            raise ValueError('Source content must be immutable bytes')
        if self.status == 'ready' and (self.language is None or self.content is None):
            raise ValueError('Ready source requires language and content')


@dataclass(frozen=True)
class Inventory:
    mode: str
    targets: tuple[SourceTarget, ...]

    def __post_init__(self):
        if (self.mode not in {'all', 'incremental'} or type(self.targets) is not tuple
                or any(not isinstance(target, SourceTarget) for target in self.targets)):
            raise ValueError('Inventory requires a known mode and immutable target tuple')

    @property
    def complete(self) -> bool:
        """Enumeration completeness only; this is never an analysis verdict."""
        return all(target.status in _COMPLETE for target in self.targets)


class _TooLarge(Exception):
    pass


def _read_bytes(path: Path, max_bytes: int | None) -> bytes:
    flags = (os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
             | getattr(os, 'O_NONBLOCK', 0))
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError('Not a regular source file')
        if max_bytes is not None and info.st_size > max_bytes:
            raise _TooLarge
        chunks = []
        remaining = None if max_bytes is None else max_bytes + 1
        while remaining is None or remaining:
            chunk = os.read(descriptor, 65536 if remaining is None else min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            if remaining is not None:
                remaining -= len(chunk)
        content = b''.join(chunks)
        if max_bytes is not None and len(content) > max_bytes:
            raise _TooLarge
        return content
    finally:
        os.close(descriptor)


def iter_inventory(root: str | Path, candidates: Iterable[str] | None = None,
                   *, max_bytes: int | None = None):
    """Yield one immutable snapshot at a time; never retain prior file contents.

    ``None`` removes the per-file byte cap for streaming consumers. Traversal is
    deterministic; only the compatibility ``inventory`` API globally sorts rows.

    Candidate paths are validated in full before reading any candidate. Symlinks
    and junctions are never intentionally followed. No Git classification is
    inferred from an incremental candidate list.
    """
    if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 1):
        raise ValueError('max_bytes must be a positive integer')
    origin = Path(root)
    if origin.is_symlink() or origin.is_junction() or not origin.is_dir():
        raise ValueError('Root must be an existing non-link directory')
    origin = origin.resolve()
    if isinstance(candidates, (str, bytes)):
        raise ValueError('Candidates must be an iterable of relative paths, not one string')
    paths = None if candidates is None else sorted({_canonical(p) for p in candidates})

    def record(relative, status, reason, content=None):
        return SourceTarget(relative, status, detect_language(relative), content, reason)

    def inspect(relative):
        parts = relative.split('/')
        if any(part.lower() in EXCLUDED for part in parts):
            yield record(relative, 'excluded', 'Excluded metadata, dependency or generated path')
            return
        path = origin
        try:
            for part in parts:
                path = path / part
                if path.is_symlink() or path.is_junction():
                    yield record(relative, 'unsafe', 'Symbolic links and junctions are not followed')
                    return
                path.lstat()
            if not path.is_file():
                yield record(relative, 'not_file', 'Candidate is not a regular file')
                return
            if detect_language(relative) is None:
                yield record(relative, 'unsupported', 'Unrecognized source extension')
                return
            content = _read_bytes(path, max_bytes)
            if b'\x00' in content:
                yield record(relative, 'binary', 'NUL-containing content is not supported text')
            else:
                yield record(relative, 'ready', 'Read-only immutable source snapshot', content)
        except FileNotFoundError:
            yield record(relative, 'missing', 'Candidate does not exist')
        except _TooLarge:
            yield record(relative, 'too_large', 'Source exceeds configured snapshot byte limit')
        except OSError:
            yield record(relative, 'unreadable', 'Source metadata or content could not be read')

    def walk(directory: Path, prefix=''):
        try:
            with os.scandir(directory) as scanner:
                entries = sorted(scanner, key=lambda entry: entry.name)
        except OSError:
            yield record(prefix or '.', 'unreadable', 'Directory could not be enumerated')
            return
        for entry in entries:
            relative = f'{prefix}/{entry.name}' if prefix else entry.name
            try:
                _canonical(relative)
            except ValueError:
                # Cannot safely expose a cross-platform canonical target path.
                yield record(prefix or '.', 'unsafe', 'Directory contains a noncanonical entry name')
                continue
            try:
                path = directory / entry.name
                if entry.name.lower() in EXCLUDED:
                    yield record(relative, 'excluded', 'Excluded metadata, dependency or generated path')
                elif entry.is_symlink() or path.is_junction():
                    yield record(relative, 'unsafe', 'Symbolic links and junctions are not followed')
                elif entry.is_dir(follow_symlinks=False):
                    yield from walk(path, relative)
                else:
                    yield from inspect(relative)
            except OSError:
                yield record(relative, 'unreadable', 'Directory entry could not be read')

    if paths is None:
        yield from walk(origin)
    else:
        for relative in paths:
            yield from inspect(relative)


def inventory(root: str | Path, candidates: Iterable[str] | None = None,
              *, max_bytes: int = 4 * 1024 * 1024) -> Inventory:
    """Compatibility snapshot API with its original per-file byte limit."""
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError('max_bytes must be a positive integer')
    return Inventory('all' if candidates is None else 'incremental',
                     tuple(sorted(iter_inventory(root, candidates, max_bytes=max_bytes),
                                  key=lambda target: target.path)))
