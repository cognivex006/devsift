from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from devsift.baseline import (BaselineError, BaselineSnapshot, UpdateApproval, capture_entry,
                              diff_snapshots, load_snapshot, save_snapshot)
from devsift.evidence import Region, verify_source


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for args in (("init", "-q"), ("config", "user.email", "fixture@example.invalid"),
                     ("config", "user.name", "Baseline Fixture")):
            self.git(*args)
        (self.root / "code.py").write_text("legacy_call()\n", encoding="utf-8")
        self.git("add", "code.py")
        self.git("commit", "-qm", "fixture")
        self.sha = self.git("rev-parse", "HEAD")
        evidence = verify_source(self.root, "fixture/repo", self.sha, "code.py", Region(1, 1, 1, 14))
        self.entry = capture_entry(self.root, "HC001", "1", evidence)
        self.snapshot = BaselineSnapshot("fixture/repo", self.sha, "devsift@fixture", "catalog@1", [self.entry])

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True,
                              check=True, text=True).stdout.strip()

    def approval(self, snapshot=None, predecessor=None):
        return UpdateApproval("author", "reviewer", "CHANGE-1", (snapshot or self.snapshot).digest, predecessor)

    def test_explicit_create_load_and_compare_and_swap_with_persisted_approval(self):
        path = self.root / "baseline.json"
        digest = save_snapshot(path, self.snapshot, self.approval())
        original = path.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), digest)
        self.assertEqual(load_snapshot(path, expected_digest=digest), self.snapshot)
        self.assertEqual(BaselineSnapshot.from_json(self.snapshot.to_json()), self.snapshot)
        wire = json.loads(original)
        self.assertEqual(wire["approval"]["reviewer"], "reviewer")
        replacement = BaselineSnapshot("fixture/repo", self.sha, "devsift@fixture", "catalog@1", ())
        next_digest = save_snapshot(path, replacement, self.approval(replacement, digest), expected_digest=digest)
        self.assertEqual(load_snapshot(path, expected_digest=next_digest), replacement)
        with self.assertRaises(BaselineError):
            save_snapshot(path, self.snapshot, self.approval(self.snapshot, digest), expected_digest=digest)
        self.assertEqual(load_snapshot(path, expected_digest=next_digest), replacement)

    def test_load_diff_and_failed_update_never_refresh_or_write(self):
        path = self.root / "baseline.json"
        digest = save_snapshot(path, self.snapshot, self.approval())
        before = {item.name: item.read_bytes() for item in self.root.iterdir() if item.is_file()}
        loaded = load_snapshot(path, expected_digest=digest)
        delta = diff_snapshots(loaded, loaded)
        self.assertEqual(delta.added, ())
        self.assertEqual(delta.resolved, ())
        self.assertEqual(delta.unchanged, (self.entry,))
        for action in (lambda: save_snapshot(path, self.snapshot, self.approval()),
                       lambda: load_snapshot(path, expected_digest="0" * 64)):
            with self.assertRaises(BaselineError):
                action()
        self.assertEqual(before, {item.name: item.read_bytes() for item in self.root.iterdir() if item.is_file()})

    def test_tamper_unknown_fields_duplicate_keys_and_incompatible_versions_rejected(self):
        wire = self.snapshot.to_dict()
        wire["extra"] = True
        with self.assertRaises(BaselineError):
            BaselineSnapshot.from_dict(wire)
        with self.assertRaises(BaselineError):
            BaselineSnapshot.from_json('{"schema_version":"1","schema_version":"1"}')
        changed = BaselineSnapshot("fixture/repo", self.sha, "other-tool", "catalog@1", ())
        with self.assertRaises(BaselineError):
            diff_snapshots(self.snapshot, changed)
        with self.assertRaises(BaselineError):
            UpdateApproval("same", "same", "CHANGE-1", self.snapshot.digest)
        with self.assertRaises(FrozenInstanceError):
            self.entry.fingerprint = "0" * 64
        path = self.root / "baseline.json"
        digest = save_snapshot(path, self.snapshot, self.approval())
        altered = json.loads(path.read_text())
        altered["snapshot"]["entries"][0]["fingerprint"] = "0" * 64
        path.write_text(json.dumps(altered), encoding="utf-8")
        with self.assertRaises(BaselineError):
            load_snapshot(path, expected_digest=digest)

    def test_existing_lock_is_not_removed_and_wrong_approval_cannot_write(self):
        path = self.root / "baseline.json"
        lock = path.with_name(path.name + ".lock")
        lock.write_text("another writer", encoding="utf-8")
        with self.assertRaises(BaselineError):
            save_snapshot(path, self.snapshot, self.approval())
        self.assertEqual(lock.read_text(), "another writer")
        self.assertFalse(path.exists())

    def test_atomic_replace_failure_preserves_prior_file_and_cleans_owned_temporaries(self):
        path = self.root / "baseline.json"
        digest = save_snapshot(path, self.snapshot, self.approval())
        before = path.read_bytes()
        replacement = BaselineSnapshot("fixture/repo", self.sha, "devsift@fixture", "catalog@1", ())
        with patch("devsift.baseline.os.replace", side_effect=OSError("private-path-must-not-leak")):
            with self.assertRaises(BaselineError) as error:
                save_snapshot(path, replacement, self.approval(replacement, digest), expected_digest=digest)
        self.assertNotIn("private-path", str(error.exception))
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(path.with_name(path.name + ".lock").exists())
        self.assertEqual(list(self.root.glob(".devsift-baseline-*")), [])

    def test_diff_add_remove_identity_and_wrong_approval_are_explicit(self):
        empty = BaselineSnapshot("fixture/repo", self.sha, "devsift@fixture", "catalog@1", ())
        self.assertEqual(diff_snapshots(empty, self.snapshot).added, (self.entry,))
        self.assertEqual(diff_snapshots(self.snapshot, empty).resolved, (self.entry,))
        path = self.root / "baseline.json"
        wrong = UpdateApproval("author", "reviewer", "CHANGE-1", "0" * 64)
        with self.assertRaises(BaselineError):
            save_snapshot(path, self.snapshot, wrong)
        self.assertFalse(path.exists())
        with self.assertRaises(BaselineError):
            UpdateApproval("author", " AUTHOR ", "CHANGE-1", self.snapshot.digest)
        entries = [self.entry]
        frozen = BaselineSnapshot("fixture/repo", self.sha, "devsift@fixture", "catalog@1", entries)
        entries.clear()
        self.assertEqual(frozen.entries, (self.entry,))


if __name__ == "__main__":
    unittest.main()
