"""Independent acceptance fixtures for T003, with explicit contract outcomes.

These test caller-supplied provenance, not the deferred Git classifier. Expected
outcomes live in human-reviewable fixtures rather than an implementation clone.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from devsift.policy import PolicyError, decide, gate_result, load_policy, resolve_policy
from devsift.registry import RULES


FIXTURES = Path(__file__).parent / "fixtures" / "policy"
LIFECYCLES = ("NEW", "MODIFIED_INTRODUCED", "MODIFIED_PREEXISTING", "LEGACY_UNCHANGED", "UNKNOWN")
SECURITY_RULES = ("HC002", "CFG003", "SEC001", "SEC002", "SEC003")


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class PolicyInvariants(unittest.TestCase):
    def test_documented_enforcement_cases(self):
        cases = fixture("enforcement.json")["cases"]
        self.assertEqual(len({case["name"] for case in cases}), len(cases))
        for case in cases:
            for lifecycle in case["classes"]:
                with self.subTest(case=case["name"], lifecycle=lifecycle):
                    result = decide(case["rule"], lifecycle, source_verified=case["verified"],
                                    policy=case["policy"])
                    self.assertEqual(result.rule_id, case["rule"])
                    self.assertEqual(result.lifecycle_class, lifecycle)
                    self.assertEqual(result.severity, case["severity"])
                    self.assertEqual(result.enforcement, case["enforcement"])
                    self.assertIs(result.security_escalation, case["escalate"])

    def test_uncertainty_never_becomes_a_pass_or_a_false_quality_block(self):
        for rule, gate in itertools.product(RULES, ([], ["Critical"], ["Error"], ["Critical", "Error"])):
            policy = {"quality_gate": {"block_on": gate}}
            # UNKNOWN stays incomplete even when evidence exists. Every lifecycle
            # stays incomplete when immutable source evidence is unavailable.
            inputs = [("UNKNOWN", True)] + [(value, False) for value in LIFECYCLES]
            for lifecycle, verified in inputs:
                with self.subTest(rule=rule, gate=gate, lifecycle=lifecycle, verified=verified):
                    decision = decide(rule, lifecycle, source_verified=verified, policy=policy)
                    self.assertEqual(decision.enforcement, "incomplete")
                    self.assertEqual(gate_result([decision]), "incomplete")
                    if not verified:
                        self.assertFalse(decision.security_escalation)

    def test_every_catalog_critical_security_rule_survives_local_downgrade(self):
        for rule, lifecycle in itertools.product(SECURITY_RULES, ("LEGACY_UNCHANGED", "MODIFIED_PREEXISTING")):
            with self.subTest(rule=rule, lifecycle=lifecycle):
                policy = {"quality_gate": {"block_on": []},
                          "rules": {rule: {"severity": "Suggestion"}}}
                decision = decide(rule, lifecycle, source_verified=True, policy=policy)
                self.assertEqual(decision.severity, "Suggestion")
                self.assertEqual(decision.enforcement, "security_review")
                self.assertTrue(decision.security_escalation)
                self.assertEqual(gate_result([decision]), "security_review")

    def test_invalid_layers_are_rejected_in_both_positions_and_from_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            for case in fixture("invalid-layers.json"):
                with self.subTest(case=case["name"]):
                    bad = case["layer"]
                    with self.assertRaises(PolicyError):
                        resolve_policy(bad, {})
                    with self.assertRaises(PolicyError):
                        resolve_policy({}, bad)
                    path.write_text(json.dumps(bad), encoding="utf-8")
                    before = path.read_bytes()
                    with self.assertRaises(PolicyError):
                        load_policy(path, {"schema_version": "1"})
                    self.assertEqual(path.read_bytes(), before)

    def test_overlay_precedence_and_no_aliasing_between_inputs_or_calls(self):
        data = fixture("overlays.json")
        repo, overlay = data["repo"], data["overlay"]
        before = deepcopy(data)
        defaults = resolve_policy()
        result = resolve_policy(repo, overlay)
        self.assertEqual(result, data["expected"])
        self.assertEqual(data, before)
        result["quality_gate"]["block_on"].append("Critical")
        result["rules"]["COM003"]["severity"] = "Suggestion"
        result["rules"]["HC002"]["severity"] = "Error"
        self.assertEqual(data, before)
        self.assertEqual(resolve_policy(repo, overlay), data["expected"])
        self.assertEqual(resolve_policy(), defaults)
        overlay["rules"]["HC001"]["severity"] = "Critical"
        self.assertEqual(result["rules"]["HC001"]["severity"], "Suggestion")

    def test_policy_resolution_and_evaluation_do_not_write_fixtures(self):
        paths = sorted(FIXTURES.glob("*.json"))
        before = {path: hashlib.sha256(path.read_bytes()).digest() for path in paths}
        data = fixture("overlays.json")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repo-policy.json"
            path.write_text(json.dumps(data["repo"]), encoding="utf-8")
            original = path.read_bytes()
            resolved = load_policy(path, data["overlay"])
            for lifecycle in LIFECYCLES:
                decide("HC001", lifecycle, source_verified=True, policy=resolved)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).digest() for path in paths})

    def test_decision_and_catalog_values_cannot_be_changed_in_place(self):
        original = RULES["HC001"]
        with self.assertRaises(TypeError):
            RULES["HC001"] = RULES["HC002"]
        with self.assertRaises(FrozenInstanceError):
            original.severity = "Suggestion"
        decision = decide("HC001", "NEW", source_verified=True)
        with self.assertRaises(FrozenInstanceError):
            decision.enforcement = "advisory"
        self.assertEqual(decide("HC001", "NEW", source_verified=True).enforcement, "block")

    def test_mixed_findings_preserve_independent_security_flag_and_gate_order(self):
        error = decide("HC001", "NEW", source_verified=True)
        unknown = decide("HC001", "UNKNOWN", source_verified=False)
        security = decide("HC002", "LEGACY_UNCHANGED", source_verified=True)
        for ordering in itertools.permutations([error, unknown, security]):
            self.assertEqual(gate_result(iter(ordering)), "block")
            self.assertTrue(security.security_escalation)
        for ordering in ([unknown, security], [security, unknown]):
            self.assertEqual(gate_result(ordering), "incomplete")
            self.assertTrue(security.security_escalation)


if __name__ == "__main__":
    unittest.main()
