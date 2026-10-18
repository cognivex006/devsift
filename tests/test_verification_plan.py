"""Actual immutable Git measurement and adversarial external-evidence records."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from devsift.change_budget import BudgetLimits, ChangeEstimate, ChangePlan
from devsift.verification_plan import (
    VerificationError, DiagnosticRecord, RegressionRecord, RollbackRecord,
    GitMeasurement, compare_verification, load_record, verify_revision_pair,
)


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.file = self.root / "sample.py"
        self.file.write_bytes(b"old\nkeep\n")
        self.before = self.commit()
        self.file.write_bytes(b"new\nkeep\nadded\n")
        self.after = self.commit()
        self.plan = ChangePlan(("case-1",), "MODIFIED_PREEXISTING", ChangeEstimate(),
                               False, "low", "bounded")
        self.limits = BudgetLimits(1, 2, 1)

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.root), *args], check=True,
                                capture_output=True, stdin=subprocess.DEVNULL)
        return result.stdout.decode().strip()

    def commit(self):
        self.git("add", "--", ".")
        self.git("commit", "--quiet", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def records(self, measurement):
        scope = measurement.scope_digest
        before = DiagnosticRecord("case-1", self.before, scope, "fixture", "1", True,
                                  (("HC001", "a" * 64), ("SEC001", "b" * 64)))
        after = DiagnosticRecord("case-1", self.after, scope, "fixture", "1", True,
                                 (("SEC001", "b" * 64), ("HC002", "c" * 64)))
        regression = RegressionRecord("case-1", self.before, self.after, scope, "pass")
        rollback = RollbackRecord("case-1", self.before, self.after, scope, "restore_before_commit")
        return before, after, regression, rollback

    def measure(self):
        return verify_revision_pair(self.root, self.before, self.after, ("sample.py",))

    def compare(self, measurement, records=None):
        return compare_verification(self.plan, self.limits, measurement,
                                    *(records or self.records(measurement)), repo_root=self.root)

    def test_actual_counts_replace_estimates_but_external_pass_is_not_proof(self):
        measured = self.measure()
        self.assertEqual((measured.files, measured.added_lines, measured.removed_lines), (1, 2, 1))
        result = self.compare(measured)
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(result.counts_basis, "verified_git_diff")
        self.assertEqual(result.budget.status, "bounded_plan_review")
        self.assertTrue(result.verification_pending)
        self.assertFalse(result.write_authorized)
        self.assertFalse(result.execution_authorized)
        self.assertEqual(result.added, (("HC002", "c" * 64),))
        self.assertEqual(result.removed, (("HC001", "a" * 64),))
        self.assertEqual(result.persisting, (("SEC001", "b" * 64),))
        self.assertIn("independent_diagnostic_capture_required", result.reasons)
        self.assertIn("independent_regression_capture_required", result.reasons)

    def test_unknown_incomplete_and_missing_records_never_promote(self):
        measurement = self.measure()
        records = list(self.records(measurement))
        records[0] = replace(records[0], complete=False)
        result = self.compare(measurement, records)
        self.assertIn("diagnostic_analysis_incomplete", result.reasons)
        self.assertEqual(result.added, ())
        for position in range(4):
            missing = list(self.records(measurement))
            missing[position] = None
            self.assertEqual(self.compare(measurement, missing).status, "incomplete")
        result = compare_verification(self.plan, self.limits, None, *self.records(measurement), repo_root=self.root)
        self.assertEqual(result.counts_basis, "declared_estimate")
        self.assertEqual(result.budget.status, "incomplete")

    def test_case_sha_scope_analyzer_and_rollback_mismatches_reject(self):
        measurement = self.measure()
        originals = self.records(measurement)
        mutations = [(0, "case_id", "other-case"), (0, "source_sha", self.after),
                     (1, "scope_digest", "0" * 64), (1, "analyzer_id", "other"),
                     (1, "analyzer_version", "2"), (2, "before_sha", self.after),
                     (3, "before_sha", self.after), (3, "after_sha", self.before)]
        for index, key, value in mutations:
            records = list(originals)
            records[index] = replace(records[index], **{key: value})
            with self.subTest(index=index, key=key), self.assertRaises(VerificationError):
                self.compare(measurement, records)

    def test_entire_diff_scope_no_hidden_files_and_exact_commit_inputs(self):
        for before, after, paths in [("HEAD~1", self.after, ("sample.py",)),
                                      (self.before, self.after, ("other.py",)),
                                      (self.before, self.after, ("../sample.py",))]:
            with self.assertRaises(VerificationError):
                verify_revision_pair(self.root, before, after, paths)
        (self.root / "extra.py").write_text("extra\n", encoding="utf-8")
        third = self.commit()
        with self.assertRaises(VerificationError):
            verify_revision_pair(self.root, self.before, third, ("sample.py",))

    def test_no_writes_working_tree_ignored_and_git_config_guard(self):
        self.file.write_text("dirty working source must not be measured\n", encoding="utf-8")
        def snapshot():
            return {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.root.rglob("*") if p.is_file()}
        before = snapshot()
        measurement = self.measure()
        self.compare(measurement)
        self.assertEqual(snapshot(), before)
        self.git("config", "remote.origin.promisor", "true")
        with self.assertRaises(VerificationError):
            self.measure()

    def test_strict_wire_no_forged_verified_or_passed_and_fresh_outputs(self):
        measurement = self.measure()
        for record in self.records(measurement):
            wire = record.to_dict()
            self.assertEqual(load_record(json.dumps(wire)), record)
            for key in ("sourceVerified", "passed", "write_authorized"):
                with self.assertRaises(VerificationError):
                    load_record(json.dumps({**wire, key: True}))
        for text in ('{"kind":"regression","kind":"diagnostic"}', '{"x":NaN}',
                     '[]', '{', '"' + "x" * 300000 + '"'):
            with self.assertRaises(VerificationError):
                load_record(text)
        records = self.records(measurement)
        with self.assertRaises(VerificationError):
            replace(records[0], complete=1)
        with self.assertRaises(VerificationError):
            replace(records[0], findings=(("HC001", "a" * 64),) * 2)
        with self.assertRaises(VerificationError):
            replace(records[2], status=True)
        with self.assertRaises(VerificationError):
            replace(records[3], action="run arbitrary rollback hook")
        result = self.compare(measurement)
        output = result.to_dict()
        output["reasons"].clear()
        output["budget"]["reasons"].append("foreign")
        self.assertTrue(result.reasons)
        self.assertNotIn("foreign", result.budget.reasons)
        with self.assertRaises(FrozenInstanceError):
            measurement.files = 999

    def test_measured_large_change_requires_separate_approval_and_unknown_risk_stays(self):
        measurement = self.measure()
        result = compare_verification(self.plan, BudgetLimits(0, 0, 0), measurement,
                                      *self.records(measurement), repo_root=self.root)
        self.assertTrue(result.budget.separate_approval_required)
        uncertain = replace(self.plan, risk_if_changed="unknown", consumer_impact="unknown")
        result = compare_verification(uncertain, self.limits, measurement,
                                      *self.records(measurement), repo_root=self.root)
        self.assertEqual(result.budget.status, "incomplete")
        self.assertIn("change_risk_unknown", result.budget.reasons)

    def test_measurement_cannot_be_restored_or_reused_for_other_root_or_stale_repo(self):
        measurement = self.measure()
        with self.assertRaises(VerificationError):
            GitMeasurement(**measurement.to_dict())
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory) / "other"
            shutil.copytree(self.root, other)
            with self.assertRaises(VerificationError):
                compare_verification(self.plan, self.limits, measurement,
                                     *self.records(measurement), repo_root=other)
        # Effective config changes after capture invalidate it on consumption.
        self.git("config", "remote.origin.promisor", "true")
        with self.assertRaises(VerificationError):
            self.compare(measurement)

    def test_binary_symlink_and_private_paths_are_rejected(self):
        self.file.write_bytes(b"binary\x00secret\n")
        binary = self.commit()
        with self.assertRaises(VerificationError):
            verify_revision_pair(self.root, self.before, binary, ("sample.py",))
        private = "ghp_" + "Ab8" * 12
        with self.assertRaises(VerificationError) as error:
            verify_revision_pair(self.root, self.before, self.after, (private,))
        self.assertNotIn(private, str(error.exception))
        # Actual Git symlink entry: no host symlink privilege is required.
        blob = self.git("hash-object", "-w", "--stdin")
        self.git("update-index", "--add", "--cacheinfo", "120000," + blob + ",link.py")
        self.git("commit", "--quiet", "-m", "symlink fixture")
        symlink = self.git("rev-parse", "HEAD")
        with self.assertRaises(VerificationError):
            verify_revision_pair(self.root, binary, symlink, ("link.py",))

    def test_lf_counts_and_rename_paths_are_actual_not_declared(self):
        self.file.write_bytes("first\u2028still-first\r\nsecond\r\n".encode("utf-8"))
        old = self.commit()
        self.file.write_bytes("first\u2028still-first\r\nnew-second\r\nthird\r\n".encode("utf-8"))
        new = self.commit()
        measured = verify_revision_pair(self.root, old, new, ("sample.py",))
        self.assertEqual((measured.files, measured.added_lines, measured.removed_lines), (1, 2, 1))
        self.file.rename(self.root / "renamed.py")
        renamed = self.commit()
        measured = verify_revision_pair(self.root, new, renamed, ("sample.py", "renamed.py"))
        self.assertEqual((measured.files, measured.added_lines, measured.removed_lines), (2, 3, 3))

    def test_legacy_critical_review_is_untouched_and_no_consumer_command_runs(self):
        from devsift.policy import decide
        measurement = self.measure()
        gate = decide("SEC001", "LEGACY_UNCHANGED", source_verified=True)
        result = self.compare(measurement)
        self.assertTrue(result.budget.legacy_advisory)
        self.assertEqual(gate.enforcement, "security_review")
        self.assertEqual(decide("SEC001", "LEGACY_UNCHANGED", source_verified=True), gate)
        hostile = self.records(measurement)[3].to_dict()
        hostile["action"] = "echo overwrite-source"
        with self.assertRaises(VerificationError):
            load_record(json.dumps(hostile))


if __name__ == "__main__":
    unittest.main()
