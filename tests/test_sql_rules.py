"""Actual ScriptDom execution-sink rules, never SQL execution."""
import os
from pathlib import Path
import shutil
import unittest

from devsift.inventory import SourceTarget
from devsift.native_host import analyze_snapshot, probe_tool, source_offsets
from devsift.sql_adapter import make_tool


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("DEVSIFT_TEST_NATIVE") == "1", "requires explicit native setup")
class SqlRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = os.environ.get("DEVSIFT_DOTNET") or shutil.which("dotnet")
        if not executable:
            raise AssertionError("requested native SQL rules require dotnet")
        artifacts = Path(os.environ.get("DEVSIFT_SQL_ARTIFACTS", str(ROOT / ".devsift/local/tools/sql"))).resolve()
        cls.tool = make_tool(str(Path(executable).resolve()), artifacts)
        if not probe_tool(cls.tool).available:
            raise AssertionError("requested native SQL rules require built pinned helper")

    def report(self, source, dialect="tsql160"):
        return analyze_snapshot(self.tool, SourceTarget("case.sql", "ready", "sql", source.encode(), ""), dialect=dialect)

    def test_executed_literal_concat_external_input_is_flagged_in_both_dialects(self):
        sources = [
            "DECLARE @sql nvarchar(max) = N'SELECT * FROM dbo.T WHERE name=' + @input; EXEC(@sql);",
            "DECLARE @sql nvarchar(max); SET @sql = N'SELECT * FROM dbo.T WHERE name=' + @input; EXEC sys.sp_executesql @sql;",
            "EXEC(N'SELECT * FROM dbo.T WHERE name=' + @input);",
            "DECLARE @sql nvarchar(max)=N'SELECT * FROM dbo.T WHERE name='; SET @sql += @input; EXEC(@sql);",
        ]
        for dialect in ("tsql150", "tsql160"):
            for source in sources:
                with self.subTest(dialect=dialect, source=source):
                    report = self.report(source, dialect)
                    self.assertTrue(report.complete)
                    self.assertEqual([item.rule_id for item in report.diagnostics], ["SEC003"])
                    start, end = source_offsets(source, report.diagnostics[0].region)
                    self.assertTrue(source[start:end].startswith("EXEC"))

    def test_bound_parameters_constants_unexecuted_strings_and_comments_pass(self):
        sources = [
            "EXEC sys.sp_executesql N'SELECT * FROM dbo.T WHERE id=@id', N'@id int', @id=@input;",
            "DECLARE @sql nvarchar(max)=N'SELECT * FROM dbo.T WHERE name=@name'; EXEC sp_executesql @stmt=@sql,@params=N'@name nvarchar(80)',@name=@input;",
            "EXEC(N'SELECT 1');",
            "DECLARE @sql nvarchar(max)=N'SELECT * FROM dbo.T WHERE name=' + N'constant'; EXEC(@sql);",
            "DECLARE @formatted nvarchar(max)=N'Hello ' + @name; SELECT @formatted;",
            "-- EXEC(N'SELECT ' + @input);\nSELECT N'EXEC(@sql)';",
        ]
        for dialect in ("tsql150", "tsql160"):
            for source in sources:
                with self.subTest(dialect=dialect, source=source):
                    report = self.report(source, dialect)
                    self.assertTrue(report.complete)
                    self.assertEqual(report.diagnostics, ())

    def test_quotename_is_only_safe_in_parsed_table_identifier_context(self):
        safe = "DECLARE @sql nvarchar(max)=N'SELECT * FROM ' + QUOTENAME(@table); EXEC(@sql);"
        unsafe = "DECLARE @sql nvarchar(max)=N'SELECT * FROM dbo.T WHERE name=' + QUOTENAME(@value); EXEC(@sql);"
        self.assertTrue(self.report(safe).complete)
        self.assertEqual(self.report(safe).diagnostics, ())
        self.assertFalse(self.report(unsafe).complete)
        self.assertEqual(self.report(unsafe).diagnostics, ())

    def test_unknown_execution_transform_and_control_flow_never_claim_complete_safe(self):
        sources = ["EXEC(@sql);", "EXEC dbo.UnknownProcedure;",
                   "DECLARE @sql nvarchar(max)=N'SELECT ' + dbo.UnknownTransform(@input); EXEC(@sql);",
                   "DECLARE @sql nvarchar(max)=N'SELECT 1'; IF @flag=1 SET @sql=@input; EXEC(@sql);",
                   "DECLARE @sql nvarchar(max)=N'SELECT 1'; SELECT @sql=Value FROM dbo.Config; EXEC(@sql);"]
        for source in sources:
            with self.subTest(source=source):
                self.assertFalse(self.report(source).complete)

    def test_exec_ast_span_uses_codepoints_lf_boundaries_and_no_raw_messages(self):
        for prefix, separator in (("SELECT N'😀'; ", " "), ("SELECT N'😀\u2028text'; ", " "),
                                  ("SELECT N'😀\u2028text';\r\n", "\r\n"), ("-- 😀\u2028comment\n", "\r\n")):
            declaration = "DECLARE @sql nvarchar(max)=N'SELECT * FROM dbo.T WHERE x=' + @input;" + separator
            source = prefix + declaration + "EXEC(@sql);"
            report = self.report(source)
            self.assertTrue(report.complete)
            self.assertEqual(len(report.diagnostics), 1)
            start, end = source_offsets(source, report.diagnostics[0].region)
            self.assertEqual(source[start:end], "EXEC(@sql);")
            expected_line = source[:source.index("EXEC(@sql)")].count("\n") + 1
            self.assertEqual(report.diagnostics[0].region.start_line, expected_line)

    def test_aliases_keep_input_provenance_and_constants_overwrite_prior_taint(self):
        source = "DECLARE @q nvarchar(max)=N'SELECT * FROM dbo.T WHERE id=' + @input; DECLARE @alias nvarchar(max)=@q; SET @q=N'SELECT 1'; EXEC(@alias);"
        self.assertEqual([item.rule_id for item in self.report(source).diagnostics], ["SEC003"])
        safe = "DECLARE @q nvarchar(max)=N'SELECT ' + @input; SET @q=N'SELECT 1'; EXEC(@q);"
        self.assertTrue(self.report(safe).complete)
        self.assertEqual(self.report(safe).diagnostics, ())
        procedure = "CREATE PROCEDURE dbo.ReadUnsafe @input nvarchar(80) AS BEGIN DECLARE @q nvarchar(max)=N'SELECT * FROM dbo.T WHERE x=' + @input; EXEC(@q); END;"
        self.assertEqual([item.rule_id for item in self.report(procedure).diagnostics], ["SEC003"])

    def test_try_catch_and_ambiguous_statement_arguments_never_inherit_convenient_safe_value(self):
        sources = [
            "DECLARE @q nvarchar(max)=N'SELECT 1'; BEGIN TRY SET @q=@input; END TRY BEGIN CATCH SET @q=N'SELECT 1'; END CATCH EXEC(@q);",
            "EXEC sp_executesql @stmt=N'SELECT 1', @stmt=@input;",
            "EXEC sp_executesql @input, @stmt=N'SELECT 1';",
        ]
        for source in sources:
            with self.subTest(source=source):
                self.assertFalse(self.report(source).complete)


if __name__ == "__main__":
    unittest.main()
