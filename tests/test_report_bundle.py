import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from devsift.ci_artifacts import build_reports, ArtifactError
from devsift.case_command import run_case_command
from devsift.evidence import SourceEvidence
from devsift.inventory import SourceTarget
from devsift.output import result
from devsift.report_bundle import verify_bundle
from devsift.scan_store import run_streamed


def record(path, cases, *, complete=False):
    return result('scan', complete=complete, findings=[{
        'case_id': case_id, 'rule_id': 'HC001', 'message': message,
        'path': path, 'source': SourceEvidence().to_dict(), 'severity': 'Error',
        'lifecycle_class': 'UNKNOWN', 'enforcement': 'incomplete', 'security_escalation': False
    } for case_id, message in cases], data={
        'mode': 'all', 'targets': [{'path': path, 'status': 'ready', 'language': 'python',
                                  'byte_count': 1, 'execution_status': 'incomplete' if cases else 'executed',
                                  'adapter_id': 'test', 'adapter_version': '1'}],
        'counts': {'executed': 1, 'skipped': 0, 'unavailable': 0, 'incomplete': int(bool(cases))}})


class ReportBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'source'
        self.root.mkdir()
        self.destination = self.base / 'scan'

    def producer(self, count, *, duplicate=False, long_path=False):
        def factory(callback):
            for number in range(count):
                path = ('segment/' * 250 if long_path else '') + f'file-{number:06d}.py'
                if callback(SourceTarget(path, 'ready', 'python', b'x', 'snapshot')):
                    identity = 'duplicate' if duplicate else f'CASE-{number:06d}'
                    message = 'password=latePrivateSecret' if number == count - 1 else 'case'
                    yield record(path, [] if long_path else [(identity, message)], complete=long_path)
        return factory

    def test_more_than_1200_cases_all_have_real_template_pages_all_formats(self):
        seen_page_sizes = []

        def actual_bounded_renderer(scan_record, **kwargs):
            self.assertIsNone(kwargs['source_timeout_seconds'])
            seen_page_sizes.append(len(scan_record['findings']))
            return build_reports(scan_record, **kwargs)

        with patch('devsift.report_bundle.build_reports', side_effect=actual_bounded_renderer):
            stored = run_streamed(self.root, self.producer(1205), destination=self.destination)
        self.addCleanup(stored.close)
        summary = stored.summary()
        self.assertEqual(summary['data']['finding_count'], 1205)
        self.assertEqual(stored.bundle['case_count'], 1205)
        self.assertTrue(stored.bundle['reports_complete'])
        self.assertFalse(stored.bundle['analysis_complete'])
        self.assertTrue(verify_bundle(stored, stored.bundle))
        self.assertLessEqual(max(seen_page_sizes), 32)
        manifest = json.loads(Path(stored.bundle['index']).read_text())
        self.assertEqual(sum(page['case_count'] for page in manifest['pages']), 1205)
        identities = []
        for page in manifest['pages']:
            self.assertTrue(page['rendered'])
            self.assertEqual({Path(item['file']).name for item in page['files']}, {'findings.json', 'report.md', 'results.sarif', 'scan.json'})
            identities.extend(page['case_ids'])
            markdown = Path(stored.bundle['index']).parent / next(item['file'] for item in page['files'] if item['file'].endswith('.md'))
            self.assertIn('AFTER (PROPOSAL)', markdown.read_text())
        self.assertEqual(len(set(identities)), 1205)
        final_page = manifest['pages'][-1]
        scan_path = Path(stored.bundle['index']).parent / next(
            item['file'] for item in final_page['files'] if item['file'].endswith('/scan.json'))
        page_envelope = json.loads(scan_path.read_text())
        self.assertEqual(page_envelope['schema_version'], '1.0')
        self.assertLessEqual(scan_path.stat().st_size, 4_000_000)
        selected = final_page['case_ids'][-1]
        prompted = run_case_command(selected, mode='review', scan_input=scan_path, repo_root=self.root)
        self.assertNotIn('CASE_INPUT_UNAVAILABLE', [error['code'] for error in prompted['errors']])
        self.assertEqual(prompted['data']['prompt']['case_id'], selected)
        self.assertIsNone(prompted['data']['approval'])

        self.assertNotIn(b'latePrivateSecret', (self.destination / 'scan.sqlite3').read_bytes())
        output = io.StringIO()
        stored.write_json(output)
        decoded = json.loads(output.getvalue())
        self.assertEqual(len(decoded['findings']), 1205)
        self.assertEqual(decoded['data']['reports'], {})
        self.assertNotIn('latePrivateSecret', output.getvalue())
        self.assertEqual(decoded['data']['mode'], 'all')

    def test_inventory_larger_than_four_megabytes_has_complete_reports(self):
        stored = run_streamed(self.root, self.producer(2200, long_path=True), destination=self.destination)
        self.addCleanup(stored.close)
        output = io.StringIO()
        stored.write_json(output)
        self.assertGreater(len(output.getvalue()), 4_000_000)
        decoded = json.loads(output.getvalue())
        self.assertEqual(len(decoded['data']['targets']), 2200)
        self.assertEqual(stored.exit_code, 0)
        self.assertEqual(stored.bundle['case_count'], 0)
        self.assertTrue(verify_bundle(stored, stored.bundle))

    def test_duplicate_ids_retained_as_two_cases_without_certifying_complete(self):
        stored = run_streamed(self.root, self.producer(2, duplicate=True), destination=self.destination)
        self.addCleanup(stored.close)
        self.assertEqual(stored.summary()['data']['finding_count'], 2)
        self.assertEqual(stored.bundle['case_count'], 2)
        self.assertEqual(stored.exit_code, 2)
        self.assertIn('DUPLICATE_CASE_ID', [error['code'] for error in stored.summary()['errors']])
        self.assertTrue(verify_bundle(stored, stored.bundle))

    def test_adaptive_split_uses_real_renderer_and_missing_coverage_fails(self):
        sizes = []

        def tiny_page(scan_record, **kwargs):
            size = len(scan_record['findings'])
            sizes.append(size)
            if size > 2:
                raise ArtifactError('Report artifacts unavailable')
            return build_reports(scan_record, **kwargs)

        with patch('devsift.report_bundle.build_reports', side_effect=tiny_page):
            stored = run_streamed(self.root, self.producer(9), destination=self.destination)
        self.addCleanup(stored.close)
        self.assertGreater(stored.bundle['page_count'], 4)
        self.assertIn(9, sizes)
        self.assertTrue(verify_bundle(stored, stored.bundle))
        stored.connection.execute('DELETE FROM report_cases WHERE finding=(SELECT min(finding) FROM report_cases)')
        self.assertFalse(verify_bundle(stored, stored.bundle))
        self.assertEqual(stored.exit_code, 2)

    def test_individual_unrenderable_case_remains_explicit_incomplete(self):
        with patch('devsift.report_bundle.build_reports', side_effect=ArtifactError('Report artifacts unavailable')):
            stored = run_streamed(self.root, self.producer(2), destination=self.destination)
        self.addCleanup(stored.close)
        self.assertEqual(stored.bundle['case_count'], 2)
        self.assertFalse(stored.bundle['reports_complete'])
        self.assertEqual(stored.exit_code, 2)
        manifest = json.loads(Path(stored.bundle['index']).read_text())
        self.assertEqual(sum(page['case_count'] for page in manifest['pages']), 2)
        self.assertTrue(all(not page['rendered'] for page in manifest['pages']))


if __name__ == '__main__':
    unittest.main()
