"""Repository cardinality must not consume a single untrusted-value budget."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from devsift.adapters import AdapterCapability
from devsift.ci_artifacts import attach_reports, build_reports
from devsift.cli import _execution_reports, parser, run
from devsift.evidence import SourceEvidence
from devsift.inventory import Inventory, SourceTarget
from devsift.redaction import Redactor
from devsift.report_model import ReportError, assemble_report
from devsift.scanner import AdapterOutcome, ScanFinding, scan


ROOT = Path(__file__).resolve().parents[1]


class LargeScanOutputTests(unittest.TestCase):
    def test_hundred_thousand_target_inventory_keeps_every_outcome_and_masks_late_secret(self):
        # Synthetic inventory, actual scan coordinator/redactor/report renderers.
        # This exceeds both former cumulative budgets by a wide margin.
        secret = 'gh' + 'p_' + 'a' * 36
        targets = tuple(SourceTarget(
            f'{index:06d}-' + ('x' * 160) + ('-' + secret if index == 90_000 else '') + '.cs',
            'ready', 'csharp', b'', '') for index in range(100_000))
        with tempfile.TemporaryDirectory() as directory:
            with patch('devsift.scanner.inventory', return_value=Inventory('all', targets)):
                record = scan(directory)
            self.assertEqual(len(record['data']['targets']), 100_000)
            self.assertEqual(record['data']['counts']['unavailable'], 100_000)
            self.assertEqual(record['exit_code'], 2)
            self.assertEqual({item['code'] for item in record['errors']},
                             {'NO_AVAILABLE_ANALYZER', 'ANALYZER_UNAVAILABLE'})
            self.assertNotIn(secret, record['data']['targets'][90_000]['path'])
            self.assertIn('[REDACTED]', record['data']['targets'][90_000]['path'])
            report, documents = build_reports(record, repo_root=directory)
            self.assertFalse(report.complete)
            self.assertEqual(set(documents), {'json', 'markdown', 'sarif'})

    def test_real_cli_with_sixteen_thousand_long_paths_keeps_reports_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(16_000):
                (root / (f'{index:05d}-' + 'x' * 140 + '.txt')).write_bytes(b'unchanged\n')
            environment = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1')
            completed = subprocess.run([sys.executable, '-B', '-m', 'devsift', 'scan', '--all'],
                                       cwd=root, env=environment, capture_output=True, text=True,
                                       timeout=180)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertEqual(completed.stderr, '')
            record = json.loads(completed.stdout)
            self.assertGreater(len(completed.stdout), 4_000_000)
            self.assertEqual(len(record['data']['targets']), 16_000)
            self.assertEqual(record['data']['counts']['skipped'], 16_000)
            self.assertEqual(set(record['data']['reports']), {'json', 'markdown', 'sarif'})
            remaining = list(root.iterdir())
            self.assertEqual(len(remaining), 16_000)
            self.assertTrue(all(path.read_bytes() == b'unchanged\n' for path in remaining))

    def test_many_actual_adapter_findings_survive_bounded_report_refusal(self):
        class ManyFindings:
            capability = AdapterCapability('fixture-python', '1', ('python',), True)

            def analyze(self, target):
                return AdapterOutcome(True, tuple(ScanFinding(
                    f'CASE-{index:05d}', 'HC001', SourceEvidence(),
                    message='token=fixture-private-value') for index in range(1200)))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source.py').write_bytes(b'print(1)\n')
            record = scan(root, adapters=(ManyFindings(),))
            original = json.dumps(record, sort_keys=True)
            # Dispatch through the real CLI scan integration, retaining only
            # the already-redacted scanner result at this explicit boundary.
            with patch('devsift.cli_scan.run_scan', return_value=record):
                rendered = run(parser().parse_args(['scan', '--all']))
            self.assertEqual(len(rendered['findings']), 1200)
            self.assertNotIn('fixture-private-value', json.dumps(rendered))
            self.assertEqual(rendered['data']['targets'], record['data']['targets'])
            self.assertEqual(rendered['data']['counts'], record['data']['counts'])
            self.assertEqual(rendered['exit_code'], 2)
            self.assertFalse(rendered['complete'])
            self.assertEqual(rendered['data']['reports'], {})
            self.assertEqual(rendered['data']['report_status'], 'unavailable')
            self.assertIn('REPORT_UNAVAILABLE', {error['code'] for error in rendered['errors']})
            self.assertEqual(json.dumps(record, sort_keys=True), original)

    def test_report_failure_never_turns_enforced_scan_clean_or_discards_safe_cases(self):
        from devsift.output import result
        # A forced renderer failure also exercises the fresh CI envelope path.
        record = result('ci', complete=True, enforced_count=1,
                        findings=[{'case_id': 'CASE-1', 'enforcement': 'block'}],
                        data={'counts': {'executed': 1}})
        failure = result('ci', complete=False, errors=[{
            'code': 'REPORT_UNAVAILABLE', 'message': 'Full source-reproved reports could not be generated.'}])
        with patch('devsift.ci_artifacts.attach_reports', return_value=failure):
            rendered = _execution_reports(record, record)
        self.assertEqual(rendered['enforced_count'], 1)
        self.assertEqual(rendered['findings'], record['findings'])
        self.assertEqual(rendered['exit_code'], 2)
        self.assertEqual(rendered['status'], 'incomplete')
        self.assertTrue(record['complete'])

    def test_individual_excessive_value_still_fails_closed_without_raw_fallback(self):
        target = SourceTarget('x' * 2_000_001 + '.txt', 'unsupported', None, None, '')
        with tempfile.TemporaryDirectory() as directory:
            with patch('devsift.scanner.inventory', return_value=Inventory('all', (target,))):
                record = scan(directory, redactor=Redactor(('private-fixture',)))
        self.assertEqual(record['errors'][0]['code'], 'REDACTION_FAILED')
        self.assertEqual(record['findings'], [])
        self.assertNotIn('x' * 100, json.dumps(record))

    def test_imported_artifact_failure_does_not_retain_untrusted_raw_findings(self):
        from devsift.output import result
        raw = result('scan', complete=False,
                     findings=[{'message': 'private-untrusted-value'}] * 1001)
        with tempfile.TemporaryDirectory() as directory:
            rejected = attach_reports(raw, raw, repo_root=directory)
        self.assertEqual(rejected['errors'][0]['code'], 'REPORT_UNAVAILABLE')
        self.assertEqual(rejected['findings'], [])
        self.assertNotIn('private-untrusted-value', json.dumps(rejected))

    def test_report_projection_discards_unused_data_without_weakening_direct_import(self):
        from devsift.output import result
        record = result('scan', complete=False, data={'unused': object()})
        record['data']['cycle'] = record
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ReportError):
                assemble_report(record, repo_root=directory)
            report, documents = build_reports(record, repo_root=directory)
        self.assertFalse(report.complete)
        self.assertNotIn('unused', json.dumps(documents))
        self.assertNotIn('cycle', json.dumps(documents))


if __name__ == '__main__':
    unittest.main()
