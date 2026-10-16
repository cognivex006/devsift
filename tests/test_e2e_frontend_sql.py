"""T050 actual TS/SQL/core/CLI contracts, source proof and no target execution."""
from collections import Counter
import json
from pathlib import Path
import unittest

from devsift.baseline import (BaselineSnapshot, UpdateApproval, capture_entry,
                              load_snapshot, save_snapshot)
from devsift.evidence import SourceEvidence
from devsift.git_changes import classify
from devsift.inventory import SourceTarget
from devsift.native_host import analyze_snapshot
from devsift.policy import decide

from e2e_support import (NATIVE_ENABLED, assert_public_record, native_tools,
                         repository, snapshot)

FIXTURES = Path(__file__).parent / 'fixtures/e2e'


@unittest.skipUnless(NATIVE_ENABLED, 'requires explicit trusted real native setup: DEVSIFT_TEST_NATIVE=1')
class FrontendSqlContractE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = native_tools('typescript', 'sql')

    def sources(self, frontend='runtime', sql='runtime'):
        return {'src/client.ts': (FIXTURES / f'frontend/{frontend}.ts').read_bytes(),
                'db/query.sql': (FIXTURES / f'sql/{sql}.sql').read_bytes()}

    def test_real_ts_sql_share_public_schema_unknown_gate_and_verified_security(self):
        for dialect in ('tsql150', 'tsql160'):
            with self.subTest(dialect=dialect), repository(self.sources()) as repo:
                manifest, digest = repo.manifest(self.tools, dialect=dialect)
                before = snapshot(repo.parent)
                record = repo.cli(manifest, digest)
                assert_public_record(self, record)
                self.assertEqual(record['exit_code'], 2)
                self.assertFalse(record['complete'])
                self.assertEqual(record['enforced_count'], 0)
                self.assertEqual(record['data']['counts']['executed'], 2)
                self.assertEqual(Counter((f['path'], f['rule_id']) for f in record['findings']),
                                 Counter([('src/client.ts', 'HC001'), ('src/client.ts', 'LOG002'),
                                          ('db/query.sql', 'SEC003')]))
                for finding in record['findings']:
                    self.assertEqual(finding['source']['status'], 'VERIFIED')
                    self.assertEqual(finding['source']['location']['source_sha'], repo.head)
                    self.assertTrue(finding['source']['before'])
                    self.assertEqual(finding['security_escalation'], finding['rule_id'] == 'SEC003')
                    self.assertEqual(finding['severity'], 'Critical' if finding['rule_id'] == 'SEC003' else 'Error')
                self.assertEqual(snapshot(repo.parent), before)

    def test_legacy_sql_security_requires_review_even_with_a_lower_local_severity(self):
        with repository(self.sources()) as repo:
            manifest, digest = repo.manifest(self.tools)
            record = repo.cli(manifest, digest)
            finding = next(item for item in record['findings'] if item['rule_id'] == 'SEC003')
            proof = SourceEvidence.from_dict(finding['source'], repo_root=repo.root)
            self.assertEqual(proof.status, 'VERIFIED')
            entry = capture_entry(repo.root, 'SEC003', '1', proof)
            baseline = BaselineSnapshot('local', repo.head, 'e2e-native@1', 'e2e-catalog@1', (entry,))
            path = repo.parent / 'reviewed-sql-baseline.json'
            digest = save_snapshot(path, baseline, UpdateApproval('fixture-author', 'fixture-reviewer', 'T050', baseline.digest))
            before = snapshot(repo.parent)
            loaded = load_snapshot(path, expected_digest=digest)
            origin = classify(repo.root, loaded.source_sha, repo.head, 'SEC003', proof)
            self.assertEqual(origin.lifecycle_class, 'LEGACY_UNCHANGED')
            self.assertEqual(origin.fingerprint, loaded.entries[0].fingerprint)
            decision = decide('SEC003', origin.lifecycle_class, source_verified=True,
                              policy={'rules': {'SEC003': {'severity': 'Warning'}}})
            self.assertTrue(decision.security_escalation)
            self.assertEqual(decision.enforcement, 'security_review')
            # This explicit library composition does not promote the original CLI.
            self.assertEqual(finding['lifecycle_class'], 'UNKNOWN')
            self.assertEqual(finding['enforcement'], 'incomplete')
            self.assertEqual(snapshot(repo.parent), before)

    def test_secret_evidence_is_redacted_and_dirty_sql_cannot_inherit_source_proof(self):
        with repository(self.sources(frontend='secret')) as repo:
            manifest, digest = repo.manifest(self.tools)
            before = snapshot(repo.parent)
            record = repo.cli(manifest, digest)
            assert_public_record(self, record)
            secret = next(item for item in record['findings'] if item['rule_id'] == 'HC002')
            self.assertEqual(secret['source']['status'], 'VERIFIED')
            self.assertEqual(secret['source']['before'], '[REDACTED]')
            self.assertTrue(secret['security_escalation'])
            self.assertNotIn('e2eSyntheticSensitiveValue', json.dumps(record))
            self.assertEqual(snapshot(repo.parent), before)
            query = repo.root / 'db/query.sql'
            query.write_bytes(query.read_bytes() + b'-- changed whole snapshot, same EXEC text\n')
            dirty = snapshot(repo.parent)
            changed = repo.cli(manifest, digest, all_scope=False)
            assert_public_record(self, changed)
            self.assertEqual({item['path'] for item in changed['data']['targets']}, {'db/query.sql'})
            self.assertEqual(changed['exit_code'], 2)
            self.assertEqual(len(changed['findings']), 1)
            self.assertEqual(changed['findings'][0]['source']['status'], 'SOURCE_UNRESOLVED')
            self.assertIsNone(changed['findings'][0]['source']['location'])
            self.assertEqual(changed['enforced_count'], 0)
            self.assertEqual(snapshot(repo.parent), dirty)

    def test_completed_parameterized_sql_vs_partial_sql_never_masks_other_language(self):
        with repository(self.sources(frontend='clean', sql='parameterized')) as repo:
            manifest, digest = repo.manifest(self.tools)
            before = snapshot(repo.parent)
            clean = repo.cli(manifest, digest)
            assert_public_record(self, clean)
            self.assertTrue(clean['complete'])
            self.assertEqual(clean['exit_code'], 0)
            self.assertEqual(clean['findings'], [])
            self.assertEqual(clean['data']['counts']['executed'], 2)
            self.assertEqual(snapshot(repo.parent), before)
        sources = self.sources()
        sources['db/query.sql'] = b'EXEC(@unknown);\n'
        with repository(sources) as repo:
            manifest, digest = repo.manifest(self.tools)
            before = snapshot(repo.parent)
            partial = repo.cli(manifest, digest)
            assert_public_record(self, partial)
            self.assertEqual(partial['exit_code'], 2)
            self.assertFalse(partial['complete'])
            self.assertEqual({f['rule_id'] for f in partial['findings']}, {'HC001', 'LOG002'})
            self.assertTrue(all(f['source']['status'] == 'VERIFIED' for f in partial['findings']))
            sql = next(target for target in partial['data']['targets'] if target['language'] == 'sql')
            self.assertEqual(sql['execution_status'], 'incomplete')
            self.assertIn('ADAPTER_INCOMPLETE', {item['code'] for item in partial['errors']})
            self.assertEqual(snapshot(repo.parent), before)

    def test_target_configs_imports_and_sql_ddl_are_parsed_not_executed(self):
        sources = self.sources(frontend='clean', sql='parse-only')
        with repository(sources) as repo:
            marker = repo.root / 'TARGET_EXECUTED'
            javascript = 'require("node:fs").writeFileSync(' + json.dumps(str(marker)) + ', "forbidden");\n'
            (repo.root / 'src/side-effect.cjs').write_text(javascript, encoding='utf-8')
            (repo.root / 'eslint.config.cjs').write_text(javascript, encoding='utf-8')
            (repo.root / 'tsconfig.json').write_text('not JSON; project service must not load it', encoding='utf-8')
            (repo.root / 'src/client.ts').write_text("import './side-effect.cjs'; export const value=1;\n", encoding='utf-8')
            (repo.root / 'customer.sqlproj').write_text('<invalid-project-must-never-build', encoding='utf-8')
            (repo.root / 'Directory.Build.targets').write_text('not XML; must never build', encoding='utf-8')
            repo.commit('target-side-effect canaries and parse-only DDL')
            manifest, digest = repo.manifest(self.tools)
            before = snapshot(repo.parent)
            sql_source = (repo.root / 'db/query.sql').read_bytes()
            parsed = analyze_snapshot(self.tools['sql'], SourceTarget('db/query.sql', 'ready', 'sql', sql_source, 'e2e'), dialect='tsql160')
            self.assertTrue(parsed.complete)
            self.assertEqual(dict(parsed.metadata), {'dialect': 'tsql160', 'ddl_statements': 2, 'unqualified_references': 0})
            self.assertEqual(parsed.diagnostics, ())
            record = repo.cli(manifest, digest)
            assert_public_record(self, record)
            self.assertTrue(record['complete'])
            self.assertEqual(record['exit_code'], 0)
            self.assertEqual(record['findings'], [])
            self.assertFalse(marker.exists())
            self.assertEqual(snapshot(repo.parent), before)


if __name__ == '__main__':
    unittest.main()
