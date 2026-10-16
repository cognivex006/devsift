"""T041 source-only context and actual three-exporter/schema compatibility."""
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.baseline import BaselineSnapshot, capture_entry
from devsift.evidence import Region, SourceEvidence, verify_source
from devsift.git_changes import BaselineObservation
from devsift.markdown_report import render_markdown
from devsift.output import result
from devsift.report_context import CandidateContext, CaseProvenance, ContextError, enrich_report_context
from devsift.report_export import render_json, render_sarif
from devsift.report_model import assemble_report

ROOT = Path(__file__).resolve().parents[1]


class ReportContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='devsift-context-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'core.hooksPath', str(self.root / 'no-hooks'))
        (self.root / 'service.py').write_text('legacy_call()\nother_call()\n', encoding='utf-8')
        (self.root / 'consumer.py').write_text('opaque = "opaqueConsumerPrivateValue"\n', encoding='utf-8')
        (self.root / 'test_service.py').write_text('assert service() == "opaqueTestPrivateValue"\n', encoding='utf-8')
        self.base = self.commit()
        (self.root / 'new.py').write_text('introduced_call()\n', encoding='utf-8')
        self.head = self.commit()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True, timeout=20).stdout.decode('utf-8').strip()

    def commit(self):
        self.git('add', '--all')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgSign=false', 'commit', '-qm', 'synthetic fixture')
        return self.git('rev-parse', 'HEAD')

    def source(self, path='service.py', *, sha=None, repository='local', masked=False):
        sha = sha or self.head
        line = self.git('show', sha + ':' + path).splitlines()[0]
        return verify_source(self.root, repository, sha, path, Region(1, 1, 1, len(line) + 1), sensitive=masked)

    def report(self, *, mixed=False, trusted=False, rule='HC001', masked=False, unresolved=False):
        cases = [('LEGACY', 'service.py', 'LEGACY_UNCHANGED')]
        if mixed:
            cases.append(('NEW', 'new.py', 'NEW'))
        findings = []
        for identity, path, lifecycle in cases:
            source = SourceEvidence() if unresolved else self.source(path, masked=masked)
            findings.append({'case_id': identity, 'rule_id': rule, 'message': 'ignored', 'path': path,
                             'source': source.to_dict(), 'severity': 'Error', 'lifecycle_class': lifecycle,
                             'enforcement': 'advisory', 'security_escalation': False})
        return assemble_report(result('scan', complete=True, findings=findings), repo_root=self.root, trusted_lifecycles=trusted)

    def context(self, role='consumer', *, path=None, sha=None, repository='local', case_id='LEGACY'):
        path = path or ('consumer.py' if role == 'consumer' else 'test_service.py')
        return CandidateContext(case_id, role, self.source(path, sha=sha, repository=repository))

    def enrich(self, report=None, **kwargs):
        return enrich_report_context(report if report is not None else self.report(), repo_root=self.root, **kwargs)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): None if p.is_dir() else p.read_bytes() for p in self.root.rglob('*')}

    def test_verified_positions_are_masked_candidates_not_proven_consumers_or_passing_tests(self):
        report = self.report()
        consumer, test = self.context(), self.context('test')
        self.assertNotIn('opaqueConsumerPrivateValue', repr(consumer))
        self.assertNotIn('opaqueTestPrivateValue', repr(test))
        enriched = self.enrich(report, candidates=(consumer, test))
        item = enriched.find_case('LEGACY').to_dict()
        self.assertEqual(item['source'], report.cases[0].source.to_dict())
        self.assertEqual(item['affected_scope']['status'], 'unknown')
        self.assertIn('relationship unproven', item['affected_scope']['consumers'][0])
        self.assertIn('not executed; no pass evidence', item['affected_scope']['test_evidence'][0])
        self.assertEqual(item['lifecycle_class'], 'UNKNOWN')
        self.assertEqual(item['enforcement'], 'incomplete')
        for source in item['related_locations']:
            self.assertEqual(source['status'], 'VERIFIED')
            self.assertEqual(source['before'], '[REDACTED]')
            self.assertEqual(source['location']['source_sha'], self.head)
            self.assertIsNone(source['location']['symbol'])
        for key in ('impact_if_unchanged', 'risk_if_changed'):
            self.assertEqual(item[key]['level'], 'unknown')
            self.assertTrue(item[key]['evidence'])
        for renderer in (render_json, render_sarif, render_markdown):
            text = renderer(enriched)
            self.assertNotIn('opaqueConsumerPrivateValue', text)
            self.assertNotIn('opaqueTestPrivateValue', text)

    def test_unresolved_wrong_sha_or_repository_candidates_stay_visible_without_fake_locations(self):
        candidates = (CandidateContext('LEGACY', 'consumer', SourceEvidence()),
                      self.context(sha=self.base), self.context(repository='wrong-repository'))
        enriched = self.enrich(candidates=candidates)
        item = enriched.find_case('LEGACY').to_dict()
        self.assertEqual(len(item['related_locations']), 3)
        self.assertEqual(len(item['affected_scope']['consumers']), 3)
        for source in item['related_locations']:
            self.assertEqual(source['status'], 'SOURCE_UNRESOLVED')
            self.assertIsNone(source['location'])
            self.assertIsNone(source['before'])
        self.assertFalse(enriched.complete)
        self.assertNotIn('consumer.py', json.dumps(item['related_locations']))
        sarif = json.loads(render_sarif(enriched))['runs'][0]['results'][0]
        self.assertNotIn('relatedLocations', sarif)
        self.assertEqual(len(sarif['properties']['related_locations']), 3)

    def test_actual_mixed_git_provenance_keeps_legacy_advisory_and_new_policy_separate(self):
        original = self.report(mixed=True)
        enriched = self.enrich(original, base_ref=self.base,
                               provenance=(CaseProvenance('LEGACY', '1'), CaseProvenance('NEW', '1')))
        old, new = enriched.find_case('LEGACY').to_dict(), enriched.find_case('NEW').to_dict()
        self.assertEqual((old['lifecycle_class'], old['enforcement']), ('LEGACY_UNCHANGED', 'advisory'))
        self.assertIn('recommendation', old['human_explanation'])
        self.assertEqual((new['lifecycle_class'], new['enforcement']), ('NEW', 'block'))
        self.assertEqual(enriched.to_dict()['enforced_count'], 1)
        self.assertFalse(original.complete)
        self.assertFalse(enriched.complete)  # enrichment never promotes incomplete execution
        self.assertEqual(enriched.exit_code, 2)

    def test_changed_region_without_baseline_analysis_does_not_become_new(self):
        (self.root / 'service.py').write_text('replacement_call()\nother_call()\n', encoding='utf-8')
        self.head = self.commit()
        original = self.report()
        unknown = self.enrich(original, base_ref=self.base, provenance=(CaseProvenance('LEGACY', '1'),))
        self.assertEqual(unknown.cases[0].to_dict()['lifecycle_class'], 'UNKNOWN')
        observation = BaselineObservation('HC001', self.base, 'service.py', (), True, 'explicit-fixture-analysis')
        introduced = self.enrich(original, base_ref=self.base,
                                 provenance=(CaseProvenance('LEGACY', '1', observation),))
        self.assertEqual(introduced.cases[0].to_dict()['lifecycle_class'], 'MODIFIED_INTRODUCED')
        self.assertEqual(introduced.cases[0].to_dict()['enforcement'], 'block')

    def test_explicit_trusted_snapshot_requires_matching_version_metadata(self):
        entry = capture_entry(self.root, 'HC001', '1', self.source(sha=self.base))
        snapshot = BaselineSnapshot('local', self.base, 'fixture@1', 'catalog@1', (entry,))
        enriched = self.enrich(base_ref=self.base, provenance=(CaseProvenance('LEGACY', '1'),), snapshot=snapshot,
                               tool_version='fixture@1', rule_catalog_version='catalog@1')
        self.assertEqual(enriched.cases[0].to_dict()['enforcement'], 'advisory')
        with self.assertRaises(ContextError) as error:
            self.enrich(base_ref=self.base, provenance=(CaseProvenance('LEGACY', '1'),), snapshot=snapshot,
                        tool_version='PRIVATE-MISMATCH', rule_catalog_version='catalog@1')
        self.assertEqual(str(error.exception), 'Invalid or unavailable report context')

    def test_existing_legacy_security_review_and_primary_overlapping_masks_are_preserved(self):
        security = self.report(trusted=True, rule='SEC003')
        enriched = self.enrich(security, candidates=(self.context(),))
        item = enriched.cases[0].to_dict()
        self.assertEqual(item['enforcement'], 'security_review')
        self.assertTrue(item['security_escalation'])
        self.assertEqual(item['lifecycle_class'], 'LEGACY_UNCHANGED')
        masked = self.report(rule='LOG001', masked=True)
        self.assertEqual(self.enrich(masked).cases[0].source.before, '[REDACTED]')
        for value in (item, self.enrich(masked).cases[0].to_dict()):
            self.assertFalse(value['automatic_fix'])
            self.assertEqual(value['approval_status'], 'pending')
            self.assertIsNone(value['after_proposal']['code'])

    def test_unresolved_primary_cannot_lend_proof_to_candidates(self):
        report = self.report(unresolved=True)
        enriched = self.enrich(report, candidates=(self.context(),))
        item = enriched.cases[0].to_dict()
        self.assertEqual(item['source']['status'], 'SOURCE_UNRESOLVED')
        self.assertIsNone(item['fingerprint'])
        self.assertIsNone(item['navigation'])
        self.assertEqual(item['related_locations'][0]['status'], 'SOURCE_UNRESOLVED')
        self.assertNotIn('consumer.py', json.dumps(item['affected_scope']))

    def test_types_bounds_private_failures_and_immutable_fresh_read_only_outputs(self):
        report = self.report()
        candidate = self.context()
        before, original = self.snapshot(), report.to_dict()
        enriched = self.enrich(report, candidates=(candidate,))
        changed = enriched.to_dict()
        changed['cases'][0]['related_locations'][0]['before'] = 'unmasked-forgery'
        self.assertNotEqual(changed, enriched.to_dict())
        with self.assertRaises(FrozenInstanceError):
            candidate.role = 'verified-callgraph'
        for bad in (report.to_dict(), {}, None):
            with self.assertRaises(ContextError):
                enrich_report_context(bad, repo_root=self.root)
        for kwargs in ({'candidates': ({'case_id': 'LEGACY'},)},
                       {'candidates': (CandidateContext('PRIVATE-NONCASE', 'consumer', SourceEvidence()),)},
                       {'candidates': (candidate,) * 33}, {'base_ref': self.base},
                       {'provenance': (CaseProvenance('LEGACY', '1'),)}):
            with self.assertRaises(ContextError) as error:
                self.enrich(report, **kwargs)
            self.assertEqual(str(error.exception), 'Invalid or unavailable report context')
        self.assertEqual(report.to_dict(), original)
        for renderer in (render_json, render_sarif, render_markdown):
            self.assertEqual(renderer(enriched), renderer(enriched))
        self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(os.environ.get('DEVSIFT_TEST_SCHEMA') == '1', 'requires explicit trusted offline schema validation setup')
    def test_enriched_report_and_all_three_exports_match_existing_official_schemas(self):
        import jsonschema
        from referencing import Registry, Resource
        from tools.setup_validation import SCHEMA_BYTES, SCHEMA_PATH, SCHEMA_SHA256
        raw = SCHEMA_PATH.read_bytes()
        self.assertEqual(len(raw), SCHEMA_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SCHEMA_SHA256)
        schema = json.loads((ROOT / 'schemas/report.schema.json').read_text(encoding='utf-8'))
        evidence = json.loads((ROOT / 'schemas/evidence.schema.json').read_text(encoding='utf-8'))
        registry = Registry().with_resource('urn:devsift:evidence:1', Resource.from_contents(evidence))
        validator = jsonschema.Draft202012Validator(schema, registry=registry)
        report = self.enrich(self.report(mixed=True), candidates=(self.context(), self.context('test'),
                            CandidateContext('NEW', 'consumer', SourceEvidence())), base_ref=self.base,
                            provenance=(CaseProvenance('LEGACY', '1'), CaseProvenance('NEW', '1')))
        validator.validate(report.to_dict())
        validator.validate(json.loads(render_json(report)))
        sarif = json.loads(render_sarif(report))
        jsonschema.Draft4Validator(json.loads(raw), format_checker=jsonschema.FormatChecker(formats=['uri', 'uri-reference'])).validate(sarif)
        self.assertEqual(sarif['runs'][0]['results'][0]['properties'], report.cases[0].to_dict())
        markdown = render_markdown(report)
        self.assertIn('Affected scope and evidence', markdown)
        self.assertIn('Candidate consumer', markdown)
        self.assertIn('SOURCE_UNRESOLVED', markdown)


if __name__ == '__main__':
    unittest.main()
