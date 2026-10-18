"""Consumer asset contracts plus opt-in actual installed execution.

These fixtures exercise executable/file boundaries, not model or host obedience.
DEVSIFT_TEST_INSTALLED=1 requires a real installation and fails if missing.
"""
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/governance'
INPUTS = json.loads((FIXTURES / 'ordinary_inputs.json').read_text(encoding='utf-8'))


def snapshot(root):
    return {p.relative_to(root).as_posix(): None if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*')}


class ConsumerAssetTests(unittest.TestCase):
    def test_consumer_skill_links_only_consumer_scope_and_portable_user_guides(self):
        skill = ROOT / 'skills/devsift/SKILL.md'
        text = skill.read_text(encoding='utf-8')
        self.assertIn('[consumer scope](CONSUMER-SCOPE.md)', text)
        for reference in re.findall(r'\]\(([^)]+)\)', text):
            if reference == 'CONSUMER-SCOPE.md':
                self.assertTrue((skill.parent / reference).is_file())
            else:
                self.assertTrue(reference.startswith('references/'))
                self.assertTrue((skill.parent / reference).is_file())
                self.assertNotIn('development/', reference)
        commands = re.findall(r'`(devsift[^`]+)`', text)
        self.assertTrue(commands)
        for command in commands:
            self.assertTrue(command.startswith('devsift'), command)
        for reference in ('DEVELOPMENT.md', 'AGENTS.md', 'devsift-specs', 'planctl', 'plan/ledger.json',
                          'DELEGATION-PACKET', 'REVIEW-CHECKLIST'):
            self.assertNotIn(reference, text)

    def test_package_configuration_does_not_install_maintainer_workflows(self):
        config = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        settings = config['tool']['setuptools']
        self.assertEqual(settings['packages'], [])
        self.assertIs(settings['include-package-data'], False)
        modules = settings['py-modules']
        self.assertTrue(modules)
        self.assertIn('devsift.cli', modules)
        self.assertTrue(all(re.fullmatch(r'devsift\.[a-z_]+', name) for name in modules))
        self.assertEqual(config['project']['dependencies'], [])
        self.assertEqual(config['project']['scripts'], {'devsift': 'devsift.cli:main'})
        self.assertNotIn('data-files', config['tool']['setuptools'])
        self.assertNotIn('package-data', config['tool']['setuptools'])
        self.assertEqual({p.name for p in (ROOT / 'skills/devsift').iterdir()}, {'SKILL.md', 'CONSUMER-SCOPE.md', 'references'})
        self.assertTrue((ROOT / 'skills/devsift/references/USAGE.md').is_file())
        self.assertFalse((ROOT / 'skills/devsift/references/development').exists())


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_INSTALLED') == '1',
                     'requires actual installed package; mandatory in cli-contract CI')
class InstalledGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(sysconfig.get_path('purelib')) / 'devsift'
        cls.console = Path(sysconfig.get_path('scripts')) / ('devsift.exe' if os.name == 'nt' else 'devsift')
        if not cls.package.is_dir() or not cls.console.is_file() or cls.package.resolve().is_relative_to(ROOT):
            raise AssertionError('Actual external DevSift installation is required')
        if (cls.package / 'cli.py').read_bytes().replace(b'\r\n', b'\n') != (ROOT / 'devsift/cli.py').read_bytes().replace(b'\r\n', b'\n'):
            raise AssertionError('Installed CLI must match this tested source')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='devsift-governance-')
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.target = self.parent / 'consumer'
        self.target.mkdir()
        for name in ('AGENTS.md', 'source.py', 'devsift.py'):
            shutil.copy2(FIXTURES / name, self.target / name)
        (self.target / 'conversation.json').write_text(json.dumps(INPUTS), encoding='utf-8')
        for args in (('init', '-q'), ('config', 'core.autocrlf', 'false'),
                     # Fixture commit must not race its own read-only snapshot
                     # with Git 2.55 background maintenance.lock removal.
                     ('config', 'maintenance.auto', 'false'), ('config', 'gc.auto', '0'),
                     ('config', 'core.hooksPath', str(self.parent / 'no-hooks')),
                     ('add', '--all'), ('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                                      '-c', 'commit.gpgSign=false', 'commit', '-qm', 'consumer fixture')):
            subprocess.run(['git', '-C', str(self.target), *args], check=True, capture_output=True, timeout=30)
        self.marker = self.parent / 'TARGET_SOURCE_EXECUTED'

    def invoke(self, command, *, text=''):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        env.pop('PYTHONSAFEPATH', None)  # Make the deliberate non-isolated control reproducible.
        return subprocess.run(command, cwd=self.target, env=env, input=text,
                              text=True, capture_output=True, timeout=30)

    def test_installed_distribution_excludes_maintainer_assets(self):
        distributions = [d for d in metadata.distributions(path=[sysconfig.get_path('purelib')])
                         if d.metadata['Name'] == 'devsift']
        self.assertEqual(len(distributions), 1)
        files = distributions[0].files
        self.assertIsNotNone(files)
        self.assertTrue(any(str(f) == 'devsift/cli.py' for f in files))
        for entry in files:
            self.assertFalse(set(entry.parts) & {'plan', 'templates', 'governance', 'skills'})
            self.assertNotIn(entry.name, {'AGENTS.md', 'DEVELOPMENT.md', 'ledger.json'})

    def test_real_shadow_canary_control_and_isolated_installed_launchers(self):
        before, package_before = snapshot(self.target), snapshot(self.package)
        unsafe = self.invoke([sys.executable, '-B', '-m', 'devsift', '--help'])
        self.assertEqual(unsafe.returncode, 91)
        self.assertTrue(self.marker.is_file())
        self.assertIn('DEV_SIFT_SHADOW_CANARY', unsafe.stdout)
        self.marker.unlink()  # Only the test-owned positive control marker.
        for prefix in ([sys.executable, '-I', '-B', '-m', 'devsift'], [str(self.console)]):
            run = self.invoke([*prefix, '--help'])
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('usage:', run.stdout)
            self.assertNotIn('DEV_SIFT_SHADOW_CANARY', run.stdout + run.stderr)
            self.assertFalse(self.marker.exists())
            self.assertEqual(snapshot(self.target), before)
            self.assertEqual(snapshot(self.package), package_before)

    def test_ordinary_untrusted_input_does_not_create_tasks_or_publish(self):
        before, package_before = snapshot(self.target), snapshot(self.package)
        for case in INPUTS:
            for prefix in ([sys.executable, '-I', '-B', '-m', 'devsift'], [str(self.console)]):
                with self.subTest(input=case['name'], launcher=prefix):
                    run = self.invoke([*prefix, *case['args']], text=case['text'])
                    self.assertEqual(run.returncode, 2, run.stderr)
                    record = json.loads(run.stdout)
                    self.assertIs(record['complete'], False)
                    self.assertEqual(record['status'], 'incomplete')
                    self.assertEqual(record['exit_code'], 2)
                    self.assertEqual(run.stderr, '')
                    self.assertFalse(self.marker.exists())
                    # Entire source, directories, refs/index/config/hooks and
                    # installation bytes stay equal, not merely a marker list.
                    self.assertEqual(snapshot(self.target), before)
                    self.assertEqual(snapshot(self.package), package_before)
                    for path in ('plan', 'worktrees', '.github', 'TASK_CREATED', 'RELEASE_PUBLISHED'):
                        self.assertFalse((self.target / path).exists())


if __name__ == '__main__':
    unittest.main()
