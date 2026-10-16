"""Actual temporary Git bundles exercise readiness pins and read-only behavior."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.build_package import build_package
from tools.check_release_readiness import check_release_readiness

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "packaging/manifest.json").read_text(encoding="utf-8"))


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class ReleaseReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="devsift-readiness-")
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / "source"
        self.root.mkdir()
        files = {p for c in MANIFEST["components"].values() for p in c["required"]}
        for name in sorted(files):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        for args in (("init", "-q"), ("config", "core.autocrlf", "false"), ("add", "--all"),
                     ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                      "-c", "commit.gpgSign=false", "commit", "-qm", "fixture")):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        self.sha = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        self.bundle = self.parent / "bundle"
        items = build_package(self.root, self.bundle, source_sha=self.sha, components=("consumer-skill",))
        self.digest = next(a.sha256 for a in items if a.name == "integrity.json")

    def test_pinned_bundle_and_security_are_checked_but_release_stays_blocked_read_only(self):
        before_source, before_bundle = snapshot(self.root), snapshot(self.bundle)
        result = check_release_readiness(self.bundle, source_sha=self.sha, integrity_sha256=self.digest)
        self.assertTrue(result["checks_complete"], result)
        self.assertEqual(result["status"], "checks_passed_release_blocked")
        self.assertFalse(result["release_ready"])
        self.assertFalse(result["publication_authorized"])
        self.assertFalse(result["checksums_authenticate"])
        self.assertIn("OWNER_LICENSE_APPROVAL_PENDING", result["blockers"])
        self.assertTrue(any(x["name"] == "bounded_archive_security_inspection" and x["passed"] for x in result["checks"]))
        self.assertEqual(snapshot(self.root), before_source)
        self.assertEqual(snapshot(self.bundle), before_bundle)

    def test_wrong_pins_and_tamper_fail_without_writes(self):
        for sha, digest in (("a" * 40, self.digest), (self.sha, "0" * 64)):
            result = check_release_readiness(self.bundle, source_sha=sha, integrity_sha256=digest)
            self.assertFalse(result["checks_complete"])
            self.assertFalse(result["publication_authorized"])
        archive = next(self.bundle.glob("*.zip"))
        original = archive.read_bytes()
        archive.write_bytes(original + b"tamper")
        before = snapshot(self.bundle)
        result = check_release_readiness(self.bundle, source_sha=self.sha, integrity_sha256=self.digest)
        self.assertFalse(result["checks_complete"])
        self.assertIn("BUNDLE_VERIFICATION_FAILED", result["blockers"])
        self.assertEqual(snapshot(self.bundle), before)

    def test_cli_success_exit_is_check_completion_only(self):
        command = [sys.executable, "-I", "-B", str(ROOT / "tools/check_release_readiness.py"),
                   "--bundle", str(self.bundle), "--source-sha", self.sha,
                   "--integrity-sha256", self.digest]
        run = subprocess.run(command, capture_output=True, text=True, check=False)
        result = json.loads(run.stdout)
        self.assertEqual(run.returncode, 0)
        self.assertTrue(result["checks_complete"])
        self.assertFalse(result["release_ready"])
        self.assertFalse(result["publication_authorized"])

    def test_untrusted_source_pin_is_never_echoed(self):
        secret = "private-source-pin-must-not-appear"
        result = check_release_readiness(self.bundle, source_sha=secret, integrity_sha256=self.digest)
        self.assertIsNone(result["source_sha"])
        command = [sys.executable, "-I", "-B", str(ROOT / "tools/check_release_readiness.py"),
                   "--bundle", str(self.bundle), "--source-sha", secret,
                   "--integrity-sha256", self.digest]
        run = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 2)
        self.assertNotIn(secret, run.stdout + run.stderr)

    def test_missing_bundle_and_archive_inspection_failure_keep_no_authority(self):
        missing = check_release_readiness(self.parent / "missing", source_sha=self.sha,
                                          integrity_sha256=self.digest)
        self.assertIsNone(missing["source_sha"])
        self.assertFalse(missing["checks_complete"])
        self.assertFalse(missing["publication_authorized"])
        archive = next(self.bundle.glob("*.zip"))
        archive.unlink()
        before = snapshot(self.bundle)
        result = check_release_readiness(self.bundle, source_sha=self.sha, integrity_sha256=self.digest)
        self.assertFalse(result["checks_complete"])
        self.assertFalse(result["publication_authorized"])
        self.assertEqual(snapshot(self.bundle), before)


if __name__ == "__main__":
    unittest.main()
