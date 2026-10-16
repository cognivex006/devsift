"""T051: real mixed native CLI, all exports, manual approval and failed gates."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from devsift.ci_gate import run_ci
from e2e_support import NATIVE_ENABLED, ROOT, environment, native_tools, repository, snapshot


FIXTURES = Path(__file__).parent / 'fixtures/e2e'
SECRET = 'e2eSyntheticSensitiveValue'


@unittest.skipUnless(NATIVE_ENABLED, 'requires explicit trusted real native setup: DEVSIFT_TEST_NATIVE=1')
class FullMixedGateE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('DEVSIFT_TEST_SCHEMA') != '1':
            raise AssertionError('Full mixed gate requires explicit offline schema validation too')
        import jsonschema
        from referencing import Registry, Resource
        from tools.setup_validation import SCHEMA_BYTES, SCHEMA_PATH, SCHEMA_SHA256
        schema_path = Path(os.environ.get('DEVSIFT_SARIF_SCHEMA_PATH', SCHEMA_PATH))
        with schema_path.open('rb') as stream:
            raw = stream.read(SCHEMA_BYTES + 1)
        if len(raw) != SCHEMA_BYTES or hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
            raise AssertionError('Pinned official offline SARIF schema unavailable')
        evidence = json.loads((ROOT / 'schemas/evidence.schema.json').read_text(encoding='utf-8'))
        report = json.loads((ROOT / 'schemas/report.schema.json').read_text(encoding='utf-8'))
        registry = Registry().with_resource('urn:devsift:evidence:1', Resource.from_contents(evidence))
        cls.report_validator = jsonschema.Draft202012Validator(report, registry=registry)
        cls.sarif_validator = jsonschema.Draft4Validator(json.loads(raw),
            format_checker=jsonschema.FormatChecker(formats=['uri', 'uri-reference']))
        cls.tools = native_tools('csharp', 'go', 'typescript', 'sql')
        # The explicitly reused frontend package must match this accepted source,
        # rather than proving a stale primary helper against a newer checkout.
        package = Path(os.environ.get('DEVSIFT_FRONTEND_PACKAGE', ROOT / 'native/frontend'))
        for name in ('analyze.cjs', 'package.json', 'package-lock.json'):
            if (package / name).read_bytes() != (ROOT / 'native/frontend' / name).read_bytes():
                raise AssertionError('Explicit frontend setup source differs from this checkout')

    def sources(self, *, clean=False, partial=False):
        files = {
            'src/service.cs': FIXTURES / ('backend/clean.cs' if clean else 'backend/service.cs'),
            'src/service.go': FIXTURES / ('backend/clean.go' if clean else 'backend/service.go'),
            'src/client.ts': FIXTURES / ('frontend/clean.ts' if clean else 'frontend/runtime.ts'),
            'db/query.sql': FIXTURES / ('sql/parameterized.sql' if clean else 'sql/runtime.sql'),
        }
        sources = {name: path.read_bytes() for name, path in files.items()}
        if not clean:
            sources['src/credential.ts'] = (FIXTURES / 'frontend/secret.ts').read_bytes()
        if partial:
            sources['db/query.sql'] = b'EXEC(@unknown);\n'
        return sources

    def cli(self, repo, *arguments):
        completed = subprocess.run([sys.executable, '-P', '-B', '-m', 'devsift', *arguments],
            cwd=repo.root, env=environment(), capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.assertEqual(completed.stderr, '', completed.stderr)
        record = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, record['exit_code'])
        self.assertNotIn(SECRET, completed.stdout)
        return record

    def ci(self, repo, manifest, digest, base):
        return self.cli(repo, 'ci', '--all', '--base', base, '--native-manifest', str(manifest),
                        '--native-manifest-digest', digest,
                        '--report-format', 'json', '--report-format', 'markdown', '--report-format', 'sarif')

    def exports(self, record):
        self.assertEqual(record['command'], 'ci')
        documents = record['data']['reports']
        self.assertEqual(set(documents), {'json', 'markdown', 'sarif'})
        report, sarif, markdown = documents['json'], documents['sarif'], documents['markdown']
        self.report_validator.validate(report)
        self.sarif_validator.validate(sarif)
        self.assertEqual((report['exit_code'], report['complete']), (record['exit_code'], record['complete']))
        invocation = sarif['runs'][0]['invocations'][0]
        self.assertEqual(invocation['exitCode'], record['exit_code'])
        self.assertEqual(invocation['executionSuccessful'], record['complete'])
        cases = {case['case_id']: case for case in report['cases']}
        rendered = {case['properties']['case_id']: case for case in sarif['runs'][0]['results']}
        self.assertEqual(set(cases), set(rendered))
        for identity, case in cases.items():
            self.assertEqual(rendered[identity]['properties'], case)
            # Markdown deliberately escapes identifiers, so compare its semantic
            # fixed sections instead of reconstructing Markdown from implementation.
            self.assertIn(case['rule_id'], markdown)
            self.assertFalse(case['automatic_fix'])
            self.assertIsNone(case['after_proposal']['code'])
        if cases:
            self.assertIn('AFTER (PROPOSAL)', markdown)
        self.assertNotIn(SECRET, json.dumps(documents))
        return report

    def test_real_all_language_cli_legacy_security_exports_and_explicit_approvals_stay_held(self):
        with repository(self.sources()) as repo:
            manifest, digest = repo.manifest(self.tools)
            before = snapshot(repo.parent)
            # Keep the actual scanner envelope for the explicit prompt-input file;
            # do not fabricate a scan by relabeling arbitrary saved CI JSON.
            execution = run_ci(repo.root, native_manifest=manifest, native_manifest_digest=digest,
                               base_ref=repo.head, all_scope=True)
            public = self.ci(repo, manifest, digest, repo.head)
            self.assertEqual(public['exit_code'], 2)
            self.assertEqual(public['enforced_count'], 0)
            self.assertEqual(public['data']['counts']['executed'], 5)
            self.assertIn('SECURITY_REVIEW_REQUIRED', {error['code'] for error in public['errors']})
            report = self.exports(public)
            self.assertTrue(report['cases'])
            self.assertEqual({case['lifecycle_class'] for case in report['cases']}, {'LEGACY_UNCHANGED'})
            self.assertEqual({case['enforcement'] for case in report['cases']}, {'advisory', 'security_review'})
            self.assertEqual({Path(case['source']['location']['path']).suffix for case in report['cases']},
                             {'.cs', '.go', '.ts', '.sql'})
            secret = next(case for case in report['cases'] if case['rule_id'] == 'HC002')
            self.assertEqual(secret['source']['before'], '[REDACTED]')
            self.assertTrue(secret['security_escalation'])
            self.assertEqual(snapshot(repo.parent), before)

            # The following external input/approval writes are explicit disposable
            # fixture setup, outside the consumer source; subsequent calls are read-only.
            scan_input = repo.parent / 'actual-native-scan.json'
            scan_input.write_text(json.dumps(execution.scan_record()), encoding='utf-8')
            selected = secret['case_id']
            arguments = ('prompt', selected, '--mode', 'implement', '--approved-case', selected,
                         '--scan-input', str(scan_input))
            before = snapshot(repo.parent)
            pending = self.cli(repo, *arguments)
            self.assertEqual(pending['exit_code'], 2)
            self.assertEqual(pending['data']['approval']['reason'], 'EXPLICIT_APPROVAL_REQUIRED')
            self.assertEqual(snapshot(repo.parent), before)
            value = pending['data']['prompt']
            now = datetime.now(timezone.utc)
            approval = {'case_id': selected, 'source_sha': value['source_sha'], 'fingerprint': value['fingerprint'],
                'prompt_digest': pending['data']['prompt_digest'], 'mode': 'implement', 'approved': True,
                'actor': 'mixed-gate-fixture-operator', 'issued_at': (now - timedelta(minutes=1)).isoformat(),
                'expires_at': (now + timedelta(minutes=10)).isoformat()}
            approved_file, wrong_file = repo.parent / 'approved.json', repo.parent / 'wrong-case.json'
            approved_file.write_text(json.dumps(approval), encoding='utf-8')
            wrong_file.write_text(json.dumps(dict(approval, case_id='ANOTHER-CASE')), encoding='utf-8')
            before = snapshot(repo.parent)
            matched = self.cli(repo, *arguments, '--approval-file', str(approved_file))
            denied = self.cli(repo, *arguments, '--approval-file', str(wrong_file))
            self.assertEqual(matched['data']['approval']['reason'], 'UNKNOWN_EFFECTS_REVIEW_REQUIRED')
            self.assertTrue(matched['data']['approval']['manual_planning_allowed'])
            self.assertEqual(denied['data']['approval']['reason'], 'APPROVAL_BINDING_MISMATCH')
            for result in (matched, denied):
                self.assertEqual(result['exit_code'], 2)
                self.assertFalse(result['data']['approval']['execution_authorized'])
                self.assertFalse(result['data']['approval']['writes_authorized'])
                self.assertFalse(result['data']['approval']['automatic_fix'])
                self.assertEqual(result['data']['prompt']['source']['before'], '[REDACTED]')
            self.assertEqual(snapshot(repo.parent), before)
            self.assertEqual(public['exit_code'], 2)  # Planning input did not waive the separate security gate.

    def test_completed_mixed_clean_and_real_new_path_block_have_distinct_release_gates(self):
        with repository(self.sources(clean=True)) as repo:
            manifest, digest = repo.manifest(self.tools)
            base = repo.head
            before = snapshot(repo.parent)
            clean = self.ci(repo, manifest, digest, base)
            self.assertEqual(clean['exit_code'], 0)
            self.assertTrue(clean['complete'])
            self.assertEqual(clean['findings'], [])
            self.assertEqual(clean['data']['counts']['executed'], 4)
            self.exports(clean)
            self.assertEqual(snapshot(repo.parent), before)
            (repo.root / 'src/added.ts').write_text(
                "export async function added() { await fetch('https://new.example.invalid'); }\n", encoding='utf-8')
            repo.commit('explicit introduced-path fixture setup')
            before = snapshot(repo.parent)
            blocked = self.ci(repo, manifest, digest, base)
            self.assertEqual(blocked['exit_code'], 1)
            self.assertTrue(blocked['complete'])
            self.assertGreater(blocked['enforced_count'], 0)
            cases = self.exports(blocked)['cases']
            introduced = next(case for case in cases if case['rule_id'] == 'HC001')
            self.assertEqual(introduced['lifecycle_class'], 'NEW')
            self.assertEqual(introduced['enforcement'], 'block')
            self.assertEqual(introduced['source']['location']['path'], 'src/added.ts')
            self.assertEqual(introduced['source']['location']['source_sha'], repo.head)
            self.assertEqual(snapshot(repo.parent), before)

    def test_partial_parser_and_invalid_native_trust_never_become_green_exports(self):
        with repository(self.sources(partial=True)) as repo:
            manifest, digest = repo.manifest(self.tools)
            before = snapshot(repo.parent)
            partial = self.ci(repo, manifest, digest, repo.head)
            self.assertEqual(partial['exit_code'], 2)
            self.assertFalse(partial['complete'])
            self.assertIn('ADAPTER_INCOMPLETE', {error['code'] for error in partial['errors']})
            self.assertEqual(partial['data']['counts']['incomplete'], 1)
            report = self.exports(partial)
            self.assertTrue(report['cases'])
            self.assertTrue(all(case['source']['location']['path'] != 'db/query.sql' for case in report['cases']))
            self.assertEqual(snapshot(repo.parent), before)
            invalid = self.ci(repo, manifest, '0' * 64, repo.head)  # Deliberately wrong trust pin, never source proof.
            self.assertEqual(invalid['exit_code'], 2)
            self.assertFalse(invalid['complete'])
            self.assertIn('CI_SCAN_UNAVAILABLE', {error['code'] for error in invalid['errors']})
            self.assertEqual(self.exports(invalid)['cases'], [])
            self.assertNotIn(str(repo.parent), json.dumps(invalid))
            self.assertEqual(snapshot(repo.parent), before)


if __name__ == '__main__':
    unittest.main()
