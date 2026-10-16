"""T042 combines real baseline/provenance and candidate context across exporters.

Finding identities/regions are explicit contract fixtures, not a native-analysis
or rule-coverage claim. No fabricated BaselineObservation absence is supplied.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.baseline import BaselineSnapshot, UpdateApproval, capture_entry, load_snapshot, save_snapshot
from devsift.case_approval import ImplementationApproval, evaluate_case_approval
from devsift.case_prompts import compose_case_prompt
from devsift.evidence import Region, SourceEvidence, verify_source
from devsift.markdown_report import render_markdown
from devsift.output import result
from devsift.report_context import CandidateContext, CaseProvenance, enrich_report_context
from devsift.report_decisions import assess_finding
from devsift.report_export import render_json, render_sarif
from devsift.report_model import assemble_report

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / 'fixtures/report_context'
GOLDEN = json.loads((FIXTURES / 'expected.json').read_text(encoding='utf-8'))


class MixedReportGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report_validator = cls.sarif_validator = None
        if os.environ.get('DEVSIFT_TEST_SCHEMA') == '1':
            import jsonschema
            from referencing import Registry, Resource
            from tools.setup_validation import SCHEMA_BYTES, SCHEMA_PATH, SCHEMA_SHA256
            raw = SCHEMA_PATH.read_bytes()
            if len(raw) != SCHEMA_BYTES or hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
                raise AssertionError('Explicit pinned offline SARIF schema cache unavailable')
            schema = json.loads((ROOT / 'schemas/report.schema.json').read_text(encoding='utf-8'))
            evidence = json.loads((ROOT / 'schemas/evidence.schema.json').read_text(encoding='utf-8'))
            registry = Registry().with_resource('urn:devsift:evidence:1', Resource.from_contents(evidence))
            cls.report_validator = jsonschema.Draft202012Validator(schema, registry=registry)
            cls.sarif_validator = jsonschema.Draft4Validator(json.loads(raw), format_checker=jsonschema.FormatChecker(formats=['uri', 'uri-reference']))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='devsift-mixed-gate-')
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / 'consumer'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'core.hooksPath', str(self.parent / 'no-hooks'))
        for path in (FIXTURES / 'base').iterdir():
            (self.root / path.name).write_bytes(path.read_bytes())
        self.base = self.commit()
        entries = []
        for case in GOLDEN['cases']:
            if case['case_id'] != 'INTRODUCED':
                source = self.source(case['path'], case.get('baseline_selected', case['selected']), sha=self.base)
                entries.append(capture_entry(self.root, case['rule_id'], '1', source))
        snapshot = BaselineSnapshot('fixture/mixed', self.base, 'fixture@1', 'catalog@1', tuple(entries))
        self.baseline_path = self.parent / 'reviewed-baseline.json'
        approved = UpdateApproval('fixture-author', 'fixture-reviewer', 'T042', snapshot.digest)
        self.baseline_digest = save_snapshot(self.baseline_path, snapshot, approved)
        self.assertEqual(hashlib.sha256(self.baseline_path.read_bytes()).hexdigest(), self.baseline_digest)
        self.baseline = load_snapshot(self.baseline_path, expected_digest=self.baseline_digest)
        for path in (FIXTURES / 'head').iterdir():
            (self.root / path.name).write_bytes(path.read_bytes())
        self.head = self.commit()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True, timeout=20).stdout.decode('utf-8').strip()

    def commit(self):
        self.git('add', '--all')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgSign=false', 'commit', '-qm', 'synthetic gate fixture')
        return self.git('rev-parse', 'HEAD')

    def source(self, path, selected=None, *, sha=None, masked=False):
        sha = sha or self.head
        lines = self.git('show', sha + ':' + path).splitlines()
        if selected is None:
            selected = lines[0]
        matches = [(index + 1, line.index(selected) + 1) for index, line in enumerate(lines) if selected in line]
        self.assertEqual(len(matches), 1, 'Golden source region must be unique')
        line, column = matches[0]
        return verify_source(self.root, 'fixture/mixed', sha, path, Region(line, column, line, column + len(selected)), sensitive=masked)

    def assemble(self, ids=None, *, execution_complete=True, masked=False):
        chosen = [case for case in GOLDEN['cases'] if ids is None or case['case_id'] in ids]
        findings, assessments = [], {}
        for case in chosen:
            proof = self.source(case['path'], case['selected'], masked=masked)
            assessment = assess_finding(self.root, self.base, self.head, case['rule_id'], proof, rule_version='1',
                                        snapshot=self.baseline, tool_version='fixture@1', rule_catalog_version='catalog@1')
            assessments[case['case_id']] = assessment
            decision = assessment.decision
            findings.append({'case_id': case['case_id'], 'rule_id': case['rule_id'], 'path': case['path'],
                             'source': proof.to_dict(), 'message': 'explicit golden fixture diagnostic',
                             'severity': decision.severity.value, 'lifecycle_class': decision.lifecycle_class,
                             'enforcement': decision.enforcement, 'security_escalation': decision.security_escalation})
        complete = execution_complete and all(item.decision.enforcement != 'incomplete' for item in assessments.values())
        record = result('scan', complete=complete, enforced_count=sum(f['enforcement'] == 'block' for f in findings), findings=findings,
                        errors=[] if execution_complete else [{'code': 'ADAPTER_INCOMPLETE', 'message': 'Explicit incomplete-execution fixture'}])
        return assemble_report(record, repo_root=self.root, trusted_lifecycles=True), assessments

    def enrich(self, report, candidates=()):
        return enrich_report_context(report, repo_root=self.root, base_ref=self.base,
                                     provenance=tuple(CaseProvenance(c.case_id, '1') for c in report.cases), candidates=candidates,
                                     snapshot=self.baseline, tool_version='fixture@1', rule_catalog_version='catalog@1')

    def candidate(self, identity, role, *, missing=False):
        return CandidateContext(identity, role, SourceEvidence() if missing else self.source('consumer.ts' if role == 'consumer' else 'test_legacy.ts'))

    def tree(self):
        return {p.relative_to(self.parent).as_posix(): None if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest() for p in self.parent.rglob('*')}

    def exports(self, report):
        wire = report.to_dict()
        json_text, sarif_text, markdown = render_json(report), render_sarif(report), render_markdown(report)
        self.assertEqual(json.loads(json_text), wire)
        sarif = json.loads(sarif_text)
        exported = {case['properties']['case_id']: case for case in sarif['runs'][0]['results']}
        for case in report.cases:
            self.assertEqual(exported[case.case_id]['properties'], case.to_dict())
        invocation = sarif['runs'][0]['invocations'][0]
        self.assertEqual(invocation['executionSuccessful'], report.complete)
        self.assertEqual(invocation['exitCode'], report.exit_code)
        for forbidden in GOLDEN['opaque_values_not_for_export']:
            self.assertNotIn(forbidden, json_text + sarif_text + markdown)
        if self.report_validator is not None:
            self.report_validator.validate(wire)
            self.report_validator.validate(json.loads(json_text))
            self.sarif_validator.validate(sarif)
        return wire, exported, markdown

    def test_four_way_gate_baseline_and_missing_source_context_survive_all_exports(self):
        before = self.tree()
        report, assessments = self.assemble()
        candidates = (self.candidate('LEGACY', 'consumer'), self.candidate('LEGACY', 'test', missing=True),
                      self.candidate('INTRODUCED', 'consumer', missing=True), self.candidate('INTRODUCED', 'test'),
                      self.candidate('UNKNOWN', 'consumer', missing=True), self.candidate('SECURITY', 'consumer'))
        enriched = self.enrich(report, candidates)
        wire, sarif, markdown = self.exports(enriched)
        for expected in GOLDEN['cases']:
            actual = enriched.find_case(expected['case_id']).to_dict()
            for key in ('lifecycle_class', 'enforcement', 'security_escalation'):
                self.assertEqual(actual[key], expected[key], expected['case_id'])
            self.assertEqual(assessments[expected['case_id']].baseline_status, expected['baseline_status'])
            self.assertEqual(actual['impact_if_unchanged']['level'], GOLDEN['effects']['impact'])
            self.assertEqual(actual['risk_if_changed']['level'], GOLDEN['effects']['risk'])
            self.assertEqual(actual['affected_scope']['status'], 'unknown')
            self.assertEqual(actual['approval_status'], 'pending')
            self.assertFalse(actual['automatic_fix'])
            self.assertIsNone(actual['after_proposal']['code'])
        for key, value in GOLDEN['mixed_gate'].items():
            self.assertEqual(wire[key], value)
        legacy = enriched.find_case('LEGACY').to_dict()
        self.assertEqual([s['status'] for s in legacy['related_locations']], ['VERIFIED', 'SOURCE_UNRESOLVED'])
        self.assertEqual(len(sarif['LEGACY']['relatedLocations']), 1)
        self.assertNotIn('relatedLocations', sarif['UNKNOWN'])
        self.assertIsNone(legacy['related_locations'][1]['location'])
        self.assertIn('relationship unproven', legacy['affected_scope']['consumers'][0])
        self.assertIn('not executed; no pass evidence', legacy['affected_scope']['test_evidence'][0])
        self.assertIn('security_review', markdown)
        self.assertIn('SOURCE_UNRESOLVED', markdown)
        self.assertEqual(self.tree(), before)

    def test_completed_legacy_security_new_block_and_prior_incomplete_are_independent_gates(self):
        before = self.tree()
        for ids, complete, expected_exit, expected_blocks in [
                ({'LEGACY', 'SECURITY'}, True, 0, 0),
                ({'LEGACY', 'SECURITY', 'INTRODUCED'}, True, 1, 1),
                ({'LEGACY', 'SECURITY', 'INTRODUCED'}, False, 2, 1)]:
            with self.subTest(ids=sorted(ids), complete=complete):
                report, _ = self.assemble(ids, execution_complete=complete)
                candidates = tuple(self.candidate(identity, 'consumer') for identity in sorted(ids))
                enriched = self.enrich(report, candidates)
                wire, _, _ = self.exports(enriched)
                self.assertEqual(wire['exit_code'], expected_exit)
                self.assertEqual(wire['enforced_count'], expected_blocks)
                self.assertEqual(wire['complete'], complete)
                self.assertTrue(enriched.find_case('SECURITY').to_dict()['security_escalation'])
                self.assertEqual(enriched.find_case('SECURITY').to_dict()['enforcement'], 'security_review')
        self.assertEqual(self.tree(), before)

    def test_enriched_masked_case_and_explicit_approval_still_allow_no_execution(self):
        before = self.tree()
        original, _ = self.assemble({'LEGACY'}, masked=True)
        enriched = self.enrich(original, (self.candidate('LEGACY', 'consumer'), self.candidate('LEGACY', 'test', missing=True)))
        self.exports(enriched)
        prompt = compose_case_prompt(enriched, 'LEGACY', mode='implement', repo_root=self.root)
        self.assertEqual(prompt.to_dict()['source']['before'], '[REDACTED]')
        now = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
        approval = ImplementationApproval(case_id='LEGACY', source_sha=self.head,
                                          fingerprint=prompt.to_dict()['fingerprint'], prompt_digest=prompt.digest,
                                          mode='implement', approved=True, actor='fixture-operator',
                                          issued_at=(now - timedelta(minutes=1)).isoformat(), expires_at=(now + timedelta(minutes=1)).isoformat())
        decision = evaluate_case_approval(enriched, 'LEGACY', prompt=prompt, repo_root=self.root, approval=approval, now=now).to_dict()
        self.assertTrue(decision['approval_matched'])
        self.assertEqual(decision['status'], 'review_required')
        self.assertEqual(decision['reason'], 'UNKNOWN_EFFECTS_REVIEW_REQUIRED')
        self.assertTrue(decision['manual_planning_allowed'])
        for key in ('execution_authorized', 'writes_authorized', 'automatic_fix'):
            self.assertFalse(decision[key])
        self.assertEqual(self.tree(), before)


if __name__ == '__main__':
    unittest.main()
