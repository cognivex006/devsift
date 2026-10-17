"""Four-component source-bundle dry run with real temporary Git inputs."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tools.build_package import PackageBuildError, build_package, verify_bundle
from tools.check_release_readiness import check_release_readiness

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "packaging/manifest.json").read_text(encoding="utf-8"))
COMPONENTS = tuple(sorted(MANIFEST["components"]))


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class ReleaseDryRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="devsift-release-dry-run-")
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.source = self.parent / "source"
        self.source.mkdir()
        selected = {path for component in MANIFEST["components"].values() for path in component["required"]}
        for name in sorted(selected):
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        for args in (("init", "-q"), ("config", "core.autocrlf", "false"), ("config", "core.hooksPath", str(self.parent / "no-hooks")),
                     ("add", "--all"), ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                      "-c", "commit.gpgSign=false", "commit", "-qm", "four component dry run")):
            subprocess.run(["git", "-C", str(self.source), *args], check=True, capture_output=True)
        self.sha = subprocess.check_output(["git", "-C", str(self.source), "rev-parse", "HEAD"], text=True).strip()

    def build(self, name):
        destination = self.parent / name
        artifacts = build_package(self.source, destination, source_sha=self.sha, components=COMPONENTS)
        digest = next(item.sha256 for item in artifacts if item.name == "integrity.json")
        return destination, artifacts, digest

    def test_all_four_components_repeat_and_readiness_stays_release_blocked(self):
        source_before = snapshot(self.source)
        bundle_a, artifacts_a, trusted = self.build("bundle-a")
        bundle_b, artifacts_b, trusted_b = self.build("bundle-b")
        self.assertEqual(artifacts_a, artifacts_b)
        self.assertEqual(trusted, trusted_b)
        self.assertEqual(snapshot(bundle_a), snapshot(bundle_b))
        self.assertEqual(verify_bundle(bundle_a, expected_source_sha=self.sha,
                                       expected_integrity_sha256=trusted), artifacts_a)
        integrity = json.loads((bundle_a / "integrity.json").read_bytes())
        self.assertEqual([item["component"] for item in integrity["components"]], list(COMPONENTS))
        for item in integrity["components"]:
            with zipfile.ZipFile(bundle_a / item["archive"]) as archive:
                self.assertEqual(archive.namelist(), MANIFEST["components"][item["component"]]["required"])
        result = check_release_readiness(bundle_a, source_sha=self.sha, integrity_sha256=trusted)
        inspections = next(check for check in result["checks"] if check["name"] == "bounded_archive_security_inspection")
        self.assertEqual(len(inspections["archives"]), 4)
        observed = {item["name"]: item["issues"] for item in inspections["archives"]}
        self.assertEqual(observed, {
            "devsift-consumer-skill.zip": ["RECOGNIZED_SENSITIVE_SHAPE"],
            "devsift-core-sdist-source.zip": ["RECOGNIZED_SENSITIVE_SHAPE"],
            "devsift-core-wheel-source.zip": ["RECOGNIZED_SENSITIVE_SHAPE"],
            "devsift-source-assets.zip": ["RECOGNIZED_SENSITIVE_SHAPE"],
        })
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["verified_archives"], sorted(item["archive"] for item in integrity["components"]))
        self.assertIn("OWNER_LICENSE_APPROVAL_PENDING", result["blockers"])
        self.assertFalse(result["release_ready"])
        self.assertFalse(result["publication_authorized"])
        self.assertFalse(result["checksums_authenticate"])
        self.assertIn("ARCHIVE_REVIEW_REQUIRED", result["blockers"])
        self.assertEqual(snapshot(self.source), source_before)
        self.assertEqual(snapshot(bundle_a), snapshot(bundle_b))

    def test_wrong_pins_tamper_no_overwrite_and_cli_failure_are_read_only(self):
        bundle, _, trusted = self.build("bundle")
        before_source = snapshot(self.source)
        before_bundle = snapshot(bundle)
        for sha, digest in (("a" * 40, trusted), (self.sha, "0" * 64)):
            result = check_release_readiness(bundle, source_sha=sha, integrity_sha256=digest)
            self.assertFalse(result["checks_complete"])
            self.assertFalse(result["publication_authorized"])
        with self.assertRaises(PackageBuildError):
            build_package(self.source, bundle, source_sha=self.sha, components=COMPONENTS)
        self.assertEqual(snapshot(bundle), before_bundle)
        archive = next(bundle.glob("*.zip"))
        original = archive.read_bytes()
        archive.write_bytes(original + b"tampered")
        tampered = snapshot(bundle)
        result = check_release_readiness(bundle, source_sha=self.sha, integrity_sha256=trusted)
        self.assertFalse(result["checks_complete"])
        self.assertFalse(result["publication_authorized"])
        self.assertEqual(snapshot(bundle), tampered)
        command = [sys.executable, "-I", "-B", str(ROOT / "tools/check_release_readiness.py"),
                   "--bundle", str(bundle), "--source-sha", self.sha, "--integrity-sha256", trusted]
        run = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 2)
        self.assertNotIn(self.sha, run.stderr)
        self.assertEqual(snapshot(self.source), before_source)


if __name__ == "__main__":
    unittest.main()
