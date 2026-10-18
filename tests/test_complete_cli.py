"""Installed-style full-run CLI storage, revalidation, and read-only boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from devsift.cli import parser, run


ROOT = Path(__file__).resolve().parents[1]


class CompleteCliTests(unittest.TestCase):
    def invoke(self, root, *arguments):
        completed = subprocess.run([sys.executable, '-P', '-B', '-m', 'devsift', *arguments],
                                   cwd=root, env=dict(os.environ, PYTHONPATH=str(ROOT)),
                                   capture_output=True, text=True, timeout=120)
        self.assertEqual(completed.stderr, '')
        record = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, record['exit_code'])
        return record

    def test_summary_points_to_every_report_and_resume_keeps_source_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            source = home / 'source'
            source.mkdir()
            (source / 'code.cs').write_bytes(b'class Sample {}\n')
            destination = home / 'full-reports'
            first = self.invoke(source, 'scan', '--all', '--summary', '--report-dir', str(destination))
            self.assertEqual(first['exit_code'], 2)
            self.assertEqual(first['data']['target_count'], 1)
            self.assertEqual(first['data']['finding_count'], 0)
            self.assertTrue(first['data']['report_bundle']['reports_complete'])
            self.assertFalse(first['data']['report_bundle']['analysis_complete'])
            index = json.loads(Path(first['data']['report_bundle']['index']).read_text('utf-8'))
            self.assertEqual(index['case_count'], 0)
            self.assertEqual(index['target_count'], 1)
            self.assertEqual(set(index['formats']), {'json', 'markdown', 'sarif'})
            resumed = self.invoke(source, 'scan', '--all', '--summary', '--resume', str(destination))
            self.assertEqual(resumed['data']['target_count'], 1)
            self.assertEqual(resumed['exit_code'], 2)
            self.assertEqual(list(source.iterdir()), [source / 'code.cs'])
            self.assertEqual((source / 'code.cs').read_bytes(), b'class Sample {}\n')

    def test_actual_ci_resume_rechecks_pinned_helper_even_when_all_source_is_cached(self):
        from test_ci_gate import CiGateTests
        fixture = CiGateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.source('value = 1\n')
        destination = fixture.directory / 'reports'
        options = ['ci', '--all', '--base', 'HEAD', '--summary',
                   '--native-manifest', str(fixture.manifest), '--native-manifest-digest', fixture.digest]
        first = self.invoke(fixture.root, *options, '--report-dir', str(destination))
        self.assertTrue(first['complete'])
        self.assertEqual(first['exit_code'], 0)
        original = fixture.helper.read_bytes()
        fixture.helper.write_bytes(original + b'\n# changed pinned helper\n')
        failed = self.invoke(fixture.root, *options, '--resume', str(destination))
        self.assertFalse(failed['complete'])
        self.assertEqual(failed['exit_code'], 2)
        self.assertIn('NATIVE_TOOL_UNAVAILABLE', {error['code'] for error in failed['errors']})
        fixture.helper.write_bytes(original)
        recovered = self.invoke(fixture.root, *options, '--resume', str(destination))
        self.assertTrue(recovered['complete'])
        self.assertEqual(recovered['exit_code'], 0)
        self.assertEqual(fixture.git('status', '--porcelain=v1'), '')

    def test_report_destination_inside_source_is_refused_without_creating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / 'reports'
            rejected = self.invoke(root, 'scan', '--all', '--report-dir', str(destination))
            self.assertEqual(rejected['errors'][0]['code'], 'SCAN_STORAGE_UNAVAILABLE')
            self.assertFalse(destination.exists())

    def test_interruption_returns_resumable_state_after_iterator_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / 'source'
            root.mkdir()
            destination = home / 'reports'
            args = parser().parse_args(['scan', '--all', '--report-dir', str(destination)])
            with patch('pathlib.Path.cwd', return_value=root), \
                    patch('devsift.cli_scan.run_scan', side_effect=KeyboardInterrupt):
                stopped = run(args)
            self.assertEqual(stopped['errors'][0]['code'], 'SCAN_INTERRUPTED')
            self.assertTrue(stopped['data']['resume_available'])
            self.assertEqual(list(root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
