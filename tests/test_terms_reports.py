"""Terms reports retain sealed governance evidence without inventing source authority."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import test_terms as fixtures
from devsift.ci_artifacts import attach_reports, build_reports
from devsift.markdown_report import MarkdownError, render_markdown, render_terms_markdown
from devsift.output import result
from devsift.report_export import render_json, render_sarif
from devsift.report_model import ReportError, assemble_report
from devsift.terms import TermsAssessment, TermsError


class TermsReportTests(unittest.TestCase):
    setUp = fixtures.TermsTests.setUp
    write = fixtures.TermsTests.write
    assess = fixtures.TermsTests.assess
    case = fixtures.TermsTests.case
    decide = fixtures.TermsTests.decide

    def report(self, assessment, **kwargs):
        return assemble_report(result('scan', complete=True), repo_root=self.root,
                               terms_assessment=assessment, **kwargs)

    def test_decline_keeps_floor_and_all_evidence_in_every_format(self):
        assessment = self.assess()
        event = self.decide(self.case(assessment), 'decline')
        assessment = self.assess()
        report = self.report(assessment, policy={'quality_gate': {'block_on': []}})
        wire = report.to_dict()
        self.assertEqual((report.complete, report.exit_code, wire['enforced_count']), (True, 1, 1))
        self.assertFalse(wire['terms_compliance']['decision_required'])
        self.assertEqual(json.loads(render_json(report))['terms_compliance'], assessment.to_dict())
        sarif = json.loads(render_sarif(report))['runs'][0]
        self.assertEqual(sarif['properties']['terms_compliance'], assessment.to_dict())
        entry = sarif['results'][0]
        self.assertEqual((entry['ruleId'], entry['kind'], entry['level']), ('TERMS/rule-1', 'fail', 'error'))
        self.assertNotIn('locations', entry)
        self.assertNotIn('physicalLocation', json.dumps(sarif))
        self.assertEqual(entry['properties']['decision']['event_id'], event['event_id'])
        for language in ('en', 'th'):
            text = render_markdown(report, language=language)
            self.assertIn(event['event_id'], text)
            self.assertIn('forbidden-workload', text)
            self.assertIn(self.case(assessment)['evidence_digest'], text)
            self.assertIn('decline', text)
            self.assertIn('การกำกับดูแล' if language == 'th' else 'Third-party terms governance', text)

    def test_source_and_terms_counts_combine_and_render_failure_keeps_terms_floor(self):
        import subprocess
        from devsift.evidence import Region, verify_source
        path = self.root / 'fixture.ts'
        path.write_text('const url = "https://provider.example";\n', encoding='utf-8')
        for args in (('config', 'user.name', 'Fixture'), ('config', 'user.email', 'fixture@example.invalid'),
                     ('add', 'fixture.ts'), ('commit', '-qm', 'fixture')):
            subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)
        sha = subprocess.check_output(['git', '-C', str(self.root), 'rev-parse', 'HEAD']).decode().strip()
        source = verify_source(self.root, 'local', sha, 'fixture.ts', Region(1, 1, 1, 6))
        finding = dict(case_id='SOURCE-1', rule_id='HC001', message='Detected', path='fixture.ts',
            source=source.to_dict(), severity='Error', lifecycle_class='NEW', enforcement='block', security_escalation=False)
        record = result('scan', complete=True, enforced_count=1, findings=[finding])
        assessment = self.assess()
        report = assemble_report(record, repo_root=self.root, terms_assessment=assessment, trusted_lifecycles=True)
        self.assertEqual(report.to_dict()['enforced_count'], 2)
        run = json.loads(render_sarif(report))['runs'][0]
        self.assertEqual(len(run['results']), 2)
        self.assertIn('locations', run['results'][0])
        self.assertNotIn('locations', run['results'][1])
        with patch('devsift.markdown_report.render_markdown', side_effect=ValueError('bounded failure')):
            failed = attach_reports(record, record, repo_root=self.root, terms_assessment=assessment)
        self.assertEqual((failed['exit_code'], failed['enforced_count']), (2, 1))
        self.assertEqual(failed['data']['terms_gate']['status'], 'blocked')

    def test_unknown_coverage_wins_exit_but_preserves_serious_block(self):
        self.write('package.json', {'dependencies': {'unknown': '1.2.3'}})
        assessment = self.assess()
        report = self.report(assessment)
        self.assertFalse(report.complete)
        self.assertEqual((report.exit_code, report.to_dict()['enforced_count']), (2, 1))
        public = attach_reports(result('scan', complete=True), result('scan', complete=True),
                                repo_root=self.root, terms_assessment=assessment)
        self.assertEqual((public['exit_code'], public['enforced_count']), (2, 1))
        for case in assessment.to_dict()['cases']:
            self.assertIn(case['case_id'], public['data']['reports']['markdown'])

    def test_wire_payload_cannot_fabricate_terms_and_wrong_seal_or_repository_rejected(self):
        assessment = self.assess()
        raw = result('scan', complete=True, data={'terms_compliance': assessment.to_dict()})
        self.assertNotIn('terms_compliance', assemble_report(raw, repo_root=self.root).to_dict())
        self.assertEqual(assemble_report(raw, repo_root=self.root).exit_code, 0)
        with self.assertRaises(ReportError):
            assemble_report(raw, repo_root=self.root, terms_assessment=assessment.to_dict())
        with self.assertRaises(MarkdownError):
            render_terms_markdown(assessment.to_dict())
        with self.assertRaises(TermsError):
            TermsAssessment('forged', 'forged', '{}')
        other = self.base / 'other'
        other.mkdir()
        with self.assertRaises(ReportError):
            assemble_report(raw, repo_root=other, terms_assessment=assessment)

    def test_html_markdown_and_fence_injection_remain_data(self):
        self.review['rationale'] = '<img src=x onerror=alert(1)> [run](https://evil.example) ```` # injected'
        assessment = self.assess()
        text = render_terms_markdown(assessment)
        self.assertIn('`````text', text)
        # Raw evidence is code fenced; explanation outside fences is escaped.
        self.assertIn('&lt;img', text)
        self.assertIn('\\[run\\]', text)
        self.assertNotIn('\n# injected\n', text)

    def test_build_and_attach_preserve_assessment_and_source_failure(self):
        assessment = self.assess()
        source = result('scan', complete=False, errors=[{'code':'NATIVE_TOOL_UNAVAILABLE', 'message':'Unavailable'}])
        report, docs = build_reports(source, repo_root=self.root, terms_assessment=assessment)
        self.assertEqual(report.exit_code, 2)
        self.assertEqual(docs['json']['terms_compliance'], assessment.to_dict())
        public = attach_reports(source, source, repo_root=self.root, terms_assessment=assessment)
        self.assertEqual(public['enforced_count'], 1)
        self.assertFalse(public['complete'])
        self.assertEqual(public['data']['terms_compliance'], assessment.to_dict())
        self.assertIn('source analysis only', render_markdown(assemble_report(result('scan', complete=True), repo_root=self.root)))

    def test_already_floored_internal_record_does_not_double_count(self):
        assessment = self.assess()
        record = result('scan', complete=True, enforced_count=1, data={
            'source_analysis_complete':True, 'source_enforced_count':0})
        report = assemble_report(record, repo_root=self.root, terms_assessment=assessment)
        self.assertEqual((report.exit_code, report.to_dict()['enforced_count']), (1, 1))

    def test_unmatched_decisions_and_reviews_are_visible(self):
        assessment = self.assess()
        event = self.decide(self.case(assessment), 'decline')
        (self.root / '.devsift/third-party.json').unlink()
        assessment = self.assess()
        text = render_terms_markdown(assessment)
        self.assertIn(event['event_id'], text)
        self.assertIn('unmatched_reviews', text)
        self.assertIn('TERMS_REVIEW_SCOPE_MISMATCH', text)
        self.assertEqual(self.report(assessment).exit_code, 2)

    def test_bounded_display_keeps_compact_decline_and_block(self):
        from devsift.redaction import Redactor, RedactionError
        assessment = self.assess()
        event = self.decide(self.case(assessment), 'decline')
        original = Redactor.redact
        forced = False
        def bounded(masker, value, **kwargs):
            nonlocal forced
            if kwargs.get('max_nodes') == 200000 and not forced:
                forced = True
                raise RedactionError('Bounded fixture')
            return original(masker, value, **kwargs)
        with patch.object(Redactor, 'redact', bounded):
            assessment = self.assess()
        report = self.report(assessment)
        self.assertEqual((report.exit_code, report.to_dict()['enforced_count']), (2, 1))
        self.assertIn('TERMS_OUTPUT_LIMIT', render_terms_markdown(assessment))
        self.assertIn(event['event_id'], render_terms_markdown(assessment))
        self.assertIn('details_omitted', render_markdown(report))
        self.assertEqual(json.loads(render_sarif(report))['runs'][0]['results'][0]['properties']['decision']['choice'], 'decline')

    @unittest.skipUnless(os.environ.get('DEVSIFT_TEST_SCHEMA') == '1', 'requires explicit official schema setup')
    def test_report_schema_accepts_real_terms_and_rejects_fabricated_case_shape(self):
        import jsonschema
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/report.schema.json').read_text(encoding='utf-8'))
        wire = self.report(self.assess()).to_dict()
        jsonschema.Draft202012Validator(schema).validate(wire)
        import hashlib
        from tools.setup_validation import SCHEMA_PATH, SCHEMA_SHA256, SCHEMA_BYTES
        raw = SCHEMA_PATH.read_bytes()
        self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (SCHEMA_BYTES, SCHEMA_SHA256))
        jsonschema.Draft4Validator(json.loads(raw)).validate(json.loads(render_sarif(self.report(self.assess()))))
        wire['terms_compliance']['cases'][0]['enforcement'] = 'waived'
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(wire)


if __name__ == '__main__':
    unittest.main()
