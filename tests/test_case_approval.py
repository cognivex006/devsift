"""T047 explicit planning approval with real Git/current bytes and zero writes."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.case_approval import (ApprovalDecision, CaseApprovalError, ImplementationApproval,
                                  evaluate_case_approval)
from devsift.case_prompts import compose_case_prompt
from devsift.evidence import Region, verify_source
from devsift.output import result
from devsift.report_model import assemble_report

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


class CaseApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='devsift-approval-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'consumer'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'core.hooksPath', str(Path(self.temp.name) / 'no-hooks'))
        self.source = b'const opaque = "approvalFixturePrivateValue";\nfetch("https://api.example.invalid");\n'
        (self.root / 'client.ts').write_bytes(self.source)
        self.git('add', 'client.ts')
        self.commit()
        self.report = self.make_report()
        self.prompt = compose_case_prompt(self.report, 'CASE-1', mode='implement', repo_root=self.root)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True, timeout=20).stdout.decode().strip()

    def commit(self):
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'commit.gpgSign=false', 'commit', '-qm', 'synthetic fixture')
        self.sha = self.git('rev-parse', 'HEAD')

    def make_report(self, *, masked=False, unresolved=False):
        line = 1 if masked else 2
        text = self.source.decode().splitlines()[line - 1]
        evidence = verify_source(self.root, 'local', self.sha, 'client.ts', Region(line, 1, line, len(text) + 1), sensitive=masked)
        source = evidence.to_dict()
        if unresolved:
            source['location']['source_sha'] = 'a' * 40
        finding = {'case_id': 'CASE-1', 'rule_id': 'LOG001' if masked else 'HC001', 'source': source,
                   'path': 'client.ts', 'message': 'fixture', 'severity': 'Error', 'lifecycle_class': 'NEW',
                   'enforcement': 'block', 'security_escalation': False}
        return assemble_report(result('scan', complete=True, findings=[finding], enforced_count=1), repo_root=self.root)

    def approval(self, prompt=None, **changes):
        prompt = prompt or self.prompt
        payload = prompt.to_dict()
        fields = dict(case_id='CASE-1', source_sha=payload['source_sha'], fingerprint=payload['fingerprint'],
                      prompt_digest=prompt.digest, mode='implement', approved=True, actor='fixture-operator',
                      issued_at=(NOW - timedelta(minutes=1)).isoformat(), expires_at=(NOW + timedelta(minutes=10)).isoformat())
        fields.update(changes)
        return ImplementationApproval.from_dict(fields)

    def evaluate(self, approval=None, *, report=None, prompt=None):
        return evaluate_case_approval(report or self.report, 'CASE-1', prompt=prompt or self.prompt,
                                      repo_root=self.root, approval=approval, now=NOW)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): None if p.is_dir() else p.read_bytes() for p in self.root.rglob('*')}

    def assert_no_execution(self, payload):
        self.assertFalse(payload['execution_authorized'])
        self.assertFalse(payload['writes_authorized'])
        self.assertFalse(payload['automatic_fix'])

    def test_exact_explicit_approval_binds_manual_planning_but_unknown_effects_require_review(self):
        decision = self.evaluate(self.approval()).to_dict()
        self.assertEqual(decision['status'], 'review_required')
        self.assertEqual(decision['reason'], 'UNKNOWN_EFFECTS_REVIEW_REQUIRED')
        self.assertTrue(decision['approval_matched'])
        self.assertTrue(decision['manual_planning_allowed'])
        self.assertEqual(decision['binding'], {'case_id': 'CASE-1', 'source_sha': self.sha,
                                               'fingerprint': self.prompt.to_dict()['fingerprint'], 'prompt_digest': self.prompt.digest})
        self.assertEqual(decision['handoff']['scope'], 'manual_case_planning_only')
        self.assertEqual(set(decision['effects'].values()), {'unknown'})
        self.assert_no_execution(decision)

    def test_missing_approval_never_discovers_even_matching_operator_json_in_project(self):
        approval = self.approval()
        (self.root / 'approval.json').write_text(json.dumps(vars(approval)), encoding='utf-8')
        before = self.snapshot()
        payload = self.evaluate().to_dict()
        self.assertEqual(payload['reason'], 'EXPLICIT_APPROVAL_REQUIRED')
        self.assertFalse(payload['manual_planning_allowed'])
        self.assert_no_execution(payload)
        self.assertEqual(self.snapshot(), before)

    def test_matching_case_id_review_or_decline_is_not_implement_approval(self):
        for approval in [self.approval(mode='review'), self.approval(approved=False)]:
            payload = self.evaluate(approval).to_dict()
            self.assertEqual(payload['status'], 'denied')
            self.assertEqual(payload['reason'], 'IMPLEMENT_APPROVAL_REQUIRED')
            self.assertFalse(payload['manual_planning_allowed'])
            self.assert_no_execution(payload)

    def test_every_identity_component_must_match_exactly(self):
        for changes in [dict(case_id='OTHER-CASE'), dict(source_sha='a' * 40),
                        dict(fingerprint='b' * 64), dict(prompt_digest='c' * 64)]:
            with self.subTest(field=next(iter(changes))):
                payload = self.evaluate(self.approval(**changes)).to_dict()
                self.assertEqual(payload['reason'], 'APPROVAL_BINDING_MISMATCH')
                self.assertFalse(payload['approval_matched'])
                self.assert_no_execution(payload)

    def test_review_prompt_and_different_prompt_context_are_rejected(self):
        review = compose_case_prompt(self.report, 'CASE-1', mode='review', repo_root=self.root)
        self.assertEqual(self.evaluate(self.approval(), prompt=review).to_dict()['reason'], 'IMPLEMENT_PROMPT_REQUIRED')
        different = compose_case_prompt(self.make_report(masked=True), 'CASE-1', mode='implement', repo_root=self.root)
        self.assertEqual(self.evaluate(self.approval(), prompt=different).to_dict()['reason'], 'PROMPT_BINDING_MISMATCH')

    def test_expired_and_not_yet_issued_approvals_cannot_match(self):
        for approval in [self.approval(issued_at=(NOW - timedelta(hours=1)).isoformat(), expires_at=NOW.isoformat()),
                         self.approval(issued_at=(NOW + timedelta(minutes=1)).isoformat())]:
            payload = self.evaluate(approval).to_dict()
            self.assertEqual(payload['reason'], 'APPROVAL_NOT_CURRENT')
            self.assertFalse(payload['manual_planning_allowed'])

    def test_malformed_unknown_fields_naive_times_and_secret_inputs_fail_constantly(self):
        base = vars(self.approval()).copy()
        bad = [dict(base, credential='PRIVATE-CREDENTIAL'), dict(base, issued_at='2026-10-16T12:00:00'),
               dict(base, expires_at='bad-PRIVATE-TIME'), dict(base, approved=1), dict(base, actor='PRIVATE\nACTOR'),
               dict(base, source_sha='PRIVATE-SHA'), {key: value for key, value in base.items() if key != 'approved'}]
        for value in bad:
            with self.subTest(keys=list(value)):
                with self.assertRaises(CaseApprovalError) as error:
                    ImplementationApproval.from_dict(value)
                self.assertEqual(str(error.exception), 'Invalid or unavailable case approval input')
        with self.assertRaises(CaseApprovalError):
            self.evaluate(base)  # explicit conversion required, never arbitrary dict grants
        with self.assertRaises(CaseApprovalError):
            evaluate_case_approval(self.report.to_dict(), 'CASE-1', prompt=self.prompt, repo_root=self.root)

    def test_dirty_selected_working_bytes_deny_without_changing_source_or_git(self):
        (self.root / 'client.ts').write_bytes(self.source + b'// dirty\n')
        before = self.snapshot()
        payload = self.evaluate(self.approval()).to_dict()
        self.assertEqual(payload['reason'], 'WORKING_TREE_MISMATCH')
        self.assertEqual(payload['source']['status'], 'SOURCE_UNRESOLVED')
        self.assertIsNone(payload['source']['before'])
        self.assert_no_execution(payload)
        self.assertEqual(self.snapshot(), before)

    def test_dirty_staged_index_denies_even_when_working_bytes_match_commit(self):
        (self.root / 'client.ts').write_bytes(self.source + b'// staged\n')
        self.git('add', 'client.ts')
        (self.root / 'client.ts').write_bytes(self.source)
        before = self.snapshot()
        self.assertEqual(self.evaluate(self.approval()).to_dict()['reason'], 'INDEX_MISMATCH')
        self.assertEqual(self.snapshot(), before)

    def test_untracked_unrelated_file_is_not_global_gate_but_selected_untracked_is_denied(self):
        (self.root / 'unrelated.txt').write_text('unrelated untracked fixture', encoding='utf-8')
        self.assertTrue(self.evaluate(self.approval()).to_dict()['manual_planning_allowed'])
        self.git('rm', '--cached', '--', 'client.ts')
        before = self.snapshot()
        self.assertEqual(self.evaluate(self.approval()).to_dict()['reason'], 'INDEX_MISMATCH')
        self.assertEqual(self.snapshot(), before)

    def test_moving_head_rejects_old_approval_even_if_selected_file_is_unchanged(self):
        (self.root / 'other.txt').write_text('new commit', encoding='utf-8')
        self.git('add', 'other.txt')
        self.commit()
        before = self.snapshot()
        self.assertEqual(self.evaluate(self.approval()).to_dict()['reason'], 'HEAD_MISMATCH')
        self.assertEqual(self.snapshot(), before)

    def test_unresolved_source_cannot_accept_a_formally_valid_binding(self):
        report = self.make_report(unresolved=True)
        prompt = compose_case_prompt(report, 'CASE-1', mode='implement', repo_root=self.root)
        payload = self.evaluate(self.approval(), report=report, prompt=prompt).to_dict()
        self.assertEqual(payload['reason'], 'SOURCE_UNRESOLVED')
        self.assertIsNone(payload['binding'])
        self.assertIsNone(payload['source']['location'])

    def test_real_selected_symlink_cannot_inherit_regular_committed_file_proof(self):
        target = Path(self.temp.name) / 'outside.ts'
        target.write_bytes(self.source)
        selected = self.root / 'client.ts'
        selected.unlink()
        try:
            selected.symlink_to(target)
        except OSError:
            self.skipTest('Host does not permit creating an actual file symlink')
        # A byte-for-byte matching destination is still an unsafe selected path.
        payload = self.evaluate(self.approval()).to_dict()
        self.assertEqual(payload['reason'], 'UNSAFE_SOURCE')
        self.assertFalse(payload['manual_planning_allowed'])

    def test_immutable_fresh_decision_no_writes_and_sensitive_masks_survive(self):
        report = self.make_report(masked=True)
        prompt = compose_case_prompt(report, 'CASE-1', mode='implement', repo_root=self.root)
        approval = self.approval(prompt, actor='Bearer fixtureActorSensitiveValue')
        before = self.snapshot()
        decision = self.evaluate(approval, report=report, prompt=prompt)
        payload = decision.to_dict()
        self.assertTrue(payload['manual_planning_allowed'])
        self.assertEqual(payload['source']['before'], '[REDACTED]')
        self.assertNotIn('approvalFixturePrivateValue', json.dumps(payload))
        self.assertNotIn('fixtureActorSensitiveValue', json.dumps(payload) + repr(approval))
        payload['writes_authorized'] = True
        payload['handoff']['scope'] = 'arbitrary-source-writes'
        self.assertFalse(decision.to_dict()['writes_authorized'])
        with self.assertRaises(FrozenInstanceError):
            decision.status = 'approved'
        with self.assertRaises(FrozenInstanceError):
            approval.approved = False
        with self.assertRaises(CaseApprovalError):
            ApprovalDecision('CASE-1', 'approved', '{}')
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
