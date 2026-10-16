"""Actual packaging input guards; opt-in builds require the exact backend."""
import copy
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
import zipfile

from tools.package_manifest import PackageManifestError, inventory, load_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'packaging/manifest.json').read_text(encoding='utf-8'))


def snapshot(root):
    return {p.relative_to(root).as_posix(): None if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*')}


def copy_inputs(destination):
    for name in sorted({p for component in MANIFEST['components'].values() for p in component['required']}):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='devsift-manifest-')
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.source = self.parent / 'source'
        self.source.mkdir()
        copy_inputs(self.source)
        for args in (('init', '-q'), ('config', 'core.autocrlf', 'false'),
                     ('config', 'core.hooksPath', str(self.parent / 'no-hooks')),
                     ('add', '--all'), ('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                                      '-c', 'commit.gpgSign=false', 'commit', '-qm', 'trusted source')):
            subprocess.run(['git', '-C', str(self.source), *args], check=True, capture_output=True)

    def write_manifest(self, data):
        (self.source / 'packaging/manifest.json').write_text(json.dumps(data), encoding='utf-8')

    def test_all_components_deterministic_physical_hashes_and_read_only(self):
        before = snapshot(self.source)
        for definition in load_manifest(self.source):
            files = inventory(self.source, definition.name)
            self.assertEqual(files, inventory(self.source, definition.name))
            self.assertEqual([f.path for f in files], sorted(definition.required))
            for entry in files:
                raw = (self.source / entry.path).read_bytes()
                self.assertEqual(entry.to_dict(), {'path': entry.path, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        self.assertEqual(snapshot(self.source), before)

    def test_untracked_optional_asset_fails_and_explicit_reviewed_extraction_is_separate(self):
        optional = self.source / 'skills/devsift/CONSUMER-SCOPE.md'
        optional.write_text('untracked private consumer configuration')
        with self.assertRaises(PackageManifestError):
            inventory(self.source, 'consumer-skill')
        extracted = inventory(self.source, 'consumer-skill', require_tracked=False)
        self.assertEqual([f.path for f in extracted], ['skills/devsift/CONSUMER-SCOPE.md', 'skills/devsift/SKILL.md'])
        for unknown in (None, 1, 'false'):
            with self.assertRaises(PackageManifestError):
                inventory(self.source, 'core-wheel', require_tracked=unknown)

    def test_duplicate_unknown_case_collision_and_unsafe_paths_fail_before_selection(self):
        for path in ('../secret', '/tmp/secret', 'C:/secret', 'native\\secret.cs',
                     'native/go/../main.go', '.devsift/local/token.json', 'worktrees/job/key.py',
                     'plan/ledger.json', 'templates/TASK.md', 'native/go/node_modules/a.go',
                     'native/sql/tool.dll', 'user-config/settings.json', 'AGENTS.md'):
            bad = copy.deepcopy(MANIFEST)
            bad['components']['source-assets']['required'] = [path]
            self.write_manifest(bad)
            with self.subTest(path=path), self.assertRaises(PackageManifestError):
                inventory(self.source, 'core-wheel')
        bad = copy.deepcopy(MANIFEST)
        bad['components']['source-assets']['required'] = sorted(bad['components']['source-assets']['required'] + ['native/go/Main.go'])
        self.write_manifest(bad)
        with self.assertRaises(PackageManifestError):
            load_manifest(self.source)
        self.write_manifest(dict(MANIFEST, unexpected=True))
        with self.assertRaises(PackageManifestError):
            load_manifest(self.source)
        (self.source / 'packaging/manifest.json').write_text('{"schema_version":"1","schema_version":"1","components":{}}')
        with self.assertRaises(PackageManifestError):
            load_manifest(self.source)

    def test_symlink_file_and_directory_escape_rejected(self):
        outside = self.parent / 'private.py'
        outside.write_text('private source must never be selected')
        selected = self.source / 'devsift/cli.py'
        selected.unlink()
        try:
            selected.symlink_to(outside)
        except OSError as error:
            self.skipTest('Host disallows actual symbolic links: ' + type(error).__name__)
        with self.assertRaises(PackageManifestError):
            inventory(self.source, 'core-wheel', require_tracked=False)
        selected.unlink()
        shutil.copy2(ROOT / 'devsift/cli.py', selected)
        (self.source / 'devsift').rename(self.source / 'held-modules')
        (self.source / 'devsift').symlink_to(self.source / 'held-modules', target_is_directory=True)
        with self.assertRaises(PackageManifestError):
            inventory(self.source, 'core-wheel', require_tracked=False)

    def test_missing_required_and_safe_cli_errors(self):
        (self.source / 'devsift/cli.py').unlink()
        with self.assertRaisesRegex(PackageManifestError, '^Invalid or unavailable package manifest$'):
            inventory(self.source, 'core-wheel')
        run = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'tools/package_manifest.py'),
                              '--component', 'private-unknown-component'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertNotIn('private-unknown-component', run.stdout + run.stderr)

    def test_python_and_sdist_configuration_match_allowed_files(self):
        config = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        self.assertEqual(config['build-system']['requires'], ['setuptools==83.0.0'])
        self.assertEqual(config['project']['dependencies'], [])
        self.assertEqual(config['project']['version'], '0.0.0.dev0')
        settings = config['tool']['setuptools']
        self.assertEqual(settings['packages'], [])
        self.assertIs(settings['include-package-data'], False)
        expected = {p[:-3].replace('/', '.') for p in MANIFEST['components']['core-wheel']['required'] if not p.endswith('/__init__.py')}
        self.assertEqual(set(settings['py-modules']), expected)
        entries = (ROOT / 'MANIFEST.in').read_text().splitlines()
        self.assertEqual(entries[1], 'global-exclude *')
        self.assertEqual({line.removeprefix('include ') for line in entries[2:]}, set(MANIFEST['components']['core-sdist']['required']))


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_PACKAGE') == '1', 'explicit actual package build opt-in')
class ActualBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if metadata.version('setuptools') != '83.0.0':
            raise AssertionError('Actual build requires setuptools 83.0.0 already provisioned')

    def test_real_wheel_sdist_inventory_and_hostile_extras_excluded_without_source_writes(self):
        before = snapshot(ROOT)
        index = Path(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--path-format=absolute', '--git-path', 'index'], text=True).strip())
        index_before = index.read_bytes()
        head_before = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'])
        with tempfile.TemporaryDirectory(prefix='devsift-trusted-build-') as temp:
            kit = Path(temp) / 'kit'
            kit.mkdir()
            # Prepare only the explicit minimal sdist inputs, never broad-copy a
            # dirty checkout or execute setup.py/project hooks from extra files.
            for name in MANIFEST['components']['core-sdist']['required']:
                target = kit / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
            for name in ('devsift/untracked_private.py', 'devsift/private.json', '.env',
                         'AGENTS.md', 'plan/ledger.json', 'templates/TASK.md',
                         'worktrees/job/private.txt', 'node_modules/tool.js', '.devsift/local/tool.dll'):
                path = kit / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('PRIVATE_UNTRACKED_PACKAGE_CANARY', encoding='utf-8')
            outputs = Path(temp) / 'outputs'
            outputs.mkdir()
            command = 'import sys; sys.path.insert(0,sys.argv[2]); from setuptools.build_meta import build_wheel,build_sdist; destination=sys.argv[1]; build_wheel(destination); build_sdist(destination)'
            backend = str(Path(metadata.distribution('setuptools').locate_file('')).resolve())
            run = subprocess.run([sys.executable, '-I', '-B', '-c', command, str(outputs), backend],
                                 cwd=kit, capture_output=True, text=True, timeout=120,
                                 env=dict(os.environ, PIP_NO_INDEX='1', SOURCE_DATE_EPOCH='1700000000'))
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            with zipfile.ZipFile(next(outputs.glob('*.whl'))) as wheel:
                sources = {n for n in wheel.namelist() if not '.dist-info/' in n}
                self.assertEqual(sources, set(MANIFEST['components']['core-wheel']['required']))
                for name in wheel.namelist():
                    self.assertNotIn(b'PRIVATE_UNTRACKED_PACKAGE_CANARY', wheel.read(name), name)
                metadata_bytes = wheel.read('devsift-0.0.0.dev0.dist-info/METADATA')
                self.assertNotIn(b'Requires-Dist:', metadata_bytes)
                self.assertIn(b'devsift = devsift.cli:main', wheel.read('devsift-0.0.0.dev0.dist-info/entry_points.txt'))
            wheel_path = next(outputs.glob('*.whl'))
            smoke = subprocess.run([sys.executable, '-I', '-B', '-c',
                                    'import sys; sys.path.insert(0,sys.argv[1]); from devsift.cli import main; main(["--help"])',
                                    str(wheel_path)], cwd=outputs, capture_output=True, text=True, timeout=30)
            self.assertEqual(smoke.returncode, 0, smoke.stderr)
            self.assertIn('usage:', smoke.stdout)
            with tarfile.open(next(outputs.glob('*.tar.gz'))) as archive:
                files = {m.name.split('/', 1)[1]: m for m in archive.getmembers() if m.isfile()}
                actual = {n for n in files if not n.startswith('devsift.egg-info/') and n not in {'PKG-INFO', 'setup.cfg'}}
                self.assertEqual(actual, set(MANIFEST['components']['core-sdist']['required']))
                for name, member in files.items():
                    self.assertNotIn(b'PRIVATE_UNTRACKED_PACKAGE_CANARY', archive.extractfile(member).read(), name)
        self.assertEqual(snapshot(ROOT), before)
        self.assertEqual(index.read_bytes(), index_before)
        self.assertEqual(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']), head_before)


if __name__ == '__main__':
    unittest.main()
