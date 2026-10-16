import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.baseline import BaselineSnapshot, capture_entry
from devsift.evidence import Region, SourceEvidence, verify_source
from devsift.git_changes import BaselineObservation
from devsift.report_decisions import AssessmentError, assess_finding
from devsift.suppressions import Suppression


class ReportDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.base = self.commit('legacy_call()\nother_call()\n')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, text):
        (self.root / 'code.py').write_bytes(text.encode())
        self.git('add', 'code.py')
        self.git('commit', '-qm', 'fixture')
        return self.git('rev-parse', 'HEAD')

    def source(self, sha, line=1):
        text = self.git('show', sha + ':code.py').splitlines()[line - 1]
        return verify_source(self.root, 'fixture/repo', sha, 'code.py', Region(line, 1, line, len(text)+1))

    def assess(self, head=None, source=None, **kwargs):
        head = head or self.base
        return assess_finding(self.root, self.base, head, 'HC001', source or self.source(head),
                              rule_version='1', **kwargs)

    def snapshot(self):
        entry = capture_entry(self.root, 'HC001', '1', self.source(self.base))
        return BaselineSnapshot('fixture/repo', self.base, 'fixture@1', 'catalog@1', (entry,))

    def test_legacy_baseline_match_is_advisory_without_claiming_low_business_risk(self):
        result = self.assess(snapshot=self.snapshot(), tool_version='fixture@1', rule_catalog_version='catalog@1')
        self.assertEqual(result.decision.enforcement, 'advisory')
        wire = result.to_dict()
        self.assertEqual(wire['baseline_status'], 'matched')
        self.assertEqual(wire['lifecycle_class'], 'LEGACY_UNCHANGED')
        self.assertEqual(wire['impact_if_unchanged']['level'], 'unknown')
        self.assertEqual(wire['risk_if_changed']['level'], 'unknown')
        self.assertFalse(wire['automatic_fix'])

    def test_changed_file_does_not_make_untouched_region_new(self):
        head = self.commit('legacy_call()\nnew_other_call()\n')
        result = self.assess(head)
        self.assertEqual(result.decision.lifecycle_class, 'MODIFIED_PREEXISTING')
        self.assertEqual(result.decision.enforcement, 'advisory')

    def test_snapshot_absence_never_proves_rule_absence(self):
        head = self.commit('replacement_call()\nother_call()\n')
        empty = BaselineSnapshot('fixture/repo', self.base, 'fixture@1', 'catalog@1', ())
        result = self.assess(head, snapshot=empty, tool_version='fixture@1', rule_catalog_version='catalog@1')
        self.assertEqual(result.decision.lifecycle_class, 'UNKNOWN')
        self.assertEqual(result.decision.enforcement, 'incomplete')
        self.assertEqual(result.to_dict()['baseline_status'], 'not_recorded')

    def test_explicit_complete_base_analysis_proves_introduced(self):
        head = self.commit('replacement_call()\nother_call()\n')
        observation = BaselineObservation('HC001', self.base, 'code.py', (), True, 'fixture@1')
        result = self.assess(head, observation=observation)
        self.assertEqual(result.decision.lifecycle_class, 'MODIFIED_INTRODUCED')
        self.assertEqual(result.decision.enforcement, 'block')

    def test_mismatched_baseline_versions_are_rejected_without_input_leak(self):
        for kwargs in ({}, {'tool_version':'private-tool-value', 'rule_catalog_version':'catalog@1'}):
            with self.assertRaisesRegex(AssessmentError, '^Invalid or unavailable decision evidence$') as error:
                self.assess(snapshot=self.snapshot(), **kwargs)
            self.assertNotIn('private-tool-value', str(error.exception))

    def test_unknown_source_cannot_be_suppressed(self):
        result = self.assess(source=SourceEvidence())
        self.assertEqual(result.decision.enforcement, 'incomplete')
        self.assertFalse(result.to_dict()['suppressed'])

    def test_scoped_unexpired_waiver_cannot_turn_unknown_into_pass(self):
        fingerprint = self.assess().proof.fingerprint
        waiver = Suppression('HC001', fingerprint, 'owner', 'reason', 'ISSUE-1', '2099-01-01T00:00:00Z')
        now = datetime(2026, 10, 16, tzinfo=timezone.utc)
        result = self.assess(suppressions=(waiver,), as_of=now)
        self.assertTrue(result.to_dict()['suppressed'])
        self.assertEqual(result.decision.enforcement, 'advisory')
        unknown = self.assess(source=SourceEvidence(), suppressions=(waiver,), as_of=now)
        self.assertEqual(unknown.decision.enforcement, 'incomplete')
        with self.assertRaises(AssessmentError):
            self.assess(suppressions=(waiver,), as_of=datetime(2100, 1, 1, tzinfo=timezone.utc))

    def test_critical_legacy_security_remains_independent_review(self):
        result = assess_finding(self.root, self.base, self.base, 'SEC003', self.source(self.base), rule_version='1')
        self.assertEqual(result.decision.enforcement, 'security_review')
        self.assertTrue(result.decision.security_escalation)

    def test_read_only_and_fresh_serialized_outputs(self):
        before = {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = self.assess()
        wire = result.to_dict(); wire['impact_if_unchanged']['level'] = 'low'
        self.assertEqual(result.to_dict()['impact_if_unchanged']['level'], 'unknown')
        after = {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
