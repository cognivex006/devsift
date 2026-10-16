"""CLI integration uses real read-only inventory and actual Git candidate sets."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CliScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              capture_output=True, check=True).stdout

    def invoke(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
        completed = subprocess.run([sys.executable, "-B", "-m", "devsift", "scan", *args],
                                   cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(completed.stderr, "")
        return json.loads(completed.stdout)

    def snapshot(self):
        return {str(path.relative_to(self.root)): None if path.is_dir() else path.read_bytes()
                for path in self.root.rglob("*")}

    def test_all_invokes_inventory_without_exposing_source_or_writing_files(self):
        sensitive = "fixture" + "PrivateSourceValue"
        (self.root / "source.py").write_text("password='" + sensitive + "'\n")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "generated.py").write_text("unused")
        (self.root / "notes.md").write_text("unsupported")
        before = self.snapshot()
        record = self.invoke("--all")
        targets = {row["path"]: row for row in record["data"]["targets"]}
        self.assertEqual(record["data"]["mode"], "all")
        self.assertEqual(targets["source.py"]["execution_status"], "unavailable")
        self.assertEqual(targets["node_modules"]["status"], "excluded")
        self.assertEqual(targets["notes.md"]["execution_status"], "skipped")
        self.assertNotIn(sensitive, json.dumps(record))
        self.assertEqual(self.snapshot(), before)

    def test_changed_uses_head_working_tree_and_untracked_candidates_read_only(self):
        self.git("init", "-q")
        self.git("config", "user.name", "CLI Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        for name in ("changed.py", "deleted.py", "untouched.py"):
            (self.root / name).write_bytes(b"print(1)\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        (self.root / "changed.py").write_bytes(b"print(2)\n")
        (self.root / "deleted.py").unlink()
        (self.root / "new.ts").write_bytes(b"const value = 1;\n")
        before = self.snapshot()
        record = self.invoke("--changed")
        targets = {row["path"]: row for row in record["data"]["targets"]}
        self.assertEqual(record["data"]["mode"], "incremental")
        self.assertEqual(set(targets), {"changed.py", "deleted.py", "new.ts"})
        self.assertEqual(targets["deleted.py"]["status"], "missing")
        self.assertFalse(record["complete"])
        self.assertEqual(self.snapshot(), before)

    def test_changed_without_git_proof_is_explicitly_incomplete(self):
        (self.root / "source.py").write_bytes(b"print(1)\n")
        record = self.invoke("--changed")
        self.assertFalse(record["complete"])
        self.assertEqual(record["errors"][0]["code"], "GIT_SCOPE_UNAVAILABLE")
        self.assertEqual(record["data"]["targets"], [])


if __name__ == "__main__":
    unittest.main()
