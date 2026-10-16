"""Bounded repository-local policy data discovery; never tool/code discovery."""
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import stat

from .policy import _invalid_constant, _unique_object, resolve_policy
from .redaction import Redactor

_DEFAULT = ".devsift/policy.json"
_MAX_BYTES = 65536
_SEAL = object()


class _Unsafe(ValueError):
    pass


class _Limit(ValueError):
    pass


class _Missing(Exception):
    def __init__(self, binding):
        self.binding = binding


def _require(condition):
    if not condition:
        raise _Unsafe() from None


def _relative(value):
    _require(type(value) is str and 0 < len(value) <= 1024)
    _require(not any(ord(char) < 32 or ord(char) == 127 or char in "\\:" for char in value))
    _require(all(part not in ("", ".", "..", ".git") for part in value.split("/")))
    _require(value.lower().endswith(".json") and Redactor().text(value) == value)
    return value


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read_fd(fd):
    before = os.fstat(fd)
    _require(stat.S_ISREG(before.st_mode))
    if before.st_size > _MAX_BYTES:
        raise _Limit()
    pieces = []
    total = 0
    while chunk := os.read(fd, min(8192, _MAX_BYTES + 1 - total)):
        pieces.append(chunk)
        total += len(chunk)
        if total > _MAX_BYTES:
            raise _Limit()
    after = os.fstat(fd)
    _require(_identity(before) == _identity(after) and total == after.st_size)
    return b"".join(pieces), _identity(after)


def _canonical(root, candidate):
    if os.name != "nt":
        # Every original absolute component was opened with O_NOFOLLOW. Avoid
        # resolving a new path through a replacement after that anchored read.
        return str(root), str(candidate), _relative(candidate.relative_to(root).as_posix())
    canonical_root = root.resolve(strict=True)
    canonical_file = candidate.resolve(strict=True)
    relative = _relative(canonical_file.relative_to(canonical_root).as_posix())
    return str(canonical_root), str(canonical_file), relative


def _read_posix(root, relative):
    """Walk original components from the filesystem anchor using nofollow fds."""
    descriptors = []
    observed = []
    root_chain = [Path(root.anchor)]
    for part in root.parts[1:]:
        root_chain.append(root_chain[-1] / part)
    candidate = root / relative

    def check_observed():
        for path, previous in observed:
            now = path.lstat()
            _require(not stat.S_ISLNK(now.st_mode) and (now.st_dev, now.st_ino) ==
                     (previous.st_dev, previous.st_ino))

    def missing():
        check_observed()
        raise _Missing((str(root), None, None, root_id)) from None

    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        for path in root_chain:
            fd = os.open(str(path) if not descriptors else path.name, flags,
                         **({"dir_fd": descriptors[-1]} if descriptors else {}))
            descriptors.append(fd)
            observed.append((path, os.fstat(fd)))
        root_id = _identity(os.fstat(descriptors[-1]))[:2]
        directory = root
        for part in relative.split("/")[:-1]:
            directory /= part
            try:
                fd = os.open(part, flags, dir_fd=descriptors[-1])
            except FileNotFoundError:
                missing()
            descriptors.append(fd)
            observed.append((directory, os.fstat(fd)))
        try:
            fd = os.open(candidate.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=descriptors[-1])
        except FileNotFoundError:
            missing()
        descriptors.append(fd)
        raw, file_id = _read_fd(fd)
        observed.append((candidate, os.fstat(fd)))
        canonical_root, canonical_file, public_path = _canonical(root, candidate)
        check_observed()
        return raw, public_path, (canonical_root, canonical_file, file_id, root_id)
    finally:
        failed = False
        for fd in reversed(descriptors):
            try:
                os.close(fd)
            except OSError:
                failed = True
        if failed:
            raise OSError()


def _read_windows(root, relative):
    """Reject reparse points and hold original components against replacement.

    Directory handles deny delete sharing (rename/replacement); file handles
    additionally deny write sharing. All are closed before returning a snapshot.
    """
    import ctypes as c
    from ctypes import wintypes as w
    import msvcrt

    class Info(c.Structure):
        _fields_ = [("attributes", w.DWORD), ("created", w.FILETIME),
                    ("accessed", w.FILETIME), ("written", w.FILETIME),
                    ("volume", w.DWORD), ("size_high", w.DWORD), ("size_low", w.DWORD),
                    ("links", w.DWORD), ("index_high", w.DWORD), ("index_low", w.DWORD)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p,
                                  w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [w.HANDLE, c.POINTER(Info)]
    kernel.GetFileInformationByHandle.restype = w.BOOL
    kernel.GetFileType.argtypes = [w.HANDLE]
    kernel.GetFileType.restype = w.DWORD
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    handles = []
    fd = None

    def open_handle(path, directory):
        handle = kernel.CreateFileW(str(path), 0x80 if directory else 0x80000000,
                                    3 if directory else 1, None, 3,
                                    0x00200000 | (0x02000000 if directory else 0), None)
        if handle == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        handles.append(handle)
        info = Info()
        _require(kernel.GetFileType(handle) == 1 and kernel.GetFileInformationByHandle(handle, c.byref(info)))
        _require(not info.attributes & 0x400 and bool(info.attributes & 0x10) == directory)
        return handle, (info.volume, info.index_high, info.index_low)

    chain = [Path(root.anchor)]
    for part in root.parts[1:]:
        chain.append(chain[-1] / part)
    candidate = root / relative
    try:
        for path in chain:
            _, root_id = open_handle(path, True)
        directory = root
        for part in relative.split("/")[:-1]:
            directory /= part
            try:
                open_handle(directory, True)
            except FileNotFoundError:
                raise _Missing((str(root.resolve(strict=True)), None, None, root_id)) from None
        try:
            handle, _ = open_handle(candidate, False)
        except FileNotFoundError:
            raise _Missing((str(root.resolve(strict=True)), None, None, root_id)) from None
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        handles.pop()  # Ownership transferred to fd; never close it twice.
        raw, file_id = _read_fd(fd)
        canonical_root, canonical_file, public_path = _canonical(root, candidate)
        return raw, public_path, (canonical_root, canonical_file, file_id, root_id)
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            for handle in reversed(handles):
                kernel.CloseHandle(handle)


def _number(text):
    if len(text) > 32:
        raise _Limit()
    value = float(text) if any(char in text for char in ".eE") else int(text)
    if not math.isfinite(value) or abs(value) > 2**63 - 1:
        raise _Limit()
    return value


def _bounded(value, depth=0):
    if depth > 16:
        raise _Limit()
    if type(value) is dict:
        for item in value.values():
            _bounded(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _bounded(item, depth + 1)


@dataclass(frozen=True, init=False)
class ProjectPolicyResolution:
    """Captured data snapshot, not analysis success, authentication or permission."""
    complete: bool
    reason: str
    relative_path: str | None
    raw_sha256: str | None
    _policy_json: str | None = field(repr=False)
    _binding: tuple | None = field(repr=False)

    def __init__(self, token=None, **values):
        _require(token is _SEAL and set(values) == set(self.__dataclass_fields__))
        for key, value in values.items():
            object.__setattr__(self, key, value)

    def policy(self):
        return None if self._policy_json is None else json.loads(self._policy_json)

    @property
    def write_authorized(self):
        return False

    @property
    def execution_authorized(self):
        return False

    def to_dict(self):
        return {"resolution_complete": self.complete, "reason": self.reason,
                "relative_path": self.relative_path, "raw_sha256": self.raw_sha256,
                "policy": self.policy()}


def discover_policy(repo_root, *, policy_path=None):
    """Read one local data path. Only an absent default permits builtin fallback.

    A returned complete resolution says nothing about analysis completeness or
    permission. No ancestor/global lookup, processes, remote fetch or code loads.
    """
    relative = digest = binding = None

    def result(complete, reason, policy=None):
        return ProjectPolicyResolution(_SEAL, complete=complete, reason=reason,
                                       relative_path=relative, raw_sha256=digest,
                                       _policy_json=None if policy is None else json.dumps(policy, sort_keys=True),
                                       _binding=binding)

    try:
        requested = _relative(_DEFAULT if policy_path is None else policy_path)
        _require(type(repo_root) in (str, Path) or isinstance(repo_root, Path))
        root = Path(repo_root)
        _require(".." not in root.parts)
        root = root.absolute()  # Do not canonicalize away original reparse components.
        reader = _read_windows if os.name == "nt" else _read_posix
        try:
            raw, relative, binding = reader(root, requested)
        except _Missing as missing:
            binding = missing.binding
            return result(True, "DEFAULTS", resolve_policy()) if policy_path is None else result(False, "POLICY_UNAVAILABLE")
        digest = hashlib.sha256(raw).hexdigest()
        layer = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant, parse_int=_number, parse_float=_number)
        _bounded(layer)
        # None cannot mean an absent layer when a present JSON file said null.
        if type(layer) is not dict:
            raise ValueError()
        policy = resolve_policy(layer)
        return result(True, "PROJECT_POLICY" if policy_path is None else "EXPLICIT_POLICY", policy)
    except _Limit:
        return result(False, "POLICY_RESOURCE_LIMIT")
    except _Unsafe:
        return result(False, "POLICY_PATH_UNSAFE")
    except (OSError, UnicodeError, ValueError, TypeError, RuntimeError, RecursionError, OverflowError):
        return result(False, "POLICY_UNAVAILABLE_OR_INVALID")
