"""Real CLI, storage, native-fixture and report integration for terms governance."""
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

from devsift.cli import parser, run
from devsift.output import result
from devsift.inventory import SourceTarget
from devsift.scan_store import StoreError, run_streamed
from devsift.terms import assess_terms
from devsift.terms_gate import apply_terms_gate, source_record

ROOT = Path(__file__).resolve().parents[1]


class TermsIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Reuse actual pinned physical evidence; do not replace the engine with
        # a mock verdict or import a TestCase into this module's discovery scope.
        from test_terms import TermsTests
        self.fixture = TermsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture
        self.f.data.update(reviewed_at='2020-01-01T00:00:00Z', review_due='2099-12-31T00:00:00Z')
        self.home = patch.object(Path, 'home', return_value=self.f.home)
        self.home.start()
        self.addCleanup(self.home.stop)
        self.previous = Path.cwd()
        os.chdir(self.f.root)
        self.addCleanup(os.chdir, self.previous)
        self.save_catalog()

    def save_catalog(self):
        self.catalog = self.f.catalog / 'review.json'
        self.catalog.write_text(json.dumps(self.f.data), encoding='utf-8')
        self.pin = hashlib.sha256(self.catalog.read_bytes()).hexdigest()

    def assessment(self):
        return assess_terms(self.f.root, catalog_path=self.catalog, catalog_digest=self.pin)

    def options(self):
        return ['--terms-catalog', str(self.catalog), '--terms-catalog-digest', self.pin]

    def check(self, *extra):
        value = run(parser().parse_args(['terms', 'check', *self.options(), *extra]))
        self.assertNotIsInstance(value, dict, value)
        self.addCleanup(value.close)
        return value

    def process(self, *arguments):
        env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
                   PYTHONIOENCODING='utf-8', USERPROFILE=str(self.f.home), HOME=str(self.f.home),
                   GIT_CONFIG_GLOBAL=os.devnull)
        completed = subprocess.run([sys.executable, '-B', '-m', 'devsift', *arguments],
            cwd=self.f.root, env=env, text=True, encoding='utf-8', capture_output=True, timeout=60)
        self.assertEqual(completed.stderr, '', completed.stderr)
        record = json.loads(completed.stdout)
        self.assertEqual(record['exit_code'], completed.returncode)
        return record

    def test_real_cli_decline_is_remembered_reconsidered_and_never_waives(self):
        first = self.process('terms', 'check', *self.options(), '--summary', '--report-language', 'th')
        case = first['data']['terms_compliance']['cases'][0]
        self.assertEqual((first['exit_code'], first['enforced_count']), (1, 1))
        decision = ['terms', 'decide', case['case_id'], *self.options(), '--owner', 'Fixture Owner',
            '--reason', 'Explicit owner decision fixture', '--fingerprint', case['fingerprint'],
            '--evidence-digest', case['evidence_digest']]
        saved = self.process(*decision, '--choice', 'decline')
        self.assertTrue(saved['data']['decision_recorded'])
        self.assertEqual(saved['enforced_count'], 1)
        again = self.process('terms', 'check', *self.options(), '--summary')
        self.assertFalse(again['data']['terms_gate']['decision_required'])
        self.assertEqual(again['exit_code'], 1)
        event = saved['data']['decision']
        changed = self.process(*decision, '--choice', 'reconsider', '--supersedes', event['event_id'])
        self.assertTrue(changed['data']['terms_gate']['decision_required'])
        self.assertEqual(changed['enforced_count'], 1)
        history = self.process('terms', 'history')
        self.assertEqual([e['choice'] for e in history['data']['decisions']], ['decline', 'reconsider'])
        self.assertEqual(history['data']['decisions'][0]['event_id'], event['event_id'])

    def test_stale_report_cannot_record_owner_answer_for_changed_usage(self):
        case = self.assessment().to_dict()['cases'][0]
        self.f.write('deploy.json', {'mode': 'changed-workload'})
        record = self.process('terms', 'decide', case['case_id'], *self.options(), '--choice', 'decline',
            '--owner', 'Fixture Owner', '--reason', 'Old report answer', '--fingerprint', case['fingerprint'],
            '--evidence-digest', case['evidence_digest'])
        self.assertFalse(record['data']['decision_recorded'])
        self.assertIn('TERMS_DECISION_STALE', {e['code'] for e in record['errors']})
        self.assertEqual(self.process('terms', 'history')['data']['decisions'], [])

    def test_complete_frontdoor_all_formats_and_inline_output_keep_terms(self):
        stored = self.check('--report-language', 'th')
        summary = stored.summary()
        bundle = summary['data']['report_bundle']
        self.assertTrue(bundle['reports_complete'])
        self.assertEqual((bundle['terms_case_count'], bundle['total_case_count']), (1, 1))
        report = Path(bundle['report']).read_text(encoding='utf-8')
        case = summary['data']['terms_compliance']['cases'][0]
        self.assertIn(case['case_id'], report)
        self.assertIn('การกำกับดูแลข้อกำหนด', report)
        self.assertIn('forbidden-workload', report)
        self.assertIn('Terms', report)
        self.assertIn('fingerprint', report)
        output = io.StringIO()
        stored.write_json(output)
        wire = json.loads(output.getvalue())
        self.assertEqual(wire['data']['reports']['json']['terms_compliance']['enforced_count'], 1)
        sarif = wire['data']['reports']['sarif']['runs'][0]
        self.assertEqual(len(sarif['results']), 1)
        self.assertNotIn('locations', sarif['results'][0])
        self.assertIn(case['case_id'], wire['data']['reports']['markdown'])
        index = json.loads(Path(bundle['index']).read_text(encoding='utf-8'))
        self.assertEqual(index['terms_case_count'], 1)
        for item in index['terms_files']:
            raw = (Path(bundle['index']).parent / item['file']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'])

    def test_json_only_request_still_delivers_full_human_terms(self):
        summary = self.check('--report-format', 'json').summary()
        bundle = summary['data']['report_bundle']
        self.assertTrue(bundle['reports_complete'])
        self.assertEqual({d['file'] for d in bundle['terms_files']}, {'terms.json', 'terms.md'})
        self.assertIn('forbidden-workload', Path(bundle['report']).read_text(encoding='utf-8'))

    def test_terms_artifact_tamper_is_incomplete_but_block_survives(self):
        stored = self.check()
        summary = stored.summary()
        path = Path(summary['data']['report_bundle']['index']).parent / 'terms.json'
        with path.open('ab') as stream:
            stream.write(b'changed')
        broken = stored.summary()
        self.assertEqual((broken['exit_code'], broken['enforced_count']), (2, 1))
        self.assertFalse(broken['data']['report_bundle']['reports_complete'])

    def test_terms_render_failure_is_reported_without_erasing_block(self):
        from devsift.ci_artifacts import ArtifactError
        with patch('devsift.report_bundle._build_terms', side_effect=ArtifactError('unavailable')):
            summary = self.check().summary()
        self.assertEqual((summary['exit_code'], summary['enforced_count']), (2, 1))
        self.assertFalse(summary['data']['report_bundle']['reports_complete'])
        self.assertIn('REPORT_UNAVAILABLE', {e['code'] for e in summary['errors']})

    def test_source_fragments_do_not_multiply_terms_count_and_resume_reuses_source(self):
        self.f.write('package.json', {'dependencies': {'unreviewed': '1.2.3'}})
        terms = self.assessment()
        for name in ('a.txt', 'b.txt'):
            (self.f.root / name).write_bytes(b'a')
        destination = self.f.base / 'session'

        def records(hook):
            for name in ('a.txt', 'b.txt'):
                target = SourceTarget(name, 'unsupported', None, None, 'Unsupported text fixture')
                if hook(target):
                    native = result('scan', complete=True, data={'targets': [{'path': name,
                        'execution_status': 'skipped'}], 'counts': {'skipped': 1}})
                    yield apply_terms_gate(native, terms)

        first = run_streamed(self.f.root, records, destination=destination,
                             configuration={'command': 'scan'}, terms_assessment=terms)
        try:
            summary = first.summary()
            self.assertEqual(summary['enforced_count'], 1)
            self.assertTrue(summary['data']['source_analysis_complete'])
            self.assertEqual(summary['data']['target_count'], 2)
            self.assertFalse(summary['complete'])
        finally:
            first.close()
        second = run_streamed(self.f.root, records, destination=destination, resume=True,
                              configuration={'command': 'scan'}, terms_assessment=self.assessment())
        try:
            summary = second.summary()
            self.assertEqual(summary['enforced_count'], 1)
            self.assertEqual(summary['data']['execution']['reused_targets'], 2)
        finally:
            second.close()

    def test_decision_change_invalidates_resume_global_state(self):
        stored = self.check()
        summary = stored.summary()
        destination = summary['data']['scan_directory']
        case = summary['data']['terms_compliance']['cases'][0]
        stored.close()
        self.f.decide(case, 'decline')
        value = run(parser().parse_args(['terms', 'check', *self.options(), '--resume', destination]))
        self.assertIsInstance(value, dict)
        self.assertEqual((value['exit_code'], value['enforced_count']), (2, 1))
        self.assertFalse(value['data']['terms_gate']['decision_required'])
        self.assertIn('SCAN_STORAGE_UNAVAILABLE', {e['code'] for e in value['errors']})

    def test_concurrent_usage_change_during_run_fails_closed(self):
        terms = self.assessment()

        def records(hook):
            yield result('scan', complete=True, data={'targets': [], 'counts': {}})
            self.f.write('deploy.json', {'mode': 'changed-after-assessment'})

        stored = run_streamed(self.f.root, records, destination=self.f.base / 'changed-session',
            configuration={'command': 'scan'}, terms_assessment=terms, terms_recheck=self.assessment)
        try:
            summary = stored.summary()
            self.assertEqual((summary['exit_code'], summary['enforced_count']), (2, 1))
            self.assertIn('TERMS_INPUT_CHANGED', {e['code'] for e in summary['errors']})
        finally:
            stored.close()

    def test_native_setup_failure_does_not_skip_terms(self):
        value = run(parser().parse_args(['ci', '--all', '--minimum-severity', 'Critical',
                                        *self.options(), '--summary']))
        self.assertNotIsInstance(value, dict, value)
        try:
            summary = value.summary()
            self.assertEqual((summary['exit_code'], summary['enforced_count']), (2, 1))
            self.assertEqual(summary['data']['terms_gate']['status'], 'blocked')
            self.assertIn('ANALYZER_SETUP_REQUIRED', {e['code'] for e in summary['errors']})
        finally:
            value.close()

    def test_actual_native_ci_cannot_hide_terms_with_paths_or_critical_threshold(self):
        from test_ci_gate import CiGateTests
        from devsift.ci_gate import GateConfig, run_ci
        ci = CiGateTests()
        ci.setUp()
        self.addCleanup(ci.doCleanups)
        ci.source('value = 1\n')
        declaration = json.loads((self.f.root / '.devsift/third-party.json').read_text(encoding='utf-8'))
        deployment = (self.f.root / 'deploy.json').read_bytes()
        self.f.root = ci.root
        self.f.write('.devsift/third-party.json', declaration)
        (ci.root / 'deploy.json').write_bytes(deployment)
        terms = self.assessment()
        before = {p.relative_to(ci.root).as_posix(): p.read_bytes() for p in ci.root.rglob('*') if p.is_file()}
        actual = run_ci(ci.root, native_manifest=ci.manifest, native_manifest_digest=ci.digest,
            paths=('code.py',), config=GateConfig('Critical'), terms_assessment=terms,
            terms_catalog=self.catalog, terms_catalog_digest=self.pin)
        self.assertEqual(actual.exit_code, 1)
        self.assertTrue(actual.to_dict()['complete'])
        self.assertEqual(actual.to_dict()['enforced_count'], 1)
        self.assertEqual(actual.scan_record()['enforced_count'], 1)
        self.assertEqual(before, {p.relative_to(ci.root).as_posix(): p.read_bytes()
                                 for p in ci.root.rglob('*') if p.is_file()})

    def test_terms_check_never_networks_or_writes_project(self):
        before = {p.relative_to(self.f.root).as_posix(): p.read_bytes()
                  for p in self.f.root.rglob('*') if p.is_file()}
        with patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')):
            with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
                summary = self.check().summary()
        self.assertEqual(summary['enforced_count'], 1)
        self.assertEqual(before, {p.relative_to(self.f.root).as_posix(): p.read_bytes()
                                 for p in self.f.root.rglob('*') if p.is_file()})

    def test_doctor_validates_config_only_without_terms_analysis(self):
        with patch('devsift.terms.assess_terms', side_effect=AssertionError('Doctor must not assess usage')):
            record = run(parser().parse_args(['doctor', *self.options()]))
        self.assertFalse(record['data']['analysis_performed'])
        checks = record['data']['terms_governance']
        self.assertFalse(checks['assessment_performed'])
        self.assertTrue(checks['catalog_configuration_valid'])
        self.assertTrue(checks['decision_history_readable'])

    def test_reapplying_gate_is_idempotent_and_source_only_is_explicit(self):
        terms = self.assessment()
        native = result('scan', complete=True, data={})
        first = apply_terms_gate(native, terms)
        again = apply_terms_gate(first, terms)
        self.assertEqual((again['enforced_count'], again['exit_code']), (1, 1))
        self.assertEqual(source_record(again, terms), native)


if __name__ == '__main__':
    unittest.main()
