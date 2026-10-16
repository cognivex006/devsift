"""T013 producer fixtures: source origin, not semantic rule re-analysis."""
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from devsift.evidence import Region, SourceEvidence, verify_source
from devsift.git_changes import BaselineObservation, classify


class GitChangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Git Fixture")
        self.git("config", "core.autocrlf", "false")
        self.base = self.commit({"code.py": "legacy_violation()\nold_call()\nend_marker()\n"})

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()

    def commit(self, files):
        for name, text in files.items():
            (self.root / name).write_bytes(text.encode("utf-8"))
        self.git("add", "--", *files)
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def source(self, sha, path="code.py", line=1, end=19):
        return verify_source(self.root, "fixture/repo", sha, path, Region(line, 1, line, end))

    def classify(self, sha, source=None, **options):
        return classify(self.root, self.base, sha, "HC001", source or self.source(sha), **options)

    def test_unchanged_file_is_legacy_and_result_is_immutable(self):
        head = self.commit({"other.py": "unrelated_unique_text()\n"})
        (self.root / "code.py").write_text("dirty working copy", encoding="utf-8")
        before = self.git("status", "--porcelain")
        result = self.classify(head)
        self.assertEqual(result.lifecycle_class, "LEGACY_UNCHANGED")
        self.assertEqual(result.merge_base_sha, self.base)
        self.assertEqual(result.base_location.source_sha, self.base)
        with self.assertRaises(FrozenInstanceError):
            result.lifecycle_class = "NEW"
        self.assertEqual(self.git("status", "--porcelain"), before)
        self.assertEqual((self.root / "code.py").read_text(), "dirty working copy")

    def test_untouched_region_of_changed_file_is_preexisting(self):
        head = self.commit({"code.py": "legacy_violation()\nchanged_call()\nend_marker()\n"})
        result = self.classify(head)
        self.assertEqual(result.lifecycle_class, "MODIFIED_PREEXISTING")
        self.assertEqual(result.base_location.region, Region(1, 1, 1, 19))

    def test_changed_region_requires_complete_baseline_absence_proof(self):
        head = self.commit({"code.py": "new_violation_call()\nold_call()\nend_marker()\n"})
        source = self.source(head, end=21)
        self.assertEqual(self.classify(head, source).lifecycle_class, "UNKNOWN")
        baseline = BaselineObservation("HC001", self.base, "code.py", (), True, "fixture-analyzer@1")
        result = self.classify(head, source, baseline=baseline)
        self.assertEqual(result.lifecycle_class, "MODIFIED_INTRODUCED")
        self.assertIsNone(result.base_location)
        for observation in (BaselineObservation("HC001", self.base, "code.py", (), False, "fixture@1"),
                            BaselineObservation("HC001", self.base, "code.py", (self.source(self.base),), True, "fixture@1")):
            self.assertEqual(self.classify(head, source, baseline=observation).lifecycle_class, "UNKNOWN")

    def test_proven_new_path_is_new_but_copy_and_possible_rename_are_unknown(self):
        head = self.commit({"new.py": "completely_novel_source()\n"})
        source = self.source(head, "new.py", end=26)
        self.assertEqual(self.classify(head, source).lifecycle_class, "NEW")
        copy = self.commit({"copy.py": "legacy_violation()\nold_call()\nend_marker()\n"})
        self.assertEqual(self.classify(copy, self.source(copy, "copy.py")).lifecycle_class, "UNKNOWN")
        self.git("rm", "code.py")
        moved = self.commit({"moved.py": "legacy_violation()\nold_call_modified()\n"})
        self.assertEqual(self.classify(moved, self.source(moved, "moved.py")).lifecycle_class, "UNKNOWN")

    def test_unknown_refs_source_and_duplicate_mapping_stay_unknown(self):
        for ref in ("missing-ref", "--help", "--output=unexpected"):
            result = classify(self.root, ref, self.base, "HC001", self.source(self.base))
            self.assertEqual(result.lifecycle_class, "UNKNOWN")
        self.assertEqual(self.classify(self.base, SourceEvidence()).lifecycle_class, "UNKNOWN")
        head = self.commit({"code.py": "legacy_violation()\nlegacy_violation()\nchanged()\n"})
        self.assertEqual(self.classify(head).lifecycle_class, "UNKNOWN")
        self.assertEqual(self.classify(head, self.source(self.base)).lifecycle_class, "UNKNOWN")

    def test_fingerprint_uses_unmasked_content_and_stays_stable_across_line_shifts(self):
        head = self.commit({"code.py": "inserted()\nlegacy_violation()\nold_call()\nend_marker()\n"})
        old = self.classify(self.base)
        current = self.classify(head, self.source(head, line=2))
        self.assertEqual(old.fingerprint, current.fingerprint)
        first = self.commit({"secret.py": "password='first-fixture-value'\n"})
        second = self.commit({"secret.py": "password='other-fixture-value'\n"})
        a = self.classify(first, self.source(first, "secret.py", end=31))
        b = self.classify(second, self.source(second, "secret.py", end=31))
        self.assertNotEqual(a.fingerprint, b.fingerprint)
        self.assertNotIn("fixture-value", repr(a) + repr(b))

    def test_shallow_and_unrelated_histories_are_unknown(self):
        head = self.commit({"other.py": "other()\n"})
        # A real local shallow clone needs file:// transport rather than a path.
        clone = self.root / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", self.root.as_uri(), str(clone)], check=True,
                       capture_output=True)
        source = verify_source(clone, "fixture/repo", head, "code.py", Region(1, 1, 1, 19))
        self.assertEqual(classify(clone, head, head, "HC001", source).lifecycle_class, "UNKNOWN")
        self.git("checkout", "--orphan", "unrelated")
        self.git("rm", "-rf", ".")
        orphan = self.commit({"fresh.py": "fresh()\n"})
        source = self.source(orphan, "fresh.py", end=8)
        self.assertEqual(self.classify(orphan, source).lifecycle_class, "UNKNOWN")

    def test_multiple_merge_bases_are_not_arbitrarily_selected(self):
        tree = self.git("rev-parse", self.base + "^{tree}")
        left = self.git("commit-tree", tree, "-p", self.base, "-m", "left")
        right = self.git("commit-tree", tree, "-p", self.base, "-m", "right")
        left_merge = self.git("commit-tree", tree, "-p", left, "-p", right, "-m", "left merge")
        right_merge = self.git("commit-tree", tree, "-p", right, "-p", left, "-m", "right merge")
        self.assertEqual(len(self.git("merge-base", "--all", left_merge, right_merge).splitlines()), 2)
        result = classify(self.root, left_merge, right_merge, "HC001", self.source(right_merge))
        self.assertEqual(result.lifecycle_class, "UNKNOWN")
        self.assertEqual(result.reason, "AMBIGUOUS_MERGE_BASE")
        self.assertIsNone(result.merge_base_sha)

    def test_partial_clone_configuration_prevents_any_lazy_fetch(self):
        source = self.source(self.base)
        self.git("config", "remote.origin.promisor", "true")
        self.git("config", "remote.origin.url", "https://invalid.example.invalid/must-not-fetch")
        result = self.classify(self.base, source)
        self.assertEqual(result.lifecycle_class, "UNKNOWN")
        self.assertEqual(result.reason, "PARTIAL_CLONE_UNSUPPORTED")

    def test_effective_worktree_environment_global_and_included_promisor_config_is_rejected(self):
        source = self.source(self.base)
        self.git("config", "extensions.worktreeConfig", "true")
        self.git("config", "--worktree", "remote.origin.promisor", "true")
        with patch("devsift.git_changes.verify_source") as verifier:
            result = self.classify(self.base, source)
            self.assertEqual(result.reason, "PARTIAL_CLONE_UNSUPPORTED")
            verifier.assert_not_called()
        self.git("config", "--worktree", "--unset", "remote.origin.promisor")
        environment = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "remote.origin.promisor",
                       "GIT_CONFIG_VALUE_0": "true"}
        with patch.dict(os.environ, environment), patch("devsift.git_changes.verify_source") as verifier:
            self.assertEqual(self.classify(self.base, source).reason, "PARTIAL_CLONE_UNSUPPORTED")
            verifier.assert_not_called()
        global_config = self.root / "isolated-global-config"
        global_config.write_text("[remote \"origin\"]\n\tpromisor = true\n", encoding="utf-8")
        with patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(global_config), "GIT_CONFIG_NOSYSTEM": "1"}), \
                patch("devsift.git_changes.verify_source") as verifier:
            self.assertEqual(self.classify(self.base, source).reason, "PARTIAL_CLONE_UNSUPPORTED")
            verifier.assert_not_called()
        included = self.root / "isolated-include-config"
        included.write_text("[remote \"origin\"]\n\tpromisor = true\n", encoding="utf-8")
        self.git("config", "include.path", included.as_posix())
        with patch("devsift.git_changes.verify_source") as verifier:
            self.assertEqual(self.classify(self.base, source).reason, "PARTIAL_CLONE_UNSUPPORTED")
            verifier.assert_not_called()


if __name__ == "__main__":
    unittest.main()
