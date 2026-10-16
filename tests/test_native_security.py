import os
from pathlib import Path
import shutil
import json
import subprocess
import tempfile
import unittest

from devsift.inventory import SourceTarget
from devsift.native_host import NativeAdapter, analyze_snapshot, probe_tool, source_offsets
from devsift.scanner import scan
from devsift.sql_adapter import make_tool as sql_tool
from devsift.typescript_adapter import make_tool


PAT = "ghp_" + "Ab7" * 12
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("DEVSIFT_TEST_NATIVE") == "1", "requires explicit pinned native setup")
class NativeSecurityContexts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        node = os.environ.get("DEVSIFT_NODE_EXECUTABLE") or shutil.which("node")
        if not node: raise AssertionError("requested native security requires Node")
        cls.tool = make_tool(str(Path(node).resolve()), Path(os.environ.get("DEVSIFT_FRONTEND_PACKAGE", str(ROOT / "native/frontend"))).resolve())
        if not probe_tool(cls.tool).available: raise AssertionError("requested frontend rulepack missing or unpinned")

    def report(self, text):
        return analyze_snapshot(self.tool, SourceTarget("src/security.ts", "ready", "typescript", text.encode(), ""))

    def test_actual_agent_ignores_second_argument_and_import_alias_mutation_is_partial(self):
        # Construct trusted built-in Agents only. No request/socket is opened.
        child = "const https=require('node:https');const a=new https.Agent(undefined,{rejectUnauthorized:false});if(a.options.rejectUnauthorized===false)process.exit(1);const b=new https.Agent({rejectUnauthorized:false});if(b.options.rejectUnauthorized!==false)process.exit(2);const original=https.Agent;const alias=https;alias.Agent=class{};if(https.Agent===original)process.exit(3);"
        result = subprocess.run([self.tool.process.executable, "-e", child], capture_output=True, timeout=10, check=True)
        self.assertEqual(result.returncode, 0)
        ignored = "import {Agent} from 'node:https';new Agent(undefined,{rejectUnauthorized:false});"
        report = self.report(ignored)
        self.assertEqual([item.rule_id for item in report.diagnostics if item.rule_id == "SEC002"], [])
        overridden = "import https from 'node:https';const alias=https;alias.Agent=class {};new https.Agent({rejectUnauthorized:false});"
        report = self.report(overridden)
        self.assertFalse(report.complete)
        self.assertNotIn("SEC002", [item.rule_id for item in report.diagnostics])
        cast_alias = "import https from 'node:https';const alias=(https as any);alias.Agent=class {};new https.Agent({rejectUnauthorized:false});"
        self.assertFalse(self.report(cast_alias).complete)
        self.assertNotIn("SEC002", [item.rule_id for item in self.report(cast_alias).diagnostics])

    def test_direct_literal_or_lexical_binding_in_actual_console_call(self):
        for source in ("console.error('" + PAT + "');", "const value='" + PAT + "'; console.log(value);"):
            with self.subTest(source=source):
                report = self.report(source)
                self.assertTrue(report.complete)
                diagnostics = [item for item in report.diagnostics if item.rule_id == "SEC001"]
                self.assertEqual(len(diagnostics), 1)
                start, end = source_offsets(source, diagnostics[0].region)
                self.assertTrue(source[start:end].startswith("console."))
        for source in ("console.error('password missing');", "console.info('[REDACTED]');",
                       "const console={log(x:string){}};console.log('" + PAT + "');",
                       "function f(console:any){console.log('" + PAT + "');}",
                       "console={log(x:string){}};console.log('" + PAT + "');",
                       "console.log=(x:any)=>{};console.log('" + PAT + "');",
                       "const value='" + PAT + "';console.log(redact(value));"):
            with self.subTest(source=source):
                self.assertNotIn("SEC001", [item.rule_id for item in self.report(source).diagnostics])

    def test_actual_node_import_tls_false_and_lookalike_or_safe_controls(self):
        positives = ["import https from 'node:https';new https.Agent({rejectUnauthorized:false});",
                     "import {Agent as A} from 'https';new A({rejectUnauthorized:false});",
                     "import * as tls from 'node:tls';tls.connect({rejectUnauthorized:false});",
                     "import https from 'node:https';https.get('https://example.invalid',{rejectUnauthorized:false});",
                     "import * as tls from 'node:tls';tls.connect(443,'example.invalid',{rejectUnauthorized:false});"]
        negatives = ["import https from 'node:https';new https.Agent({rejectUnauthorized:true});",
                     "import https from 'node:https';new https.Agent({rejectUnauthorized:'false'});",
                     "import https from 'other';new https.Agent({rejectUnauthorized:false});",
                     "import https from 'node:https';https.Agent=class {};new https.Agent({rejectUnauthorized:false});",
                     "import https from 'node:https';new https.Agent({rejectUnauthorized:false,rejectUnauthorized:true});",
                     "import https from 'node:https';function f(https:any){new https.Agent({rejectUnauthorized:false});}"]
        for source in positives:
            with self.subTest(source=source): self.assertIn("SEC002", [item.rule_id for item in self.report(source).diagnostics])
        for source in negatives:
            with self.subTest(source=source): self.assertNotIn("SEC002", [item.rule_id for item in self.report(source).diagnostics])

    def test_real_native_sec001_immutable_span_is_whole_masked_through_scan(self):
        prefix = "const banner='😀\u2028'; "
        source = prefix + "console.error('" + PAT + "');\r\n"
        report = self.report(source)
        diagnostic = next(item for item in report.diagnostics if item.rule_id == "SEC001")
        start, end = source_offsets(source, diagnostic.region)
        self.assertEqual(source[start:end], "console.error('" + PAT + "')")
        self.assertEqual(diagnostic.region.start_line, 1)
        self.assertEqual(diagnostic.region.start_column, len(prefix) + 1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()
            git("init", "-q")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "user.name", "Native Context")
            git("config", "core.autocrlf", "false")
            (root / "security.ts").write_bytes(source.encode())
            git("add", "security.ts")
            git("commit", "-qm", "fixture")
            adapter = NativeAdapter(self.tool, repo_root=root, source_sha=git("rev-parse", "HEAD"))
            record = scan(root, ("security.ts",), adapters=(adapter,))
            finding = next(item for item in record["findings"] if item["rule_id"] == "SEC001")
            self.assertEqual(finding["source"]["status"], "VERIFIED")
            self.assertEqual(finding["source"]["before"], "[REDACTED]")
            self.assertEqual(finding["lifecycle_class"], "UNKNOWN")
            self.assertTrue(finding["security_escalation"])
            self.assertEqual(record["enforced_count"], 0)
            self.assertNotIn(PAT, json.dumps(record))
            self.assertEqual(git("status", "--porcelain"), "")

    def test_unchanged_real_scriptdom_unsafe_and_parameterized_controls(self):
        dotnet = os.environ.get("DEVSIFT_DOTNET") or shutil.which("dotnet")
        if not dotnet: raise AssertionError("requested security SQL controls require dotnet")
        artifacts = Path(os.environ.get("DEVSIFT_SQL_ARTIFACTS", str(ROOT / ".devsift/local/tools/sql"))).resolve()
        tool = sql_tool(str(Path(dotnet).resolve()), artifacts)
        if not probe_tool(tool).available: raise AssertionError("requested real ScriptDom missing or unpinned")
        unsafe = "DECLARE @q nvarchar(max)=N'SELECT * FROM dbo.T WHERE x='+@input;EXEC(@q);"
        safe = "EXEC sys.sp_executesql N'SELECT * FROM dbo.T WHERE x=@x',N'@x int',@x=@input;"
        for dialect in ("tsql150", "tsql160"):
            positive = analyze_snapshot(tool, SourceTarget("x.sql", "ready", "sql", unsafe.encode(), ""), dialect=dialect)
            negative = analyze_snapshot(tool, SourceTarget("x.sql", "ready", "sql", safe.encode(), ""), dialect=dialect)
            self.assertTrue(positive.complete and negative.complete)
            self.assertEqual([item.rule_id for item in positive.diagnostics], ["SEC003"])
            self.assertEqual(negative.diagnostics, ())


if __name__ == "__main__": unittest.main()
