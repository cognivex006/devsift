import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from devsift.evidence import Region, SourceEvidence, verify_source
from devsift.output import result
from devsift.report_export import ExportError, render_json, render_sarif
from devsift.report_model import assemble_report

ROOT = Path(__file__).resolve().parents[1]


class GitFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = 'view [1].ts'
        self.text = 'const text = "😀"; console.log(text);\r\n'
        (self.root / self.path).write_bytes(self.text.encode())
        for args in (('init', '-q'), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@example.invalid'), ('config', 'core.autocrlf', 'false'),
                     ('add', self.path), ('commit', '-qm', 'fixture')):
            self.git(*args)
        self.sha = self.git('rev-parse', 'HEAD')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def report(self, *, unresolved=False, rules=('LOG001',), lifecycle='NEW', complete=True):
        column = self.text.index('console') + 1
        region = Region(1, column, 1, len(self.text.rstrip('\r\n')) + 1)
        proof = SourceEvidence() if unresolved else verify_source(self.root, 'local', self.sha, self.path, region)
        findings = [dict(case_id=f'CASE-{index}', rule_id=rule, message='ignored', path=self.path,
                         source=proof.to_dict(), severity='Warning', lifecycle_class=lifecycle,
                         enforcement='advisory', security_escalation=False) for index, rule in enumerate(rules, 1)]
        return assemble_report(result('scan', complete=complete, findings=findings), repo_root=self.root,
                               trusted_lifecycles=True, repository_urls=(('local', 'https://github.com/owner/repo'),))


class ReportExportTests(GitFixture, unittest.TestCase):
    def test_full_json_matches_model_without_dropping_case_evidence_or_prompts(self):
        report = self.report(rules=('HC001', 'LOG001'))
        self.assertEqual(json.loads(render_json(report)), report.to_dict())

    def test_sarif_real_locations_unicode_columns_rule_levels_and_known_fingerprints(self):
        report = self.report(rules=('HC001', 'LOG001', 'HC002', 'COM003'))
        wire = json.loads(render_sarif(report))
        self.assertEqual(wire['version'], '2.1.0')
        run = wire['runs'][0]
        self.assertEqual(run['columnKind'], 'unicodeCodePoints')
        self.assertTrue(run['invocations'][0]['executionSuccessful'])
        self.assertEqual([item['level'] for item in run['results']], ['error', 'warning', 'error', 'note'])
        for exported, case in zip(run['results'], report.cases):
            self.assertEqual(run['tool']['driver']['rules'][exported['ruleIndex']]['id'], exported['ruleId'])
            region = exported['locations'][0]['physicalLocation']['region']
            actual = case.source.location.region
            self.assertEqual(region['startColumn'], actual.start_column)
            self.assertEqual(region['endColumn'], actual.end_column)
            self.assertEqual(region['snippet']['text'], case.source.before)
            self.assertEqual(exported['locations'][0]['physicalLocation']['artifactLocation']['uri'], 'view%20%5B1%5D.ts')
            self.assertEqual(exported['partialFingerprints']['devsiftRegion/v1'], case.to_dict()['fingerprint'])
            self.assertNotIn('fixes', exported)
            self.assertNotIn('baselineState', exported)

    def test_unknown_source_is_review_without_locations_or_synthetic_urls(self):
        report = self.report(unresolved=True, lifecycle='UNKNOWN')
        run = json.loads(render_sarif(report))['runs'][0]
        item = run['results'][0]
        self.assertFalse(run['invocations'][0]['executionSuccessful'])
        self.assertNotIn('locations', item)
        self.assertNotIn('partialFingerprints', item)
        self.assertEqual(item['kind'], 'review')
        self.assertEqual(item['properties']['source']['status'], 'SOURCE_UNRESOLVED')
        self.assertTrue(item['properties']['source']['lookup_plan'])
        self.assertNotIn('github.com', json.dumps(item))
        self.assertNotIn('file://', json.dumps(item))

    def test_whole_mask_security_and_overlapping_nonsecurity_export_without_secret(self):
        private = 'fixtureOddCredentialValue'
        self.text = 'console.log("' + private + '");\r\n'
        (self.root / self.path).write_bytes(self.text.encode())
        self.git('add', self.path)
        self.git('commit', '-qm', 'secret fixture')
        self.sha = self.git('rev-parse', 'HEAD')
        region = Region(1, 1, 1, len(self.text.rstrip('\r\n')) + 1)
        proof = verify_source(self.root, 'local', self.sha, self.path, region, sensitive=True)
        findings = [dict(case_id=f'SECRET-{i}', rule_id=rule, message='ignored', path=self.path,
                         source=proof.to_dict(), severity='Critical', lifecycle_class='LEGACY_UNCHANGED',
                         enforcement='advisory', security_escalation=False) for i, rule in enumerate(('HC002', 'LOG001'), 1)]
        report = assemble_report(result('scan', complete=True, findings=findings), repo_root=self.root, trusted_lifecycles=True)
        for renderer in (render_json, render_sarif):
            self.assertNotIn(private, renderer(report))
        exported = json.loads(render_sarif(report))['runs'][0]['results']
        self.assertTrue(exported[0]['properties']['security_escalation'])
        self.assertEqual(exported[0]['properties']['enforcement'], 'security_review')
        self.assertTrue(all(item['locations'][0]['physicalLocation']['region']['snippet']['text'] == '[REDACTED]' for item in exported))

    def test_deterministic_read_only_strict_and_bounded(self):
        report = self.report(complete=False)
        before = {str(p.relative_to(self.root)): None if p.is_dir() else p.read_bytes() for p in self.root.rglob('*')}
        for renderer in (render_json, render_sarif):
            self.assertEqual(renderer(report), renderer(report))
            for bad in ({}, None, report.to_dict()):
                with self.assertRaises(ExportError):
                    renderer(bad)
            with patch('devsift.report_export.MAX_OUTPUT_BYTES', 100):
                with self.assertRaises(ExportError):
                    renderer(report)
        self.assertEqual(before, {str(p.relative_to(self.root)): None if p.is_dir() else p.read_bytes() for p in self.root.rglob('*')})


class ValidationSetupTests(unittest.TestCase):
    def test_wrong_schema_download_hash_never_creates_trusted_cache(self):
        from tools import setup_validation
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'schema.json'
            with patch.object(setup_validation, 'SCHEMA_PATH', target), \
                 patch.object(setup_validation.urllib.request, 'urlopen') as opened:
                opened.return_value.__enter__.return_value.read.return_value = b'X' * setup_validation.SCHEMA_BYTES
                with self.assertRaisesRegex(RuntimeError, '^Validation schema setup unavailable$'):
                    setup_validation.setup_schema()
            self.assertFalse(target.exists())


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_SCHEMA') == '1', 'requires explicit official schema setup')
class OfficialSchemaTests(GitFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import jsonschema
        from referencing import Registry, Resource
        from tools.setup_validation import SCHEMA_PATH, SCHEMA_SHA256, SCHEMA_BYTES
        raw = SCHEMA_PATH.read_bytes()
        if len(raw) != SCHEMA_BYTES or hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
            raise AssertionError('Pinned official SARIF schema cache unavailable or changed')
        report_schema = json.loads((ROOT / 'schemas/report.schema.json').read_text())
        evidence_schema = json.loads((ROOT / 'schemas/evidence.schema.json').read_text())
        registry = Registry().with_resource('urn:devsift:evidence:1', Resource.from_contents(evidence_schema))
        jsonschema.Draft202012Validator.check_schema(report_schema)
        cls.report_validator = jsonschema.Draft202012Validator(report_schema, registry=registry)
        official = json.loads(raw)
        jsonschema.Draft4Validator.check_schema(official)
        formats = jsonschema.FormatChecker(formats=['uri', 'uri-reference'])
        cls.sarif_validator = jsonschema.Draft4Validator(official, format_checker=formats)

    def test_actual_exports_pass_offline_report_registry_and_official_sarif_schema(self):
        for options in ({'rules': ('HC001', 'LOG001')}, {'unresolved': True, 'lifecycle': 'UNKNOWN'}, {'complete': False}):
            report = self.report(**options)
            with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')), \
                 patch('socket.create_connection', side_effect=AssertionError('Network forbidden')):
                self.report_validator.validate(json.loads(render_json(report)))
                self.sarif_validator.validate(json.loads(render_sarif(report)))

    def test_official_schema_rejects_corrupt_versions_columns_levels_and_locations(self):
        from jsonschema import ValidationError
        original = json.loads(render_sarif(self.report()))
        corrupted = []
        for key, value in (('version', '9.9.9'),):
            item = copy.deepcopy(original); item[key] = value; corrupted.append(item)
        item = copy.deepcopy(original); item['runs'][0]['columnKind'] = 'byteOffsets'; corrupted.append(item)
        item = copy.deepcopy(original); item['runs'][0]['results'][0]['level'] = 'critical'; corrupted.append(item)
        item = copy.deepcopy(original); item['runs'][0]['results'][0]['locations'][0]['physicalLocation']['region']['startLine'] = 0; corrupted.append(item)
        item = copy.deepcopy(original); item['runs'][0]['invocations'][0]['executionSuccessful'] = 'unknown'; corrupted.append(item)
        item = copy.deepcopy(original); item['runs'][0]['results'][0]['locations'][0]['physicalLocation']['artifactLocation']['uri'] = 'invalid uri with spaces'; corrupted.append(item)
        for item in corrupted:
            with self.assertRaises(ValidationError):
                self.sarif_validator.validate(item)
        bad_report = json.loads(render_json(self.report()))
        bad_report['cases'][0]['source']['status'] = 'SELF_ASSERTED'
        with self.assertRaises(ValidationError):
            self.report_validator.validate(bad_report)


if __name__ == '__main__':
    unittest.main()
