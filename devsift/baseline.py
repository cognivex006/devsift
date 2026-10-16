"""Immutable reviewed baseline snapshots; reads never refresh or write."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .evidence import SourceEvidence, SourceLocation
from .git_changes import classify
from .redaction import Redactor
from .registry import RULES


class BaselineError(ValueError):
    """Safe baseline contract, integrity, approval or storage failure."""


def _require(condition):
    if not condition:
        raise BaselineError("invalid or unavailable baseline") from None


def _text(value, maximum=256):
    _require(type(value) is str and bool(value.strip()) and len(value) <= maximum
             and not any(ord(char) < 32 for char in value))
    return Redactor().text(value.strip())


def _digest(value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None)
    return value


def _fields(data, keys):
    _require(type(data) is dict and set(data) == set(keys))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _parse(text):
    _require(type(text) is str and len(text) <= 5_000_000)
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=lambda _: _require(False))
    except (ValueError, RecursionError):
        raise BaselineError("invalid or unavailable baseline") from None


def _encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


@dataclass(frozen=True)
class BaselineEntry:
    rule_id: str
    rule_version: str
    fingerprint: str
    location: SourceLocation

    def __post_init__(self):
        _require(type(self.rule_id) is str and self.rule_id in RULES)
        object.__setattr__(self, "rule_version", _text(self.rule_version))
        _digest(self.fingerprint)
        _require(type(self.location) is SourceLocation)

    def to_dict(self):
        return {"rule_id": self.rule_id, "rule_version": self.rule_version,
                "fingerprint": self.fingerprint, "location": self.location.to_dict()}

    @classmethod
    def from_dict(cls, data):
        _fields(data, ("rule_id", "rule_version", "fingerprint", "location"))
        try:
            return cls(data["rule_id"], data["rule_version"], data["fingerprint"], SourceLocation.from_dict(data["location"]))
        except ValueError:
            raise BaselineError("invalid or unavailable baseline") from None


def capture_entry(repo_root, rule_id, rule_version, evidence, *, redactor=None):
    _require(type(evidence) is SourceEvidence and evidence.status == "VERIFIED")
    sha = evidence.location.source_sha
    proof = classify(repo_root, sha, sha, rule_id, evidence, redactor=redactor)
    _require(proof.lifecycle_class == "LEGACY_UNCHANGED" and proof.fingerprint is not None)
    return BaselineEntry(rule_id, rule_version, proof.fingerprint, proof.head_location)


@dataclass(frozen=True)
class BaselineSnapshot:
    repository: str
    source_sha: str
    tool_version: str
    rule_catalog_version: str
    entries: tuple[BaselineEntry, ...]

    def __post_init__(self):
        object.__setattr__(self, "repository", _text(self.repository, 1024))
        _require(type(self.source_sha) is str and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", self.source_sha) is not None)
        object.__setattr__(self, "tool_version", _text(self.tool_version))
        object.__setattr__(self, "rule_catalog_version", _text(self.rule_catalog_version))
        _require(type(self.entries) in (tuple, list) and len(self.entries) <= 1000)
        _require(all(type(entry) is BaselineEntry and entry.location.source_sha == self.source_sha
                     and entry.location.repository == self.repository for entry in self.entries))
        _require(len({(entry.rule_id, entry.fingerprint) for entry in self.entries}) == len(self.entries))
        _require(all(len({entry.rule_version for entry in self.entries if entry.rule_id == rule_id}) == 1
                     for rule_id in {entry.rule_id for entry in self.entries}))
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda entry: (entry.rule_id, entry.fingerprint))))

    def to_dict(self):
        return {"schema_version": "1", "repository": self.repository, "source_sha": self.source_sha,
                "tool_version": self.tool_version, "rule_catalog_version": self.rule_catalog_version,
                "entries": [entry.to_dict() for entry in self.entries]}

    @property
    def digest(self):
        return hashlib.sha256(_encode(self.to_dict())).hexdigest()

    def to_json(self):
        return _encode(self.to_dict()).decode("utf-8")

    @classmethod
    def from_dict(cls, data):
        _fields(data, ("schema_version", "repository", "source_sha", "tool_version", "rule_catalog_version", "entries"))
        _require(data["schema_version"] == "1" and type(data["entries"]) is list and len(data["entries"]) <= 1000)
        return cls(data["repository"], data["source_sha"], data["tool_version"], data["rule_catalog_version"],
                   tuple(BaselineEntry.from_dict(entry) for entry in data["entries"]))

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


@dataclass(frozen=True)
class BaselineDiff:
    added: tuple[BaselineEntry, ...]
    resolved: tuple[BaselineEntry, ...]
    unchanged: tuple[BaselineEntry, ...]


def diff_snapshots(old, new):
    _require(type(old) is BaselineSnapshot and type(new) is BaselineSnapshot)
    _require((old.repository, old.tool_version, old.rule_catalog_version) ==
             (new.repository, new.tool_version, new.rule_catalog_version))
    versions = {}
    for entry in old.entries + new.entries:
        _require(entry.rule_id not in versions or versions[entry.rule_id] == entry.rule_version)
        versions[entry.rule_id] = entry.rule_version
    before = {(entry.rule_id, entry.fingerprint): entry for entry in old.entries}
    after = {(entry.rule_id, entry.fingerprint): entry for entry in new.entries}
    return BaselineDiff(tuple(after[key] for key in sorted(after.keys() - before.keys())),
                        tuple(before[key] for key in sorted(before.keys() - after.keys())),
                        tuple(after[key] for key in sorted(after.keys() & before.keys())))


@dataclass(frozen=True)
class UpdateApproval:
    actor: str
    reviewer: str
    ticket: str
    approved_digest: str
    expected_digest: str | None = None

    def __post_init__(self):
        for name in ("actor", "reviewer", "ticket"):
            object.__setattr__(self, name, _text(getattr(self, name)))
        _require(self.actor.casefold() != self.reviewer.casefold())
        _digest(self.approved_digest)
        if self.expected_digest is not None:
            _digest(self.expected_digest)

    def to_dict(self):
        return {name: getattr(self, name) for name in ("actor", "reviewer", "ticket", "approved_digest", "expected_digest")}

    @classmethod
    def from_dict(cls, data):
        _fields(data, ("actor", "reviewer", "ticket", "approved_digest", "expected_digest"))
        return cls(**data)


def _read(path):
    _require(not path.is_symlink())
    with path.open("rb") as stream:
        raw = stream.read(5_000_001)
    _require(len(raw) <= 5_000_000)
    return raw


def load_snapshot(path, *, expected_digest):
    """Read only; trust requires an independently supplied exact file digest."""
    _digest(expected_digest)
    try:
        raw = _read(Path(path))
        _require(hashlib.sha256(raw).hexdigest() == expected_digest)
        envelope = _parse(raw.decode("utf-8"))
        _fields(envelope, ("schema_version", "snapshot", "approval"))
        _require(envelope["schema_version"] == "1")
        snapshot = BaselineSnapshot.from_dict(envelope["snapshot"])
        approval = UpdateApproval.from_dict(envelope["approval"])
        _require(approval.approved_digest == snapshot.digest)
        return snapshot
    except (OSError, ValueError, TypeError, UnicodeError):
        raise BaselineError("invalid or unavailable baseline") from None


def save_snapshot(path, snapshot, approval, *, expected_digest=None):
    """Explicit cooperating-writer CAS with reviewed payload and atomic replace.

    None means create only. The return value is the persisted envelope digest,
    distinct from the snapshot payload digest bound by the approval.
    """
    _require(type(snapshot) is BaselineSnapshot and type(approval) is UpdateApproval)
    _require(approval.approved_digest == snapshot.digest and approval.expected_digest == expected_digest)
    if expected_digest is not None:
        _digest(expected_digest)
    lock_owned = False
    temporary = None
    try:
        target = Path(path).absolute()
        _require(target.parent.resolve(strict=True) == target.parent and not target.is_symlink())
        lock = target.with_name(target.name + ".lock")
        with lock.open("xb"):
            lock_owned = True
        _require(not target.is_symlink())
        if expected_digest is None:
            _require(not target.exists())
        else:
            _require(hashlib.sha256(_read(target)).hexdigest() == expected_digest)
        raw = _encode({"schema_version": "1", "snapshot": snapshot.to_dict(), "approval": approval.to_dict()})
        _require(len(raw) <= 5_000_000)
        with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent, prefix=".devsift-baseline-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
        return hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError, TypeError):
        raise BaselineError("invalid or unavailable baseline") from None
    finally:
        try:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if lock_owned:
                lock.unlink(missing_ok=True)
        except OSError:
            raise BaselineError("invalid or unavailable baseline") from None
