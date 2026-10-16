import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from devsift.adapters import AdapterCapability
from devsift.baseline import capture_entry
from devsift.evidence import Region, SourceEvidence, verify_source
from devsift.inventory import SourceTarget
from devsift.git_changes import classify
from devsift.scanner import AdapterOutcome, ScanFinding, scan
from devsift.security_adapter import SecurityAdapter


PAT = "ghp_" + "Ab9" * 12
AWS = "Ab9/" * 10
PEM = "-----BEGIN PRIVATE KEY-----\n" + "Ab9+" * 16 + "\n-----END PRIVATE KEY-----"


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for args in (("init", "-q"), ("config", "user.email", "fixture@example.invalid"),
                     ("config", "user.name", "Security Fixture"), ("config", "core.autocrlf", "false")):
            self.git(*args)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True,
                              text=True, check=True).stdout.strip()

    def committed(self, text, path="client.py", language="python", **options):
        (self.root / path).write_bytes(text.encode())
        self.git("add", "--", path)
        self.git("commit", "-qm", "fixture")
        sha = self.git("rev-parse", "HEAD")
        target = SourceTarget(path, "ready", language, text.encode(), "")
        adapter = SecurityAdapter(repo_root=self.root, source_sha=sha, **options)
        return adapter, target, sha

    def test_actual_git_shapes_are_fully_masked_immutable_and_read_only(self):
        text = "api_token = '" + PAT + "'\naws_secret_access_key = '" + AWS + "'\nprivate_key = '''" + PEM + "'''\n"
        adapter, target, sha = self.committed(text)
        before = self.git("status", "--porcelain")
        outcome = adapter.analyze(target)
        self.assertTrue(outcome.complete)
        self.assertEqual(len(outcome.findings), 3)
        for finding in outcome.findings:
            self.assertEqual(finding.rule_id, "HC002")
            self.assertEqual(finding.lifecycle_class, "UNKNOWN")
            self.assertEqual(finding.source.status, "VERIFIED")
            self.assertEqual(finding.source.before, "[REDACTED]")
            self.assertEqual(finding.source.location.source_sha, sha)
            restored = SourceEvidence.from_dict(finding.source.to_dict(), repo_root=self.root)
            self.assertEqual(restored.before, "[REDACTED]")
            provenance = classify(self.root, sha, sha, "HC002", restored)
            self.assertEqual(provenance.lifecycle_class, "LEGACY_UNCHANGED")
            entry = capture_entry(self.root, "HC002", "1", restored)
            self.assertEqual(entry.fingerprint, provenance.fingerprint)
            self.assertEqual(len(entry.fingerprint), 64)
        record = scan(self.root, (target.path,), adapters=(adapter,))
        self.assertEqual(record["exit_code"], 2)
        self.assertEqual(record["enforced_count"], 0)
        for value in (PAT, AWS, PEM):
            self.assertNotIn(value, repr(outcome) + json.dumps(record))
        self.assertTrue(all(finding["security_escalation"] for finding in record["findings"]))
        self.assertEqual(self.git("status", "--porcelain"), before)

    def test_six_language_static_assignments_use_literal_context_and_proven_config_scope(self):
        cases = {"python": ("x.py", "token = '" + PAT + "'"),
                 "typescript": ("x.ts", "const token = '" + PAT + "';"),
                 "javascript": ("x.js", "const token = '" + PAT + "';"),
                 "csharp": ("x.cs", 'class C { string token = "' + PAT + '"; }'),
                 "go": ("x.go", 'package x; var token = "' + PAT + '"'),
                 "sql": ("x.sql", "DECLARE @token nvarchar(max) = N'" + PAT + "';")}
        for language, (path, text) in cases.items():
            with self.subTest(language=language):
                target = SourceTarget(path, "ready", language, text.encode(), "")
                normal = SecurityAdapter().analyze(target)
                config = SecurityAdapter(config_paths=(path,)).analyze(target)
                self.assertTrue(normal.complete)
                self.assertEqual([item.rule_id for item in normal.findings], ["HC002"])
                self.assertEqual([item.rule_id for item in config.findings], ["CFG003"])
                self.assertEqual(normal.findings[0].source.status, "SOURCE_UNRESOLVED")

    def test_comments_documentation_placeholders_ids_and_arbitrary_passwords_do_not_invent_secrets(self):
        cases = [("python", "x.py", "# token = '" + PAT + "'\ntext = 'documentation " + PAT + "'\n"),
                 ("python", "x.py", '"""' + PAT + '"""\n'),
                 ("typescript", "x.ts", "// const token='" + PAT + "';\nconst password='ordinary';"),
                 ("javascript", "x.js", "const pattern=/['" + PAT + "']/;"),
                 ("sql", "x.sql", "-- DECLARE @token nvarchar(max)=N'" + PAT + "';\nSELECT 1;"),
                 ("go", "x.go", "package x // token = \"" + PAT + "\"\n"),
                 ("python", "x.py", "aws_access_key_id='AKIA" + "A" * 16 + "'\npassword='ordinary'\napiKey='YOUR_API_KEY'\n")]
        for language, path, text in cases:
            with self.subTest(language=language):
                self.assertEqual(SecurityAdapter().analyze(SourceTarget(path, "ready", language, text.encode(), "")).findings, ())

    def test_invalid_encoding_malformed_literal_and_excessive_source_are_incomplete(self):
        for content in (b"\xff", b"token = 'unterminated", b"x" * 2_000_001):
            result = SecurityAdapter().analyze(SourceTarget("x.py", "ready", "python", content, ""))
            self.assertFalse(result.complete)
            self.assertEqual(result.findings, ())
        with self.assertRaises(ValueError) as error:
            SecurityAdapter(config_paths=("../private",))
        self.assertNotIn("private", str(error.exception))

    def test_stale_snapshot_does_not_inherit_verified_source_and_crop_never_unmasks(self):
        text = "# 😀\u2028 physical line\r\ntoken='" + PAT + "';\r\n"
        adapter, target, sha = self.committed(text)
        finding = adapter.analyze(target).findings[0]
        self.assertEqual(finding.source.location.region.start_line, 2)
        region = finding.source.location.region
        cropped = verify_source(self.root, "local", sha, target.path,
                                Region(2, region.start_column + 3, 2, region.start_column + 8), sensitive=True)
        self.assertEqual(cropped.before, "[REDACTED]")
        changed = SourceTarget(target.path, "ready", "python", (text + "# changed\n").encode(), "")
        self.assertEqual(adapter.analyze(changed).findings[0].source.status, "SOURCE_UNRESOLVED")

    def test_delegate_failure_and_logs_are_safely_composed_without_competing_provider(self):
        target = SourceTarget("x.ts", "ready", "typescript", ("const token='" + PAT + "';").encode(), "")

        class Failed:
            capability = AdapterCapability("fixture-native", "1", ("typescript",), False)

            def analyze(self, target):
                print(PAT)
                raise RuntimeError(PAT)

        adapter = SecurityAdapter(Failed())
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = adapter.analyze(target)
        self.assertFalse(result.complete)
        self.assertEqual(len(result.findings), 1)
        self.assertEqual(adapter.capability.languages, ("typescript",))
        self.assertNotIn(PAT, output.getvalue() + repr(result) + repr(adapter))

    def test_duplicate_delegate_findings_are_normalized_and_full_region_masked(self):
        text = "token='" + PAT + "'\n"
        adapter, target, sha = self.committed(text)
        own = adapter.analyze(target).findings[0]

        class Duplicate:
            capability = AdapterCapability("fixture-native", "1", ("python",), True)

            def analyze(self, target):
                unsafe_message = ScanFinding("same", "HC002", own.source, PAT)
                return AdapterOutcome(False, (unsafe_message, unsafe_message))

        composed = SecurityAdapter(Duplicate(), repo_root=self.root, source_sha=sha).analyze(target)
        self.assertFalse(composed.complete)
        self.assertEqual(len(composed.findings), 1)
        self.assertEqual(composed.findings[0].source.before, "[REDACTED]")
        self.assertNotIn(PAT, composed.findings[0].message + repr(composed))

    def test_unresolved_delegate_findings_are_retained_without_raw_ids_or_messages(self):
        class Unresolved:
            capability = AdapterCapability("fixture-native", "1", ("python",), True)

            def analyze(self, target):
                finding = ScanFinding(PAT, "HC002", SourceEvidence(), PAT)
                return AdapterOutcome(False, (finding, finding))

        target = SourceTarget("x.py", "ready", "python", b"value=1", "")
        result = SecurityAdapter(Unresolved()).analyze(target)
        self.assertFalse(result.complete)
        self.assertEqual(len(result.findings), 1)
        finding = result.findings[0]
        self.assertEqual(finding.source.status, "SOURCE_UNRESOLVED")
        self.assertNotIn(PAT, finding.case_id + finding.message + repr(result))

    def test_typed_aws_assignment_context_and_private_case_identity(self):
        cases = {"typescript": "const awsSecretAccessKey: string = '" + AWS + "';",
                 "javascript": "const awsSecretAccessKey = '" + AWS + "';",
                 "csharp": 'class C { string awsSecretAccessKey = "' + AWS + '"; }',
                 "go": 'package x; var awsSecretAccessKey string = "' + AWS + '"',
                 "sql": "DECLARE @aws_secret_access_key nvarchar(80) = N'" + AWS + "';"}
        for language, text in cases.items():
            with self.subTest(language=language):
                result = SecurityAdapter().analyze(SourceTarget("case.txt", "ready", language, text.encode(), ""))
                self.assertEqual([finding.rule_id for finding in result.findings], ["HC002"])
        first = SecurityAdapter().analyze(SourceTarget("x.py", "ready", "python", ("token='" + PAT + "'").encode(), ""))
        second = SecurityAdapter().analyze(SourceTarget("x.py", "ready", "python", ("token='" + PAT[:-1] + "Z'").encode(), ""))
        self.assertNotEqual(first.findings[0].case_id, second.findings[0].case_id)

    def test_javascript_regex_data_is_not_an_assignment_and_ambiguous_slashes_are_incomplete(self):
        for language, path in (("javascript", "x.js"), ("typescript", "x.ts")):
            for text in ("const pattern=/token = '" + PAT + "'/;",
                         "const pattern=/[/'\"]token = '" + PAT + "'/gi;"):
                with self.subTest(language=language, text=text):
                    report = SecurityAdapter().analyze(SourceTarget(path, "ready", language, text.encode(), ""))
                    self.assertEqual(report.findings, ())
                    self.assertTrue(report.complete)
            positive = "const pattern=/token = '" + PAT + "'/; const token='" + PAT + "';"
            report = SecurityAdapter().analyze(SourceTarget(path, "ready", language, positive.encode(), ""))
            self.assertEqual(len(report.findings), 1)
            ambiguous = "const ratio=left/right;"
            self.assertFalse(SecurityAdapter().analyze(SourceTarget(path, "ready", language, ambiguous.encode(), "")).complete)

    def test_malformed_pem_is_linear_bounded_and_requires_nonwhitespace_body(self):
        # Isolated child provides a real wall-clock bound without leaving a
        # catastrophic regex running in the main test process on failure.
        child = """from devsift.security_adapter import SecurityAdapter
from devsift.inventory import SourceTarget
for width in (2000, 20000, 65000):
    for footer in ('-----END PRIVATE XEY-----', '-----END PRIVATE KEY-----'):
        value='-----BEGIN PRIVATE KEY-----' + ' '*width + footer
        source='key = '+repr(value)
        result=SecurityAdapter().analyze(SourceTarget('x.py','ready','python',source.encode(),''))
        assert result.complete and not result.findings
"""
        result = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True,
                                timeout=5, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 0)

    def test_composed_scan_keeps_full_mask_for_nonsecurity_delegate_region(self):
        text = "aws_secret_access_key='" + AWS + "'\n"
        adapter, target, sha = self.committed(text)
        whole = verify_source(self.root, "local", sha, target.path, Region(1, 1, 1, len(text.rstrip()) + 1))

        class LogDelegate:
            capability = AdapterCapability("fixture-logging", "1", ("python",), True)

            def analyze(self, target):
                return AdapterOutcome(True, (ScanFinding("logging-case", "LOG001", whole, "ignored"),))

        composed = SecurityAdapter(LogDelegate(), repo_root=self.root, source_sha=sha)
        direct = composed.analyze(target)
        self.assertEqual([finding.source.before for finding in direct.findings], ["[REDACTED]", "[REDACTED]"])
        record = scan(self.root, (target.path,), adapters=(composed,))
        self.assertNotIn(AWS, json.dumps(record))
        for finding in record["findings"]:
            self.assertEqual(finding["source"]["before"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
