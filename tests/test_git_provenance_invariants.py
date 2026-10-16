"""T015: adversarial immutable histories must preserve uncertainty and evidence."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.evidence import Region, SourceEvidence, verify_source
from devsift.git_changes import BaselineObservation, classify
from devsift.policy import decide


class ProvenanceInvariants(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Provenance Invariant Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.legacy = "legacy('ไทย')"
        self.base = self.commit({"core.py": self.legacy + "\r\nold_tail()\r\n"})

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()

    def commit(self, files, removed=()):
        for path in removed:
            self.git("rm", "--", path)
        for path, text in files.items():
            (self.root / path).write_bytes(text.encode("utf-8"))
        self.git("add", "--", *files)
        self.git("commit", "-qm", "invariant fixture")
        return self.git("rev-parse", "HEAD")

    def source(self, sha, path="core.py", line=1, text=None):
        text = self.legacy if text is None else text
        result = verify_source(self.root, "fixture/repository", sha, path,
                               Region(line, 1, line, len(text) + 1))
        self.assertEqual(result.status, "VERIFIED")
        return result

    def snapshot(self):
        return {str(path.relative_to(self.root)): None if path.is_dir() else path.read_bytes()
                for path in self.root.rglob("*")}

    def test_crisscross_ambiguity_cannot_be_overridden_by_complete_baseline(self):
        tree = self.git("rev-parse", self.base + "^{tree}")
        left = self.git("commit-tree", tree, "-p", self.base, "-m", "left")
        right = self.git("commit-tree", tree, "-p", self.base, "-m", "right")
        a = self.git("commit-tree", tree, "-p", left, "-p", right, "-m", "a")
        b = self.git("commit-tree", tree, "-p", right, "-p", left, "-m", "b")
        self.assertEqual(set(self.git("merge-base", "--all", a, b).splitlines()), {left, right})
        before = self.snapshot()
        for base, head in ((a, b), (b, a)):
            observation = BaselineObservation("HC001", left, "core.py", (), True, "fixture@1")
            result = classify(self.root, base, head, "HC001", self.source(head), baseline=observation)
            self.assertEqual(result.lifecycle_class, "UNKNOWN")
            self.assertEqual(result.reason, "AMBIGUOUS_MERGE_BASE")
            self.assertIsNone(result.merge_base_sha)
            self.assertIsNone(result.base_location)
            self.assertEqual(decide("HC001", result.lifecycle_class,
                                    source_verified=True).enforcement, "incomplete")
        self.assertEqual(self.snapshot(), before)

    def test_changed_region_requires_correct_complete_empty_baseline_scope(self):
        new_text = "introduced_call()"
        head = self.commit({"core.py": new_text + "\r\nold_tail()\r\n"})
        source = self.source(head, text=new_text)
        observations = (
            BaselineObservation("HC001", self.base, "core.py", (), False, "fixture@1"),
            BaselineObservation("CFG001", self.base, "core.py", (), True, "fixture@1"),
            BaselineObservation("HC001", head, "core.py", (), True, "fixture@1"),
            BaselineObservation("HC001", self.base, "different.py", (), True, "fixture@1"),
            BaselineObservation("HC001", self.base, "core.py", (self.source(self.base),), True, "fixture@1"),
            BaselineObservation("HC001", self.base, "core.py", (SourceEvidence(),), True, "fixture@1"),
        )
        for observation in observations:
            with self.subTest(observation=observation):
                result = classify(self.root, self.base, head, "HC001", source, baseline=observation)
                self.assertEqual(result.lifecycle_class, "UNKNOWN")
                self.assertIsNone(result.base_location)
        complete = BaselineObservation("HC001", self.base, "core.py", (), True, "fixture@1")
        result = classify(self.root, self.base, head, "HC001", source, baseline=complete)
        self.assertEqual(result.lifecycle_class, "MODIFIED_INTRODUCED")

    def test_unicode_crlf_region_drift_uses_immutable_source_not_dirty_index(self):
        head = self.commit({"core.py": "prefix()\r\n" + self.legacy + "\r\nnew_tail()\r\n"})
        (self.root / "core.py").write_bytes(b"staged content\n")
        self.git("add", "--", "core.py")
        (self.root / "core.py").write_bytes(b"different unstaged content\n")
        before = self.snapshot()
        old = classify(self.root, self.base, self.base, "HC001", self.source(self.base))
        current = classify(self.root, self.base, head, "HC001", self.source(head, line=2))
        self.assertEqual(current.lifecycle_class, "MODIFIED_PREEXISTING")
        self.assertEqual(current.base_location.source_sha, self.base)
        self.assertEqual(current.base_location.region, Region(1, 1, 1, len(self.legacy) + 1))
        self.assertEqual(current.head_location.region.start_line, 2)
        self.assertEqual(old.fingerprint, current.fingerprint)
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_rename_predecessors_stay_unknown_even_with_empty_baseline(self):
        self.commit({"other.py": self.legacy + "\r\nold_tail()\r\n"})
        base = self.git("rev-parse", "HEAD")
        head = self.commit({"renamed.py": self.legacy + "\r\nold_tail()\r\n"},
                           removed=("core.py", "other.py"))
        observation = BaselineObservation("HC001", base, "renamed.py", (), True, "fixture@1")
        result = classify(self.root, base, head, "HC001", self.source(head, "renamed.py"),
                          baseline=observation)
        self.assertEqual(result.lifecycle_class, "UNKNOWN")
        self.assertEqual(result.reason, "AMBIGUOUS_RENAME_PREDECESSOR")
        self.assertIsNone(result.base_location)

    def test_invalid_refs_and_stale_or_unresolved_evidence_never_guess_new(self):
        head = self.commit({"other.py": "unrelated()\n"})
        source = self.source(head)
        before = self.snapshot()
        for ref in ("missing-ref", "--help", "--output=unexpected", "HEAD^{tree}",
                    self.base + ":core.py", "HEAD\ninvalid"):
            with self.subTest(ref=ref):
                result = classify(self.root, ref, head, "HC001", source)
                self.assertEqual(result.lifecycle_class, "UNKNOWN")
                self.assertNotIn(ref, json.dumps(result.to_dict()))
        stale = classify(self.root, self.base, head, "HC001", self.source(self.base))
        self.assertEqual(stale.lifecycle_class, "UNKNOWN")
        self.assertEqual(stale.reason, "SOURCE_COMMIT_MISMATCH")
        unproven = classify(self.root, self.base, head, "HC001", SourceEvidence())
        self.assertEqual(unproven.lifecycle_class, "UNKNOWN")
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
