"""T014 real immutable histories for renamed and shifted source provenance."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.evidence import Region, verify_source
from devsift.git_changes import classify


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Rename Fixture")
        self.git("config", "core.autocrlf", "false")

    def git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.root), *arguments], check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()

    def commit(self, files, removed=()):
        for path in removed:
            self.git("rm", "--", path)
        for path, text in files.items():
            (self.root / path).write_bytes(text.encode())
        self.git("add", "--", *files)
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def result(self, base, head, path="new.py", line=1):
        source = verify_source(self.root, "fixture/repo", head, path, Region(line, 1, line, 14))
        self.assertEqual(source.status, "VERIFIED")
        return classify(self.root, base, head, "HC001", source)

    def test_exact_unique_rename_is_legacy_with_original_path_proof_and_fingerprint(self):
        text = "legacy_call()\nunique_tail()\n"
        base = self.commit({"old.py": text})
        original = self.result(base, base, "old.py")
        head = self.commit({"new.py": text, "other.py": "unrelated_change()\n"}, ["old.py"])
        status = self.git("status", "--porcelain")
        renamed = self.result(base, head)
        self.assertEqual(renamed.lifecycle_class, "LEGACY_UNCHANGED")
        self.assertEqual(renamed.base_location.path, "old.py")
        self.assertEqual(renamed.base_location.source_sha, base)
        self.assertEqual(renamed.fingerprint, original.fingerprint)
        self.assertEqual(self.git("status", "--porcelain"), status)

    def test_renamed_changed_file_preserves_unique_chunk_with_line_drift(self):
        base = self.commit({"old.py": "legacy_call()\nold_tail()\n"})
        original = self.result(base, base, "old.py")
        head = self.commit({"new.py": "inserted()\nlegacy_call()\nchanged_tail()\n"}, ["old.py"])
        renamed = self.result(base, head, line=2)
        self.assertEqual(renamed.lifecycle_class, "MODIFIED_PREEXISTING")
        self.assertEqual(renamed.base_location.path, "old.py")
        self.assertEqual(renamed.base_location.region, Region(1, 1, 1, 14))
        self.assertEqual(renamed.head_location.region, Region(2, 1, 2, 14))
        self.assertEqual(renamed.fingerprint, original.fingerprint)

    def test_duplicate_old_paths_and_duplicate_occurrences_remain_unknown(self):
        text = "legacy_call()\ntail()\n"
        base = self.commit({"one.py": text, "two.py": text})
        head = self.commit({"new.py": text}, ["one.py", "two.py"])
        self.assertEqual(self.result(base, head).lifecycle_class, "UNKNOWN")
        duplicate_base = self.commit({"duplicates.py": "legacy_call()\nlegacy_call()\n"})
        duplicate_head = self.commit({"moved.py": "legacy_call()\nlegacy_call()\n"}, ["duplicates.py"])
        self.assertEqual(self.result(duplicate_base, duplicate_head, "moved.py").lifecycle_class, "UNKNOWN")

    def test_copy_with_old_kept_and_multiple_destinations_remain_unknown(self):
        text = "legacy_call()\ntail()\n"
        base = self.commit({"old.py": text})
        copied = self.commit({"new.py": text})
        self.assertEqual(self.result(base, copied).lifecycle_class, "UNKNOWN")
        moved_twice = self.commit({"second.py": text}, ["old.py"])
        self.assertEqual(self.result(base, moved_twice).lifecycle_class, "UNKNOWN")

    def test_edited_copy_and_unmatched_replacement_do_not_guess_origin(self):
        base = self.commit({"old.py": "legacy_call()\nold_tail()\n"})
        copied = self.commit({"new.py": "legacy_call()\nchanged_tail()\n"})
        self.assertEqual(self.result(base, copied).lifecycle_class, "UNKNOWN")
        replaced = self.commit({"novel.py": "brand_new_fn()\n"}, ["old.py"])
        self.assertEqual(self.result(base, replaced, "novel.py").lifecycle_class, "UNKNOWN")

    def test_second_destination_in_previously_existing_changed_file_is_ambiguous(self):
        text = "legacy_call()\ntail()\n"
        base = self.commit({"old.py": text, "existing.py": "old_other_content()\n"})
        head = self.commit({"new.py": text, "existing.py": "legacy_call()\nchanged_other_content()\n"}, ["old.py"])
        self.assertEqual(self.result(base, head).lifecycle_class, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
