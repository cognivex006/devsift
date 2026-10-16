"""Acceptance: real Git proof and declared success never authorize remediation."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from devsift.change_budget import BudgetError, BudgetLimits, ChangeEstimate, ChangePlan, assess_plan, load_plan
from devsift.policy import decide
from devsift.verification_plan import (
    GitMeasurement, VerificationError, compare_verification, load_record, verify_revision_pair,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "remediation"


def digest_files(root, paths=None):
    paths = paths if paths is not None else root.rglob("*")
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths if path.is_file()}


class RemediationDenialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        # Semantic behavior intentionally changes. An external "pass" must not
        # magically prove this arbitrary proposal preserves consumer behavior.
        self.source = self.root / "pricing.py"
        self.source.write_text("def price():\n    return 10\n", encoding="utf-8")
        self.before = self.commit()
        self.source.write_text("def price():\n    return 999\n", encoding="utf-8")
        self.after = self.commit()
        self.plan = ChangePlan(("case-1",), "MODIFIED_PREEXISTING", ChangeEstimate(1, 1, 1),
                               False, "low", "bounded")
        self.limits = BudgetLimits(1, 1, 1)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True).stdout.decode().strip()

    def commit(self):
        self.git("add", "--", ".")
        self.git("commit", "--quiet", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def evidence(self):
        proof = verify_revision_pair(self.root, self.before, self.after, ("pricing.py",))
        text = (FIXTURES / "declared-evidence.json").read_text(encoding="utf-8")
        wire = json.loads(text.replace("BEFORE", self.before).replace("AFTER", self.after)
                          .replace("SCOPE", proof.scope_digest))
        records = [load_record(json.dumps(wire[key])) for key in ("before", "after", "regression", "rollback")]
        return proof, records

    def compare(self, proof, records, plan=None):
        return compare_verification(plan or self.plan, self.limits, proof, *records,
                                    repo_root=self.root)

    def denied(self, result):
        self.assertFalse(result.write_authorized)
        self.assertFalse(result.execution_authorized)
        self.assertTrue(result.verification_pending)
        self.assertEqual(result.status, "incomplete")
        self.assertTrue(result.to_dict()["requires_case_authorization"])

    def test_real_changed_behavior_external_pass_and_removed_diagnostic_still_denied(self):
        snapshot = digest_files(self.root)
        proof, records = self.evidence()
        self.assertEqual((proof.files, proof.added_lines, proof.removed_lines), (1, 1, 1))
        result = self.compare(proof, records)
        self.denied(result)
        self.assertEqual(result.removed, (("HC001", "a" * 64),))
        self.assertEqual(result.to_dict()["diagnostics_basis"], "declared")
        self.assertEqual(result.to_dict()["regression_basis"], "declared")
        self.assertIn("independent_regression_capture_required", result.reasons)
        self.assertEqual(digest_files(self.root), snapshot)

    def test_missing_each_mandatory_evidence_and_incomplete_analysis(self):
        proof, records = self.evidence()
        for position in range(4):
            missing = list(records)
            missing[position] = None
            with self.subTest(position=position):
                self.denied(self.compare(proof, missing))
        for position in (0, 1):
            incomplete = list(records)
            incomplete[position] = replace(records[position], complete=False)
            result = self.compare(proof, incomplete)
            self.denied(result)
            self.assertEqual((result.added, result.removed, result.persisting), ((), (), ()))
        self.denied(self.compare(None, records))

    def test_bound_case_pair_scope_and_root_cannot_be_substituted(self):
        proof, records = self.evidence()
        attacks = [(0, {"case_id": "case-2"}), (0, {"source_sha": self.after}),
                   (1, {"scope_digest": "0" * 64}), (2, {"after_sha": self.before}),
                   (3, {"before_sha": self.after})]
        for index, update in attacks:
            hostile = list(records)
            hostile[index] = replace(hostile[index], **update)
            with self.subTest(update=update), self.assertRaises(VerificationError):
                self.compare(proof, hostile)
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory) / "other"
            shutil.copytree(self.root, other)
            with self.assertRaises(VerificationError):
                compare_verification(self.plan, self.limits, proof, *records, repo_root=other)

    def test_hostile_wire_proof_and_approval_claims_never_execute(self):
        proof, records = self.evidence()
        snapshot = digest_files(self.root)
        private = "ghp_" + "Ab8" * 12
        for key in ("approved", "passed", "sourceVerified", "execute", private):
            wire = {**records[2].to_dict(), key: True}
            with self.assertRaises(VerificationError) as error:
                load_record(json.dumps(wire))
            self.assertNotIn(private, str(error.exception))
        for key in ("approved", "approval_token", "write_authorized", "command"):
            with self.assertRaises(BudgetError):
                load_plan(json.dumps({**self.plan.to_dict(), key: "overwrite pricing.py"}))
        with self.assertRaises(VerificationError):
            GitMeasurement(**proof.to_dict())
        with self.assertRaises(VerificationError):
            self.compare(proof.to_dict(), records)
        with self.assertRaises(VerificationError):
            load_record('{"kind":"regression","kind":"rollback"}')
        self.assertEqual(digest_files(self.root), snapshot)

    def test_case_batch_refactor_and_unknowns_keep_edit_boundary(self):
        cases = json.loads((FIXTURES / "planning-cases.json").read_text(encoding="utf-8"))
        proof, records = self.evidence()
        for row in cases:
            plan = replace(self.plan, case_ids=row["cases"], lifecycle_class=row["lifecycle"],
                           risk_if_changed=row["risk"], consumer_impact=row["consumers"],
                           refactor=row["refactor"])
            budget = assess_plan(plan, self.limits)
            with self.subTest(row=row["name"]):
                self.assertEqual(budget.status, row["expected"])
                self.assertEqual(budget.separate_approval_required, row["separate"])
                self.assertFalse(budget.write_authorized)
                self.assertFalse(budget.execution_authorized)
                if len(plan.case_ids) == 1:
                    self.denied(self.compare(proof, records, plan))
                else:
                    with self.assertRaises(VerificationError):
                        self.compare(proof, records, plan)
        self.assertEqual(assess_plan(self.plan, BudgetLimits()).status, "incomplete")
        self.assertTrue(assess_plan(self.plan, BudgetLimits(0, 0, 0)).separate_approval_required)

    def test_critical_legacy_security_review_survives_declared_fix_claim(self):
        proof, records = self.evidence()
        gate = decide("SEC001", "LEGACY_UNCHANGED", source_verified=True)
        legacy = replace(self.plan, lifecycle_class="LEGACY_UNCHANGED")
        self.denied(self.compare(proof, records, legacy))
        self.assertEqual(gate.enforcement, "security_review")
        self.assertEqual(decide("SEC001", "LEGACY_UNCHANGED", source_verified=True), gate)

    def invoke(self, *args):
        launcher = "import runpy,sys;sys.path.insert(0," + repr(str(ROOT)) + ");runpy.run_module('devsift',run_name='__main__')"
        return subprocess.run([sys.executable, "-I", "-B", "-c", launcher, *args],
                              cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_actual_cli_read_only_and_pending_per_case_implement_guard(self):
        # The fixture shadows the package name and contains an executable hook;
        # neither target code nor hooks may execute during read-only CLI work.
        (self.root / "devsift.py").write_text("raise RuntimeError('target imported')\n", encoding="utf-8")
        (self.root / ".git" / "hooks" / "post-checkout").write_text(
            "#!/bin/sh\necho forbidden > hook-executed\n", encoding="utf-8")
        snapshot = digest_files(self.root)
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                                 check=True, capture_output=True).stdout.decode().split("\0")
        tool_paths = [ROOT / path for path in tracked if path]
        tool_before = digest_files(ROOT, tool_paths)
        scan = self.invoke("scan", "--all", "--security")
        self.assertIn(scan.returncode, (0, 2), scan.stderr)
        record = json.loads(scan.stdout)
        self.assertEqual(record["command"], "scan")
        self.assertEqual(scan.stderr, "")
        for args, expected in [(("prompt", "case-1", "--mode", "review"), 2),
                               (("prompt", "case-1", "--mode", "implement"), 3),
                               (("prompt", "case-1", "--mode", "implement", "--approved-case", "case-2"), 3),
                               (("prompt", "case-1", "--mode", "implement", "--approved-case", "case-1"), 2)]:
            child = self.invoke(*args)
            self.assertEqual(child.returncode, expected, child.stderr)
            payload = json.loads(child.stdout if expected == 2 else child.stderr)
            self.assertFalse(payload["complete"])
            if expected == 2:
                self.assertEqual(payload["errors"][0]["code"], "CAPABILITY_UNAVAILABLE")
        self.assertEqual(digest_files(self.root), snapshot)
        self.assertEqual(digest_files(ROOT, tool_paths), tool_before)
        self.assertFalse((self.root / "hook-executed").exists())


if __name__ == "__main__":
    unittest.main()
