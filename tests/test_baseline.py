from dataclasses import FrozenInstanceError
import hashlib
import json
import os
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

    @unittest.skipUnless(os.name == 'nt', 'Windows short-path alias')
    def test_short_directory_alias_supports_reviewed_create_and_cas(self):
        import ctypes
        parent = self.root / 'baseline storage with a long directory name'
        parent.mkdir()
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.windll.kernel32.GetShortPathNameW(str(parent), buffer, len(buffer))
        self.assertTrue(size, 'Actual Windows short-path lookup failed')
        alias = Path(buffer.value)
        if alias.absolute() == parent.resolve():
            self.skipTest('Filesystem has no distinct 8.3 alias')
        self.assertEqual(alias.resolve(), parent.resolve())
        target = alias / 'baseline.json'
        digest = save_snapshot(target, self.snapshot, self.approval())
        self.assertEqual(load_snapshot(parent / 'baseline.json', expected_digest=digest), self.snapshot)
        replacement = BaselineSnapshot('fixture/repo', self.sha, 'devsift@fixture', 'catalog@1', ())
        next_digest = save_snapshot(target, replacement, self.approval(replacement, digest), expected_digest=digest)
        self.assertEqual(load_snapshot(parent / 'baseline.json', expected_digest=next_digest), replacement)
        with self.assertRaises(BaselineError):
            save_snapshot(target, self.snapshot, self.approval(self.snapshot, digest), expected_digest=digest)

    @unittest.skipUnless(os.name == 'nt', 'Windows short-file alias lock identity')
    def test_existing_short_file_alias_uses_same_cooperating_writer_lock(self):
        import ctypes
        target = self.root / 'reviewed baseline snapshot with long filename.json'
        digest = save_snapshot(target, self.snapshot, self.approval())
        buffer = ctypes.create_unicode_buffer(32768)
        self.assertTrue(ctypes.windll.kernel32.GetShortPathNameW(str(target), buffer, len(buffer)))
        alias = Path(buffer.value)
        if alias.name == target.name:
            self.skipTest('Filesystem has no distinct file 8.3 alias')
        lock = target.with_name(target.name + '.lock')
        lock.write_bytes(b'other writer')
        before = target.read_bytes()
        with self.assertRaises(BaselineError):
            save_snapshot(alias, self.snapshot, self.approval(self.snapshot, digest), expected_digest=digest)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(lock.read_bytes(), b'other writer')
        lock.unlink()
        # An alias update is allowed once the shared canonical lock is free.
        next_digest = save_snapshot(alias, self.snapshot, self.approval(self.snapshot, digest), expected_digest=digest)
        self.assertEqual(load_snapshot(target, expected_digest=next_digest), self.snapshot)

    def test_symlink_parent_and_parent_traversal_cannot_redirect_save(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory)
            link = self.root / 'redirect'
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest('Host symlink creation unavailable: ' + type(error).__name__)
            with self.assertRaises(BaselineError):
                save_snapshot(link / 'baseline.json', self.snapshot, self.approval())
            self.assertEqual(list(outside.iterdir()), [])
        nested = self.root / 'nested'
        nested.mkdir()
        with self.assertRaises(BaselineError):
            save_snapshot(nested / '..' / 'baseline.json', self.snapshot, self.approval())
        self.assertFalse((self.root / 'baseline.json').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction safety')
    def test_junction_parent_cannot_redirect_save(self):
        import _winapi
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory)
            junction = self.root / 'junction'
            _winapi.CreateJunction(str(outside), str(junction))
            try:
                self.assertTrue(junction.is_junction())
                with self.assertRaises(BaselineError):
                    save_snapshot(junction / 'baseline.json', self.snapshot, self.approval())
                self.assertEqual(list(outside.iterdir()), [])
            finally:
                junction.rmdir()


if __name__ == "__main__":
    unittest.main()
