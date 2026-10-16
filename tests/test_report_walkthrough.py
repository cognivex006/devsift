"""Execute the documented walkthrough verbatim against a fresh actual Git repo."""
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReportWalkthroughTests(unittest.TestCase):
    def test_documented_cli_and_model_observations(self):
        document = (ROOT / "docs/cases/REPORT-WALKTHROUGH.md").read_text(encoding="utf-8")
        match = re.search(r"<!-- walkthrough: executable -->\s*```python\n(.*?)\n```", document, re.S)
        self.assertIsNotNone(match)
        executed = subprocess.run([sys.executable, "-I", "-B", "-c", match.group(1), str(ROOT)],
                                  capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertEqual(executed.stderr, "")
        observed = json.loads(executed.stdout)
        self.assertEqual(observed["scan_exit"], 2)
        self.assertFalse(observed["report_complete"])
        self.assertEqual(observed["formats"], ["json", "markdown", "sarif"])
        case = observed["verified_case"]
        self.assertEqual(case["rule_id"], "HC002")
        self.assertEqual(case["source"]["status"], "VERIFIED")
        self.assertEqual(case["source"]["before"], "[REDACTED]")
        location = case["source"]["location"]
        self.assertEqual(location["source_sha"], observed["source_sha"])
        self.assertEqual(location["path"], "settings.py")
        self.assertEqual(location["region"], dict(start_line=1, start_column=9, end_line=1, end_column=51))
        self.assertEqual(case["lifecycle_class"], "UNKNOWN")
        self.assertTrue(case["security_escalation"])
        self.assertEqual(case["after_proposal"]["label"], "AFTER (PROPOSAL)")
        self.assertIsNone(case["after_proposal"]["code"])
        self.assertEqual(case["risk_if_changed"]["level"], "unknown")
        self.assertFalse(case["automatic_fix"])
        imported = observed["imported_case"]
        self.assertEqual(imported["lifecycle_class"], "UNKNOWN")
        self.assertEqual(imported["severity"], "Critical")
        unresolved = observed["unresolved_case"]["source"]
        self.assertEqual(unresolved["status"], "SOURCE_UNRESOLVED")
        self.assertIsNone(unresolved["location"])
        self.assertIsNone(unresolved["before"])
        self.assertTrue(unresolved["lookup_plan"])
        self.assertEqual(observed["review_exit"], 0)
        self.assertFalse(observed["review_data"]["analysis_performed"])
        self.assertEqual(observed["implement_exit"], 2)
        self.assertEqual(observed["unapproved"]["reason"], "EXPLICIT_APPROVAL_REQUIRED")
        self.assertEqual(observed["matched_exit"], 2)
        matched = observed["matched"]
        self.assertEqual(matched["reason"], "UNKNOWN_EFFECTS_REVIEW_REQUIRED")
        self.assertTrue(matched["approval_matched"])
        self.assertTrue(matched["manual_planning_allowed"])
        self.assertFalse(matched["writes_authorized"])
        self.assertFalse(matched["execution_authorized"])
        self.assertTrue(observed["consumer_and_git_unchanged"])
        self.assertNotIn("ghp_" + "Ab8" * 12, executed.stdout + executed.stderr)


if __name__ == "__main__":
    unittest.main()
