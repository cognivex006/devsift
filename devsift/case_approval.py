"""Explicit per-case manual-planning approval, never a patch/execution engine."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from .git_runtime import git_executable
from .case_prompts import CasePrompt, compose_case_prompt
from .evidence import SourceEvidence
from .redaction import Redactor
from .report_model import Report

_SEAL = object()
_ERROR = 'Invalid or unavailable case approval input'
_FIELDS = {'case_id', 'source_sha', 'fingerprint', 'prompt_digest', 'mode', 'approved', 'actor', 'issued_at', 'expires_at'}


class CaseApprovalError(ValueError):
    """Constant failures never echo operator input, source or local paths."""


def _require(condition):
    if not condition:
        raise CaseApprovalError(_ERROR) from None


def _timestamp(value):
    _require(type(value) is str and len(value) <= 64 and re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value) is not None)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        _require(parsed.tzinfo is not None and parsed.utcoffset() is not None)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise CaseApprovalError(_ERROR) from None


@dataclass(frozen=True)
class ImplementationApproval:
    case_id: str
    source_sha: str
    fingerprint: str
    prompt_digest: str
    mode: str
    approved: bool
    actor: str = field(repr=False)
    issued_at: str
    expires_at: str

    def __post_init__(self):
        try:
            _require(type(self.case_id) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', self.case_id) is not None)
            _require(type(self.source_sha) is str and re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', self.source_sha) is not None)
            for digest in (self.fingerprint, self.prompt_digest):
                _require(type(digest) is str and re.fullmatch(r'[a-f0-9]{64}', digest) is not None)
            _require(type(self.mode) is str and self.mode in {'review', 'implement'} and type(self.approved) is bool)
            _require(type(self.actor) is str and 0 < len(self.actor.strip()) <= 128
                     and not any(ord(c) < 32 or ord(c) == 127 for c in self.actor))
            object.__setattr__(self, 'actor', Redactor().text(self.actor.strip()))
            _require(_timestamp(self.issued_at) < _timestamp(self.expires_at))
        except (ValueError, TypeError, AttributeError, OverflowError):
            raise CaseApprovalError(_ERROR) from None

    @classmethod
    def from_dict(cls, value):
        """Explicit trusted-operator input only; no file loading or discovery."""
        try:
            _require(type(value) is dict and set(value) == _FIELDS)
            return cls(**value)
        except (ValueError, TypeError, KeyError):
            raise CaseApprovalError(_ERROR) from None


@dataclass(frozen=True, init=False)
class ApprovalDecision:
    case_id: str
    status: str
    _payload: str = field(repr=False)

    def __init__(self, case_id, status, payload, *, _seal=None):
        _require(_seal is _SEAL)
        for name, value in (('case_id', case_id), ('status', status), ('_payload', payload)):
            object.__setattr__(self, name, value)

    def to_dict(self):
        return json.loads(self._payload)


def _git(root, *args):
    environment = os.environ.copy()
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
        environment.pop(name, None)
    environment.update(GIT_NO_REPLACE_OBJECTS='1', GIT_LITERAL_PATHSPECS='1', GIT_OPTIONAL_LOCKS='0',
                       GIT_TERMINAL_PROMPT='0', GIT_NO_LAZY_FETCH='1')
    process = subprocess.run([git_executable(root), '--no-optional-locks', '-c', 'core.fsmonitor=false', '-C', str(root), *args],
                             env=environment, capture_output=True, timeout=10)
    if process.returncode or len(process.stdout) > 2_000_000:
        raise ValueError('Git check unavailable')
    return process.stdout


def _linked(path):
    info = path.lstat()
    return (stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0)
            & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)))


def _current_file(root, location):
    """Check selected path only, raw bytes/index/HEAD; never run conversion drivers."""
    try:
        if Path(_git(root, 'rev-parse', '--show-toplevel').decode('utf-8').strip()).resolve() != root:
            return 'SOURCE_UNAVAILABLE'
        head = _git(root, 'rev-parse', '--verify', 'HEAD^{commit}').decode('ascii').strip()
        if head != location['source_sha']:
            return 'HEAD_MISMATCH'
        name = location['path']
        entries = _git(root, 'ls-tree', '-z', head, '--', name).split(b'\0')
        if len(entries) != 2 or not entries[0]:
            return 'SOURCE_UNAVAILABLE'
        metadata, path = entries[0].split(b'\t', 1)
        mode, kind, blob = metadata.split(b' ')
        if path.decode('utf-8') != name or mode not in {b'100644', b'100755'} or kind != b'blob':
            return 'UNSAFE_SOURCE'
        expected_index = mode + b' ' + blob + b' 0\t' + path + b'\0'
        if _git(root, 'ls-files', '--stage', '-z', '--', name) != expected_index:
            return 'INDEX_MISMATCH'
        current = root
        for part in name.split('/'):
            current = current / part
            if _linked(current):
                return 'UNSAFE_SOURCE'
        info = current.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 2_000_000:
            return 'UNSAFE_SOURCE'
        descriptor = os.open(current, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor, 'rb') as stream:
            before = os.fstat(stream.fileno())
            data = stream.read(2_000_001)
            after = os.fstat(stream.fileno())
        if len(data) > 2_000_000 or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            return 'WORKING_TREE_MISMATCH'
        raw = b'blob ' + str(len(data)).encode('ascii') + b'\0' + data
        digest = hashlib.sha1(raw, usedforsecurity=False).hexdigest() if len(blob) == 40 else hashlib.sha256(raw).hexdigest() if len(blob) == 64 else None
        if digest != blob.decode('ascii'):
            return 'WORKING_TREE_MISMATCH'
        final = current.lstat()
        if (_linked(current) or (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            return 'UNSAFE_SOURCE'
        if (_git(root, 'rev-parse', '--verify', 'HEAD^{commit}').decode('ascii').strip() != head
                or _git(root, 'ls-files', '--stage', '-z', '--', name) != expected_index):
            return 'SOURCE_CHANGED_DURING_CHECK'
        return None
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, subprocess.SubprocessError):
        return 'SOURCE_UNAVAILABLE'


def _decision(case_id, status, reason, *, prompt=None, matched=False, actor=None):
    source = prompt['source'] if prompt is not None else SourceEvidence(reason='SOURCE_UNAVAILABLE').to_dict()
    binding = ({'case_id': case_id, 'source_sha': prompt['source_sha'], 'fingerprint': prompt['fingerprint'],
                'prompt_digest': prompt['digest']} if prompt is not None else None)
    payload = {
        'schema_version': '1', 'kind': 'case_approval_decision', 'case_id': case_id,
        'status': status, 'reason': reason, 'binding': binding, 'source': source,
        'approval_matched': matched, 'manual_planning_allowed': matched,
        'execution_authorized': False, 'writes_authorized': False, 'automatic_fix': False,
        'effects': {'impact': 'unknown', 'change_risk': 'unknown', 'consumers': 'unknown'},
        'handoff': ({'scope': 'manual_case_planning_only', 'binding': binding, 'actor': actor,
                     'required_next_action': 'Review actual consumers, effects, tests and rollback before any separately authorized source edit.'} if matched else None),
        'authority_boundary': 'Explicit trusted operator planning input; no authentication, signature trust, file discovery or enforcement of external agent writes.',
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return ApprovalDecision(case_id, status, encoded, _seal=_SEAL)


def evaluate_case_approval(report, case_id, *, prompt, repo_root, approval=None, now=None):
    """Recheck one exact implement prompt; never apply code or grant execution.

    Only an explicitly supplied ImplementationApproval can match. Even a match
    remains review_required because current report impact/risk/consumers are unknown.
    """
    try:
        _require(type(report) is Report and type(prompt) is CasePrompt and type(case_id) is str
                 and isinstance(repo_root, (str, Path)) and (approval is None or type(approval) is ImplementationApproval))
        report.find_case(case_id)  # safe exact lookup, never trust an approval's ID
        if prompt.case_id != case_id or prompt.mode != 'implement':
            return _decision(case_id, 'denied', 'IMPLEMENT_PROMPT_REQUIRED')
        original_root = Path(repo_root).absolute()
        current = Path(original_root.anchor)
        for part in original_root.parts[1:]:
            current = current / part
            if _linked(current):
                return _decision(case_id, 'denied', 'UNSAFE_SOURCE')
        root = original_root.resolve(strict=True)
        fresh = compose_case_prompt(report, case_id, mode='implement', repo_root=root)
        payload = fresh.to_dict()
        if payload['source']['status'] != 'VERIFIED' or payload['source_sha'] is None or payload['fingerprint'] is None:
            return _decision(case_id, 'denied', 'SOURCE_UNRESOLVED')
        if fresh.digest != prompt.digest:
            return _decision(case_id, 'denied', 'PROMPT_BINDING_MISMATCH')
        failure = _current_file(root, payload['source']['location'])
        if failure:
            return _decision(case_id, 'denied', failure)
        payload['digest'] = fresh.digest
        if approval is None:
            return _decision(case_id, 'review_required', 'EXPLICIT_APPROVAL_REQUIRED', prompt=payload)
        if approval.mode != 'implement' or approval.approved is not True:
            return _decision(case_id, 'denied', 'IMPLEMENT_APPROVAL_REQUIRED', prompt=payload)
        if (approval.case_id, approval.source_sha, approval.fingerprint, approval.prompt_digest) != (
                case_id, payload['source_sha'], payload['fingerprint'], fresh.digest):
            return _decision(case_id, 'denied', 'APPROVAL_BINDING_MISMATCH', prompt=payload)
        now = datetime.now(timezone.utc) if now is None else now
        _require(type(now) is datetime and now.tzinfo is not None and now.utcoffset() is not None)
        if not _timestamp(approval.issued_at) <= now.astimezone(timezone.utc) < _timestamp(approval.expires_at):
            return _decision(case_id, 'denied', 'APPROVAL_NOT_CURRENT', prompt=payload)
        return _decision(case_id, 'review_required', 'UNKNOWN_EFFECTS_REVIEW_REQUIRED',
                         prompt=payload, matched=True, actor=approval.actor)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError, OverflowError):
        raise CaseApprovalError(_ERROR) from None
