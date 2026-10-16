"""T020 real process protocol fixtures, not claims of native language analysis."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from devsift.inventory import SourceTarget
from devsift.native_host import (NativeAdapter, ToolDefinition, analyze_snapshot,
                                 file_digest, probe_tool)
from devsift.process_runner import ProcessSpec
from devsift.scanner import scan


class NativeHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.helper = self.root / "trusted_probe.py"
        self.target = SourceTarget("a.ts", "ready", "typescript", b"safe = 1\n", "fixture")

    def tool(self, *, probe_change=None, report_change=None, raw=None):
        probe = {"protocol_version": "1", "tool_id": "fixture", "tool_version": "1.0.0",
                 "languages": ["typescript"], "engine_versions": {"parser": "1.0.0"}}
        report = {"protocol_version": "1", "tool_id": "fixture", "tool_version": "1.0.0",
                  "complete": True, "diagnostics": [{"rule_id": "LOG002", "region": {
                      "start_line": 1, "start_column": 1, "end_line": 1, "end_column": 5}}],
                  "reason": "COMPLETED", "metadata": {}}
        probe.update(probe_change or {})
        report.update(report_change or {})
        self.helper.write_text(
            "import json,sys\n"
            + "if sys.argv[-1]=='--probe': print(json.dumps(" + repr(probe) + "))\n"
            + "else:\n request=json.load(sys.stdin)\n "
            + ("print(" + repr(raw) + ")" if raw is not None else "print(json.dumps(" + repr(report) + "))")
            + "\n", encoding="utf-8")
        return ToolDefinition("fixture", "1.0.0", ("typescript",),
                              ProcessSpec(str(Path(sys.executable).resolve()), (str(self.helper),)),
                              file_digest(sys.executable), ((str(self.helper), file_digest(self.helper)),),
                              (("parser", "1.0.0"),))

    def test_real_probe_and_normalization_run_without_touching_target(self):
        tool = self.tool()
        before = self.helper.read_bytes()
        self.assertTrue(probe_tool(tool).available)
        report = analyze_snapshot(tool, self.target)
        self.assertTrue(report.complete)
        self.assertEqual(report.diagnostics[0].rule_id, "LOG002")
        self.assertEqual(report.diagnostics[0].region.end_column, 5)
        self.assertEqual(self.helper.read_bytes(), before)
        self.assertNotIn("safe = 1", repr(report))

    def test_missing_or_changed_artifact_never_executes_or_becomes_available(self):
        tool = self.tool()
        marker = self.root / "SHOULD_NOT_EXECUTE"
        self.helper.write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n")
        self.assertFalse(probe_tool(tool).available)
        self.assertFalse(analyze_snapshot(tool, self.target).complete)
        self.assertFalse(marker.exists())
        missing = replace(tool, process=ProcessSpec(str(self.root / "missing-executable")))
        self.assertFalse(probe_tool(missing).available)

    def test_probe_versions_and_engine_identities_are_exact(self):
        for change in ({"tool_version": "2.0.0"}, {"protocol_version": "2"},
                       {"engine_versions": {"parser": "different"}}, {"languages": ["go"]},
                       {"extra": True}):
            with self.subTest(change=change):
                self.assertFalse(probe_tool(self.tool(probe_change=change)).available)

    def test_invalid_completeness_rules_bounds_and_unknown_fields_are_incomplete(self):
        cases = ({"complete": "unknown"}, {"complete": 1}, {"tool_version": "2.0.0"},
                 {"unexpected": True}, {"diagnostics": [{"rule_id": "UNKNOWN", "region": {}}]},
                 {"diagnostics": [{"rule_id": "LOG002", "region": {
                     "start_line": 1, "start_column": 1, "end_line": 99, "end_column": 2}}]})
        for change in cases:
            with self.subTest(change=change):
                self.assertFalse(analyze_snapshot(self.tool(report_change=change), self.target).complete)

    def test_duplicate_wire_keys_and_nonfinite_json_cannot_claim_clean(self):
        for raw in ('{"complete":false,"complete":true}', '{"unexpected":NaN}'):
            with self.subTest(raw=raw):
                self.assertFalse(analyze_snapshot(self.tool(raw=raw), self.target).complete)

    def test_physical_lf_codepoint_bounds_and_partial_failure_metadata(self):
        target = SourceTarget("a.ts", "ready", "typescript", "a😀\u2028b\r\nnext".encode(), "fixture")
        tool = self.tool(report_change={"diagnostics": [{"rule_id": "LOG002", "region": {
            "start_line": 1, "start_column": 2, "end_line": 1, "end_column": 5}}],
                                       "complete": False, "reason": "PARSE_ERROR"})
        report = analyze_snapshot(tool, target)
        self.assertFalse(report.complete)
        self.assertEqual(len(report.diagnostics), 1)
        self.assertEqual(report.diagnostics[0].region.end_column, 5)

    def test_adapter_reproves_source_but_never_guesses_new_lifecycle(self):
        tool = self.tool()
        def git(*args):
            return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                                  capture_output=True, text=True).stdout.strip()
        git("init", "-q")
        git("config", "user.name", "Native Protocol Fixture")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "core.autocrlf", "false")
        (self.root / "a.ts").write_bytes(self.target.content)
        git("add", "a.ts")
        git("commit", "-qm", "fixture")
        head = git("rev-parse", "HEAD")
        adapter = NativeAdapter(tool, repo_root=self.root, source_sha=head)
        record = scan(self.root, ["a.ts"], adapters=(adapter,))
        self.assertEqual(record["exit_code"], 2)
        self.assertEqual(record["findings"][0]["lifecycle_class"], "UNKNOWN")
        self.assertEqual(record["findings"][0]["source"]["status"], "VERIFIED")
        (self.root / "a.ts").write_bytes(b"other = 2\n")
        stale = scan(self.root, ["a.ts"], adapters=(adapter,))
        self.assertEqual(stale["exit_code"], 2)
        self.assertEqual(stale["findings"][0]["source"]["status"], "SOURCE_UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
