"""Actual credential/Python detectors, Git proof and independent escalation."""
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from devsift.security_gate import run_security_gate

PAT = "ghp_" + "Ab8" * 12


class SecurityGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.file = self.root / "sample.py"

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True).stdout.decode().strip()

    def commit(self, text):
        self.file.write_bytes(text.encode("utf-8"))
        self.git("add", "--", ".")
        self.git("commit", "--quiet", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def run_gate(self, **kwargs):
        return run_security_gate(self.root, paths=("sample.py",), **kwargs)

    def test_actual_logging_and_credential_critical_cannot_be_downgraded(self):
        sha = self.commit("import logging\ncredential = '" + PAT + "'\nlogging.error(credential)\n")
        # The finding has existed unchanged since the initial commit. The gate
        # still does not invent a lifecycle from file age or a caller assertion.
        (self.root / "unrelated.txt").write_text("later commit\n", encoding="utf-8")
        self.git("add", "--", ".")
        self.git("commit", "--quiet", "-m", "unrelated")
        result = self.run_gate(policy={"quality_gate": {"block_on": []},
                                      "rules": {"HC002": {"severity": "Suggestion"},
                                                "SEC001": {"severity": "Suggestion"}}})
        self.assertTrue(result.complete)
        self.assertEqual(result.status, "security_review")
        self.assertTrue(result.requires_security_review)
        findings = result.to_dict()["findings"]
        self.assertEqual({item["rule_id"] for item in findings}, {"HC002", "SEC001"})
        for finding in findings:
            self.assertEqual(finding["source"]["status"], "VERIFIED")
            self.assertEqual(finding["source"]["before"], "[REDACTED]")
            self.assertEqual(finding["lifecycle_class"], "UNKNOWN")
            self.assertEqual(finding["quality_enforcement"], "incomplete")
            self.assertEqual(finding["catalog_severity"], "Critical")
            self.assertEqual(finding["resolved_severity"], "Suggestion")
        self.assertNotIn(PAT, json.dumps(result.to_dict()))
        self.assertNotIn(PAT, repr(result))
        self.assertNotIn(str(self.root), json.dumps(result.to_dict()))
        self.assertNotEqual(sha, result.source_sha)

    def test_actual_tls_unsafe_and_matched_safe_controls(self):
        self.commit("import ssl\ncontext = ssl._create_unverified_context()\n")
        unsafe = self.run_gate()
        self.assertTrue(unsafe.requires_security_review)
        self.assertIn("SEC002", {item["rule_id"] for item in unsafe.to_dict()["findings"]})
        self.commit("import ssl\ncontext = ssl._create_unverified_context(cert_reqs=ssl.CERT_REQUIRED, check_hostname=True)\n")
        safe = self.run_gate()
        self.assertTrue(safe.complete)
        self.assertFalse(safe.requires_security_review)
        self.assertEqual(safe.status, "no_detected_critical_in_declared_scope")
        self.assertEqual(safe.to_dict()["findings"], [])

    def test_dirty_or_untracked_clean_source_is_incomplete_not_false_pass(self):
        self.commit("value = 1\n")
        self.file.write_text("value = 2\n", encoding="utf-8")
        dirty = self.run_gate()
        self.assertFalse(dirty.complete)
        self.assertEqual(dirty.status, "incomplete")
        (self.root / "untracked.py").write_text("value = 3\n", encoding="utf-8")
        untracked = run_security_gate(self.root, paths=("untracked.py",))
        self.assertFalse(untracked.complete)
        self.assertFalse(untracked.requires_security_review)

    def test_incomplete_other_source_does_not_hide_verified_critical(self):
        self.commit("credential = '" + PAT + "'\n")
        (self.root / "untracked.py").write_text("value = 1\n", encoding="utf-8")
        result = run_security_gate(self.root, paths=("sample.py", "untracked.py"))
        self.assertFalse(result.complete)
        self.assertEqual(result.status, "incomplete")
        self.assertTrue(result.requires_security_review)
        self.assertEqual(result.to_dict()["findings"][0]["source"]["before"], "[REDACTED]")

    def test_source_git_unchanged_fresh_reruns_and_fresh_output_no_authority(self):
        self.commit("credential = '" + PAT + "'\n")
        def snapshot():
            return {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.root.rglob("*") if p.is_file()}
        before = snapshot()
        result = self.run_gate()
        self.assertEqual(snapshot(), before)
        public = result.to_dict()
        public["findings"].clear()
        self.assertTrue(result.to_dict()["findings"])
        for name in ("write_authorized", "execution_authorized", "rotation_authorized", "publication_authorized"):
            self.assertFalse(getattr(result, name))
        self.assertEqual(result.to_dict()["credential_liveness"], "unknown")
        self.assertEqual(result.to_dict()["exploitability"], "unknown")
        with self.assertRaises(FrozenInstanceError):
            result.complete = True
        self.commit("value = 'placeholder'\n")
        self.assertFalse(self.run_gate().requires_security_review)
        self.assertTrue(result.requires_security_review)  # Captured old result is not reused.

    def test_missing_scope_invalid_config_missing_source_and_partial_repo_fail_closed(self):
        self.commit("value = 1\n")
        for kwargs in ({}, {"paths": ()}, {"paths": ("../escape.py",)},
                       {"paths": ("missing.py",)}, {"paths": ("sample.py",), "tools": (True,)},
                       {"paths": ("sample.py",), "policy": {"waiver": True}}):
            result = run_security_gate(self.root, **kwargs)
            self.assertFalse(result.complete)
            self.assertEqual(result.status, "incomplete")
        self.git("config", "remote.origin.promisor", "true")
        self.assertFalse(self.run_gate().complete)

    def test_explicit_redactor_masks_metadata_without_masking_fixed_enums(self):
        from devsift.redaction import Redactor
        self.commit("credential = '" + PAT + "'\n")
        result = self.run_gate(redactor=Redactor(("Critical",)))
        self.assertTrue(result.complete)
        self.assertTrue(result.requires_security_review)
        output = result.to_dict()
        self.assertNotIn(PAT, json.dumps(output))
        self.assertEqual(output["findings"][0]["catalog_severity"], "Critical")
        private_path = self.run_gate(redactor=Redactor(("sample.py",)))
        self.assertFalse(private_path.complete)
        self.assertNotIn("sample.py", json.dumps(private_path.to_dict()))
        self.assertEqual(private_path.to_dict()["findings"][0]["source"]["status"], "SOURCE_UNRESOLVED")

    def test_no_saved_report_waiver_approval_or_project_git_execution(self):
        self.commit("value = 1\n")
        for key in ("saved_report", "baseline", "waiver", "approved", "threshold"):
            with self.assertRaises(TypeError):
                self.run_gate(**{key: True})
        fake = self.root / ("git.exe" if os.name == "nt" else "git")
        fake.write_bytes(b"not a trusted executable")
        fake.chmod(0o755)
        with patch.dict(os.environ, {"PATH": str(self.root) + os.pathsep + "." + os.pathsep + os.environ["PATH"]}):
            self.assertTrue(self.run_gate().complete)

    def test_explicit_unavailable_native_provider_preserves_incomplete_and_critical_floor(self):
        from devsift.native_host import ToolDefinition, file_digest
        from devsift.process_runner import ProcessSpec
        self.commit("credential = '" + PAT + "'\n")
        missing = ToolDefinition("missing-provider", "1", ("python",), ProcessSpec(sys.executable),
                                 file_digest(sys.executable), ((str(self.root / "missing-helper"), "0" * 64),))
        result = self.run_gate(tools=(missing,))
        self.assertFalse(result.complete)
        self.assertTrue(result.requires_security_review)
        self.assertNotIn(str(self.root), json.dumps(result.to_dict()))
        self.assertFalse(self.run_gate(tools=(missing, missing)).complete)

    def test_unavailable_provider_with_unselected_language_never_reports_complete(self):
        from devsift.native_host import ToolDefinition, file_digest
        from devsift.process_runner import ProcessSpec
        missing = ToolDefinition("missing-go", "1", ("go",), ProcessSpec(sys.executable),
                                 file_digest(sys.executable), ((str(self.root / "missing-helper"), "0" * 64),))
        for text, critical in (("value = 1\n", False), ("credential = '" + PAT + "'\n", True)):
            with self.subTest(critical=critical):
                self.commit(text)
                result = self.run_gate(tools=(missing,))
                self.assertFalse(result.complete)
                self.assertEqual(result.status, "incomplete")
                self.assertIn("CONFIGURED_PROVIDER_UNAVAILABLE", result.reasons)
                self.assertEqual(result.requires_security_review, critical)
                self.assertNotIn(str(self.root), json.dumps(result.to_dict()))

    def test_ordinary_logging_upgraded_to_critical_is_not_security_evidence(self):
        self.commit("import logging\nlogging.info('ordinary message')\n")
        result = self.run_gate(policy={"rules": {"LOG001": {"severity": "Critical"}}})
        self.assertTrue(result.complete)
        self.assertFalse(result.requires_security_review)
        self.assertEqual(result.to_dict()["findings"], [])

    def test_transient_different_scan_bytes_cannot_pass_after_source_is_restored(self):
        from devsift.scanner import scan as real_scan
        self.commit("value = 1\n")
        original = self.file.read_bytes()
        def changed_scan(*args, **kwargs):
            self.file.write_bytes(b"value = 2\n")
            try:
                return real_scan(*args, **kwargs)
            finally:
                self.file.write_bytes(original)
        with patch("devsift.security_gate.scan", side_effect=changed_scan):
            result = self.run_gate()
        self.assertFalse(result.complete)
        self.assertEqual(self.file.read_bytes(), original)

    def test_actual_config_label_and_resource_bounds_are_not_waivers(self):
        self.commit("credential = '" + PAT + "'\n")
        result = self.run_gate(config_paths=("sample.py",))
        self.assertEqual({item["rule_id"] for item in result.to_dict()["findings"]}, {"CFG003"})
        self.assertTrue(result.requires_security_review)
        self.file.write_bytes(b"x" * 2_000_001)
        result = self.run_gate()
        self.assertFalse(result.complete)
        self.assertEqual(result.status, "incomplete")
        self.assertNotIn(PAT, json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
