"""Immutable, source-verified evidence and separately labeled proposals."""
from dataclasses import dataclass, field
from datetime import datetime
import codecs
import hashlib
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from .git_runtime import git_executable
from .redaction import Redactor


class EvidenceError(ValueError):
    """Invalid evidence contract; input values are never included in errors."""


def _require(condition):
    if not condition:
        raise EvidenceError("invalid evidence contract") from None


def _text(value, *, empty=False, maximum=2_000_000, redactor=None):
    _require(type(value) is str and (empty or bool(value)) and len(value) <= maximum)
    return (redactor or Redactor()).text(value)


def _fields(data, required, optional=()):
    _require(type(data) is dict and set(required) <= data.keys()
             and data.keys() <= set(required) | set(optional))


def _path(value):
    _require(type(value) is str and 0 < len(value) <= 4096)
    _require(not any(ord(char) < 32 or ord(char) == 127 or char in "\\:" for char in value))
    _require(all(part not in ("", ".", "..", ".git") for part in value.split("/")))
    _require(Redactor().text(value) == value)
    return value


@dataclass(frozen=True)
class Region:
    """One-based Unicode code-point columns; exclusive end (SARIF convention)."""
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def __post_init__(self):
        _require(all(type(value) is int and value > 0 for value in (
            self.start_line, self.start_column, self.end_line, self.end_column)))
        _require((self.end_line, self.end_column) >= (self.start_line, self.start_column))

    def to_dict(self):
        return {name: getattr(self, name) for name in ("start_line", "start_column", "end_line", "end_column")}

    @classmethod
    def from_dict(cls, data):
        _fields(data, ("start_line", "start_column", "end_line", "end_column"))
        return cls(**data)


@dataclass(frozen=True)
class SourceLocation:
    repository: str
    source_sha: str
    path: str
    region: Region
    symbol: str | None = None

    def __post_init__(self):
        repository = _text(self.repository, maximum=1024)
        _require(not any(ord(char) < 32 for char in repository))
        _require(type(self.source_sha) is str and re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", self.source_sha) is not None)
        _path(self.path)
        _require(type(self.region) is Region)
        if self.symbol is not None:
            symbol = _text(self.symbol, maximum=1024)
            _require(not any(ord(char) < 32 for char in symbol))
            object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "repository", repository)
        object.__setattr__(self, "source_sha", self.source_sha.lower())

    def to_dict(self):
        return {"repository": self.repository, "source_sha": self.source_sha,
                "path": self.path, "region": self.region.to_dict(), "symbol": self.symbol}

    @classmethod
    def from_dict(cls, data):
        _fields(data, ("repository", "source_sha", "path", "region", "symbol"))
        return cls(data["repository"], data["source_sha"], data["path"],
                   Region.from_dict(data["region"]), data["symbol"])


_SEAL = object()
_REASONS = frozenset({"SOURCE_NOT_VERIFIED", "SOURCE_UNAVAILABLE", "SOURCE_MISMATCH",
                      "REGION_UNAVAILABLE", "UNSUPPORTED_SOURCE", "SENSITIVE_LOCATION"})
_LOOKUP = "Inspect the immutable commit and exact source region; retain unresolved status until verified."


@dataclass(frozen=True, init=False)
class SourceEvidence:
    status: str
    location: SourceLocation | None
    before: str | None
    reason: str | None
    lookup_plan: str | None

    def __init__(self, status="SOURCE_UNRESOLVED", location=None, before=None,
                 reason="SOURCE_NOT_VERIFIED", lookup_plan=_LOOKUP, *, redactor=None, _seal=None):
        _require(redactor is None or type(redactor) is Redactor)
        _require(type(status) is str and status in ("VERIFIED", "SOURCE_UNRESOLVED"))
        if status == "VERIFIED":
            _require(_seal is _SEAL and type(location) is SourceLocation
                     and type(before) is str and reason is None and lookup_plan is None)
        else:
            _require(location is None and before is None and type(reason) is str and reason in _REASONS)
            lookup_plan = _text(lookup_plan, maximum=4096, redactor=redactor)
        for name, value in (("status", status), ("location", location), ("before", before),
                            ("reason", reason), ("lookup_plan", lookup_plan)):
            object.__setattr__(self, name, value)

    def to_dict(self):
        return {"status": self.status, "location": None if self.location is None else self.location.to_dict(),
                "before": self.before, "reason": self.reason, "lookup_plan": self.lookup_plan}

    @classmethod
    def from_dict(cls, data, *, repo_root=None, redactor=None):
        _fields(data, ("status", "location", "before", "reason", "lookup_plan"))
        if data["status"] == "SOURCE_UNRESOLVED":
            return cls(**data, redactor=redactor)
        _require(data["status"] == "VERIFIED" and repo_root is not None
                 and data["reason"] is None and data["lookup_plan"] is None and type(data["before"]) is str)
        location = SourceLocation.from_dict(data["location"])
        # Symbol is not proven by a physical region. A future symbol-aware adapter
        # must supply a separate verified contract instead of trusting wire labels.
        _require(location.symbol is None)
        return verify_source(repo_root, location.repository, location.source_sha, location.path,
                             location.region, expected_before=data["before"], redactor=redactor,
                             sensitive=data["before"] == '[REDACTED]')


def _git(root, *args):
    process = subprocess.run([git_executable(root), "-C", str(root), *args], capture_output=True,
                             timeout=10, env=_git_environment())
    if process.returncode:
        raise EvidenceError("source lookup unavailable")
    return process.stdout


def _git_environment():
    environment = os.environ.copy()
    environment.update(GIT_NO_REPLACE_OBJECTS="1", GIT_LITERAL_PATHSPECS="1",
                       GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
    return environment


_SMALL_SOURCE_BYTES = 2_000_000
_SOURCE_STREAM_SECONDS = 10
_SOURCE_CHUNK_BYTES = 65_536


def _reap_source_process(process):
    if process.poll() is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    process.wait()


def _stream_region(root, blob, byte_count, region):
    """Prove a large immutable blob without retaining source or whole lines.

    Only host Git's raw object reader runs: no worktree/filter/textconv, pager,
    network/lazy fetch or target code. The reader retains one bounded byte/text
    chunk and line counters, verifies strict UTF-8/NUL exclusion over *all* bytes,
    and independently checks the raw Git object digest and declared byte count.
    LF defines lines; a CR is removed from the column bound only before LF.

    A worker drains the pipe because blocking pipe reads cannot otherwise honor
    a whole-operation timeout on Windows. Every exit, including cancellation,
    kills/reaps the owned Git process and joins the reader before closing handles.
    No source bytes or subprocess diagnostics enter exceptions or logs.
    """
    _require(type(byte_count) is int and byte_count > _SMALL_SOURCE_BYTES)
    _require(re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', blob) is not None)
    process = None
    try:
        process = subprocess.Popen(
            [git_executable(root), '--no-pager', '-C', str(root), 'cat-file', 'blob', blob],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, env=_git_environment())
        return _read_source_stream(process, blob, byte_count, region)
    finally:
        # Also cover cancellation/errors before the reader thread is constructed.
        if process is not None:
            _reap_source_process(process)
            process.stdout.close()


def _read_source_stream(process, blob, byte_count, region):
    finished = threading.Event()
    outcome = {'valid': False, 'failed': False}

    def read():
        try:
            decoder = codecs.getincrementaldecoder('utf-8')('strict')
            digest = (hashlib.sha1(usedforsecurity=False) if len(blob) == 40 else hashlib.sha256())
            digest.update(b'blob ' + str(byte_count).encode('ascii') + b'\0')
            received, line_number, line_length, tail = 0, 1, 0, ''
            start_valid = end_valid = False

            def decoded(text, *, final=False):
                nonlocal line_number, line_length, tail, start_valid, end_valid
                _require('\x00' not in text)
                pieces = text.split('\n')  # only the bounded decoded chunk
                for index, piece in enumerate(pieces):
                    line_length += len(piece)
                    if piece:
                        tail = piece[-1]
                    ended = index < len(pieces) - 1
                    if ended or (final and line_length):
                        body_length = line_length - (1 if ended and tail == '\r' else 0)
                        if line_number == region.start_line:
                            start_valid = region.start_column <= body_length + 1
                        if line_number == region.end_line:
                            end_valid = region.end_column <= body_length + 1
                        line_number += 1
                        line_length, tail = 0, ''

            while True:
                chunk = process.stdout.read(_SOURCE_CHUNK_BYTES)
                if not chunk:
                    break
                received += len(chunk)
                _require(received <= byte_count)
                digest.update(chunk)
                decoded(decoder.decode(chunk))
            decoded(decoder.decode(b'', final=True), final=True)
            _require(received == byte_count and digest.hexdigest() == blob)
            outcome['valid'] = start_valid and end_valid
        except (OSError, ValueError, UnicodeError):
            outcome['failed'] = True
        finally:
            finished.set()

    worker = threading.Thread(target=read, name='devsift-source-proof', daemon=True)
    started = False
    try:
        deadline = time.monotonic() + _SOURCE_STREAM_SECONDS
        worker.start()
        started = True
        while not finished.wait(0.05):
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired('git source proof', _SOURCE_STREAM_SECONDS)
        _require(not outcome['failed'])
        remaining = max(0.001, deadline - time.monotonic())
        _require(process.wait(timeout=remaining) == 0)
        return outcome['valid']
    finally:
        _reap_source_process(process)
        if started:
            worker.join()


def requires_source_mask(rule_id, source=None):
    """Preserve an already fully masked region, including overlapping rules.

    This only withholds display. It never grants source proof or changes raw
    identity, location, lifecycle or enforcement. The subsequent Git check still
    verifies the immutable region before returning VERIFIED.
    """
    _require(type(rule_id) is str and (source is None or type(source) is SourceEvidence))
    return rule_id in {'HC002', 'CFG003', 'SEC001'} or (source is not None and source.before == '[REDACTED]')


def verify_source(repo_root, repository, source_sha, path, region, *, expected_before=None, redactor=None,
                  sensitive=False):
    """Verify/extract an immutable UTF-8 Git blob region, never follow symlinks.

    Invalid input raises a safe contract error. Missing objects, unsupported source
    modes/encoding, invalid source bounds, or mismatches return unresolved evidence.
    Working-tree content and runtime logs are never used to prove source locations.
    """
    redactor = redactor or Redactor()
    _require(type(redactor) is Redactor)
    location = SourceLocation(repository, source_sha, path, region)
    _require(expected_before is None or type(expected_before) is str)
    _require(type(sensitive) is bool)
    if redactor.text(path) != path:
        return SourceEvidence(reason="SENSITIVE_LOCATION")
    location = SourceLocation(redactor.text(repository), location.source_sha, path, region)
    try:
        root = Path(repo_root).resolve(strict=True)
        top = Path(_git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
        if root != top:
            return SourceEvidence(reason="SOURCE_UNAVAILABLE")
        commit = _git(root, "rev-parse", "--verify", location.source_sha + "^{commit}").decode("ascii").strip()
        if commit != location.source_sha:
            return SourceEvidence(reason="SOURCE_UNAVAILABLE")
        entries = _git(root, "ls-tree", "-z", commit, "--", path).split(b"\0")
        if len(entries) != 2 or not entries[0]:
            return SourceEvidence(reason="SOURCE_UNAVAILABLE")
        metadata, recorded_path = entries[0].split(b"\t", 1)
        mode, kind, blob = metadata.split(b" ")
        if recorded_path.decode("utf-8") != path or mode not in (b"100644", b"100755") or kind != b"blob":
            return SourceEvidence(reason="UNSUPPORTED_SOURCE")
        byte_count = int(_git(root, "cat-file", "-s", blob.decode("ascii")))
        if byte_count > _SMALL_SOURCE_BYTES:
            if not _stream_region(root, blob.decode('ascii'), byte_count, region):
                return SourceEvidence(reason="REGION_UNAVAILABLE")
            # Full-context secret matching is bounded for generic text. Large
            # source is proved, never partially inspected then shown as plaintext.
            # An imported plaintext excerpt cannot be certified by this path.
            if expected_before is not None and expected_before != '[REDACTED]':
                return SourceEvidence(reason="SOURCE_MISMATCH")
            return SourceEvidence("VERIFIED", location, '[REDACTED]', None, None, _seal=_SEAL)
        content = _git(root, "cat-file", "blob", blob.decode("ascii")).decode("utf-8")
        if "\x00" in content:
            return SourceEvidence(reason="UNSUPPORTED_SOURCE")
        # Git hunk line numbers count LF, not Python's broader Unicode line
        # separator set. Preserve all original bytes represented in UTF-8 text.
        pieces = content.split("\n")
        lines = [piece + "\n" for piece in pieces[:-1]]
        if pieces[-1]:
            lines.append(pieces[-1])
        if region.end_line > len(lines):
            return SourceEvidence(reason="REGION_UNAVAILABLE")

        def line_body(line):
            if line.endswith("\n"):
                line = line[:-1]
                if line.endswith("\r"):
                    line = line[:-1]
            return line

        start = line_body(lines[region.start_line - 1])
        end = line_body(lines[region.end_line - 1])
        if region.start_column > len(start) + 1 or region.end_column > len(end) + 1:
            return SourceEvidence(reason="REGION_UNAVAILABLE")
        start_offset = sum(len(line) for line in lines[:region.start_line - 1]) + region.start_column - 1
        end_offset = sum(len(line) for line in lines[:region.end_line - 1]) + region.end_column - 1
        before = redactor.slice(content, start_offset, end_offset)
        if (expected_before is not None and redactor.text(expected_before) != before
                and not (sensitive and expected_before == '[REDACTED]')):
            return SourceEvidence(reason="SOURCE_MISMATCH")
        if sensitive:
            before = '[REDACTED]'
        return SourceEvidence("VERIFIED", location, before, None, None, _seal=_SEAL)
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        return SourceEvidence(reason="SOURCE_UNAVAILABLE")


@dataclass(frozen=True)
class RuntimeEvidence:
    origin: str
    message: str
    observed_at: str | None = None
    redactor: object = field(default=None, repr=False, compare=False, kw_only=True)

    def __post_init__(self):
        redactor = self.redactor or Redactor()
        _require(type(redactor) is Redactor)
        object.__setattr__(self, "origin", _text(self.origin, maximum=4096, redactor=redactor))
        object.__setattr__(self, "message", _text(self.message, empty=True, redactor=redactor))
        if self.observed_at is not None:
            _require(type(self.observed_at) is str and len(self.observed_at) <= 64)
            _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", self.observed_at) is not None)
            try:
                timestamp = datetime.fromisoformat(self.observed_at)
                _require(timestamp.tzinfo is not None)
            except ValueError:
                raise EvidenceError("invalid evidence contract") from None
        object.__setattr__(self, "redactor", None)

    def to_dict(self):
        return {"origin": self.origin, "message": self.message, "observed_at": self.observed_at}

    @classmethod
    def from_dict(cls, data, *, redactor=None):
        _fields(data, ("origin", "message", "observed_at"))
        return cls(**data, redactor=redactor)


@dataclass(frozen=True)
class AfterProposal:
    code: str
    confidence: str = "unknown"
    redactor: object = field(default=None, repr=False, compare=False, kw_only=True)

    def __post_init__(self):
        _require(type(self.confidence) is str and self.confidence in ("high", "medium", "low", "unknown"))
        _require(self.redactor is None or type(self.redactor) is Redactor)
        object.__setattr__(self, "code", _text(self.code, empty=True, redactor=self.redactor))
        object.__setattr__(self, "redactor", None)

    def to_dict(self):
        return {"label": "AFTER (PROPOSAL)", "code": self.code, "confidence": self.confidence}

    @classmethod
    def from_dict(cls, data, *, redactor=None):
        _fields(data, ("label", "code", "confidence"))
        _require(data["label"] == "AFTER (PROPOSAL)")
        return cls(data["code"], data["confidence"], redactor=redactor)
