"""T030 acceptance uses actual pinned ScriptDom, no database or SQL execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from devsift.inventory import SourceTarget
from devsift.git_changes import classify
from devsift.native_host import NativeAdapter, analyze_snapshot, probe_tool, source_offsets
from devsift.policy import decide
from devsift.sql_adapter import make_tool


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "sql"


@unittest.skipUnless(os.environ.get("DEVSIFT_TEST_NATIVE") == "1", "set native opt-in after explicit pinned setup")
class SqlAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = os.environ.get("DEVSIFT_DOTNET") or shutil.which("dotnet")
        if not executable:
            raise AssertionError("requested SQL acceptance requires dotnet")
        cls.dotnet = str(Path(executable).resolve())
        cls.artifacts = Path(os.environ.get("DEVSIFT_SQL_ARTIFACTS", str(ROOT / ".devsift/local/tools/sql"))).resolve()
        cls.tool = make_tool(cls.dotnet, cls.artifacts)
        if not probe_tool(cls.tool).available:
            raise AssertionError("requested SQL acceptance requires pinned built helper")

    def target(self, text):
        return SourceTarget("fixture.sql", "ready", "sql", text.encode("utf-8"), "")

    def test_both_explicit_dialects_parse_real_metadata_and_parameterized_negative(self):
        facts = (FIXTURES / "schema-facts.sql").read_text(encoding="utf-8")
        safe = (FIXTURES / "parameterized.sql").read_text(encoding="utf-8")
        for dialect in ("tsql150", "tsql160"):
            with self.subTest(dialect=dialect):
                report = analyze_snapshot(self.tool, self.target(facts), dialect=dialect)
                self.assertTrue(report.complete)
                self.assertEqual(dict(report.metadata), {"dialect": dialect, "ddl_statements": 4, "unqualified_references": 1})
                parameterized = analyze_snapshot(self.tool, self.target(safe), dialect=dialect)
                self.assertTrue(parameterized.complete)
                self.assertEqual(parameterized.diagnostics, ())

    def test_raw_unsupported_and_missing_dialects_cannot_silently_choose_parser(self):
        base = {"protocol_version": "1", "path": "fixture.sql", "language": "sql", "source": "SELECT 1;", "dialect": None}
        for dialect in (None, "postgres", "mysql", "tsql140", "TSQL160"):
            with self.subTest(dialect=dialect), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run([self.dotnet, str(self.artifacts / "DevSift.Sql.dll"), "--analyze"],
                                        input=json.dumps(base | {"dialect": dialect}), text=True,
                                        encoding="utf-8", capture_output=True, check=True, cwd=directory)
                report = json.loads(result.stdout)
                self.assertFalse(report["complete"])
                self.assertEqual(report["reason"], "UNSUPPORTED_DIALECT")
                self.assertEqual(report["diagnostics"], [])

    def test_invalid_grammar_and_unresolved_flow_are_incomplete_in_both_dialects(self):
        cases = json.loads((FIXTURES / "incomplete-cases.json").read_text(encoding="utf-8"))
        for dialect in ("tsql150", "tsql160"):
            for case in cases:
                with self.subTest(dialect=dialect, name=case["name"]):
                    report = analyze_snapshot(self.tool, self.target(case["source"]), dialect=dialect)
                    self.assertFalse(report.complete)
                    self.assertEqual(report.reason, case["reason"])

    def test_ddl_dynamic_commands_and_customer_project_hooks_never_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "must-not-exist.txt"
            sql_path = root / "fixture.sql"
            text = ("CREATE TABLE dbo.ParseOnly(Id int); DROP TABLE dbo.ParseOnly;\n"
                    + "EXEC xp_cmdshell 'echo unsafe > " + str(marker).replace("'", "''") + "';")
            sql_path.write_text(text, encoding="utf-8")
            # A user project must never be loaded: even invalid XML cannot affect
            # stdin-only SQL analysis. No project/build command is requested.
            (root / "customer.sqlproj").write_text("<invalid-customer-project", encoding="utf-8")
            (root / "Directory.Build.targets").write_text("not XML; must never be read", encoding="utf-8")
            before = {item.name: item.read_bytes() for item in root.iterdir()}
            report = analyze_snapshot(self.tool, self.target(text), dialect="tsql160")
            self.assertFalse(report.complete)  # xp_cmdshell is unknown, never safe.
            self.assertEqual(dict(report.metadata)["ddl_statements"], 2)
            self.assertFalse(marker.exists())
            self.assertEqual(before, {item.name: item.read_bytes() for item in root.iterdir()})

    def test_real_git_native_adapter_proves_source_but_retains_unknown_lifecycle(self):
        text = (FIXTURES / "unsafe-concat.sql").read_text(encoding="utf-8")
        for dialect in ("tsql150", "tsql160"):
            with self.subTest(dialect=dialect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)

                def git(*args):
                    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                          text=True, check=True).stdout.strip()

                git("init", "-q")
                git("config", "user.email", "fixture@example.invalid")
                git("config", "user.name", "SQL Acceptance")
                git("config", "core.autocrlf", "false")
                (root / "fixture.sql").write_bytes(text.encode("utf-8"))
                git("add", "fixture.sql")
                git("commit", "-qm", "fixture")
                sha = git("rev-parse", "HEAD")
                adapter = NativeAdapter(self.tool, repo_root=root, source_sha=sha,
                                        repository="fixture/repo", dialect=dialect)
                before = git("status", "--porcelain")
                outcome = adapter.analyze(self.target(text))
                self.assertTrue(outcome.complete)
                self.assertEqual(len(outcome.findings), 1)
                finding = outcome.findings[0]
                self.assertEqual(finding.rule_id, "SEC003")
                self.assertEqual(finding.source.status, "VERIFIED")
                self.assertEqual(finding.source.location.source_sha, sha)
                self.assertEqual(finding.lifecycle_class, "UNKNOWN")
                start, end = source_offsets(text, finding.source.location.region)
                self.assertEqual(text[start:end], "EXEC(@query);")
                self.assertEqual(finding.source.before, "EXEC(@query);")
                policy = decide("SEC003", finding.lifecycle_class, source_verified=True)
                self.assertEqual(policy.enforcement, "incomplete")
                self.assertTrue(policy.security_escalation)
                provenance = classify(root, sha, sha, "SEC003", finding.source)
                self.assertEqual(provenance.lifecycle_class, "LEGACY_UNCHANGED")
                legacy = decide("SEC003", provenance.lifecycle_class, source_verified=True)
                self.assertEqual(legacy.enforcement, "security_review")
                self.assertEqual(git("status", "--porcelain"), before)
                # An altered snapshot cannot inherit the committed BEFORE proof.
                altered = adapter.analyze(self.target(text + "-- uncommitted snapshot\n"))
                self.assertEqual(altered.findings[0].source.status, "SOURCE_UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
