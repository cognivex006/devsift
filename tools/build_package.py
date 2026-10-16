"""Deterministic source-component bundles; no wheel/native build or install."""
import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
if __package__:
    from .package_manifest import COMPONENTS, inventory
else:
    # Explicit trusted authoring-script path, never the consumer cwd.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from package_manifest import COMPONENTS, inventory

MAX_BYTES = 64_000_000
_MESSAGE = 'Invalid or unavailable package bundle'
_NAMES = {c: 'devsift-' + c + ('-source' if c.startswith('core-') else '') + '.zip' for c in COMPONENTS}


class PackageBuildError(ValueError):
    """Fixed safe error; never include source, paths or command output."""


@dataclass(frozen=True)
class Artifact:
    name: str
    size: int
    sha256: str

    def to_dict(self):
        return {'name': self.name, 'size': self.size, 'sha256': self.sha256}


def _require(ok):
    if not ok:
        raise PackageBuildError(_MESSAGE)


def _sha(value):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{40}', value) and value != '0' * 40)
    return value


def _digest(value):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value))
    return value


def _plain(path, *, file=False):
    info = path.lstat()
    _require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 1024))
    _require(stat.S_ISREG(info.st_mode) if file else stat.S_ISDIR(info.st_mode))
    return info


def _directory(path):
    path = Path(path).absolute()
    for part in reversed((path, *path.parents)):
        _plain(part)
    return path.resolve(strict=True)


def _read(path, limit):
    _directory(path.parent)
    info = _plain(path, file=True)
    _require(info.st_size <= limit)
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    after = _plain(path, file=True)
    _require(len(raw) <= limit and (info.st_ino, info.st_dev, info.st_size, info.st_mtime_ns)
             == (after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns))
    return raw


def _git(root, *args):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env['GIT_LITERAL_PATHSPECS'] = '1'
    run = subprocess.run(['git', '--no-replace-objects', '-c', 'core.fsmonitor=false', '-C', str(root), *args],
                         env=env, capture_output=True, timeout=30, check=True)
    _require(len(run.stdout) <= MAX_BYTES)
    return run.stdout


def _index(root, paths):
    result = {}
    for raw in _git(root, 'ls-files', '--stage', '-z', '--', *paths).split(b'\0'):
        if raw:
            meta, path = raw.split(b'\t', 1)
            mode, oid, stage = meta.split(b' ')
            name = path.decode('utf-8')
            _require(stage == b'0' and mode in {b'100644', b'100755'} and name not in result)
            result[name] = (mode, oid)
    return result


def _inputs(root, source_sha, components):
    _require(_git(root, 'rev-parse', '--verify', source_sha + '^{commit}').strip().decode('ascii') == source_sha)
    _require(_git(root, 'rev-parse', '--verify', 'HEAD').strip().decode('ascii') == source_sha)
    records = {c: inventory(root, c) for c in components}
    expected = {f.path: f for files in records.values() for f in files}
    paths = tuple(sorted(set(expected) | {'packaging/manifest.json'}))
    indexed = _index(root, paths)
    tree = {}
    for raw in _git(root, 'ls-tree', '-z', source_sha, '--', *paths).split(b'\0'):
        if raw:
            meta, path = raw.split(b'\t', 1)
            mode, kind, oid = meta.split(b' ')
            _require(kind == b'blob' and mode in {b'100644', b'100755'})
            tree[path.decode('utf-8')] = (mode, oid)
    _require(set(tree) == set(paths) and tree == indexed)
    data = {}
    for name, (_, oid) in sorted(tree.items()):
        length = int(_git(root, 'cat-file', '-s', oid.decode('ascii')).strip())
        _require(0 <= length <= 8_000_000 and sum(map(len, data.values())) + length <= MAX_BYTES)
        raw = _git(root, 'cat-file', 'blob', oid.decode('ascii'))
        _require(len(raw) == length and raw == _read(root / name, 8_000_000))
        if name in expected:
            _require(expected[name].size == length and expected[name].sha256 == hashlib.sha256(raw).hexdigest())
        data[name] = raw
    _require(_index(root, paths) == indexed and _git(root, 'rev-parse', '--verify', 'HEAD').strip().decode('ascii') == source_sha)
    return records, data


def _encode(data):
    return (json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('ascii')


def _archive(files, data):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for entry in files:
            item = zipfile.ZipInfo(entry.path, (1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data[entry.path])
    return buffer.getvalue()


def _artifact(name, raw):
    return Artifact(name, len(raw), hashlib.sha256(raw).hexdigest())


def _sums(items):
    return ''.join(item.sha256 + '  ' + item.name + '\n' for item in sorted(items, key=lambda x: x.name)).encode('ascii')


def build_package(root, destination, *, source_sha, components=tuple(sorted(COMPONENTS))):
    """Create a new outside-source directory only after all input proof passes."""
    try:
        source_sha = _sha(source_sha)
        root = _directory(root)
        _require(type(components) is tuple and 0 < len(components) <= 4
                 and all(type(c) is str and c in COMPONENTS for c in components)
                 and len(set(components)) == len(components))
        components = tuple(sorted(components))
        output = Path(destination)
        _require(output.is_absolute() and '..' not in output.parts and not os.path.lexists(output))
        parent = _directory(output.parent)
        output = parent / output.name
        excluded = [root]
        for option in ('--git-dir', '--git-common-dir'):
            excluded.append(Path(_git(root, 'rev-parse', '--path-format=absolute', option).strip().decode()).resolve())
        _require(not any(output.is_relative_to(path) for path in excluded))
        records, data = _inputs(root, source_sha, components)
        payloads, descriptions = {}, []
        for component in components:
            name = _NAMES[component]
            raw = _archive(records[component], data)
            payloads[name] = raw
            descriptions.append({'component': component, 'archive': name, 'size': len(raw),
                                 'sha256': hashlib.sha256(raw).hexdigest(),
                                 'files': [f.to_dict() for f in records[component]]})
        payloads['integrity.json'] = _encode({'schema_version': '1', 'artifact_kind': 'component-source-bundles',
            'source_sha': source_sha, 'package_manifest_sha256': hashlib.sha256(data['packaging/manifest.json']).hexdigest(),
            'components': descriptions})
        payloads['SHA256SUMS'] = _sums([_artifact(name, raw) for name, raw in payloads.items()])
        output.mkdir()  # Exclusive; never reuse an existing empty directory.
        for name, raw in sorted(payloads.items()):
            _directory(output)
            with (output / name).open('xb') as stream:
                stream.write(raw)
        return tuple(_artifact(name, raw) for name, raw in sorted(payloads.items()))
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, subprocess.SubprocessError):
        raise PackageBuildError(_MESSAGE) from None


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _relative(path):
    _require(type(path) is str and len(path) <= 200 and re.fullmatch('[A-Za-z0-9_./-]+', path))
    _require(not path.startswith('/') and all(p not in {'', '.', '..'} for p in path.split('/')))


def verify_bundle(destination, *, expected_integrity_sha256, expected_source_sha):
    """Read-only integrity validation; expected digest must be trusted separately."""
    try:
        _digest(expected_integrity_sha256)
        _sha(expected_source_sha)
        output = Path(destination)
        _require(output.is_absolute())
        output = _directory(output)
        raw = _read(output / 'integrity.json', 1_000_000)
        _require(hashlib.sha256(raw).hexdigest() == expected_integrity_sha256)
        info = json.loads(raw, object_pairs_hook=_pairs)
        _require(type(info) is dict and set(info) == {'schema_version', 'artifact_kind', 'source_sha', 'package_manifest_sha256', 'components'})
        _require(info['schema_version'] == '1' and info['artifact_kind'] == 'component-source-bundles'
                 and info['source_sha'] == expected_source_sha)
        _digest(info['package_manifest_sha256'])
        components = info['components']
        _require(type(components) is list and 0 < len(components) <= 4)
        seen, items = [], [_artifact('integrity.json', raw)]
        for component in components:
            _require(type(component) is dict and set(component) == {'component', 'archive', 'size', 'sha256', 'files'})
            name = component['component']
            _require(type(name) is str and name in COMPONENTS and name not in seen)
            seen.append(name)
            _require(component['archive'] == _NAMES[name])
            _require(type(component['size']) is int and 0 <= component['size'] <= MAX_BYTES + 2_000_000)
            _digest(component['sha256'])
            content = _read(output / _NAMES[name], MAX_BYTES + 2_000_000)
            _require(len(content) == component['size'] and hashlib.sha256(content).hexdigest() == component['sha256'])
            files = component['files']
            _require(type(files) is list and 0 < len(files) <= 400)
            names, total = [], 0
            for f in files:
                _require(type(f) is dict and set(f) == {'path', 'size', 'sha256'})
                _relative(f['path'])
                _require(f['path'].casefold() not in [n.casefold() for n in names])
                names.append(f['path'])
                _require(type(f['size']) is int and 0 <= f['size'] <= 8_000_000)
                _digest(f['sha256'])
                total += f['size']
            _require(names == sorted(names) and total <= MAX_BYTES)
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                _require(archive.namelist() == names and not archive.comment)
                for entry, f in zip(archive.infolist(), files):
                    _require(entry.compress_type == zipfile.ZIP_STORED and entry.file_size == f['size']
                             and entry.compress_size == f['size'] and entry.flag_bits == 0
                             and entry.date_time == (1980, 1, 1, 0, 0, 0) and entry.create_system == 3
                             and entry.external_attr == 0o100644 << 16 and not entry.extra and not entry.comment)
                    _require(hashlib.sha256(archive.read(entry)).hexdigest() == f['sha256'])
            items.append(_artifact(_NAMES[name], content))
        _require(seen == sorted(seen))
        _require({p.name for p in output.iterdir()} == {i.name for i in items} | {'SHA256SUMS'})
        sums = _read(output / 'SHA256SUMS', 4_000)
        _require(sums == _sums(items))
        return tuple(sorted([*items, _artifact('SHA256SUMS', sums)], key=lambda a: a.name))
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, zipfile.BadZipFile):
        raise PackageBuildError(_MESSAGE) from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise PackageBuildError(_MESSAGE)


def main(argv=None):
    try:
        parser = _Parser(description=__doc__, allow_abbrev=False)
        commands = parser.add_subparsers(dest='command', required=True, parser_class=_Parser)
        build = commands.add_parser('build', allow_abbrev=False)
        build.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
        build.add_argument('--output', required=True)
        build.add_argument('--source-sha', required=True)
        build.add_argument('--component', action='append', choices=sorted(COMPONENTS))
        verify = commands.add_parser('verify', allow_abbrev=False)
        verify.add_argument('--output', required=True)
        verify.add_argument('--source-sha', required=True)
        verify.add_argument('--integrity-sha256', required=True)
        args = parser.parse_args(argv)
        if args.command == 'build':
            artifacts = build_package(args.root, args.output, source_sha=args.source_sha,
                                      components=tuple(args.component) if args.component else tuple(sorted(COMPONENTS)))
        else:
            artifacts = verify_bundle(args.output, expected_source_sha=args.source_sha,
                                      expected_integrity_sha256=args.integrity_sha256)
        print(json.dumps({'schema_version': '1', 'artifacts': [a.to_dict() for a in artifacts]}, sort_keys=True))
        return 0
    except PackageBuildError:
        print(_MESSAGE, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
