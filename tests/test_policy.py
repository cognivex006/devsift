"""Producer regressions for the policy contract (no Git classification)."""
import json
from pathlib import Path
import tempfile
import unittest

from devsift.policy import PolicyError, decide, gate_result, load_policy, resolve_policy
from devsift.registry import RULES, Severity


class PolicyTests(unittest.TestCase):
    def test_precedence_and_independent_results(self):
        repo = {"quality_gate": {"block_on": ["Critical"]},
                "rules": {"HC001": {"severity": "Warning"}}}
        overlay = {"rules": {"HC001": {"severity": "Error"}}}
        result = resolve_policy(repo, overlay)
        self.assertEqual(result["quality_gate"]["block_on"], ["Critical"])
        self.assertEqual(result["rules"]["HC001"]["severity"], "Error")
        self.assertEqual(repo["rules"]["HC001"]["severity"], "Warning")
        result["quality_gate"]["block_on"].clear()
        self.assertEqual(resolve_policy()["quality_gate"]["block_on"], ["Critical", "Error"])

    def test_invalid_layers_are_never_hidden_by_overlay(self):
        invalid = [None, [], {"unknown": 1}, {"quality_gate": {"typo": []}},
                   {"rules": {"UNKNOWN": {"severity": "Error"}}},
                   {"rules": {"HC001": {"enabled": False}}},
                   {"rules": {"HC001": {"severity": "advisory"}}},
                   {"rules": {"HC001": None}}, {"quality_gate": []},
                   {"quality_gate": {"block_on": ["Error", "Error"]}},
                   {"quality_gate": {"block_on": ["Suggestion"]}},
                   {"legacy_mode": "block"}, {"schema_version": True},
                   {"schema_version": "2"}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(PolicyError):
                # None denotes absent only at the public optional-layer boundary.
                if value is None:
                    load_policy(self.write_json("null"))
                else:
                    resolve_policy(value, {"schema_version": "1"})

    def write_json(self, content):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "policy.json"
        path.write_text(content, encoding="utf-8")
        return path

    def test_json_errors_and_duplicate_keys(self):
        for content in ('{"legacy_mode":"recommend","legacy_mode":"block"}',
                        '{"quality_gate":{"block_on":NaN}}', '{bad'):
            with self.subTest(content=content), self.assertRaises(PolicyError):
                load_policy(self.write_json(content))
        self.assertEqual(load_policy(self.write_json('{}')), resolve_policy())

    def test_schema_and_defaults_agree(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root / "policy/defaults.json").read_text()), resolve_policy())
        schema = json.loads((root / "policy/schema.json").read_text())
        self.assertEqual(schema["properties"]["rules"]["propertyNames"]["enum"], list(RULES))

    def test_registry_is_stable_immutable_and_preserves_historical_ids(self):
        expected = ("HC001 HC002 HC003 HC004 HC005 CFG001 CFG002 CFG003 COM001 COM002 "
                    "COM003 SEC001 SEC002 SEC003 ARC001 ARC002 ARC003 API001 API002 "
                    "LOG001 LOG002 TST001 TST002").split()
        self.assertEqual(list(RULES), expected)
        self.assertEqual(RULES["COM003"].severity, Severity.SUGGESTION)
        self.assertEqual(RULES["ARC002"].severity, Severity.SUGGESTION)
        with self.assertRaises(TypeError):
            RULES["HC001"] = RULES["HC002"]

    def test_only_verified_introduced_configured_findings_block(self):
        for lifecycle in ("NEW", "MODIFIED_INTRODUCED"):
            self.assertEqual(decide("HC001", lifecycle, source_verified=True).enforcement, "block")
            self.assertEqual(decide("HC001", lifecycle, source_verified=False).enforcement, "incomplete")
            self.assertEqual(decide("HC004", lifecycle, source_verified=True).enforcement, "advisory")
        policy = resolve_policy({"quality_gate": {"block_on": ["Critical"]}})
        self.assertEqual(decide("HC001", "NEW", source_verified=True, policy=policy).enforcement, "advisory")

    def test_legacy_and_unknown_never_silently_pass(self):
        for lifecycle in ("LEGACY_UNCHANGED", "MODIFIED_PREEXISTING"):
            self.assertEqual(decide("HC001", lifecycle, source_verified=True).enforcement, "advisory")
            self.assertEqual(decide("HC002", lifecycle, source_verified=True).enforcement, "security_review")
        unknown = decide("HC001", "UNKNOWN", source_verified=True)
        self.assertEqual(unknown.enforcement, "incomplete")
        self.assertEqual(gate_result([unknown]), "incomplete")
        security = decide("HC002", "UNKNOWN", source_verified=True)
        self.assertTrue(security.security_escalation)
        self.assertEqual(security.enforcement, "incomplete")
        self.assertEqual(gate_result([decide("HC002", "LEGACY_UNCHANGED", source_verified=True)]), "security_review")

    def test_invalid_decision_input_and_unverified_security(self):
        for rule, lifecycle, verified in (("unknown", "NEW", True), ("HC001", "MODIFIED", True),
                                           ("HC001", "NEW", "true")):
            with self.assertRaises(PolicyError):
                decide(rule, lifecycle, source_verified=verified)
        self.assertFalse(decide("HC002", "NEW", source_verified=False).security_escalation)
        self.assertEqual(gate_result([]), "pass")

    def test_security_escalation_cannot_be_suppressed_by_local_severity(self):
        policy = resolve_policy({"rules": {"HC002": {"severity": "Suggestion"}},
                                 "quality_gate": {"block_on": []}})
        decision = decide("HC002", "LEGACY_UNCHANGED", source_verified=True, policy=policy)
        self.assertEqual(decision.severity, Severity.SUGGESTION)
        self.assertEqual(decision.enforcement, "security_review")
        self.assertTrue(decision.security_escalation)

    def test_gate_precedence_preserves_incomplete_and_rejects_foreign_records(self):
        advisory = decide("HC001", "LEGACY_UNCHANGED", source_verified=True)
        unknown = decide("HC001", "UNKNOWN", source_verified=False)
        block = decide("HC001", "NEW", source_verified=True)
        self.assertEqual(gate_result([advisory]), "pass")
        self.assertEqual(gate_result([advisory, unknown]), "incomplete")
        self.assertEqual(gate_result([unknown, block]), "block")
        with self.assertRaises(PolicyError):
            gate_result([{"enforcement": "pass"}])


if __name__ == "__main__":
    unittest.main()
