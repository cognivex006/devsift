"""T021 transport/source conformance with real portable process fixtures."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from devsift.inventory import SourceTarget
from devsift.native_host import ToolDefinition, analyze_snapshot, file_digest, probe_tool
from devsift.process_runner import ProcessSpec, run_process


class NativeConformance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.helper = self.root / "transport_fixture.py"
        self.target = SourceTarget("src/ไทย component.ts", "ready", "typescript",
                                   "😀Z\r\nnext".encode("utf-8"), "conformance")
        self.report = {"protocol_version": "1", "tool_id": "fixture", "tool_version": "1.0.0",
                       "complete": True, "diagnostics": [{"rule_id": "LOG002", "region": {
                           "start_line": 1, "start_column": 2, "end_line": 1, "end_column": 3}}],
                       "reason": "COMPLETED", "metadata": {}}

    def tool(self, report=None, *, prefix="", delay=0):
        probe = {"protocol_version": "1", "tool_id": "fixture", "tool_version": "1.0.0",
                 "languages": ["typescript"], "engine_versions": {}}
        source = ("import json,sys,time\nsys.stdin.reconfigure(encoding='utf-8')\n"
                  "sys.stdout.reconfigure(encoding='utf-8')\n"
                  "if sys.argv[-1]=='--probe':\n print(json.dumps(" + repr(probe)
                  + "))\nelse:\n request=json.load(sys.stdin)\n time.sleep(" + repr(delay)
                  + ")\n assert request['path']=='src/ไทย component.ts'\n print(" + repr(prefix)
                  + "+json.dumps(" + repr(self.report if report is None else report) + "))\n")
        self.helper.write_text(source, encoding="utf-8")
        return ToolDefinition("fixture", "1.0.0", ("typescript",),
                              ProcessSpec(str(Path(sys.executable).resolve()), (str(self.helper),),
                                          timeout_seconds=2 if delay else 10),
                              file_digest(sys.executable), ((str(self.helper), file_digest(self.helper)),))

    def test_portable_paths_do_not_become_output_controlled_locations(self):
        tool = self.tool()
        self.assertTrue(probe_tool(tool).available)
        report = analyze_snapshot(tool, self.target)
        self.assertTrue(report.complete)
        self.assertEqual(report.diagnostics[0].region.start_column, 2)
        self.assertEqual(report.diagnostics[0].region.end_column, 3)
        # Unicode emoji counts as one coordinate, despite native UTF16 width two.
        self.assertEqual("😀Z"[1:2], "Z")

    def test_external_negative_contract_cases_never_claim_complete(self):
        fixture = Path(__file__).parent / "fixtures/native-protocol/rejected-analysis.json"
        for mutation in json.loads(fixture.read_text(encoding="utf-8")):
            changed = dict(self.report)
            changed[mutation["field"]] = mutation["value"]
            with self.subTest(field=mutation["field"]):
                report = analyze_snapshot(self.tool(changed), self.target)
                self.assertFalse(report.complete)

    def test_partial_parse_retains_valid_diagnostics_without_clean_status(self):
        changed = dict(self.report, complete=False, reason="PARSE_ERROR")
        report = analyze_snapshot(self.tool(changed), self.target)
        self.assertFalse(report.complete)
        self.assertEqual(report.reason, "PARSE_ERROR")
        self.assertEqual(len(report.diagnostics), 1)

    def test_timeout_and_unstructured_output_cannot_become_empty_success(self):
        for configuration in ({"delay": 10}, {"prefix": "unsolicited private fixture output\n"}):
            tool = self.tool(**configuration)
            self.assertTrue(probe_tool(tool).available)
            executions = []
            def execute(*args, **kwargs):
                result = run_process(*args, **kwargs)
                executions.append(result.status)
                return result
            with patch("devsift.native_host.run_process", side_effect=execute):
                report = analyze_snapshot(tool, self.target)
            self.assertFalse(report.complete)
            self.assertNotIn("private fixture", repr(report))
            if "delay" in configuration:
                self.assertEqual(executions, ["completed", "timeout"])

    def test_transport_analysis_never_writes_source_or_fixture_files(self):
        tool = self.tool()
        (self.root / "target.ts").write_bytes(self.target.content)
        def snapshot():
            return {str(path.relative_to(self.root)): None if path.is_dir() else path.read_bytes()
                    for path in self.root.rglob("*")}
        before = snapshot()
        probe_tool(tool)
        analyze_snapshot(tool, self.target)
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()
