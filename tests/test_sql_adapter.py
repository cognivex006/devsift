"""Real ScriptDom opt-in checks; requested native tests fail if setup is absent."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from devsift.inventory import SourceTarget
from devsift.native_host import analyze_snapshot, probe_tool
from devsift.sql_adapter import make_tool


ROOT = Path(__file__).resolve().parents[1]
NATIVE = os.environ.get("DEVSIFT_TEST_NATIVE") == "1"


class SqlFactoryTests(unittest.TestCase):
    def test_setup_requires_absolute_runtime_and_complete_explicit_artifacts(self):
        with self.assertRaises(ValueError):
            make_tool("dotnet", Path.cwd())
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                make_tool(str(Path(sys.executable).resolve()), Path(directory))

    def test_dependency_version_mismatch_is_rejected_before_native_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("DevSift.Sql.dll", "DevSift.Sql.runtimeconfig.json", "Microsoft.SqlServer.TransactSql.ScriptDom.dll"):
                (root / name).write_bytes(b"fixture-not-executable")
            (root / "DevSift.Sql.deps.json").write_text(json.dumps({"libraries": {
                "Microsoft.SqlServer.TransactSql.ScriptDom/160.0.0": {}}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                make_tool(str(Path(sys.executable).resolve()), root)


@unittest.skipUnless(NATIVE, "set DEVSIFT_TEST_NATIVE=1 after explicit native setup")
class SqlAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = os.environ.get("DEVSIFT_DOTNET") or shutil.which("dotnet")
        if not executable:
            raise AssertionError("configured native SQL tests require dotnet")
        cls.dotnet = str(Path(executable).resolve())
        cls.artifacts = Path(os.environ.get("DEVSIFT_SQL_ARTIFACTS", str(ROOT / ".devsift/local/tools/sql"))).resolve()
        cls.tool = make_tool(cls.dotnet, cls.artifacts)
        if not probe_tool(cls.tool).available:
            raise AssertionError("configured native SQL helper must be built and available")

    def report(self, source, dialect="tsql160"):
        target = SourceTarget("fixture.sql", "ready", "sql", source.encode("utf-8"), "")
        return analyze_snapshot(self.tool, target, dialect=dialect)

    def test_actual_parser_probe_and_ddl_unqualified_metadata_without_execution(self):
        source = "CREATE TABLE dbo.NoDatabaseAccess(Id int); SELECT * FROM Unqualified; SELECT * FROM dbo.Qualified;"
        for dialect in ("tsql150", "tsql160"):
            report = self.report(source, dialect)
            self.assertTrue(report.complete)
            self.assertEqual(dict(report.metadata), {"dialect": dialect, "ddl_statements": 1, "unqualified_references": 1})
            self.assertEqual(report.diagnostics, ())

    def test_parser_errors_are_incomplete_and_safe_strings_parse_as_data(self):
        self.assertFalse(self.report("SELECT * FROM;").complete)
        self.assertEqual(self.report("SELECT * FROM;").reason, "PARSE_ERROR")
        self.assertTrue(self.report("EXEC sp_executesql N'SELECT 1';").complete)
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "must-not-exist"
            source = "EXEC xp_cmdshell 'echo unexpected > " + str(marker).replace("'", "''") + "';"
            self.assertTrue(self.report(source).complete)
            self.assertFalse(marker.exists())

    def test_unicode_literals_crlf_and_line_separators_do_not_change_ast_counts(self):
        source = "SELECT N'😀\u2028value' FROM Unqualified;\r\nSELECT * FROM dbo.Qualified;\n"
        self.assertTrue(self.report(source).complete)
        self.assertEqual(dict(self.report(source).metadata)["unqualified_references"], 1)

    def test_raw_protocol_rejects_unknown_dialect_and_duplicate_or_unknown_input_keys(self):
        valid = {"protocol_version": "1", "path": "fixture.sql", "language": "sql", "source": "SELECT 1;", "dialect": "tsql160"}
        cases = [(json.dumps(valid | {"dialect": "postgres"}), "UNSUPPORTED_DIALECT"),
                 (json.dumps(valid | {"dialect": None}), "UNSUPPORTED_DIALECT"),
                 (json.dumps(valid | {"extra": True}), "ANALYSIS_FAILED"),
                 (json.dumps(valid).replace('"sql"', '"sql", "language": "sql"', 1), "ANALYSIS_FAILED")]
        for text, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                executed = subprocess.run([self.dotnet, str(self.artifacts / "DevSift.Sql.dll"), "--analyze"],
                                          input=text, capture_output=True, text=True, encoding="utf-8", cwd=directory, check=True)
                data = json.loads(executed.stdout)
                self.assertFalse(data["complete"])
                self.assertEqual(data["reason"], expected)
                self.assertEqual(data["diagnostics"], [])


if __name__ == "__main__":
    unittest.main()
