"""Real immutable Git inputs, deterministic ZIP bytes and fail-closed output."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tools.build_package import PackageBuildError, build_package, verify_bundle

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'packaging/manifest.json').read_text(encoding='utf-8'))


def snapshot(root):
    return {p.relative_to(root).as_posix(): None if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*')}


class ReproducibleBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='devsift-source-bundles-')
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / 'source'
        self.root.mkdir()
        files = {p for c in MANIFEST['components'].values() for p in c['required']}
        for name in sorted(files):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        for args in (('init', '-q'), ('config', 'core.autocrlf', 'false'),
                     ('config', 'core.hooksPath', str(self.parent / 'no-hooks')),
                     ('add', '--all'), ('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                                      '-c', 'commit.gpgSign=false', 'commit', '-qm', 'immutable fixture')):
            self.git(*args)
        self.sha = self.git('rev-parse', 'HEAD').decode().strip()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, timeout=30).stdout

    def build(self, name='output', **kwargs):
        output = self.parent / name
        items = build_package(self.root, output, source_sha=self.sha, **kwargs)
        trusted = next(i.sha256 for i in items if i.name == 'integrity.json')
        return output, items, trusted

    def test_same_commit_and_inputs_repeat_identical_bytes_despite_file_timestamps(self):
        (self.root / '.env').write_text('UNTRACKED_SECRET_MUST_NOT_BE_PACKAGED')
        before = snapshot(self.root)
        first, items, trusted = self.build('first')
        for name in MANIFEST['components']['core-wheel']['required']:
            os.utime(self.root / name, (1800000000, 1800000000))
        second, repeated, second_trust = self.build('second')
        self.assertEqual(items, repeated)
        self.assertEqual(trusted, second_trust)
        self.assertEqual({p.name for p in first.iterdir()}, {p.name for p in second.iterdir()})
        for path in first.iterdir():
            self.assertEqual(path.read_bytes(), (second / path.name).read_bytes(), path.name)
            self.assertNotIn(b'UNTRACKED_SECRET_MUST_NOT_BE_PACKAGED', path.read_bytes())
        self.assertEqual(verify_bundle(first, expected_integrity_sha256=trusted, expected_source_sha=self.sha), items)
        metadata = json.loads((first / 'integrity.json').read_bytes())
        self.assertEqual(metadata['source_sha'], self.sha)
        self.assertEqual(metadata['package_manifest_sha256'], hashlib.sha256((self.root / 'packaging/manifest.json').read_bytes()).hexdigest())
        for component in metadata['components']:
            with zipfile.ZipFile(first / component['archive']) as archive:
                self.assertEqual(archive.namelist(), MANIFEST['components'][component['component']]['required'])
                for member in archive.infolist():
                    self.assertEqual(archive.read(member), (self.root / member.filename).read_bytes())
                    self.assertEqual(member.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(member.external_attr, 0o100644 << 16)
                    self.assertEqual(member.compress_type, zipfile.ZIP_STORED)
        self.assertEqual(snapshot(self.root), before)

    def test_tamper_archive_integrity_checksums_and_unknown_file_fail_read_only(self):
        output, _, digest = self.build(components=('consumer-skill',))
        saved = {p.name: p.read_bytes() for p in output.iterdir()}
        with self.assertRaises(PackageBuildError):
            verify_bundle(output, expected_integrity_sha256=digest, expected_source_sha='a' * 40)
        archive = next(p for p in output.iterdir() if p.suffix == '.zip')
        for name in (archive.name, 'integrity.json', 'SHA256SUMS'):
            (output / name).write_bytes(saved[name] + b'tampered')
            before = snapshot(output)
            with self.subTest(file=name), self.assertRaises(PackageBuildError):
                verify_bundle(output, expected_integrity_sha256=digest, expected_source_sha=self.sha)
            self.assertEqual(snapshot(output), before)
            (output / name).write_bytes(saved[name])
        (output / 'unexpected.txt').write_text('not allowed')
        with self.assertRaises(PackageBuildError):
            verify_bundle(output, expected_integrity_sha256=digest, expected_source_sha=self.sha)
        with self.assertRaises(PackageBuildError):
            verify_bundle(output, expected_integrity_sha256='0' * 64, expected_source_sha=self.sha)

    def test_dirty_selected_bytes_staged_changes_missing_and_wrong_commit_fail_before_output(self):
        selected = self.root / 'devsift/cli.py'
        original = selected.read_bytes()
        for label in ('dirty-bytes', 'staged', 'staged-then-restored', 'missing'):
            if label == 'missing':
                selected.unlink()
            else:
                selected.write_bytes(original + b'\n# uncommitted change\n')
                if label.startswith('staged'):
                    self.git('add', 'devsift/cli.py')
                if label == 'staged-then-restored':
                    selected.write_bytes(original)
            before = snapshot(self.root)
            output = self.parent / label
            with self.subTest(label=label), self.assertRaises(PackageBuildError):
                build_package(self.root, output, source_sha=self.sha, components=('core-wheel',))
            self.assertFalse(output.exists())
            self.assertEqual(snapshot(self.root), before)
            selected.write_bytes(original)
            self.git('add', 'devsift/cli.py')
        for sha in ('main', '0' * 40, 'a' * 40, self.sha.upper()):
            with self.subTest(sha=sha), self.assertRaises(PackageBuildError):
                build_package(self.root, self.parent / 'wrong-sha', source_sha=sha)
        self.assertFalse((self.parent / 'wrong-sha').exists())
        manifest = self.root / 'packaging/manifest.json'
        manifest.write_bytes(manifest.read_bytes() + b' ')
        with self.assertRaises(PackageBuildError):
            self.build('dirty-manifest', components=('consumer-skill',))
        self.assertFalse((self.parent / 'dirty-manifest').exists())

    def test_source_git_filter_and_fsmonitor_callbacks_never_execute(self):
        marker = self.parent / 'SOURCE_CALLBACK_EXECUTED'
        helper = self.parent / 'hook.py'
        helper.write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("bad")\n', encoding='utf-8')
        command = shlex.join([Path(sys.executable).as_posix(), helper.as_posix()])
        (self.root / '.gitattributes').write_text('*.py filter=probe\n')
        for setting in ('filter.probe.clean', 'filter.probe.smudge', 'filter.probe.process', 'core.fsmonitor'):
            self.git('config', setting, command)
        self.git('config', 'filter.probe.required', 'true')
        before = snapshot(self.root)
        output, _, digest = self.build('no-callbacks', components=('core-wheel',))
        verify_bundle(output, expected_integrity_sha256=digest, expected_source_sha=self.sha)
        self.assertFalse(marker.exists())
        self.assertEqual(snapshot(self.root), before)

    def test_output_source_git_boundary_collision_and_symlink_rejected(self):
        metadata = self.parent / 'external-git-metadata'
        (self.root / '.git').rename(metadata)
        (self.root / '.git').write_text('gitdir: ' + metadata.as_posix() + '\n', encoding='utf-8')
        metadata_before = snapshot(metadata)
        existing = self.parent / 'existing'
        existing.mkdir()
        (existing / 'canary').write_bytes(b'preserve')
        empty = self.parent / 'existing-empty'
        empty.mkdir()
        before = snapshot(self.root)
        for output in (metadata / 'out', empty, self.root / 'artifacts', self.root / '.git/out', existing, Path('relative-output'),
                       self.parent / 'missing-parent/out'):
            with self.subTest(output=output), self.assertRaises(PackageBuildError):
                build_package(self.root, output, source_sha=self.sha, components=('consumer-skill',))
        self.assertEqual((existing / 'canary').read_bytes(), b'preserve')
        self.assertEqual(snapshot(metadata), metadata_before)
        self.assertEqual(snapshot(self.root), before)
        link = self.parent / 'alias'
        try:
            link.symlink_to(existing, target_is_directory=True)
        except OSError as error:
            self.skipTest('Host disallows symbolic links: ' + type(error).__name__)
        with self.assertRaises(PackageBuildError):
            build_package(self.root, link / 'out', source_sha=self.sha, components=('consumer-skill',))
        self.assertFalse((existing / 'out').exists())
        file = self.root / 'skills/devsift/SKILL.md'
        file.unlink()
        file.symlink_to(ROOT / 'skills/devsift/SKILL.md')
        with self.assertRaises(PackageBuildError):
            self.build('source-link', components=('consumer-skill',))
        self.assertFalse((self.parent / 'source-link').exists())

    def test_actual_cli_build_verify_and_private_input_errors(self):
        output = self.parent / 'cli-output'
        base = [sys.executable, '-I', '-B', str(ROOT / 'tools/build_package.py')]
        run = subprocess.run([*base, 'build', '--root', str(self.root), '--output', str(output),
                              '--source-sha', self.sha, '--component', 'consumer-skill'], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        digest = next(i['sha256'] for i in json.loads(run.stdout)['artifacts'] if i['name'] == 'integrity.json')
        check = subprocess.run([*base, 'verify', '--output', str(output), '--source-sha', self.sha,
                                '--integrity-sha256', digest], capture_output=True, text=True, timeout=30)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertEqual(json.loads(run.stdout), json.loads(check.stdout))
        bad = subprocess.run([*base, 'build', '--private-sensitive-argument'], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn('private-sensitive-argument', bad.stdout + bad.stderr)


if __name__ == '__main__':
    unittest.main()
