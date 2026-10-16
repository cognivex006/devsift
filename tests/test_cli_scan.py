"""CLI integration uses real read-only inventory and actual Git candidate sets."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


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
        for name in ("changed.py", "deleted.py", "untouched.py", "index_only.py"):
            (self.root / name).write_bytes(b"print(1)\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        (self.root / "index_only.py").write_bytes(b"print(234)\n")
        self.git("add", "index_only.py")
        (self.root / "index_only.py").write_bytes(b"print(1)\n")
        (self.root / "changed.py").write_bytes(b"print(2)\n")
        (self.root / "deleted.py").unlink()
        (self.root / "new.ts").write_bytes(b"const value = 1;\n")
        before = self.snapshot()
        record = self.invoke("--changed")
        targets = {row["path"]: row for row in record["data"]["targets"]}
        self.assertEqual(record["data"]["mode"], "incremental")
        self.assertEqual(set(targets), {"changed.py", "deleted.py", "new.ts", "index_only.py"})
        self.assertEqual(targets["index_only.py"]["byte_count"], len(b"print(1)\n"))
        self.assertEqual(targets["deleted.py"]["status"], "missing")
        self.assertFalse(record["complete"])
        self.assertEqual(self.snapshot(), before)

    def test_changed_without_git_proof_is_explicitly_incomplete(self):
        (self.root / "source.py").write_bytes(b"print(1)\n")
        record = self.invoke("--changed")
        self.assertFalse(record["complete"])
        self.assertEqual(record["errors"][0]["code"], "GIT_SCOPE_UNAVAILABLE")
        self.assertEqual(record["data"]["targets"], [])

    def prepare_filter_fixture(self):
        self.git('init', '-q')
        self.git('config', 'user.name', 'CLI Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'core.autocrlf', 'false')
        (self.root / 'source.py').write_bytes(b'print(1)\n')
        self.git('add', 'source.py')
        self.git('commit', '-qm', 'fixture')
        helper = self.root / 'filter_probe.py'
        helper.write_text('from pathlib import Path\nimport sys\n'
                          'Path("FILTER_WAS_EXECUTED").write_text("called")\n'
                          'if "--process" in sys.argv: sys.exit(1)\n'
                          'sys.stdout.buffer.write(sys.stdin.buffer.read())\n', encoding='utf-8')
        command = '"' + sys.executable.replace('\\', '/') + '" "' + str(helper).replace('\\', '/') + '"'
        (self.root / '.gitattributes').write_text('*.py filter=CaseSensitiveDriver\n', encoding='utf-8')
        (self.root / 'source.py').write_bytes(b'print(23456789)\n')
        return command

    def test_changed_disables_local_clean_filters_without_any_git_or_source_writes(self):
        command = self.prepare_filter_fixture()
        self.git('config', 'filter.CaseSensitiveDriver.clean', command)
        self.git('config', 'filter.CaseSensitiveDriver.required', 'true')
        before = self.snapshot()
        record = self.invoke('--changed')
        self.assertFalse((self.root / 'FILTER_WAS_EXECUTED').exists())
        self.assertEqual(self.snapshot(), before)
        targets = {row['path']: row for row in record['data']['targets']}
        self.assertIn('source.py', targets)
        self.assertEqual(targets['source.py']['byte_count'], len(b'print(23456789)\n'))
        self.assertFalse(record['complete'])

    def test_changed_disables_effective_env_process_filter_and_required_flag(self):
        command = self.prepare_filter_fixture()
        environment = {'GIT_CONFIG_COUNT': '2',
                       'GIT_CONFIG_KEY_0': 'filter.CaseSensitiveDriver.process',
                       'GIT_CONFIG_VALUE_0': command + ' --process',
                       'GIT_CONFIG_KEY_1': 'filter.CaseSensitiveDriver.required',
                       'GIT_CONFIG_VALUE_1': 'true'}
        before = self.snapshot()
        with patch.dict(os.environ, environment):
            record = self.invoke('--changed')
        self.assertFalse((self.root / 'FILTER_WAS_EXECUTED').exists())
        self.assertEqual(self.snapshot(), before)
        self.assertIn('source.py', {row['path'] for row in record['data']['targets']})

    def test_changed_disables_filters_from_global_config_and_nested_include(self):
        command = self.prepare_filter_fixture()
        with tempfile.TemporaryDirectory() as configuration:
            global_config = Path(configuration) / 'global.gitconfig'
            included_config = Path(configuration) / 'included.gitconfig'
            self.git('config', '--file', str(global_config), 'include.path', str(included_config))
            self.git('config', '--file', str(included_config), 'filter.CaseSensitiveDriver.clean', command)
            self.git('config', '--file', str(included_config), 'filter.CaseSensitiveDriver.required', 'true')
            before = self.snapshot()
            config_before = (global_config.read_bytes(), included_config.read_bytes())
            with patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': str(global_config)}):
                record = self.invoke('--changed')
            self.assertFalse((self.root / 'FILTER_WAS_EXECUTED').exists())
            self.assertEqual(self.snapshot(), before)
            self.assertEqual((global_config.read_bytes(), included_config.read_bytes()), config_before)
            self.assertIn('source.py', {row['path'] for row in record['data']['targets']})


if __name__ == "__main__":
    unittest.main()
