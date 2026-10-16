"""Report contracts proven with actual immutable Git source and safe failures."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.evidence import Region, verify_source
from devsift.output import result
from devsift.redaction import Redactor
from devsift.report_model import Report, ReportCase, ReportError, assemble_report


class ReportModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        def git(*args):
            return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                                  capture_output=True, text=True).stdout.strip()
        self.git = git
        git('init', '-q')
        source = "const apiKey='fixtureUnrecognizedValue';\nfetch('https://api.example.test');\n"
        (self.root / 'client.ts').write_bytes(source.encode())
        git('add', 'client.ts')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        self.sha = git('rev-parse', 'HEAD')
        self.source = verify_source(self.root, 'local', self.sha, 'client.ts', Region(2, 1, 2, len(source.splitlines()[1])+1))
        self.assertEqual(self.source.status, 'VERIFIED')

    def record(self, rule='HC001', lifecycle='NEW', complete=True):
        finding = dict(case_id='CASE-1', rule_id=rule, message='untrusted message content', path='client.ts',
                       source=self.source.to_dict(), severity='Error', lifecycle_class=lifecycle,
                       enforcement='block', security_escalation=False)
        return result('scan', complete=complete, findings=[finding], enforced_count=1)

    def test_default_wire_classification_cannot_assert_new_or_clean(self):
        report = assemble_report(self.record(), repo_root=self.root)
        case = report.cases[0].to_dict()
        self.assertEqual((report.complete, report.exit_code), (False, 2))
        self.assertEqual((case['lifecycle_class'], case['enforcement']), ('UNKNOWN', 'incomplete'))
        self.assertNotIn('untrusted message content', json.dumps(report.to_dict()))
        self.assertEqual(case['impact_if_unchanged']['level'], 'unknown')
        self.assertEqual(case['risk_if_changed']['level'], 'unknown')
        self.assertEqual(case['approval_status'], 'pending')
        self.assertFalse(case['automatic_fix'])
        self.assertIsNone(case['after_proposal']['code'])

    def test_trusted_in_process_attribution_recomputes_policy_and_keeps_incomplete(self):
        report = assemble_report(self.record(), repo_root=self.root, trusted_lifecycles=True)
        self.assertEqual((report.exit_code, report.complete), (1, True))
        self.assertEqual(report.cases[0].to_dict()['severity'], 'Error')
        incomplete = assemble_report(self.record(complete=False), repo_root=self.root, trusted_lifecycles=True)
        self.assertEqual((incomplete.exit_code, incomplete.complete), (2, False))
        self.assertEqual(incomplete.to_dict()['enforced_count'], 1)

    def test_legacy_security_routes_review_and_withholds_complete_region(self):
        line = (self.root / 'client.ts').read_text().splitlines()[0]
        self.source = verify_source(self.root, 'local', self.sha, 'client.ts', Region(1, 1, 1, len(line)+1))
        record = self.record('HC002', 'LEGACY_UNCHANGED')
        report = assemble_report(record, repo_root=self.root, trusted_lifecycles=True)
        case = report.cases[0].to_dict()
        self.assertEqual(case['source']['before'], '[REDACTED]')
        self.assertEqual(case['enforcement'], 'security_review')
        self.assertTrue(case['security_escalation'])
        self.assertNotIn('fixtureUnrecognizedValue', json.dumps(report.to_dict()))
        self.assertIsNone(case['navigation'])
        self.assertEqual(len(case['fingerprint']), 64)

    def test_unavailable_source_does_not_keep_fake_location_or_navigation(self):
        record = self.record()
        record['findings'][0]['source']['location']['source_sha'] = 'a' * 40
        report = assemble_report(record, repo_root=self.root, trusted_lifecycles=True,
                                 repository_urls=(('local', 'https://github.com/owner/repo'),))
        case = report.cases[0].to_dict()
        self.assertEqual(case['source']['status'], 'SOURCE_UNRESOLVED')
        self.assertIsNone(case['source']['location'])
        self.assertIsNone(case['navigation'])
        self.assertEqual(case['lifecycle_class'], 'UNKNOWN')
        self.assertEqual(report.exit_code, 2)

    def test_navigation_requires_explicit_trusted_repository_mapping(self):
        report = assemble_report(self.record(), repo_root=self.root,
                                 repository_urls=(('local', 'https://github.com/owner/repo'),))
        self.assertEqual(report.cases[0].to_dict()['navigation'],
                         f'https://github.com/owner/repo/blob/{self.sha}/client.ts#L2-L2')
        for url in ['file:///tmp/a', 'https://github.com.evil.test/owner/repo', 'https://github.com/owner/repo?x=1']:
            with self.assertRaises(ReportError):
                assemble_report(self.record(), repo_root=self.root, repository_urls=(('local', url),))

    def test_invalid_envelopes_counts_nested_fields_and_duplicate_ids_fail_safely(self):
        bad = []
        for key, value in [('complete', 1), ('enforced_count', True), ('exit_code', 0), ('status', 'clean')]:
            item = self.record(); item[key] = value; bad.append(item)
        item = self.record(); item['findings'] *= 2; bad.append(item)
        item = self.record(); item['findings'][0]['source']['unexpected'] = 'private'; bad.append(item)
        item = self.record(); item['enforced_count'] = 2; bad.append(item)
        item = self.record(); item['data']['nonfinite'] = float('inf'); bad.append(item)
        item = self.record(); item['data']['huge'] = 'x' * 4_000_001; bad.append(item)
        item = self.record(); item['data']['cycle'] = item; bad.append(item)
        for record in bad:
            with self.subTest(keys=list(record)):
                with self.assertRaises(ReportError) as error:
                    assemble_report(record, repo_root=self.root)
                self.assertEqual(str(error.exception), 'Invalid or unavailable report input')

    def test_immutable_fresh_outputs_safe_lookup_and_no_source_or_git_writes(self):
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        record = self.record()
        untouched = copy.deepcopy(record)
        report = assemble_report(record, repo_root=self.root)
        mutated = report.to_dict(); mutated['cases'][0]['title'] = 'changed'
        self.assertNotEqual(report.to_dict()['cases'][0]['title'], 'changed')
        self.assertEqual(record, untouched)
        self.assertEqual(report.find_case('CASE-1'), report.cases[0])
        with self.assertRaises(ReportError): report.find_case('missing-secret-value')
        with self.assertRaises(ReportError): Report((), True, 0, '{}')
        with self.assertRaises(ReportError): ReportCase('x', 'HC001', self.source, '{}')
        after = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_failure_errors_are_static_and_do_not_echo_scan_values(self):
        record = result('scan', complete=False, errors=[{'code': 'TOOL_FAILED', 'message': 'fixturePrivateErrorValue'}])
        report = assemble_report(record, repo_root=self.root)
        self.assertNotIn('fixturePrivateErrorValue', json.dumps(report.to_dict()))
        self.assertEqual(report.exit_code, 2)
        self.assertEqual(report.cases, ())

    def test_error_code_secret_and_explicit_reserved_words_preserve_schema(self):
        secret = 'AK' + 'IA' + 'A' * 16
        raw = result('scan', complete=False, errors=[{'code': secret, 'message': 'private'}])
        wire = assemble_report(raw, repo_root=self.root, redactor=Redactor((secret,))).to_dict()
        self.assertNotIn(secret, json.dumps(wire))
        for word in ['confidence', 'unknown', 'pending', 'Error', 'cases', 'source']:
            report = assemble_report(self.record(), repo_root=self.root, redactor=Redactor((word,)))
            case = report.cases[0].to_dict()
            self.assertIn('confidence', case)
            self.assertEqual(case['confidence'], 'unknown')
            self.assertEqual(case['approval_status'], 'pending')
            self.assertEqual(case['severity'], 'Error')
            self.assertEqual(case['impact_if_unchanged']['level'], 'unknown')

    def test_repository_mapping_rejects_controls_and_withholds_sensitive_links(self):
        for suffix in ['\n', '\t', ' ', '\r', '\x00']:
            with self.assertRaises(ReportError):
                assemble_report(self.record(), repo_root=self.root,
                                repository_urls=(('local', 'https://github.com/owner/repo' + suffix),))
        report = assemble_report(self.record(), repo_root=self.root,
                                 redactor=Redactor(('owner/repo',)),
                                 repository_urls=(('local', 'https://github.com/owner/repo'),))
        self.assertIsNone(report.cases[0].to_dict()['navigation'])

    def test_existing_full_mask_on_overlapping_nonsecurity_rule_survives_report(self):
        line = (self.root / 'client.ts').read_text().splitlines()[0]
        self.source = verify_source(self.root, 'local', self.sha, 'client.ts',
                                    Region(1, 1, 1, len(line)+1), sensitive=True)
        report = assemble_report(self.record('LOG001'), repo_root=self.root)
        self.assertEqual(report.cases[0].to_dict()['source']['before'], '[REDACTED]')
        self.assertNotIn('fixtureUnrecognizedValue', json.dumps(report.to_dict()))
