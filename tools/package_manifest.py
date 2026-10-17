"""Read-only explicit packaging input inventory. Never imported by scanning."""
from dataclasses import dataclass
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

COMPONENTS = frozenset({'core-wheel', 'core-sdist', 'consumer-skill', 'source-assets'})
_FORBIDDEN = frozenset({'.git', '.devsift', '.venv', 'venv', 'worktrees', '.worktrees',
                        'node_modules', '__pycache__', '.pytest_cache', 'build', 'dist',
                        'bin', 'obj', 'plan', 'templates', 'governance', '.github'})
_BAD_SUFFIXES = ('.dll', '.exe', '.so', '.dylib', '.pyd', '.node', '.pyc', '.pyo', '.log', '.pem', '.key')
_MESSAGE = 'Invalid or unavailable package manifest'


class PackageManifestError(ValueError):
    """Only fixed public errors; input paths and file data are never echoed."""


@dataclass(frozen=True)
class Component:
    name: str
    required: tuple[str, ...]
    optional: tuple[str, ...]


@dataclass(frozen=True)
class PackageFile:
    path: str
    size: int
    sha256: str

    def to_dict(self):
        return {'path': self.path, 'size': self.size, 'sha256': self.sha256}


def _require(condition):
    if not condition:
        raise PackageManifestError(_MESSAGE)


def _path(value):
    _require(type(value) is str and 0 < len(value) <= 200)
    _require(re.fullmatch(r'[A-Za-z0-9_./-]+', value) is not None)
    parts = PurePosixPath(value).parts
    _require((not value.startswith('/') and '/' in value) or value in {'MANIFEST.in', 'pyproject.toml'})
    _require(all(p not in {'', '.', '..'} for p in value.split('/')))
    _require(not (set(p.casefold() for p in parts) & _FORBIDDEN))
    _require(not any(p.casefold().startswith(('.env', '.git', '.ssh')) or p.casefold().endswith('.egg-info') for p in parts))
    _require(not value.casefold().endswith(_BAD_SUFFIXES))
    _require(parts[0] not in {'AGENTS.md', 'DEVELOPMENT.md'})
    return value


def _allowed(path, component):
    parts = PurePosixPath(path).parts
    module = len(parts) == 2 and parts[0] == 'devsift' and re.fullmatch(r'[a-z_]+\.py', parts[1]) is not None
    metadata = {'MANIFEST.in', 'pyproject.toml', 'packaging/manifest.json',
                'tools/package_manifest.py', 'docs/development/PACKAGING.md'}
    if component == 'core-wheel':
        _require(module)
    elif component == 'core-sdist':
        _require(module or path in metadata)
    elif component == 'consumer-skill':
        _require(path in {'skills/devsift/SKILL.md', 'skills/devsift/CONSUMER-SCOPE.md'}
                 or (parts[:3] == ('skills', 'devsift', 'references')
                     and len(parts) in {4, 5} and path.endswith('.md')
                     and (len(parts) == 4 or parts[3] in {'reference', 'cases'})))
    else:
        native = (len(parts) == 3 and parts[0] == 'native' and parts[1] in {'dotnet', 'sql', 'go', 'frontend'}
                  and PurePosixPath(path).suffix.casefold() in {'.cs', '.csproj', '.json', '.config', '.props', '.targets', '.go', '.mod', '.cjs'})
        schema = len(parts) == 2 and parts[0] == 'schemas' and parts[1].endswith('.schema.json')
        _require(native or schema or path in {'policy/defaults.json', 'policy/schema.json',
                 'tools/build_native.py', 'docs/NATIVE-SETUP.md', 'docs/development/NATIVE-PROTOCOL.md'})


def _plain(path, *, file=False):
    info = path.lstat()
    _require(not stat.S_ISLNK(info.st_mode))
    _require(not (getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024)))
    _require(stat.S_ISREG(info.st_mode) if file else stat.S_ISDIR(info.st_mode))
    return info


def _root(value):
    root = Path(value).absolute()
    for part in reversed((root, *root.parents)):
        _plain(part)
    return root.resolve(strict=True)


def _read(root, name, limit=8_000_000):
    name = _path(name)
    path = root
    for part in PurePosixPath(name).parts[:-1]:
        path /= part
        _plain(path)
    path /= PurePosixPath(name).name
    before = _plain(path, file=True)
    _require(before.st_size <= limit)
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    after = _plain(path, file=True)
    _require(len(raw) <= limit and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
             == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
    return raw


def _pairs(pairs):
    data = {}
    for key, value in pairs:
        _require(key not in data)
        data[key] = value
    return data


def load_manifest(root):
    """Return frozen components after validating the complete bounded manifest."""
    try:
        root = _root(root)
        data = json.loads(_read(root, 'packaging/manifest.json', 200_000), object_pairs_hook=_pairs)
        _require(type(data) is dict and set(data) == {'schema_version', 'components'})
        _require(data['schema_version'] == '1' and type(data['components']) is dict
                 and set(data['components']) == COMPONENTS)
        result = []
        spellings = {}
        for name, value in sorted(data['components'].items()):
            _require(type(value) is dict and set(value) == {'required', 'optional'})
            seen = set()
            for key in ('required', 'optional'):
                values = value[key]
                _require(type(values) is list and len(values) <= 200 and values == sorted(values))
                for item in values:
                    path = _path(item)
                    _allowed(path, name)
                    folded = path.casefold()
                    _require(folded not in seen)
                    seen.add(folded)
                    _require(folded not in spellings or spellings[folded] == path)
                    spellings[folded] = path
            _require(bool(value['required']))
            result.append(Component(name, tuple(value['required']), tuple(value['optional'])))
        return tuple(result)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise PackageManifestError(_MESSAGE) from None


def _tracked(root, paths):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env['GIT_LITERAL_PATHSPECS'] = '1'
    run = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', str(root),
                          'ls-files', '--stage', '-z', '--', *paths], env=env,
                         capture_output=True, timeout=30, check=True)
    _require(len(run.stdout) <= 1_000_000)
    files = {}
    for entry in run.stdout.split(b'\0'):
        if not entry:
            continue
        metadata, path = entry.split(b'\t', 1)
        mode, _, stage = metadata.split(b' ')
        name = path.decode('utf-8')
        _require(mode in {b'100644', b'100755'} and stage == b'0' and name not in files)
        files[name] = True
    return files


def inventory(root, component, *, require_tracked=True):
    """Sorted immutable physical input hashes; no files written or tools built.

    Trusted stable checkout boundary, not protection against a concurrent hostile
    filesystem owner. Git mode only reads the index, disabling fsmonitor hooks.
    Explicit False supports already-reviewed extracted source without a Git DB;
    its provenance/trust must be checked by the caller, never guessed here.
    """
    try:
        _require(type(require_tracked) is bool and type(component) is str and component in COMPONENTS)
        root = _root(root)
        definition = next(c for c in load_manifest(root) if c.name == component)
        paths = tuple(sorted(definition.required + tuple(
            p for p in definition.optional if os.path.lexists(root / p))))
        if require_tracked:
            tracked = _tracked(root, ('packaging/manifest.json', *paths))
            _require('packaging/manifest.json' in tracked and all(p in tracked for p in paths))
        result = []
        for name in paths:
            raw = _read(root, name)
            result.append(PackageFile(name, len(raw), hashlib.sha256(raw).hexdigest()))
        return tuple(result)
    except (OSError, ValueError, TypeError, KeyError, StopIteration, subprocess.SubprocessError):
        raise PackageManifestError(_MESSAGE) from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise PackageManifestError(_MESSAGE)


def main(argv=None):
    try:
        parser = _Parser(description=__doc__, allow_abbrev=False)
        parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
        parser.add_argument('--component', required=True, choices=sorted(COMPONENTS))
        parser.add_argument('--reviewed-extracted-source', action='store_true')
        args = parser.parse_args(argv)
        files = inventory(args.root, args.component, require_tracked=not args.reviewed_extracted_source)
        print(json.dumps({'schema_version': '1', 'component': args.component,
                          'files': [item.to_dict() for item in files]}, sort_keys=True))
        return 0
    except PackageManifestError:
        print(_MESSAGE, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
