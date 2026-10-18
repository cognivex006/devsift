"""Owned disk-backed scan sessions: raw source stays in the current snapshot only."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .output import result
import stat


class StoreError(ValueError):
    """Constant-message storage failure without source or operating-system details."""


def _require(condition):
    if not condition:
        raise StoreError('Scan storage unavailable')


def _json(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _safe_path(path):
    for component in (path, *path.parents):
        _require(not component.is_symlink() and not component.is_junction())
        if component.exists():
            metadata = component.stat(follow_symlinks=False)
            _require(stat.S_ISDIR(metadata.st_mode) or
                     (stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1))


def _mkdir_private(directory):
    """Create only missing owned ancestors with private POSIX permissions."""
    missing = []
    component = directory
    while not component.exists():
        missing.append(component)
        component = component.parent
    _safe_path(component)
    for component in reversed(missing):
        component.mkdir(mode=0o700)


def _private_file(path, mode, **kwargs):
    # The containing directory is already private before any source data exists.
    # Windows inherits the user's existing ACL; no ACL/chmod changes are applied.
    return open(path, mode, opener=lambda name, flags: os.open(name, flags, 0o600), **kwargs)


def _lock(directory):
    path = directory / 'session.lock'
    _safe_path(path)
    stream = _private_file(path, 'a+b')
    try:
        if not path.stat().st_size:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return stream
    except OSError:
        stream.close()
        raise StoreError('Scan storage unavailable') from None


def _unlock(stream):
    if stream is not None and not stream.closed:
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def _verify_database(path, owner):
    probe = None
    try:
        probe = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0)
        row = probe.execute("SELECT value FROM metadata WHERE key='owner'").fetchone()
        _require(row is not None and row[0] == owner)
    except sqlite3.Error:
        raise StoreError('Scan storage unavailable') from None
    finally:
        if probe is not None:
            probe.close()


def _owned_directory(root, destination, resume, configuration):
    source = Path(root)
    _safe_path(source.absolute())
    source = source.resolve(strict=True)
    _require(source.is_dir())
    identity = _hash(os.path.normcase(str(source)).encode())
    config = _hash(_json(configuration).encode())
    directory = (Path.home() / '.local/share/devsift/scans' / identity / uuid.uuid4().hex
                 if destination is None else Path(destination))
    _require(directory.is_absolute())
    _safe_path(directory)
    directory = directory.resolve()
    _require(not directory.is_relative_to(source))
    if resume:
        _require(directory.is_dir())
        _safe_path(directory / 'ownership.json')
        marker = json.loads((directory / 'ownership.json').read_text('utf-8'))
        _require(set(marker) == {'schema', 'root', 'configuration', 'owner'}
                 and marker['schema'] == 1 and marker['root'] == identity
                 and marker['configuration'] == config and len(marker['owner']) == 32)
    else:
        _require(not directory.exists())
        _mkdir_private(directory)
        marker = dict(schema=1, root=identity, configuration=config, owner=uuid.uuid4().hex)
        temporary = directory / 'ownership.pending'
        with _private_file(temporary, 'x', encoding='utf-8') as stream:
            stream.write(_json(marker))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(directory / 'ownership.json')
    return source, directory, marker


class StoredResult:
    def __init__(self, root, directory, connection, generation, lock_handle=None):
        self.root, self.directory, self.connection = root, directory, connection
        self.generation = generation
        self.bundle = None
        self.lock_handle = lock_handle

    def _meta(self, key):
        return self.connection.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()[0]

    def _set(self, key, value):
        self.connection.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', (key, str(value)))

    def error(self, code):
        with self.connection:
            self.connection.execute('INSERT OR IGNORE INTO session_errors VALUES (?)', (code,))

    def errors(self):
        # Category cardinality is fixed by producer/error protocol, not target count.
        codes = {row[0] for row in self.connection.execute('SELECT code FROM session_errors')}
        for (raw,) in self.connection.execute('SELECT record FROM targets WHERE generation=?', (self.generation,)):
            codes.update(error['code'] for error in json.loads(raw)['errors'])
        duplicate = self.connection.execute('''SELECT 1 FROM findings f JOIN targets t ON t.identity=f.target
            WHERE t.generation=? GROUP BY f.case_id HAVING count(*)>1 LIMIT 1''', (self.generation,)).fetchone()
        if duplicate:
            codes.add('DUPLICATE_CASE_ID')
        return [{'code': code, 'message': 'Scan work is incomplete; inspect stored coverage and evidence.'}
                for code in sorted(codes)]

    def iter_findings(self):
        return self.connection.execute('''SELECT f.id,f.payload FROM findings f JOIN targets t
            ON t.identity=f.target WHERE t.generation=? ORDER BY json_extract(f.payload, '$.path'),f.case_id,f.id''', (self.generation,))

    def summary(self):
        counts = dict(executed=0, skipped=0, unavailable=0, incomplete=0)
        target_count = finding_count = enforced = 0
        security_review_required = False
        complete = self._meta('finished') == '1'
        for (raw,) in self.connection.execute('SELECT record FROM targets WHERE generation=?', (self.generation,)):
            record = json.loads(raw)
            target_count += len(record['data'].get('targets', []))
            security_review_required = security_review_required or bool(
                record['data'].get('quality_gate', {}).get('security_review_required', False))

            complete = complete and record['complete']
            for key in counts:
                counts[key] += record['data'].get('counts', {}).get(key, 0)
        for _, payload in self.iter_findings():
            finding_count += 1
            finding = json.loads(payload)
            enforced += finding['enforcement'] == 'block'
            security_review_required = security_review_required or finding['security_escalation']
        errors = self.errors()
        complete = complete and not errors
        if self.bundle is not None:
            from .report_bundle import verify_bundle
            valid = verify_bundle(self, self.bundle)
            complete = complete and valid and self.bundle.get('complete', False)
            if not valid:
                errors.append({'code': 'REPORT_UNAVAILABLE', 'message': 'A report page is missing or changed.'})
        command = self._meta('command')
        record = result(command, complete=complete, enforced_count=enforced, errors=errors,
                        data={'counts': counts, 'target_count': target_count,
                              'finding_count': finding_count, 'scan_directory': str(self.directory),
                              'execution': {'fresh_targets': int(self._meta('fresh_targets')),
                                            'reused_targets': int(self._meta('reused_targets'))}})
        public_data = self.connection.execute("SELECT value FROM metadata WHERE key='public_data'").fetchone()
        if public_data:
            record['data'].update(json.loads(public_data[0]))
        if security_review_required or 'quality_gate' in record['data']:
            gate = record['data'].setdefault('quality_gate', {})
            gate['security_review_required'] = bool(gate.get('security_review_required') or security_review_required)
        if self.bundle is not None:
            record['data']['report_bundle'] = {key: self.bundle[key] for key in
                                              ('index', 'markdown_index', 'page_count', 'case_count', 'reports_complete', 'analysis_complete')}
            record['data']['report_bundle']['reports_complete'] = bool(valid and self.bundle['reports_complete'])
        return record

    @property
    def exit_code(self):
        return self.summary()['exit_code']

    def write_json(self, text_stream):
        summary = self.summary()
        # Large arrays are emitted from SQLite; no joined repository-sized object.
        if self.bundle is not None and not any(e['code'] == 'REPORT_UNAVAILABLE' for e in summary['errors']) and summary['data']['target_count'] <= 2048 and summary['data']['finding_count'] <= 32 and self.bundle['page_count'] == 1:
            documents = {}
            row = self.connection.execute('SELECT payload FROM report_pages').fetchone()
            if row:
                for descriptor in json.loads(row[0])['files']:
                    path = Path(self.bundle['index']).parent / descriptor['file']
                    name = path.name
                    if name in ('findings.json', 'report.md', 'results.sarif') and descriptor['bytes'] <= 16_000_000:
                        raw = path.read_text('utf-8')
                        documents[{'findings.json': 'json', 'report.md': 'markdown', 'results.sarif': 'sarif'}[name]] = raw if name == 'report.md' else json.loads(raw)
            summary['data']['reports'] = documents
        else:
            summary['data']['reports'] = {}
        prefix = {key: value for key, value in summary.items() if key not in ('findings', 'data')}
        text_stream.write(_json(prefix)[:-1] + ',"findings":[')
        separator = ''
        for _, payload in self.iter_findings():
            text_stream.write(separator + payload)
            separator = ','
        text_stream.write('],"data":' + _json(summary['data'])[:-1] + ',"targets":[')
        separator = ''
        for (raw,) in self.connection.execute("SELECT record FROM targets WHERE generation=? ORDER BY json_extract(record, '$.data.targets[0].path'),identity", (self.generation,)):
            for target in json.loads(raw)['data'].get('targets', []):
                text_stream.write(separator + _json(target))
                separator = ','
        text_stream.write(']}}\n')
        return summary['exit_code']

    def close(self):
        try:
            self.connection.close()
        finally:
            _unlock(self.lock_handle)


def run_streamed(root, records_factory, *, destination=None, resume=False,
                 configuration=None, formats=None, policy=None, trusted_lifecycles=False):
    """Persist per-target safe records transactionally and render complete paged reports.

    The factory must call ``should_scan(SourceTarget)`` before each target analysis.
    KeyboardInterrupt/SystemExit propagate after marking the session incomplete;
    resuming the owned destination reuses only complete byte-identical targets.
    """
    source, directory, marker = _owned_directory(root, destination, resume, configuration)
    lock_handle = _lock(directory)
    success = False
    connection = None
    stored = None
    iterator = None
    try:
        database = directory / 'scan.sqlite3'
        for name in ('scan.sqlite3', 'scan.sqlite3-wal', 'scan.sqlite3-shm', 'scan.sqlite3-journal'):
            _safe_path(directory / name)
        if resume:
            _require(database.is_file())
            _verify_database(database, marker['owner'])
        if not resume:
            with _private_file(database, 'xb'):
                pass
        connection = sqlite3.connect(database)
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA synchronous=FULL')
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS targets(identity TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,
                generation TEXT NOT NULL,complete INTEGER NOT NULL,record TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS findings(id INTEGER PRIMARY KEY,target TEXT NOT NULL,
                case_id TEXT NOT NULL,payload TEXT NOT NULL,
                FOREIGN KEY(target) REFERENCES targets(identity) ON DELETE CASCADE);
            CREATE INDEX IF NOT EXISTS case_index ON findings(case_id);
            CREATE TABLE IF NOT EXISTS session_errors(code TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS occurrences(identity TEXT PRIMARY KEY,count INTEGER NOT NULL);
        ''')
        generation = uuid.uuid4().hex
        stored = StoredResult(source, directory, connection, generation, lock_handle)
        if resume:
            _require(stored._meta('owner') == marker['owner'])
        else:
            stored._set('owner', marker['owner'])
        with connection:
            stored._set('finished', 0)
            stored._set('fresh_targets', 0)
            stored._set('reused_targets', 0)
            stored._set('generation', generation)
            stored._set('command', configuration.get('command', 'scan') if type(configuration) is dict else 'scan')
            connection.execute('DELETE FROM session_errors')
            connection.execute('DELETE FROM occurrences')
        pending = None
        cached_public_data = None

        def should_scan(target):
            nonlocal pending
            _require(pending is None)
            path_identity = _hash(target.path.encode('utf-8'))
            prior = connection.execute('SELECT count FROM occurrences WHERE identity=?', (path_identity,)).fetchone()
            ordinal = 0 if prior is None else prior[0]
            with connection:
                connection.execute('INSERT OR REPLACE INTO occurrences VALUES (?,?)', (path_identity, ordinal + 1))
            identity = _hash((path_identity + ':' + str(ordinal)).encode())
            digest = hashlib.sha256()
            digest.update(_json([target.status, target.language, target.reason]).encode())
            if target.content is not None:
                digest.update(target.content)
            fingerprint = digest.hexdigest()
            previous = connection.execute('SELECT fingerprint,complete FROM targets WHERE identity=?', (identity,)).fetchone()
            with connection:
                if previous and previous == (fingerprint, 1):
                    connection.execute('UPDATE targets SET generation=? WHERE identity=?', (generation, identity))
                    stored._set('reused_targets', int(stored._meta('reused_targets')) + 1)
                    return False
                connection.execute('DELETE FROM targets WHERE identity=?', (identity,))
            pending = (identity, fingerprint)
            return True

        iterator = iter(records_factory(should_scan))
        for record in iterator:
            _require(type(record) is dict and record.get('command') in ('scan', 'ci')
                     and type(record.get('data')) is dict and type(record.get('findings')) is list)
            targets = record['data'].get('targets', [])
            _require(type(targets) is list and len(targets) <= 1)
            if pending is None:
                _require(not targets)
                identity, fingerprint = 'empty-scope', ''
            else:
                identity, fingerprint = pending
                _require(len(targets) == 1)
            pending = None
            # Defense in depth: only safe producer records cross the disk boundary.
            from .redaction import Redactor
            masker = Redactor()
            header = masker.redact({**record, 'findings': [], 'data': {
                **record['data'], 'targets': []}})
            header['data']['targets'] = [masker.redact(target) for target in targets]
            header['findings'] = [masker.redact(finding) for finding in record['findings']]
            public_data = {key: value for key, value in header['data'].items() if key not in ('targets', 'counts', 'reports', 'report_bundle')}
            if cached_public_data and type(public_data.get('quality_gate')) is dict:
                previous_gate = cached_public_data.get('quality_gate', {})
                public_data['quality_gate']['security_review_required'] = bool(
                    public_data['quality_gate'].get('security_review_required')
                    or previous_gate.get('security_review_required'))
            if public_data and public_data != cached_public_data:
                with connection:
                    stored._set('public_data', _json(public_data))
                cached_public_data = public_data
            safe_findings = header.pop('findings')
            header['findings'] = []
            with connection:
                connection.execute('INSERT OR REPLACE INTO targets VALUES (?,?,?,?,?)',
                                   (identity, fingerprint, generation, int(header['complete']), _json(header)))
                if targets:
                    stored._set('fresh_targets', int(stored._meta('fresh_targets')) + 1)
                for finding in safe_findings:
                    connection.execute('INSERT INTO findings(target,case_id,payload) VALUES (?,?,?)',
                                       (identity, finding['case_id'], _json(finding)))
        _require(pending is None)
        with connection:
            connection.execute('DELETE FROM targets WHERE generation<>?', (generation,))
            stored._set('finished', 1)
        from .report_bundle import build_bundle
        stored.bundle = build_bundle(stored, formats=formats, policy=policy,
                                     trusted_lifecycles=trusted_lifecycles)
        success = True
        return stored
    except BaseException:
        if stored is not None:
            with connection:
                stored._set('finished', 0)
            stored.error('SCAN_INTERRUPTED')
        if connection is not None:
            connection.close()
        raise
    finally:
        if iterator is not None and hasattr(iterator, 'close'):
            iterator.close()
        if not success:
            _unlock(lock_handle)
