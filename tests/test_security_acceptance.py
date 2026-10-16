"""T069: real builtin/Git gate observations across reports and artifact assurance.

No successful native provider or consumer source execution is simulated.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from devsift.native_host import ToolDefinition, file_digest
from devsift.process_runner import ProcessSpec
from devsift.project_policy import discover_policy
from devsift.report_export import render_json
from devsift.report_model import assemble_report
from devsift.scanner import scan
from devsift.security_adapter import SecurityAdapter
from devsift.security_gate import SecurityGateResult, run_security_gate
from tools.check_artifact_security import inspect_archive

PAT = 'gh' + 'p_' + 'Z9x' * 12  # Synthetic shape, never a live credential check.


def snapshot(root):
    return {p.relative_to(root).as_posix(): None if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*')}


class SecurityReleaseAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='devsift-security-acceptance-')
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / 'consumer'
        (self.root / 'src').mkdir(parents=True)
        self.marker = self.parent / 'CONSUMER_OR_PROVIDER_EXECUTED'
        self.settings = self.root / 'src/settings.py'
        self.safe = self.root / 'src/safe.py'
        self.safe.write_text('value = 1\n', encoding='utf-8')
        self.settings.write_text('value = 1\n', encoding='utf-8')
        (self.root / 'AGENTS.md').write_text('Read-only review; no tasks, source execution or releases.\n')
        for args in (('init', '-q'), ('config', 'core.autocrlf', 'false'),
                     ('config', 'core.hooksPath', str(self.parent / 'no-hooks')),
                     ('config', 'user.name', 'Fixture'), ('config', 'user.email', 'fixture@example.invalid')):
            self.git(*args)
        self.base = self.commit()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, timeout=30).stdout.decode().strip()

    def commit(self):
        self.git('add', '--all')
        self.git('-c', 'commit.gpgSign=false', 'commit', '-qm', 'acceptance fixture')
        return self.git('rev-parse', 'HEAD')

    def credential(self):
        self.settings.write_text("credential = '" + PAT + "'\nfrom pathlib import Path\nPath(" + repr(str(self.marker))
                                 + ").write_text('consumer source executed')\n", encoding='utf-8')
        return self.commit()

    def assert_no_authority(self, gate):
        wire = gate.to_dict()
        for key in ('write_authorized', 'execution_authorized', 'rotation_authorized', 'publication_authorized'):
            self.assertIs(wire[key], False)
            self.assertIs(getattr(gate, key), False)
        self.assertIs(wire['quality_gate_complete'], False)
        for key in ('credential_liveness', 'exploitability', 'business_impact'):
            self.assertEqual(wire[key], 'unknown')
        self.assertNotIn(PAT, json.dumps(wire))
        self.assertNotIn(str(self.parent), json.dumps(wire))
        self.assertFalse(self.marker.exists())
        return wire

    def gate(self, *, paths=('src/settings.py',), **kwargs):
        before = snapshot(self.parent)
        gate = run_security_gate(self.root, paths=paths, **kwargs)
        self.assertEqual(snapshot(self.parent), before)
        self.assert_no_authority(gate)
        return gate

    def test_quality_report_incomplete_and_unavailable_provider_cannot_hide_actual_critical(self):
        sha = self.credential()
        policy_file = self.root / '.devsift/policy.json'
        policy_file.parent.mkdir()
        policy_file.write_text(json.dumps({'quality_gate': {'block_on': []},
                                          'rules': {'HC002': {'severity': 'Suggestion'}}}), encoding='utf-8')
        before_config = snapshot(self.parent)
        resolution = discover_policy(self.root)
        self.assertTrue(resolution.complete)
        self.assertEqual(resolution.reason, 'PROJECT_POLICY')
        self.assertEqual(snapshot(self.parent), before_config)
        policy = resolution.policy()
        adapter = SecurityAdapter(repo_root=self.root, source_sha=sha)
        before = snapshot(self.parent)
        quality = scan(self.root, ('src/settings.py',), adapters=(adapter,), policy=policy)
        report = assemble_report(quality, repo_root=self.root, policy=policy)
        saved_report = json.loads(render_json(report))
        self.assertFalse(saved_report['complete'])
        self.assertEqual(saved_report['exit_code'], 2)
        self.assertEqual(saved_report['cases'][0]['lifecycle_class'], 'UNKNOWN')
        self.assertNotIn(PAT, json.dumps(saved_report))
        self.assertEqual(snapshot(self.parent), before)
        gate = self.gate(policy=policy)
        self.assertTrue(gate.complete)
        self.assertEqual(gate.status, 'security_review')
        self.assertTrue(gate.requires_security_review)
        findings = gate.to_dict()['findings']
        self.assertEqual({f['rule_id'] for f in findings}, {'HC002'})
        self.assertTrue(all(f['catalog_severity'] == 'Critical' and f['resolved_severity'] == 'Suggestion'
                            and f['source']['status'] == 'VERIFIED' and f['source']['before'] == '[REDACTED]'
                            and f['lifecycle_class'] == 'UNKNOWN' and f['quality_enforcement'] == 'incomplete'
                            and f['requires_security_review'] for f in findings))
        helper = self.parent / 'trusted-provider-fixture.py'
        helper.write_text('from pathlib import Path\nPath(' + repr(str(self.marker)) + ').write_text("bad")\n')
        unavailable = ToolDefinition('acceptance-missing-go', '1', ('go',),
            ProcessSpec(str(Path(sys.executable).resolve()), ('-I', '-B', str(helper))),
            file_digest(sys.executable), ((str(self.parent / 'missing-pin'), '0' * 64),))
        partial = self.gate(policy=policy, tools=(unavailable,))
        self.assertFalse(partial.complete)
        self.assertEqual(partial.status, 'incomplete')
        self.assertIn('CONFIGURED_PROVIDER_UNAVAILABLE', partial.reasons)
        self.assertTrue(partial.requires_security_review)
        self.assertTrue(partial.to_dict()['findings'][0]['requires_security_review'])

    def test_stale_saved_success_and_approved_waiver_data_do_not_replace_fresh_source_gate(self):
        prior = self.gate()
        self.assertTrue(prior.complete)
        self.assertFalse(prior.requires_security_review)
        forged = prior.to_dict()
        forged.update(approved=True, waiver=True, publication_authorized=True, write_authorized=True)
        (self.root / '.devsift').mkdir()
        saved = self.root / '.devsift/report.json'
        saved.write_text(json.dumps(forged), encoding='utf-8')
        new_sha = self.credential()
        before = snapshot(self.parent)
        fresh = self.gate()
        self.assertNotEqual(prior.source_sha, new_sha)
        self.assertEqual(fresh.source_sha, new_sha)
        self.assertTrue(fresh.requires_security_review)
        self.assertEqual(fresh.status, 'security_review')
        self.assertFalse(json.loads(saved.read_text())['requires_security_review'])
        with self.assertRaises(TypeError):
            run_security_gate(self.root, paths=('src/settings.py',), saved_report=forged)
        with self.assertRaises(ValueError):
            SecurityGateResult(**forged)
        invalid = self.gate(policy={'waiver': True, 'approved': True})
        self.assertFalse(invalid.complete)
        self.assertEqual(invalid.status, 'incomplete')
        self.assertEqual(invalid.reasons, ('SECURITY_GATE_UNAVAILABLE_OR_INVALID',))
        self.assertEqual(snapshot(self.parent), before)
        self.assertTrue(prior.complete)  # A captured old result is not a current observation.

    def test_missing_and_changed_source_remain_observable_while_verified_critical_survives(self):
        sha = self.credential()
        for state in ('missing', 'dirty'):
            if state == 'missing':
                paths = ('src/settings.py', 'src/missing.py')
            else:
                self.safe.write_text('value = 2  # not committed\n')
                paths = ('src/settings.py', 'src/safe.py')
            with self.subTest(state=state):
                result = self.gate(paths=paths)
                self.assertFalse(result.complete)
                self.assertEqual(result.status, 'incomplete')
                self.assertIn('SNAPSHOT_UNVERIFIED', result.reasons)
                self.assertTrue(result.requires_security_review)
                critical = [f for f in result.to_dict()['findings'] if f['requires_security_review']]
                self.assertTrue(critical)
                self.assertTrue(all(f['source']['status'] == 'VERIFIED' and f['source']['location']['source_sha'] == sha
                                    and f['catalog_severity'] == 'Critical' for f in critical))

    def test_scoped_security_result_and_artifact_confidentiality_are_independent_never_publication(self):
        gate = self.gate(paths=('src/safe.py',))
        self.assertTrue(gate.complete)
        self.assertEqual(gate.status, 'no_detected_critical_in_declared_scope')
        archive = self.parent / 'declared.zip'
        def prepare(text):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as bundle:
                bundle.writestr('devsift/allowed_source.py', text)
            archive.write_bytes(stream.getvalue())
            return hashlib.sha256(stream.getvalue()).hexdigest()
        clean_digest = prepare('value = 1\n')
        before = snapshot(self.parent)
        clean = inspect_archive(archive, expected_sha256=clean_digest)
        self.assertTrue(clean['complete'])
        self.assertEqual(clean['status'], 'no_detected_shapes_in_declared_archive')
        self.assertEqual(snapshot(self.parent), before)
        secret_digest = prepare("credential = '" + PAT + "'\n")
        before = snapshot(self.parent)
        wrong = inspect_archive(archive, expected_sha256=clean_digest)
        reviewed = inspect_archive(archive, expected_sha256=secret_digest)
        self.assertEqual(wrong['issues'], ['ARCHIVE_DIGEST_MISMATCH'])
        self.assertFalse(wrong['complete'])
        self.assertFalse(reviewed['complete'])
        self.assertEqual(reviewed['status'], 'review_required')
        self.assertIn('RECOGNIZED_SENSITIVE_SHAPE', reviewed['issues'])
        for record in (clean, wrong, reviewed):
            self.assertIs(record['release_review_required'], True)
            for key in ('publication_authorized', 'writes_authorized', 'execution_authorized'):
                self.assertIs(record[key], False)
            self.assertNotIn(PAT, json.dumps(record))
        self.assertEqual(snapshot(self.parent), before)
        self.assertTrue(self.gate(paths=('src/safe.py',)).complete)
        self.assert_no_authority(gate)


if __name__ == '__main__':
    unittest.main()
