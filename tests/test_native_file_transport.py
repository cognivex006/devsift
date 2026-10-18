"""Streaming native transport: complete snapshots and individually validated records."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from devsift.inventory import SourceTarget
from devsift.native_host import ToolDefinition, analyze_snapshot, file_digest, probe_tool
from devsift.process_runner import ProcessSpec


class NativeFileTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def tool(self, action="normal", timeout=10):
        helper = self.root / "helper.py"
        helper.write_text('''import json,sys,time,os
from pathlib import Path
probe = {"protocol_version":"1", "tool_id":"fixture", "tool_version":"1",
 "languages":["typescript"], "engine_versions":{}, "transports":["inline","files"]}
if sys.argv[-1] == '--probe':
 print(json.dumps(probe)); raise SystemExit()
r=json.load(sys.stdin)
assert sys.argv[-1]=='--analyze-files'
assert Path(r['source_file']).is_absolute()
source=Path(r['source_file']).read_bytes()
assert source.startswith(b'x')
p=Path(r['diagnostics_file'])
action=ACTION
if action=='timeout': time.sleep(10)
if action=='slow': time.sleep(.7)
count=1 if action=='eof_cr' else 1201
if action=='symlink':
 p.unlink(); p.symlink_to(r['source_file'])
elif action=='directory':
 p.unlink(); p.mkdir()
else:
 with p.open('wb') as f:
  for i in range(count):
   d={"rule_id":"LOG002","region":{"start_line":i+1,"start_column":1,"end_line":i+1,"end_column":2}}
   if action=='duplicate': d['region']['start_line']=d['region']['end_line']=1
   if action=='coordinate': d['region']['end_column']=999
   if action=='eof_cr': d['region']['end_column']=3
   f.write((json.dumps(d)+'\\n').encode())
  if action=='trailing': f.write(b'garbage')
  if action=='huge_line': f.write(b' '*16385+b'\\n')
  if action=='invalid_utf8': f.write(b'\\xff\\n')
 if action=='replaced':
  replacement=p.with_name('replacement'); replacement.write_bytes(p.read_bytes()); replacement.replace(p)
 if action=='bad_count': count+=1
print(json.dumps({"protocol_version":"1", "tool_id":"fixture", "tool_version":"1",
 "complete":True,"reason":"COMPLETED","metadata":{},"diagnostic_count":count}))
'''.replace('ACTION', repr(action)), encoding='utf-8')
        return ToolDefinition('fixture', '1', ('typescript',),
                              ProcessSpec(str(Path(sys.executable).resolve()), (str(helper),), timeout_seconds=timeout),
                              file_digest(sys.executable), ((str(helper), file_digest(helper)),))

    def target(self):
        return SourceTarget('large.ts', 'ready', 'typescript', b'x\n' * 1201 + b'/' * 2_100_000, 'fixture')

    def test_large_source_and_every_diagnostic_survive_small_process_limits(self):
        tool = self.tool()
        self.assertEqual(probe_tool(tool).transports, ('inline', 'files'))
        report = analyze_snapshot(tool, self.target())
        self.assertTrue(report.complete)
        self.assertEqual(len(report.diagnostics), 1201)
        self.assertEqual(report.diagnostics[-1].region.end_line, 1201)
        self.assertFalse((self.root / 'large.ts').exists())

    def test_invalid_file_records_counts_and_nonregular_output_fail_closed(self):
        for action in ('duplicate', 'coordinate', 'bad_count', 'trailing', 'huge_line', 'invalid_utf8', 'directory', 'replaced'):
            with self.subTest(action=action):
                self.assertFalse(analyze_snapshot(self.tool(action), self.target()).complete)

    @unittest.skipIf(os.name == 'nt', 'Creating Windows symbolic links requires a separately configured privilege')
    def test_symlink_output_is_rejected(self):
        self.assertFalse(analyze_snapshot(self.tool('symlink'), self.target()).complete)

    def test_timeout_and_integrity_fail_without_partial_clean_result(self):
        self.assertFalse(analyze_snapshot(self.tool('timeout', timeout=.3), self.target()).complete)
        tool = self.tool()
        Path(tool.artifacts[0][0]).write_text('raise SystemExit(0)')
        self.assertFalse(analyze_snapshot(tool, self.target()).complete)

    def test_interruption_propagates_and_removes_private_snapshot_files(self):
        tool = self.tool()
        directories = []
        def interrupt(_process, *, stdin, redactor):
            request = json.loads(stdin)
            source = Path(request['source_file'])
            directories.append(source.parent)
            self.assertTrue(source.is_file())
            self.assertTrue(Path(request['diagnostics_file']).is_file())
            self.assertNotEqual(source.parent, self.root)
            raise KeyboardInterrupt()
        with patch('devsift.native_host.run_process', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                analyze_snapshot(tool, self.target(), transports=('inline', 'files'))
        self.assertEqual(len(directories), 1)
        self.assertFalse(directories[0].exists())

    def test_explicit_complete_run_outlives_configured_process_deadline(self):
        tool = self.tool('slow', timeout=.3)
        report = analyze_snapshot(tool, self.target(), transports=('inline', 'files'), wait_for_completion=True)
        self.assertTrue(report.complete)
        self.assertEqual(len(report.diagnostics), 1201)

    def test_unterminated_final_carriage_return_is_a_source_codepoint(self):
        target = SourceTarget('last.ts', 'ready', 'typescript', b'x\r', 'fixture')
        report = analyze_snapshot(self.tool('eof_cr'), target)
        self.assertTrue(report.complete)
        self.assertEqual(report.diagnostics[0].region.end_column, 3)

    def test_invalid_transport_capabilities_are_rejected(self):
        tool = self.tool()
        helper = Path(tool.artifacts[0][0])
        helper.write_text(helper.read_text().replace('["inline","files"]', '["files","unknown"]'))
        tool = replace(tool, artifacts=((str(helper), file_digest(helper)),))
        self.assertFalse(probe_tool(tool).available)


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_NATIVE') == '1', 'explicit native setup required')
class RealNativeFileTransportTests(unittest.TestCase):
    def test_all_native_helpers_analyze_large_source_and_more_than_1000_cases(self):
        import shutil
        from devsift.dotnet_adapter import make_tool as dotnet_tool
        from devsift.go_adapter import make_tool as go_tool
        from devsift.sql_adapter import make_tool as sql_tool
        from devsift.typescript_adapter import make_tool as frontend_tool
        root = Path(__file__).resolve().parents[1]
        output = root / '.devsift/local/tools'
        padding = '/*' + 'x' * 2_100_000 + '*/\n'
        configurations = (
            (dotnet_tool(str(Path(shutil.which('dotnet')).resolve()), output / 'dotnet'), 'large.cs', 'csharp',
             'using System; class C { static void Main() {\n' + 'Console.WriteLine(1);\n' * 1001 + '} }\n' + padding, None),
            (sql_tool(str(Path(shutil.which('dotnet')).resolve()), output / 'sql'), 'large.sql', 'sql',
             "DECLARE @sql nvarchar(max)=N'SELECT * FROM dbo.T WHERE id=' + @input;\n" + 'EXEC(@sql);\n' * 1001 + padding, 'tsql160'),
            (frontend_tool(str(Path(shutil.which('node')).resolve()), root / 'native/frontend'), 'large.ts', 'typescript',
             'try {} catch {}\n' * 1001 + padding, None),
            (go_tool(str((output / 'go' / ('devsift-go.exe' if os.name == 'nt' else 'devsift-go')).resolve())), 'large.go', 'go',
             'package main\nimport "fmt"\nfunc main() {\n' + 'fmt.Println(1)\n' * 1001 + '}\n' + padding, None),
        )
        for tool, path, language, source, dialect in configurations:
            with self.subTest(language=language):
                tool = replace(tool, process=replace(tool.process, timeout_seconds=120))
                probe = probe_tool(tool)
                self.assertTrue(probe.available)
                self.assertIn('files', probe.transports)
                report = analyze_snapshot(tool, SourceTarget(path, 'ready', language, source.encode(), 'fixture'), dialect=dialect)
                self.assertTrue(report.complete, report.reason)
                self.assertEqual(len(report.diagnostics), 1001)


if __name__ == '__main__':
    unittest.main()
