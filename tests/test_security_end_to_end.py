"""T033 actual CLI/Git/report redaction; native opt-in never fakes a provider."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from devsift.evidence import Region, verify_source
from devsift.git_changes import classify
from devsift.native_host import probe_tool
from devsift.native_manifest import ConfiguredTool, manifest_bytes
from devsift.typescript_adapter import make_tool


ROOT = Path(__file__).resolve().parents[1]
PAT = "ghp_" + "Ab8" * 12
NEW_PAT = "ghp_" + "Cd9" * 12
AWS = "Ab8/" * 10
BODY = "Ab8+" * 16


class SecurityEndToEnd(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / "source"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Security E2E")
        self.git("config", "core.autocrlf", "false")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True,
                              text=True, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1")).stdout.strip()

    def commit(self, name, text):
        (self.root / name).write_bytes(text.encode())
        self.git("add", "--", name)
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def state(self):
        return {path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob("*") if path.is_file()}

    def cli(self, *args, timeout=45):
        # Run the actual package entrypoint with isolated trusted import roots;
        # never let a customer devsift.py/config shadow the tool itself.
        launcher = "import runpy,sys;sys.path.insert(0," + repr(str(ROOT)) + ");runpy.run_module('devsift',run_name='__main__')"
        result = subprocess.run([sys.executable, "-I", "-B", "-c", launcher, *args], cwd=self.root,
                                capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        stream = result.stdout if result.stdout.strip() else result.stderr
        return result, json.loads(stream)

    def assert_private_reports(self, result, record, secrets=(PAT, AWS, BODY)):
        for value in secrets:
            self.assertNotIn(value, result.stdout + result.stderr)
        reports = record["data"]["reports"]
        self.assertEqual(set(reports), {"json", "markdown", "sarif"})
        cases = reports["json"]["cases"]
        self.assertTrue(cases)
        self.assertEqual(reports["sarif"]["version"], "2.1.0")
        self.assertEqual(len(reports["sarif"]["runs"][0]["results"]), len(cases))
        for finding in reports["sarif"]["runs"][0]["results"]:
            for location in finding.get("locations", []):
                self.assertEqual(location["physicalLocation"]["region"]["snippet"]["text"], "[REDACTED]")
        for case in cases:
            self.assertEqual(case["source"]["before"], "[REDACTED]")
            self.assertEqual(case["approval_status"], "pending")
            self.assertFalse(case["automatic_fix"])
            self.assertIn("Read only", case["review_prompt"])
            self.assertIn("explicit per-case approval", case["implement_prompt"])
            self.assertIn(case["case_id"], reports["markdown"])
        return cases

    def test_actual_cli_masks_all_formats_prompts_and_preserves_source_and_git(self):
        source = ("import logging\nstatus='" + PAT + "'\naws_secret_access_key='" + AWS + "'\n"
                  + "private_key='''-----BEGIN PRIVATE KEY-----\n" + BODY + "\n-----END PRIVATE KEY-----'''\n"
                  + "logging.error(aws_secret_access_key)\n")
        sha = self.commit("credential.py", source)
        before = self.state()
        result, record = self.cli("scan", "--all", "--security")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(record["enforced_count"], 0)
        cases = self.assert_private_reports(result, record)
        self.assertIn("SEC001", [case["rule_id"] for case in cases])
        for case in cases:
            self.assertEqual(case["source"]["location"]["source_sha"], sha)
            self.assertEqual(case["lifecycle_class"], "UNKNOWN")
        self.assertEqual(before, self.state())

    def test_actual_cli_schema_and_permission_errors_never_echo_untrusted_values_or_keys(self):
        self.commit("safe.py", "value=1\n")
        malformed = self.directory / "untrusted-manifest.json"
        raw = json.dumps({"schema_version": "1", "tools": [], PAT: AWS}).encode()
        malformed.write_bytes(raw)
        before = self.state()
        result, record = self.cli("scan", "--all", "--security", "--native-manifest", str(malformed),
                                  "--native-manifest-digest", hashlib.sha256(raw).hexdigest())
        self.assertEqual(result.returncode, 2)
        self.assertTrue(record["errors"])
        self.assertEqual(set(record["data"]["reports"]), {"json", "markdown", "sarif"})
        for value in (PAT, AWS): self.assertNotIn(value, result.stdout + result.stderr)
        result, record = self.cli("prompt", PAT, "--mode", "implement", "--approved-case", NEW_PAT)
        self.assertEqual(result.returncode, 3)
        for value in (PAT, NEW_PAT): self.assertNotIn(value, result.stdout + result.stderr)
        self.assertEqual(before, self.state())

    def test_real_git_source_origin_proofs_do_not_promote_unknown_cli_findings(self):
        base = self.commit("legacy.py", "token='" + PAT + "'\n")
        legacy = verify_source(self.root, "local", base, "legacy.py", Region(1, 7, 1, 49), sensitive=True)
        old_proof = classify(self.root, base, base, "HC002", legacy)
        self.assertEqual(old_proof.lifecycle_class, "LEGACY_UNCHANGED")
        head = self.commit("new.py", "token='" + NEW_PAT + "'\n")
        new = verify_source(self.root, "local", head, "new.py", Region(1, 7, 1, 49), sensitive=True)
        self.assertEqual(classify(self.root, base, head, "HC002", new).lifecycle_class, "NEW")
        before = self.state()
        result, record = self.cli("scan", "--all", "--security")
        cases = self.assert_private_reports(result, record, (PAT, NEW_PAT))
        self.assertEqual({case["source"]["location"]["path"] for case in cases}, {"legacy.py", "new.py"})
        self.assertTrue(all(case["lifecycle_class"] == "UNKNOWN" for case in cases))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(before, self.state())

    def test_malformed_pem_cli_is_bounded_without_inventing_credentials(self):
        source = "key='-----BEGIN PRIVATE KEY-----" + " " * 20000 + "-----END PRIVATE XEY-----'\n"
        self.commit("malformed.py", source)
        before = self.state()
        result, record = self.cli("scan", "--all", "--security", timeout=15)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(record["findings"], [])
        self.assertEqual(set(record["data"]["reports"]), {"json", "markdown", "sarif"})
        self.assertEqual(before, self.state())


@unittest.skipUnless(os.environ.get("DEVSIFT_TEST_NATIVE") == "1", "requires explicit installed native setup")
class NativeSecurityEndToEnd(SecurityEndToEnd):
    # Only the native-specific method is needed; avoid inheriting duplicate stdlib tests.
    test_actual_cli_masks_all_formats_prompts_and_preserves_source_and_git = None
    test_actual_cli_schema_and_permission_errors_never_echo_untrusted_values_or_keys = None
    test_real_git_source_origin_proofs_do_not_promote_unknown_cli_findings = None
    test_malformed_pem_cli_is_bounded_without_inventing_credentials = None

    def test_actual_native_cli_new_legacy_and_reserved_word_secret_values(self):
        node = os.environ.get("DEVSIFT_NODE_EXECUTABLE") or shutil.which("node")
        if not node: raise AssertionError("requested native E2E requires Node")
        package = Path(os.environ.get("DEVSIFT_FRONTEND_PACKAGE", str(ROOT / "native/frontend"))).resolve()
        tool = make_tool(str(Path(node).resolve()), package)
        if not probe_tool(tool).available: raise AssertionError("requested native E2E helper missing or unpinned")
        raw = manifest_bytes((ConfiguredTool(tool),))
        manifest = self.directory / "trusted-native.json"
        manifest.write_bytes(raw)
        arguments = ("--native-manifest", str(manifest), "--native-manifest-digest", hashlib.sha256(raw).hexdigest())
        source = ("const access_token='" + PAT + "';console.error(access_token);\n"
                  + "const apiKey='Critical';const clientSecret='source';const privateKey='status';\n")
        base = self.commit("legacy.ts", source)
        before = self.state()
        result, record = self.cli("ci", *arguments, "--security", "--base", base, "--paths", "legacy.ts", timeout=90)
        cases = self.assert_private_reports(result, record, (PAT,))
        self.assertGreater(record["data"]["counts"]["executed"], 0)
        self.assertIn("SEC001", [case["rule_id"] for case in cases])  # Actual native work, not only built-in shapes.
        self.assertTrue(all(case["lifecycle_class"] == "LEGACY_UNCHANGED" for case in cases))
        self.assertEqual(record["enforced_count"], 0)
        self.assertEqual(result.returncode, 2)  # Independent security review remains required.
        self.assertTrue(any(case["severity"] == "Critical" for case in cases))  # Reserved schema label preserved.
        for literal in ("apiKey='Critical'", "clientSecret='source'", "privateKey='status'"):
            self.assertNotIn(literal, result.stdout + result.stderr)
        self.assertEqual(before, self.state())
        self.commit("fresh.ts", "const authToken='" + NEW_PAT + "';console.warn(authToken);\n")
        before = self.state()
        result, record = self.cli("ci", *arguments, "--security", "--base", base, "--paths", "fresh.ts", timeout=90)
        cases = self.assert_private_reports(result, record, (PAT, NEW_PAT))
        self.assertIn("SEC001", [case["rule_id"] for case in cases])
        self.assertTrue(all(case["lifecycle_class"] == "NEW" for case in cases))
        self.assertGreater(record["enforced_count"], 0)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(before, self.state())


if __name__ == "__main__": unittest.main()
