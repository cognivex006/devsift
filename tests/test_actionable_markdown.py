import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from devsift.adapters import AdapterCapability
from devsift.evidence import Region, SourceEvidence, verify_source
from devsift.markdown_report import render_markdown
from devsift.report_bundle import build_bundle, verify_bundle
from devsift.scanner import AdapterOutcome, ScanFinding, iter_scan
from devsift.scan_store import run_streamed


class ActionableMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'source[project]'
        self.root.mkdir()
        self.destination = self.base / 'session'

    def run_language(self, factory, *, language='th', formats=None, resume=False):
        actual = build_bundle
        def localized(stored, **kwargs):
            return actual(stored, **kwargs, language=language)
        with patch('devsift.report_bundle.build_bundle', side_effect=localized):
            return run_streamed(self.root, factory, destination=self.destination,
                                formats=formats, resume=resume)

    def two_cases(self):
        def git(*args):
            return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                                  capture_output=True, text=True).stdout.strip()
        git('init', '-q')
        git('config', 'core.autocrlf', 'false')
        (self.root / 'a.py').write_bytes(b'try:\n    work()\nexcept:\n    pass\n')
        (self.root / 'b.py').write_bytes(b'value = 1\n')
        git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'source')
        sha = git('rev-parse', 'HEAD')
        proof = verify_source(self.root, 'fixture', sha, 'a.py', Region(3, 1, 4, 9))
        self.assertEqual(proof.status, 'VERIFIED')

        class Cases:
            capability = AdapterCapability('case-fixture', '1', ('python',), True)
            def analyze(self, target):
                return AdapterOutcome(True, (ScanFinding(
                    'CASE-A' if target.path == 'a.py' else 'CASE-B',
                    'LOG002' if target.path == 'a.py' else 'HC001',
                    proof if target.path == 'a.py' else SourceEvidence(),
                    lifecycle_class='NEW'),))
        return lambda callback: iter_scan(self.root, ['a.py', 'b.py'], adapters=(Cases(),), should_scan=callback)

    def test_thai_frontdoor_has_actual_locations_actions_and_full_cases(self):
        stored = self.run_language(self.two_cases())
        self.addCleanup(stored.close)
        report = Path(stored.bundle['report']).read_text('utf-8')
        self.assertTrue(report.startswith('# รายงาน DevSift'))
        self.assertIn('## ผลวินิจฉัยและขั้นตอนถัดไป', report)
        self.assertIn('แนวทางตรวจแก้', report)
        self.assertIn('catch', report)
        self.assertIn('configuration', report)
        self.assertIn('3 | except:', report)
        self.assertIn('4 |     pass', report)
        self.assertIn('SOURCE_UNRESOLVED', report)
        self.assertNotIn('b.py', report)
        self.assertIn('## กรณี CASE', report)
        self.assertIn('source\\[project\\]', report)
        self.assertNotIn('[source[project]]', report)
        self.assertEqual(hashlib.sha256(Path(stored.bundle['report']).read_bytes()).hexdigest(), stored.bundle['report_sha256'])
        self.assertTrue(verify_bundle(stored, stored.bundle))
        self.assertEqual(Path(stored.bundle['report']), self.destination / 'REPORT.md')
        self.assertIn('](reports-', report)
        self.assertEqual(subprocess.run(['git', '-C', str(self.root), 'status', '--porcelain'], check=True, capture_output=True, text=True).stdout, '')
        self.assertNotIn('id="case-0001"', report)
        self.assertIn('id="page-00000001-case-0001"', report)

    def test_no_provider_diagnoses_setup_and_empty_changed_scope_separately(self):
        stored = self.run_language(lambda callback: iter_scan(self.root, [], should_scan=callback))
        self.addCleanup(stored.close)
        report = Path(stored.bundle['report']).read_text('utf-8')
        self.assertIn('changed เลือกได้ 0 ไฟล์', report)
        self.assertIn('ยังไม่มีการเรียก analyzer จริง', report)
        self.assertIn('devsift setup --status', report)
        self.assertIn('--native-manifest-digest TRUSTED_SHA256', report)
        self.assertIn('devsift scan --all', report)
        self.assertEqual(stored.exit_code, 2)
        self.assertTrue(stored.bundle['reports_complete'])
        self.assertFalse(stored.bundle['analysis_complete'])

    def test_human_frontdoor_exists_without_markdown_format_and_tampering_fails(self):
        stored = self.run_language(self.two_cases(), formats=('json',))
        self.addCleanup(stored.close)
        page = json.loads(stored.connection.execute('SELECT payload FROM report_pages').fetchone()[0])
        self.assertTrue(page['human_file'].endswith('/human.md'))
        self.assertEqual(stored.bundle['formats'], ('json',))
        self.assertTrue(verify_bundle(stored, stored.bundle))
        path = Path(stored.bundle['report'])
        path.write_text(path.read_text('utf-8') + '\nforeign edit\n', encoding='utf-8')
        self.assertFalse(verify_bundle(stored, stored.bundle))
        self.assertFalse(stored.summary()['data']['report_bundle']['reports_complete'])

    def test_atomic_resume_updates_only_owned_report_and_refuses_foreign_or_hardlink(self):
        factory = lambda callback: iter_scan(self.root, [], should_scan=callback)
        stored = self.run_language(factory)
        stored.close()
        resumed = self.run_language(factory, resume=True)
        self.assertTrue(verify_bundle(resumed, resumed.bundle))
        self.assertEqual(Path(resumed.bundle['report']), self.destination / 'REPORT.md')
        resumed.close()
        self.assertTrue((self.destination / 'REPORT.md').read_text('utf-8').startswith('# รายงาน DevSift'))
        report = self.destination / 'REPORT.md'
        report.write_bytes(b'operator-owned replacement')
        with self.assertRaises(ValueError):
            self.run_language(factory, resume=True)
        self.assertEqual(report.read_bytes(), b'operator-owned replacement')
        self.assertFalse(list(self.destination.glob('REPORT-*.pending')))

    def test_existing_report_hardlink_is_refused_without_touching_other_link(self):
        factory = lambda callback: iter_scan(self.root, [], should_scan=callback)
        stored = self.run_language(factory)
        stored.close()
        report = self.destination / 'REPORT.md'
        other = self.base / 'another-report-link'
        try:
            os.link(report, other)
        except OSError:
            self.skipTest('Host does not support hardlinks')
        original = other.read_bytes()
        with self.assertRaises(ValueError):
            self.run_language(factory, resume=True)
        self.assertEqual(other.read_bytes(), original)
        self.assertEqual(report.read_bytes(), original)

    def test_temporary_creation_collision_never_removes_foreign_file(self):
        import devsift.report_bundle as bundle_module
        actual = bundle_module._private_file
        collision = []

        def obstruct(path, mode, **kwargs):
            if path.name.startswith('REPORT-') and mode == 'x':
                path.write_bytes(b'foreign temporary file')
                collision.append(path)
            return actual(path, mode, **kwargs)

        with patch('devsift.report_bundle._private_file', side_effect=obstruct):
            with self.assertRaises(OSError):
                self.run_language(lambda callback: iter_scan(self.root, [], should_scan=callback))
        self.assertEqual(len(collision), 1)
        self.assertEqual(collision[0].read_bytes(), b'foreign temporary file')

    def test_every_case_across_1205_pages_is_streamed_in_thai_without_aggregate_cap(self):
        from test_report_bundle import ReportBundleTests
        fixture = ReportBundleTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        # A tight *page* budget forces adaptive pages; the full book may exceed it.
        with patch('devsift.markdown_report.MAX_OUTPUT_BYTES', 300_000):
            stored = self.run_language(fixture.producer(1205))
        self.addCleanup(stored.close)
        report = Path(stored.bundle['report'])
        self.assertGreater(report.stat().st_size, 300_000)
        self.assertEqual(stored.bundle['case_count'], 1205)
        self.assertTrue(verify_bundle(stored, stored.bundle))
        case_sections = 0
        with report.open(encoding='utf-8') as stream:
            for line in stream:
                if line.startswith('## กรณี '):
                    case_sections += 1
        self.assertEqual(case_sections, 1205)
        self.assertTrue(stored.bundle['reports_complete'])


if __name__ == '__main__':
    unittest.main()
