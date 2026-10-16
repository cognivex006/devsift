"""Producer regressions using immutable commits, not the working copy."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.evidence import (AfterProposal, EvidenceError, Region, RuntimeEvidence,
                              SourceEvidence, SourceLocation, verify_source)
from devsift.redaction import Redactor


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Evidence Fixture")
        (self.root / "code.py").write_bytes("one\nsecond ไทย\nthree\n".encode())
        self.git("add", "code.py")
        self.git("commit", "-qm", "fixture")
        self.sha = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout

    def evidence(self, **options):
        return verify_source(self.root, "fixture/repo", self.sha, "code.py",
                             Region(2, 1, 2, 11), **options)

    def test_verified_before_comes_from_commit_and_roundtrips(self):
        (self.root / "code.py").write_text("uncommitted content", encoding="utf-8")
        before_status = self.git("status", "--porcelain")
        result = self.evidence()
        self.assertEqual(result.status, "VERIFIED")
        self.assertEqual(result.before, "second ไทย")
        self.assertEqual(result.location.source_sha, self.sha)
        wire = result.to_dict()
        self.assertEqual(SourceEvidence.from_dict(json.loads(json.dumps(wire)), repo_root=self.root), result)
        self.assertEqual(self.git("status", "--porcelain"), before_status)
        self.assertEqual((self.root / "code.py").read_text(), "uncommitted content")

    def test_missing_mismatch_and_out_of_bounds_have_no_fake_location(self):
        results = [self.evidence(expected_before="wrong"),
                   verify_source(self.root, "fixture/repo", "0" * 40, "code.py", Region(1, 1, 1, 2)),
                   verify_source(self.root, "fixture/repo", self.sha, "missing.py", Region(1, 1, 1, 2)),
                   verify_source(self.root, "fixture/repo", self.sha, "code.py", Region(99, 1, 99, 2)),
                   verify_source(self.root, "fixture/repo", self.sha, "code.py", Region(1, 1, 1, 99))]
        for result in results:
            with self.subTest(reason=result.reason):
                self.assertEqual(result.status, "SOURCE_UNRESOLVED")
                self.assertIsNone(result.location)
                self.assertIsNone(result.before)
                self.assertTrue(result.lookup_plan)
                self.assertEqual(SourceEvidence.from_dict(result.to_dict()), result)

    def test_invalid_paths_sha_and_region_rejected_without_echoing_input(self):
        paths = ("../secret", "/root", "C:/secret", "C:secret", "a\\b", "a//b", "./a", "a/../b", "a\x00b")
        for path in paths:
            with self.subTest(path=path), self.assertRaises(EvidenceError):
                verify_source(self.root, "fixture/repo", self.sha, path, Region(1, 1, 1, 2))
        for sha in ("HEAD", self.sha[:12], "g" * 40, "a" * 41):
            with self.subTest(sha=sha), self.assertRaises(EvidenceError):
                SourceLocation("fixture/repo", sha, "code.py", Region(1, 1, 1, 2))
        for args in ((0, 1, 1, 2), (1, True, 1, 2), (2, 1, 1, 2), (1, 3, 1, 2)):
            with self.subTest(args=args), self.assertRaises(EvidenceError):
                Region(*args)
        self.assertEqual(SourceLocation("fixture/repo", "a" * 64, "code.py", Region(1, 1, 1, 1)).source_sha, "a" * 64)

    def test_wire_cannot_self_assert_verified_or_change_before(self):
        wire = self.evidence().to_dict()
        with self.assertRaises(EvidenceError):
            SourceEvidence.from_dict(wire)
        wire["before"] = "fabricated"
        result = SourceEvidence.from_dict(wire, repo_root=self.root)
        self.assertEqual(result.status, "SOURCE_UNRESOLVED")
        wire["extra"] = True
        with self.assertRaises(EvidenceError):
            SourceEvidence.from_dict(wire, repo_root=self.root)
        with self.assertRaises(EvidenceError):
            SourceEvidence(status="VERIFIED")

    def test_git_symlink_mode_is_unresolved_without_following_target(self):
        # Create a Git symlink via index, portable even without Windows symlink privilege.
        blob = subprocess.run(["git", "-C", str(self.root), "hash-object", "-w", "--stdin"],
                              input="../../outside", text=True, capture_output=True, check=True).stdout.strip()
        self.git("update-index", "--add", "--cacheinfo", "120000", blob, "link")
        self.git("commit", "-qm", "symlink fixture")
        sha = self.git("rev-parse", "HEAD").strip()
        result = verify_source(self.root, "fixture/repo", sha, "link", Region(1, 1, 1, 2))
        self.assertEqual(result.status, "SOURCE_UNRESOLVED")
        self.assertIsNone(result.location)

    def test_runtime_and_proposal_are_redacted_separate_and_strict(self):
        secret = "fixture" + "SensitiveValue"
        redactor = Redactor((secret,))
        runtime = RuntimeEvidence("service log", "line " + secret, redactor=redactor)
        proposal = AfterProposal("change " + secret, redactor=redactor)
        self.assertNotIn(secret, repr(runtime) + repr(proposal) + json.dumps(runtime.to_dict()))
        self.assertEqual(proposal.to_dict()["label"], "AFTER (PROPOSAL)")
        self.assertEqual(RuntimeEvidence.from_dict(runtime.to_dict()), runtime)
        self.assertEqual(AfterProposal.from_dict(proposal.to_dict()), proposal)
        data = runtime.to_dict()
        data["line"] = 10
        with self.assertRaises(EvidenceError):
            RuntimeEvidence.from_dict(data)

    def test_multiline_columns_and_crlf_preserve_exact_selected_source(self):
        (self.root / "code.py").write_bytes(b"alpha\r\nbeta\r\ngamma\r\n")
        self.git("-c", "core.autocrlf=false", "add", "code.py")
        self.git("commit", "-qm", "CRLF fixture")
        sha = self.git("rev-parse", "HEAD").strip()
        result = verify_source(self.root, "fixture/repo", sha, "code.py", Region(1, 3, 3, 3))
        self.assertEqual(result.before, "pha\r\nbeta\r\nga")

    def test_secret_in_verified_before_and_metadata_is_never_exposed(self):
        secret = "fixture" + "SensitiveValue"
        (self.root / "code.py").write_text(secret + "\n", encoding="utf-8")
        self.git("add", "code.py")
        self.git("commit", "-qm", "masking fixture")
        sha = self.git("rev-parse", "HEAD").strip()
        redactor = Redactor((secret,))
        result = verify_source(self.root, "fixture/" + secret, sha, "code.py",
                               Region(1, 1, 1, len(secret) + 1), redactor=redactor)
        self.assertEqual(result.before, "[REDACTED]")
        self.assertNotIn(secret, repr(result) + json.dumps(result.to_dict()))
        direct = SourceEvidence(lookup_plan="Inspect " + secret, redactor=Redactor((secret,)))
        self.assertEqual(direct.lookup_plan, "Inspect [REDACTED]")
        self.assertEqual(SourceEvidence.from_dict(result.to_dict(), repo_root=self.root, redactor=redactor), result)

    def test_nested_wire_types_and_runtime_timestamp_are_strict(self):
        wire = self.evidence().to_dict()
        wire["location"]["region"]["start_line"] = True
        with self.assertRaises(EvidenceError):
            SourceEvidence.from_dict(wire, repo_root=self.root)
        for value in ("2026-10-16", "2026-10-16T12:00:00", "2026-99-16T12:00:00Z", True):
            with self.subTest(value=value), self.assertRaises(EvidenceError):
                RuntimeEvidence("log", "message", value)
        self.assertEqual(RuntimeEvidence("log", "message", "2026-10-16T12:00:00Z").observed_at,
                         "2026-10-16T12:00:00Z")

    def test_git_lf_lines_ignore_unicode_separators_and_preserve_content_cr(self):
        text = "a\u2028b\u2029c\vd\fe\r\r\nlast\r"
        (self.root / "code.py").write_bytes(text.encode("utf-8"))
        self.git("-c", "core.autocrlf=false", "add", "code.py")
        self.git("commit", "-qm", "physical line fixture")
        sha = self.git("rev-parse", "HEAD").strip()
        first = verify_source(self.root, "fixture/repo", sha, "code.py", Region(1, 1, 1, 11))
        self.assertEqual(first.before, "a\u2028b\u2029c\vd\fe\r")
        second = verify_source(self.root, "fixture/repo", sha, "code.py", Region(2, 1, 2, 6))
        self.assertEqual(second.before, "last\r")

    def test_source_slice_uses_complete_secret_context_not_only_selected_text(self):
        secret = "fixture" + "SensitiveValue"
        content = ("password='" + secret + "'\n"
                   + "Authorization: Bearer " + secret + "\n"
                   + "-----BEGIN PRIVATE KEY-----\n" + secret + "\n-----END PRIVATE KEY-----\n")
        (self.root / "code.py").write_bytes(content.encode())
        self.git("-c", "core.autocrlf=false", "add", "code.py")
        self.git("commit", "-qm", "context masking fixture")
        sha = self.git("rev-parse", "HEAD").strip()
        for region in (Region(1, 11, 1, 32), Region(1, 14, 1, 19),
                       Region(2, 23, 2, 44), Region(4, 1, 4, 22), Region(3, 1, 5, 26)):
            with self.subTest(region=region):
                result = verify_source(self.root, "fixture/repo", sha, "code.py", region)
                self.assertEqual(result.status, "VERIFIED")
                self.assertEqual(result.location.region, region)
                self.assertEqual(result.before, "[REDACTED]")
                self.assertNotIn(secret, repr(result) + json.dumps(result.to_dict()))

    def test_unresolved_wire_lookup_plan_honors_explicit_redactor(self):
        secret = "fixture" + "SensitiveValue"
        wire = SourceEvidence().to_dict()
        wire["lookup_plan"] = "Inspect " + secret
        result = SourceEvidence.from_dict(wire, redactor=Redactor((secret,)))
        self.assertEqual(result.lookup_plan, "Inspect [REDACTED]")
        self.assertNotIn(secret, repr(result) + json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
