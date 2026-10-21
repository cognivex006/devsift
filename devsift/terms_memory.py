"""External append-only owner attribution; decisions never waive an enforced block.

A hash chain detects edited/reordered events, not whole-store rollback to a valid
backup. Independent protected checkpoints are needed for that stronger property.
Actor names are attribution, not authentication, signatures or legal permission.
The host account and its private home directory are trusted; this is not a sandbox
against a hostile process running with that same account.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import threading
from urllib.parse import urlsplit
import uuid

from .git_runtime import git_executable
from .redaction import Redactor

_ZERO = '0' * 64
_MAX_BYTES = 8_000_000
_MAX_EVENTS = 10_000
_SEAL = object()
_HEX = re.compile(r'[0-9a-f]{64}')
_CHOICES = {'remediate', 'decline', 'reconsider', 'resolved'}
_KEYS = {'repository_id', 'case_id', 'fingerprint', 'evidence_digest', 'choice',
         'owner', 'rationale', 'timestamp', 'event_id', 'supersedes',
         'previous_hash', 'event_hash'}


class TermsMemoryError(ValueError):
    """Safe closed failure: never includes paths, origins or owner text."""


def _require(condition):
    if not condition:
        raise TermsMemoryError('Terms decision history unavailable or invalid')


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(',', ':')).encode('utf-8')


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _text(value, limit):
    _require(type(value) is str and 0 < len(value) <= limit
             and bool(value.strip()) and not any(ord(c) < 32 for c in value))
    return value


def _case_id(value):
    _text(value, 256)
    _require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}', value) is not None
             and Redactor().text(value) == value)


def _digest(value):
    _require(type(value) is str and _HEX.fullmatch(value) is not None)
    return value


def _safe(path):
    for part in (path, *path.parents):
        _require(not part.is_symlink() and not part.is_junction())
        if part.exists():
            info = part.stat(follow_symlinks=False)
            _require(stat.S_ISDIR(info.st_mode) or
                     (stat.S_ISREG(info.st_mode) and info.st_nlink == 1))


def _origin(value):
    _text(value, 4096)
    # The conventional Git SSH transport user is not a credential. Other
    # userinfo, query strings and fragments are rejected before any output.
    if re.fullmatch(r'git@[^/:\s]+:[^\s]+', value):
        host, path = value[4:].split(':', 1)
    else:
        parsed = urlsplit(value)
        _require(parsed.scheme in ('https', 'ssh') and parsed.hostname
                 and not parsed.query and not parsed.fragment
                 and parsed.password is None
                 and (parsed.username is None or
                      (parsed.scheme == 'ssh' and parsed.username == 'git')))
        _require(parsed.port is None or parsed.port ==
                 (443 if parsed.scheme == 'https' else 22))
        host, path = parsed.hostname, parsed.path
    path = path.strip('/')
    if path.endswith('.git'):
        path = path[:-4]
    _require(path and all(p not in ('', '.', '..') for p in path.split('/'))
             and not any(c in path for c in ('?', '#', '@', '\\', '%')))
    _require(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?', host) is not None)
    return host.lower() + '/' + path


def _git_origin(root):
    """Capture at most 4097 origin bytes, with a bounded trusted Git lifetime."""
    pieces = []
    process = subprocess.Popen(
        [git_executable(root), '-C', str(root), 'config', '--local',
         '--no-includes', '--get', 'remote.origin.url'],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def capture():
        try:
            pieces.append(process.stdout.read(4097))
            if len(pieces[0]) > 4096:
                process.kill()
        except OSError:
            pass

    reader = threading.Thread(target=capture)
    reader.start()
    try:
        try:
            code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise TermsMemoryError('Terms decision history unavailable or invalid') from None
    finally:
        reader.join()
        process.stdout.close()
    _require(len(pieces) == 1 and len(pieces[0]) <= 4096)
    return code, pieces[0]


def repository_identity(repo_root):
    """Bind normalized local origin across checkouts; otherwise bind physical path.

    Origin is operator-local repository configuration, not authenticated ownership.
    No network, includes, target executables or hooks are evaluated.
    """
    try:
        root = Path(repo_root).absolute()
        _safe(root)
        root = root.resolve(strict=True)
        _require(root.is_dir())
        code, output = _git_origin(root)
        if code == 0:
            origin = output.decode('utf-8').strip()
            return _hash(('origin:' + _origin(origin)).encode('utf-8'))
        _require(code == 1 or not (root / '.git').exists())
        return _hash(('path:' + os.path.normcase(str(root))).encode('utf-8'))
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.SubprocessError):
        raise TermsMemoryError('Terms decision history unavailable or invalid') from None


class DecisionHistory:
    """Sealed verified history; event access returns defensive JSON copies."""
    __slots__ = ('_repository_id', '_revision', '_encoded')

    def __init__(self, repository_id, revision, events, *, _seal=None):
        _require(_seal is _SEAL)
        object.__setattr__(self, '_repository_id', repository_id)
        object.__setattr__(self, '_revision', revision)
        object.__setattr__(self, '_encoded', tuple(_json(e) for e in events))

    def __setattr__(self, name, value):
        raise AttributeError('Verified history is immutable')

    @property
    def repository_id(self):
        return self._repository_id

    @property
    def revision(self):
        return self._revision

    @property
    def events(self):
        return tuple(json.loads(e) for e in self._encoded)


def _location(repo_root, home, identity):
    root = Path(repo_root).absolute().resolve(strict=True)
    base = Path.home() if home is None else Path(home)
    _require(base.is_absolute())
    _safe(base)
    base = base.resolve()
    directory = base / '.local' / 'share' / 'devsift' / 'terms' / identity
    _safe(directory)
    _require(not directory.is_relative_to(root))
    return directory


def _read(path):
    _safe(path)
    _require(path.is_file() and path.stat().st_size <= _MAX_BYTES)
    # Private owned directories and nofollow checks guard accidental aliases.
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        info = os.fstat(stream.fileno())
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
        data = stream.read(_MAX_BYTES + 1)
    _require(len(data) <= _MAX_BYTES)
    return data


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _load(data):
    return json.loads(data, object_pairs_hook=_unique)


def _timestamp(value):
    _text(value, 64)
    parsed = datetime.fromisoformat(value)
    _require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0)
    return parsed


def _validated(directory, identity):
    marker = _load(_read(directory / 'ownership.json'))
    _require(marker == {'schema_version': '1', 'repository_id': identity})
    journal = _load(_read(directory / 'journal.json'))
    _require(type(journal) is dict and set(journal) == {'schema_version', 'repository_id', 'events'}
             and journal['schema_version'] == '1' and journal['repository_id'] == identity
             and type(journal['events']) is list and len(journal['events']) <= _MAX_EVENTS)
    previous = _ZERO
    seen = set()
    latest = {}
    prior_time = None
    for event in journal['events']:
        _require(type(event) is dict and set(event) == _KEYS
                 and event['repository_id'] == identity
                 and event['previous_hash'] == previous)
        _case_id(event['case_id'])
        _digest(event['fingerprint'])
        _digest(event['evidence_digest'])
        _require(type(event['choice']) is str and event['choice'] in _CHOICES)
        _text(event['owner'], 256)
        _text(event['rationale'], 8192)
        stamp = _timestamp(event['timestamp'])
        _require(prior_time is None or stamp >= prior_time)
        _require(type(event['event_id']) is str and re.fullmatch(r'[0-9a-f]{32}', event['event_id'])
                 and event['event_id'] not in seen)
        old = latest.get(event['case_id'])
        _require(event['supersedes'] is None or (old is not None and event['supersedes'] == old))
        _require(event['choice'] != 'reconsider' or event['supersedes'] is not None)
        _digest(event['event_hash'])
        body = {k: v for k, v in event.items() if k != 'event_hash'}
        _require(_hash(_json(body)) == event['event_hash'])
        # Persisted values must already be masked; never rehydrate a secret.
        _require(Redactor().text(event['owner']) == event['owner']
                 and Redactor().text(event['rationale']) == event['rationale'])
        previous, prior_time = event['event_hash'], stamp
        seen.add(event['event_id'])
        latest[event['case_id']] = event['event_id']
    return DecisionHistory(identity, previous, journal['events'], _seal=_SEAL)


@contextmanager
def _locked(directory, *, create=False):
    path = directory / 'history.lock'
    _safe(path)
    flags = os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
    if create:
        flags |= os.O_CREAT
    stream = os.fdopen(os.open(path, flags, 0o600), 'r+b', buffering=0)
    acquired = False
    try:
        info = os.fstat(stream.fileno())
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
        if create and info.st_size == 0:
            stream.write(b'0')
            os.fsync(stream.fileno())
        deadline = time.monotonic() + 15
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                _require(time.monotonic() < deadline)
                time.sleep(0.02)
        yield
    finally:
        if acquired:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def _atomic(directory, filename, value):
    data = _json(value)
    _require(len(data) <= _MAX_BYTES)
    pending = directory / (uuid.uuid4().hex + '.pending')
    try:
        with os.fdopen(os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                               0o600), 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _safe(directory / filename)
        os.replace(pending, directory / filename)
        if os.name != 'nt':
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if pending.exists():
            pending.unlink()


def read_history(repo_root, *, home=None):
    """Read only: a never-created store is empty; missing owned files fail closed."""
    try:
        identity = repository_identity(repo_root)
        directory = _location(repo_root, home, identity)
        if not directory.exists():
            return DecisionHistory(identity, _ZERO, (), _seal=_SEAL)
        _require(directory.is_dir())
        with _locked(directory):
            return _validated(directory, identity)
    except (OSError, ValueError, TypeError, RuntimeError):
        raise TermsMemoryError('Terms decision history unavailable or invalid') from None


def record_decision(repo_root, *, case_id, fingerprint, evidence_digest, choice,
                    owner, rationale, supersedes=None, as_of=None, home=None):
    """Append explicit attribution, retaining every previous event under OS lock.

    The caller must freshly assess the case and establish actual owner authority.
    A resolved claim still requires fresh evidence; no choice clears enforcement.
    """
    try:
        _case_id(case_id)
        _digest(fingerprint)
        _digest(evidence_digest)
        _require(type(choice) is str and choice in _CHOICES)
        owner = Redactor().text(_text(owner, 256))
        rationale = Redactor().text(_text(rationale, 8192))
        _require(supersedes is None or (type(supersedes) is str
                 and re.fullmatch(r'[0-9a-f]{32}', supersedes)))
        stamp = datetime.now(timezone.utc) if as_of is None else as_of
        _require(isinstance(stamp, datetime) and stamp.tzinfo is not None)
        stamp = stamp.astimezone(timezone.utc)
        identity = repository_identity(repo_root)
        directory = _location(repo_root, home, identity)
        # Create ancestors with private permissions before serializing initialization.
        ancestors = []
        parent = directory.parent
        while not parent.exists():
            ancestors.append(parent)
            parent = parent.parent
        _safe(parent)
        for parent in reversed(ancestors):
            parent.mkdir(mode=0o700, exist_ok=True)
            _safe(parent)
        # Parent initialization lock prevents a second writer overtaking the
        # directory creator before its ownership marker is committed.
        with _locked(directory.parent, create=True):
            created = False
            try:
                directory.mkdir(mode=0o700)
                created = True
            except FileExistsError:
                _require(directory.is_dir())
            _safe(directory)
            with _locked(directory, create=True):
                if created:
                    _require(not (directory / 'ownership.json').exists()
                             and not (directory / 'journal.json').exists())
                    _atomic(directory, 'ownership.json', {'schema_version': '1', 'repository_id': identity})
                    _atomic(directory, 'journal.json', {'schema_version': '1', 'repository_id': identity, 'events': []})
                history = _validated(directory, identity)
                events = list(history.events)
                _require(len(events) < _MAX_EVENTS)
                prior = next((e for e in reversed(events) if e['case_id'] == case_id), None)
                _require(supersedes is None or (prior is not None and prior['event_id'] == supersedes))
                _require(choice != 'reconsider' or supersedes is not None)
                if as_of is None:
                    stamp = datetime.now(timezone.utc)
                if events:
                    _require(stamp >= _timestamp(events[-1]['timestamp']))
                event = dict(repository_id=identity, case_id=case_id,
                             fingerprint=fingerprint, evidence_digest=evidence_digest,
                             choice=choice, owner=owner, rationale=rationale,
                             timestamp=stamp.isoformat(), event_id=uuid.uuid4().hex,
                             supersedes=supersedes, previous_hash=history.revision)
                event['event_hash'] = _hash(_json(event))
                events.append(event)
                _atomic(directory, 'journal.json', {'schema_version': '1', 'repository_id': identity, 'events': events})
                return dict(event)
    except (OSError, ValueError, TypeError, RuntimeError):
        raise TermsMemoryError('Terms decision history unavailable or invalid') from None
