"""Planning counterexamples: budget results are never editing authority."""
from dataclasses import FrozenInstanceError
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.change_budget import (
    BudgetDecision, BudgetError, BudgetLimits, ChangeEstimate, ChangePlan, assess_plan, load_plan,
)


class ChangeBudgetTests(unittest.TestCase):
    def plan(self, **updates):
        values = dict(case_ids=("case-1",), lifecycle_class="NEW",
                      estimate=ChangeEstimate(1, 5, 2), refactor=False,
                      risk_if_changed="low", consumer_impact="bounded")
        values.update(updates)
        return ChangePlan(**values)

    def test_budget_is_not_authority_even_zero_change(self):
        for estimate in (ChangeEstimate(1, 5, 2), ChangeEstimate(0, 0, 0)):
            decision = assess_plan(self.plan(estimate=estimate), BudgetLimits(1, 5, 2))
            self.assertEqual(decision.status, "bounded_plan_review")
            self.assertFalse(decision.write_authorized)
            self.assertFalse(decision.execution_authorized)
            self.assertTrue(decision.requires_case_authorization)
            self.assertTrue(decision.verification_pending)
            self.assertEqual(decision.counts_basis, "declared_estimate")
            self.assertEqual(decision.labels_basis, "declared")

    def test_large_refactor_batch_and_high_risk_need_separate_approval(self):
        examples = [self.plan(estimate=ChangeEstimate(2, 5, 2)),
                    self.plan(estimate=ChangeEstimate(1, 6, 2)),
                    self.plan(estimate=ChangeEstimate(1, 5, 3)),
                    self.plan(refactor=True), self.plan(case_ids=("a", "b")),
                    self.plan(risk_if_changed="high"), self.plan(consumer_impact="broad")]
        for plan in examples:
            result = assess_plan(plan, BudgetLimits(1, 5, 2))
            self.assertEqual(result.status, "separate_approval_required")
            self.assertTrue(result.separate_approval_required)
            self.assertFalse(result.write_authorized)

    def test_unknown_does_not_become_low_or_within_budget(self):
        examples = [self.plan(lifecycle_class="UNKNOWN"),
                    self.plan(risk_if_changed="unknown"),
                    self.plan(consumer_impact="unknown"),
                    self.plan(estimate=ChangeEstimate(None, 0, 0))]
        for plan in examples:
            self.assertEqual(assess_plan(plan, BudgetLimits(100, 100, 100)).status,
                             "incomplete")
        self.assertEqual(assess_plan(self.plan(), BudgetLimits()).status, "incomplete")
        mixed = assess_plan(self.plan(refactor=True, risk_if_changed="unknown"),
                            BudgetLimits())
        self.assertEqual(mixed.status, "incomplete")
        self.assertTrue(mixed.separate_approval_required)

    def test_legacy_is_only_planning_advisory(self):
        for lifecycle in ("LEGACY_UNCHANGED", "MODIFIED_PREEXISTING"):
            result = assess_plan(self.plan(lifecycle_class=lifecycle), BudgetLimits(1, 5, 2))
            self.assertTrue(result.legacy_advisory)
            self.assertFalse(result.write_authorized)
        self.assertFalse(assess_plan(self.plan(lifecycle_class="UNKNOWN"),
                                    BudgetLimits(1, 5, 2)).legacy_advisory)

    def test_strict_counts_not_bool_nan_negative_or_unbounded(self):
        for bad in (True, False, -1, 1.0, float("nan"), float("inf"), 2**63, "1", []):
            for cls in (BudgetLimits, ChangeEstimate):
                with self.subTest(cls=cls, bad=bad), self.assertRaises(BudgetError):
                    cls(bad, 1, 1)

    def test_schema_and_private_failures(self):
        wire = self.plan().to_dict()
        for bad in ({**wire, "write_authorized": True},
                    {**wire, "schema_version": True}, {**wire, "schema_version": "2"},
                    {**wire, "refactor": 1}, {**wire, "lifecycle_class": []},
                    {**wire, "risk_if_changed": "safe"},
                    {**wire, "consumer_impact": False},
                    {**wire, "case_ids": []}, {**wire, "case_ids": ["a", "a"]},
                    {**wire, "case_ids": "a"},
                    {**wire, "estimate": {"files": 1, "added_lines": 0,
                                           "removed_lines": 0, "verified": True}}):
            with self.assertRaises(BudgetError):
                ChangePlan.from_dict(bad)
        with self.assertRaises(BudgetError):
            BudgetLimits.from_dict({"max_files": 1, "max_added_lines": 1,
                                    "max_removed_lines": 1, "approved": True})
        private = "ghp_" + "Ab8" * 12
        with self.assertRaises(BudgetError) as caught:
            self.plan(case_ids=(private,))
        self.assertNotIn(private, str(caught.exception))
        with self.assertRaises(BudgetError):
            self.plan(case_ids=tuple("case" + str(i) for i in range(1001)))

    def test_real_repository_untouched_and_security_gate_independent(self):
        from devsift.policy import decide, resolve_policy
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "--quiet", folder], check=True,
                           capture_output=True)
            (root / "source.py").write_text("print('unchanged')\n", encoding="utf-8")
            def snapshot():
                return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in root.rglob("*") if p.is_file()}
            before = snapshot()
            policy = resolve_policy()
            gate_before = decide("SEC001", "LEGACY_UNCHANGED", source_verified=True,
                                 policy=policy)
            for lifecycle in ("NEW", "MODIFIED_INTRODUCED", "MODIFIED_PREEXISTING",
                              "LEGACY_UNCHANGED", "UNKNOWN"):
                result = assess_plan(self.plan(lifecycle_class=lifecycle), BudgetLimits(1, 5, 2))
                self.assertFalse(result.write_authorized)
                self.assertFalse(result.execution_authorized)
            gate_after = decide("SEC001", "LEGACY_UNCHANGED", source_verified=True,
                                policy=policy)
            self.assertEqual(gate_after, gate_before)
            self.assertEqual(gate_after.enforcement, "security_review")
            self.assertEqual(snapshot(), before)

    def test_roundtrip_immutability_fresh_output_and_no_writes(self):
        plan = self.plan()
        wire = plan.to_dict()
        self.assertEqual(ChangePlan.from_dict(wire), plan)
        wire["case_ids"].clear()
        wire["estimate"]["files"] = 999
        self.assertEqual(plan.case_ids, ("case-1",))
        with self.assertRaises(FrozenInstanceError):
            plan.refactor = True
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plan.json"
            path.write_text(json.dumps(plan.to_dict()), encoding="utf-8")
            before = path.read_bytes()
            loaded = load_plan(before.decode())
            result = assess_plan(loaded, BudgetLimits(1, 5, 2))
            output = result.to_dict()
            output["reasons"].append("foreign")
            self.assertNotIn("foreign", result.reasons)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_json_duplicates_and_nonfinite_fail_closed(self):
        for text in ('{"case_ids":[],"case_ids":[]}', '{"x":NaN}',
                     '{"estimate":{"files":0,"files":1}}',
                     '{"x":Infinity}', "null", "[]", "{" , " " * 65537):
            with self.assertRaises(BudgetError):
                load_plan(text)

    def test_decision_does_not_accept_mutable_or_freeform_fields(self):
        for reasons in ([], ("private credential",), ("refactor", "refactor")):
            with self.assertRaises(BudgetError):
                BudgetDecision("bounded_plan_review", reasons, False, False)
        with self.assertRaises(BudgetError):
            BudgetDecision("approved", (), False, False)
        # Reserved schema words in a legitimate ID remain data, never masked keys.
        result = self.plan(case_ids=("Critical",)).to_dict()
        self.assertEqual(result["case_ids"], ["Critical"])
        self.assertEqual(result["lifecycle_class"], "NEW")


if __name__ == "__main__":
    unittest.main()
