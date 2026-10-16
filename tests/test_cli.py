"""Behavioral CLI and stable exit contract tests; no analyzers are simulated."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def invoke(self, *args, cwd=None):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        return subprocess.run([sys.executable, '-P', '-m', 'devsift', *args],
                              cwd=cwd or ROOT, env=env, text=True, capture_output=True)

    def test_help_for_commands(self):
        for command in ('scan', 'explain', 'report', 'doctor', 'prompt'):
            with self.subTest(command=command):
                result = self.invoke(command, '--help')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('usage:', result.stdout)

    def test_strict_machine_errors(self):
        for args in ((), ('nope',), ('scan', '--cha'), ('scan', '--changed', '--all'),
                     ('scan', '--legacy-mode', 'enforce'), ('report', '--output', 'x'),
                     ('explain',), ('doctor', '--fix'),
                     ('prompt', 'OBS-001', '--mode', 'implement'),
                     ('prompt', 'OBS-001', '--mode', 'implement', '--approved-case', 'OTHER')):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 3, result)
                record = json.loads(result.stderr)
                self.assertEqual(record['exit_code'], 3)
                self.assertEqual(record['status'], 'misuse')
                self.assertEqual(record['errors'][0]['code'], 'INVALID_ARGUMENT')
                self.assertEqual(result.stdout, '')

    def test_unimplemented_capabilities_are_incomplete(self):
        for args in (('scan', '--changed'), ('scan', '--all', '--legacy-mode', 'recommend'),
                     ('report', '--latest'), ('explain', 'OBS-001'),
                     ('prompt', 'OBS-001', '--mode', 'review'),
                     ('prompt', 'OBS-001', '--mode', 'implement', '--approved-case', 'OBS-001')):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                record = json.loads(result.stdout)
                self.assertEqual(record['status'], 'incomplete')
                self.assertFalse(record['complete'])
                self.assertEqual(record['findings'], [])
                self.assertEqual(result.stderr, '')

    def test_doctor_reports_actual_runtime_and_missing_engine(self):
        result = self.invoke('doctor')
        self.assertEqual(result.returncode, 2)
        record = json.loads(result.stdout)
        self.assertEqual(record['data']['runtime']['version'], sys.version.split()[0])
        self.assertFalse(record['data']['capabilities']['analyzers'])
        self.assertTrue(record['data']['capabilities']['reports'])
        self.assertTrue(record['data']['capabilities']['case_prompts'])

    def test_commands_do_not_write_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source.py').write_text('print("unchanged")\n', encoding='utf-8')
            def snapshot():
                return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            before = snapshot()
            for args in (('scan', '--all'), ('doctor',), ('report', '--latest'),
                         ('explain', 'OBS-001'), ('prompt', 'OBS-001', '--mode', 'review')):
                self.invoke(*args, cwd=directory)
                self.assertEqual(snapshot(), before)

    def test_cold_module_execution_with_B_does_not_write_package_bytecode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'devsift', root / 'devsift',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            before = {str(p.relative_to(root)): p.read_bytes()
                      for p in root.rglob('*') if p.is_file()}
            env = dict(os.environ, PYTHONPATH=str(root))
            env.pop('PYTHONDONTWRITEBYTECODE', None)
            for args in (('scan', '--changed'), ('doctor',), ('scan', '--invalid')):
                result = subprocess.run([sys.executable, '-B', '-m', 'devsift', *args],
                                        cwd=root, env=env, capture_output=True)
                self.assertIn(result.returncode, (2, 3))
            after = {str(p.relative_to(root)): p.read_bytes()
                     for p in root.rglob('*') if p.is_file()}
            self.assertEqual(after, before)

    def test_exit_precedence_and_schema(self):
        from devsift.output import Outcome, result
        for complete, enforced, expected in ((True, 0, 0), (True, 1, 1),
                                               (False, 0, 2), (False, 1, 2)):
            record = result('scan', complete=complete, enforced_count=enforced)
            self.assertEqual(record['exit_code'], expected)
            self.assertEqual(record['schema_version'], '1.0')
        self.assertEqual(int(Outcome.MISUSE), 3)
        with self.assertRaises(ValueError):
            result('scan', complete=True, enforced_count=-1)

    def test_completion_requires_an_explicit_boolean(self):
        from devsift.output import result
        for ambiguous in (None, 'unknown', 1, 0, [], {}, ''):
            with self.subTest(complete=ambiguous):
                with self.assertRaisesRegex(ValueError, 'complete must be a boolean'):
                    result('scan', complete=ambiguous)


if __name__ == '__main__':
    unittest.main()
