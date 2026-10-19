"""Explicit user setup and fixed-location analyzer registration; never build on scan."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import tempfile
import unicodedata
import uuid
import zipfile
from dataclasses import replace

from .native_manifest import load_manifest
from .native_host import probe_tool


class SetupError(ValueError):
    """Safe setup/configuration failure, without executable arguments or source."""


def _require(value):
    if not value:
        raise SetupError('Analyzer setup unavailable; run devsift setup --help or reinstall DevSift.')


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def _safe(path, *, directory=False):
    path = Path(path).absolute()
    for part in reversed((path, *path.parents)):
        _require(not part.is_symlink() and not part.is_junction())
        if part.exists():
            info = part.stat(follow_symlinks=False)
            _require(stat.S_ISDIR(info.st_mode) or
                     (part == path and not directory and stat.S_ISREG(info.st_mode) and info.st_nlink == 1))
    return path


def _mkdir(path):
    _safe(path, directory=True)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    _safe(path, directory=True)


def registry_path(home=None):
    _require(home is None or Path(home).is_absolute())
    return (Path.home() if home is None else Path(home)) / '.local/share/devsift/analyzers.json'


def registered(home=None):
    """Read only the operator registry, never a project manifest or current cwd."""
    path = _safe(registry_path(home))
    if not path.exists():
        return None
    try:
        with path.open('rb') as stream:
            before = os.fstat(stream.fileno())
            raw = stream.read(32769)
            after = os.fstat(stream.fileno())
        _require(len(raw) <= 32768 and (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns)
                 == (after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns))
        value = _json(raw)
        _require(type(value) is dict and set(value) == {'schema_version', 'manifest', 'digest'}
                 and value['schema_version'] == '1' and type(value['manifest']) is str
                 and Path(value['manifest']).is_absolute())
        manifest = _safe(value['manifest'])
        # Stored pins are preserved; changed files must be explicitly set up again.
        load_manifest(manifest, value['digest'])
        return str(manifest), value['digest']
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise SetupError('Registered analyzers are unavailable or changed; run devsift setup --help.') from None


def resolve(manifest, digest, *, home=None):
    if manifest is not None or digest is not None:
        _require(manifest is not None and digest is not None)
        return manifest, digest
    return registered(home)


def _atomic(path, raw):
    _safe(path)
    _mkdir(path.parent)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.devsift-', delete=False) as stream:
            temporary = Path(stream.name)
            if os.name != 'nt':
                os.chmod(temporary, 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _safe(path)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def register(manifest, digest, *, home=None):
    """Operator authorization: verify every identity before activating a default."""
    _require(Path(manifest).is_absolute())
    path = _safe(manifest)
    entries = load_manifest(path, digest)
    _require(entries and all(ready(entry.tool) for entry in entries))
    value = {'schema_version': '1', 'manifest': str(path), 'digest': digest}
    _atomic(registry_path(home), (json.dumps(value, sort_keys=True) + '\n').encode('utf-8'))
    return {'analysis_performed': False, 'analysis_ready': True,
            'registered_tools': [entry.tool.tool_id for entry in entries],
            'languages': sorted({language for entry in entries for language in entry.tool.languages})}


def ready(tool):
    """Metadata probes are finite even when source analysis has no wall deadline."""
    timeout = tool.process.timeout_seconds
    bounded = replace(tool, process=replace(tool.process, timeout_seconds=5 if timeout is None else min(timeout, 5)))
    return probe_tool(bounded).available


def platform_id():
    system = {'Windows': 'windows', 'Linux': 'linux', 'Darwin': 'macos'}.get(platform.system())
    machine = platform.machine().lower()
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(machine)
    _require(system and arch)
    return system + '-' + arch


def _member(name):
    _require(type(name) is str and 0 < len(name) <= 1000 and '\\' not in name
             and ':' not in name and not name.startswith('/')
             and not any(unicodedata.category(char).startswith('C') for char in name))
    parts = name.split('/')
    _require(all(part not in ('', '.', '..') and not part.endswith((' ', '.'))
                 and not re.fullmatch(r'(?:con|prn|aux|nul|com[1-9\u00b9\u00b2\u00b3]|lpt[1-9\u00b9\u00b2\u00b3])(?:\..*)?', part, re.I)
                 for part in parts))
    return PurePosixPath(name)


def deploy(archive, digest, *, home=None):
    """Deploy a caller-authorized release archive, then register its frozen pins."""
    _require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest))
    _require(Path(archive).is_absolute())
    archive = _safe(archive)
    _require(archive.stat().st_size <= 512_000_000)
    with archive.open('rb') as stream:
        raw = stream.read(512_000_001)
    _require(len(raw) <= 512_000_000 and hashlib.sha256(raw).hexdigest() == digest)
    base = registry_path(home).parent / 'analyzers'
    _mkdir(base)
    destination = base / uuid.uuid4().hex
    _mkdir(destination)
    # This new directory is never activated on any extraction/probe failure.
    # Extract the exact immutable bytes whose digest was approved, not a reopened
    # path that could have been replaced after verification.
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        entries = bundle.infolist()
        _require(0 < len(entries) <= 30000)
        seen, total = set(), 0
        for entry in entries:
            relative = _member(entry.filename)
            key = unicodedata.normalize('NFC', str(relative)).casefold()
            mode = entry.external_attr >> 16
            _require(key not in seen and not entry.is_dir() and not entry.flag_bits & 1
                     and (not stat.S_IFMT(mode) or stat.S_ISREG(mode))
                     and entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                     and 0 <= entry.file_size <= 200_000_000)
            seen.add(key)
            total += entry.file_size
            _require(total <= 2_000_000_000)
        _require('manifest-template.json' in seen)
        for entry in entries:
            target = destination.joinpath(*_member(entry.filename).parts)
            _mkdir(target.parent)
            _safe(target)
            count = 0
            with bundle.open(entry) as source, target.open('xb') as output:
                while block := source.read(65536):
                    count += len(block)
                    _require(count <= entry.file_size)
                    output.write(block)
            _require(count == entry.file_size)
            if os.name != 'nt':
                target.chmod(0o700 if entry.external_attr >> 16 & 0o111 else 0o600)
    template = destination / 'manifest-template.json'
    _require(template.stat().st_size <= 2_000_000)
    data = _json(template.read_bytes())
    _require(type(data) is dict and set(data) == {'schema_version', 'platform', 'tools'}
             and data['schema_version'] == '1' and data['platform'] == platform_id()
             and type(data['tools']) is list and len(data['tools']) == 4)

    def rebase(value):
        _require(type(value) is str and value.startswith('@ROOT@/'))
        relative = _member(value[7:])
        target = destination.joinpath(*relative.parts)
        _safe(target)
        _require(target.is_file())
        return str(target)

    for entry in data['tools']:
        _require(type(entry) is dict and set(entry) == {'definition', 'dialect'})
        definition = entry['definition']
        _require(type(definition) is dict and set(definition) == {
            'tool_id', 'tool_version', 'languages', 'process', 'executable_digest', 'artifacts', 'engine_versions'})
        process = definition['process']
        _require(type(process) is dict and set(process) == {
            'executable', 'argv', 'timeout_seconds', 'max_stdout_bytes', 'max_stderr_bytes', 'max_stdin_bytes', 'environment'})
        _require(type(process['argv']) is list and all(type(value) is str and value.startswith('@ROOT@/')
                 for value in process['argv']))
        _require(type(definition['artifacts']) is list and all(type(pair) is list and len(pair) == 2
                 and all(type(value) is str for value in pair) for pair in definition['artifacts']))
        process['executable'] = rebase(process['executable'])
        process['argv'] = [rebase(value) for value in process['argv']]
        definition['artifacts'] = [[rebase(name), pin] for name, pin in definition['artifacts']]
    manifest = destination / 'native-manifest.json'
    raw = (json.dumps({'schema_version': '1', 'tools': data['tools']}, separators=(',', ':')) + '\n').encode('utf-8')
    _atomic(manifest, raw)
    pin = hashlib.sha256(raw).hexdigest()
    configured = load_manifest(manifest, pin)
    _require({entry.tool.tool_id for entry in configured} ==
             {'devsift-go', 'devsift-roslyn', 'devsift-sql', 'devsift-typescript'})
    return register(manifest, pin, home=home)
