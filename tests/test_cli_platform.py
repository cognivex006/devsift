"""Opt-in installed console contract, exercised on Windows and Linux CI.

Install into an isolated environment, then set DEVSIFT_TEST_INSTALLED=1.
No subprocess imports DevSift through the checkout or PYTHONPATH.
"""
import json
import os
from pathlib import Path
import subprocess
import sysconfig
import tempfile
import unittest


def snapshot(root):
    """Include empty directories as well as complete file bytes."""
    return {str(path.relative_to(root)): ('directory', None) if path.is_dir()
            else ('file', path.read_bytes()) for path in root.rglob('*')}


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_INSTALLED') == '1',
                     'requires an isolated package installation; see cli-contract workflow')
class InstalledCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.console = Path(sysconfig.get_path('scripts')) / (
            'devsift.exe' if os.name == 'nt' else 'devsift')
        if not cls.console.is_file():
            raise AssertionError(f'Installed console script is missing: {cls.console}')
        # Read the environment's install location directly. A wheel build can
        # leave checkout-local egg-info that shadows metadata discovery.
        cls.package = (Path(sysconfig.get_path('purelib')) / 'devsift').resolve()
        checkout = Path(__file__).resolve().parents[1]
        if cls.package.is_relative_to(checkout) or not cls.package.is_dir():
            raise AssertionError('The contract must use an installed package outside the checkout')

    def invoke(self, args, cwd):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        return subprocess.run([str(self.console), *args], cwd=cwd, env=env,
                              text=True, capture_output=True, timeout=30)

    def test_installed_help_and_machine_contract(self):
        cases = [(('--help',), 0)]
        cases += [((command, '--help'), 0)
                  for command in ('scan', 'explain', 'report', 'doctor', 'prompt')]
        cases += [(('scan', '--changed'), 2),
                  (('scan', '--all', '--legacy-mode', 'recommend'), 2),
                  (('report', '--latest'), 2), (('explain', 'OBS-001'), 2),
                  (('doctor',), 2), (('prompt', 'OBS-001', '--mode', 'review'), 2),
                  (('prompt', 'OBS-001', '--mode', 'implement', '--approved-case', 'OBS-001'), 2),
                  (('scan', '--changed', '--all'), 3), (('scan', '--cha'), 3),
                  (('scan', '--legacy-mode', 'enforce'), 3),
                  (('prompt', 'OBS-001', '--mode', 'implement'), 3),
                  (('doctor', '--do-not-echo-private-value'), 3)]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / 'src').mkdir()
            (target / 'empty-directory').mkdir()
            (target / '.devsift').mkdir()
            (target / 'src' / 'source.txt').write_bytes(b'unchanged source\r\n')
            (target / '.devsift' / 'config.json').write_bytes(b'{"fixture":true}\n')
            (target / '.devsift' / 'report.json').write_bytes(b'{"stale":true}\n')
            before_target, before_package = snapshot(target), snapshot(self.package)
            for args, expected in cases:
                with self.subTest(args=args):
                    completed = self.invoke(args, target)
                    self.assertEqual(completed.returncode, expected, completed.stderr)
                    if expected == 0:
                        self.assertIn('usage:', completed.stdout)
                        self.assertEqual(completed.stderr, '')
                    else:
                        stream = completed.stdout if expected == 2 else completed.stderr
                        other = completed.stderr if expected == 2 else completed.stdout
                        self.assertEqual(other, '')
                        record = json.loads(stream)
                        self.assertEqual(record['schema_version'], '1.0')
                        self.assertEqual(record['exit_code'], expected)
                        self.assertEqual(record['status'], 'incomplete' if expected == 2 else 'misuse')
                        self.assertIs(record['complete'], False)
                        self.assertEqual(record['enforced_count'], 0)
                        self.assertEqual(record['findings'], [])
                        self.assertTrue(record['errors'])
                        self.assertIn('data', record)
                        self.assertIn('command', record)
                        self.assertNotIn('do-not-echo-private-value', stream)
                    self.assertEqual(snapshot(target), before_target)
                    self.assertEqual(snapshot(self.package), before_package)


if __name__ == '__main__':
    unittest.main()
