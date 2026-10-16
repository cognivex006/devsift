"""T049 real C#/Go → native protocol → core/CLI → explicit legacy baseline."""
from collections import Counter
from pathlib import Path
import unittest

from devsift.baseline import (BaselineSnapshot, UpdateApproval, capture_entry,
                              diff_snapshots, load_snapshot, save_snapshot)
from devsift.evidence import SourceEvidence
from devsift.git_changes import classify
from devsift.policy import decide

from e2e_support import (NATIVE_ENABLED, assert_public_record, native_tools,
                         repository, snapshot)

FIXTURES = Path(__file__).parent / 'fixtures/e2e/backend'


@unittest.skipUnless(NATIVE_ENABLED, 'requires explicit trusted real native setup: DEVSIFT_TEST_NATIVE=1')
class BackendContractE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = native_tools('csharp', 'go')

    def sources(self, prefix='service'):
        return {f'src/{prefix}.{extension}': (FIXTURES / f'{prefix}.{extension}').read_bytes()
                for extension in ('cs', 'go')}

    def assert_backend_findings(self, record):
        assert_public_record(self, record)
        self.assertEqual(record['exit_code'], 2)
        self.assertFalse(record['complete'])
        self.assertEqual(record['enforced_count'], 0)
        self.assertEqual(record['data']['counts']['executed'], 2)
        self.assertEqual(Counter((f['path'], f['rule_id']) for f in record['findings']),
                         Counter((f'src/service.{ext}', rule) for ext in ('cs', 'go')
                                 for rule in ('HC001', 'LOG001', 'LOG002')))
        for finding in record['findings']:
            self.assertEqual(finding['source']['status'], 'VERIFIED')
            self.assertEqual(finding['severity'], 'Warning' if finding['rule_id'] == 'LOG001' else 'Error')
            self.assertFalse(finding['security_escalation'])

    def test_real_mixed_backend_cli_emits_verified_unknown_and_writes_nothing(self):
        with repository(self.sources()) as repo:
            manifest, digest = repo.manifest(self.tools)
            before = snapshot(repo.parent)
            record = repo.cli(manifest, digest)
            self.assert_backend_findings(record)
            for finding in record['findings']:
                location = finding['source']['location']
                self.assertEqual(location['source_sha'], repo.head)
                self.assertEqual(location['path'], finding['path'])
                snippet = finding['source']['before']
                self.assertTrue(snippet)
                self.assertIn(snippet, (repo.root / finding['path']).read_text(encoding='utf-8'))
            self.assertEqual(snapshot(repo.parent), before)

    def test_reviewed_legacy_baseline_integrates_with_core_without_magic_cli_attribution(self):
        with repository(self.sources()) as repo:
            manifest, digest = repo.manifest(self.tools)
            record = repo.cli(manifest, digest)
            self.assert_backend_findings(record)
            evidence = [(item, SourceEvidence.from_dict(item['source'], repo_root=repo.root))
                        for item in record['findings']]
            entries = tuple(capture_entry(repo.root, item['rule_id'], '1', proof) for item, proof in evidence)
            baseline = BaselineSnapshot('local', repo.head, 'e2e-native@1', 'e2e-catalog@1', entries)
            path = repo.parent / 'reviewed-legacy.json'
            # Synthetic review is fixture setup, never a scan-time baseline write.
            approval = UpdateApproval('fixture-author', 'fixture-reviewer', 'T049', baseline.digest)
            file_digest = save_snapshot(path, baseline, approval)
            before = snapshot(repo.parent)
            accepted = load_snapshot(path, expected_digest=file_digest)
            delta = diff_snapshots(accepted, baseline)
            self.assertEqual(len(delta.unchanged), 6)
            self.assertEqual((delta.added, delta.resolved), ((), ()))
            for item, proof in evidence:
                origin = classify(repo.root, accepted.source_sha, repo.head, item['rule_id'], proof)
                self.assertEqual(origin.lifecycle_class, 'LEGACY_UNCHANGED')
                self.assertIn((item['rule_id'], origin.fingerprint),
                              {(entry.rule_id, entry.fingerprint) for entry in accepted.entries})
                decision = decide(item['rule_id'], origin.lifecycle_class, source_verified=proof.status == 'VERIFIED')
                self.assertEqual(decision.enforcement, 'advisory')
            # Merely storing/loading a baseline must not silently wire a classifier
            # into today's CLI: default native attribution remains UNKNOWN.
            self.assert_backend_findings(repo.cli(manifest, digest))
            self.assertEqual(snapshot(repo.parent), before)

    def test_changed_scope_stale_source_is_incomplete_and_untouched_legacy_is_not_selected(self):
        with repository(self.sources()) as repo:
            manifest, digest = repo.manifest(self.tools)
            path = repo.root / 'src/service.cs'
            path.write_bytes(path.read_bytes() + b'// dirty whole snapshot, same diagnostic snippets\n')
            before = snapshot(repo.parent)
            record = repo.cli(manifest, digest, all_scope=False)
            assert_public_record(self, record)
            self.assertEqual(record['exit_code'], 2)
            self.assertEqual({target['path'] for target in record['data']['targets']}, {'src/service.cs'})
            self.assertEqual(record['data']['counts']['executed'], 1)
            self.assertEqual(len(record['findings']), 3)
            self.assertTrue(all(f['source']['status'] == 'SOURCE_UNRESOLVED' for f in record['findings']))
            self.assertTrue(all(f['source']['location'] is None for f in record['findings']))
            self.assertEqual(record['enforced_count'], 0)
            self.assertEqual(snapshot(repo.parent), before)

    def test_completed_clean_backend_and_actual_parser_failures_have_different_gates(self):
        with repository(self.sources('clean')) as repo:
            manifest, digest = repo.manifest(self.tools)
            before = snapshot(repo.parent)
            clean = repo.cli(manifest, digest)
            assert_public_record(self, clean)
            self.assertTrue(clean['complete'])
            self.assertEqual(clean['exit_code'], 0)
            self.assertEqual(clean['findings'], [])
            self.assertEqual(clean['data']['counts']['executed'], 2)
            self.assertEqual(snapshot(repo.parent), before)
        with repository({'src/broken.cs': b'class Broken { void Run( {',
                         'src/broken.go': b'package broken; func Run( {'}) as repo:
            manifest, digest = repo.manifest(self.tools)
            before = snapshot(repo.parent)
            failed = repo.cli(manifest, digest)
            assert_public_record(self, failed)
            self.assertFalse(failed['complete'])
            self.assertEqual(failed['exit_code'], 2)
            self.assertEqual(failed['findings'], [])
            self.assertEqual(failed['data']['counts']['incomplete'], 2)
            self.assertIn('ADAPTER_INCOMPLETE', {item['code'] for item in failed['errors']})
            self.assertEqual(snapshot(repo.parent), before)


if __name__ == '__main__':
    unittest.main()
