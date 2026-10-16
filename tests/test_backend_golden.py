"""Cross-backend acceptance fixtures use real pinned tools, not simulated ASTs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from devsift.dotnet_adapter import make_tool as dotnet_tool
from devsift.go_adapter import make_tool as go_tool
from devsift.inventory import SourceTarget
from devsift.native_host import NativeAdapter, analyze_snapshot, probe_tool, source_offsets
from devsift.registry import RULES
from devsift.scanner import scan

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/backend'


def snapshot(root):
    return {str(p.relative_to(root)): None if p.is_dir() else p.read_bytes() for p in root.rglob('*')}


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_NATIVE') == '1', 'requires explicit real backend setup')
class BackendGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = os.environ.get('DEVSIFT_DOTNET_EXECUTABLE') or shutil.which('dotnet')
        if not executable:
            raise AssertionError('Configured dotnet runtime is required')
        dotnet_directory = Path(os.environ.get('DEVSIFT_ROSLYN_ARTIFACT_DIR', ROOT / '.devsift/local/tools/dotnet')).resolve()
        go_executable = os.environ.get('DEVSIFT_GO_ARTIFACT') or str(
            ROOT / '.devsift/local/tools/go' / ('devsift-go.exe' if os.name == 'nt' else 'devsift-go'))
        cls.tools = {'csharp': dotnet_tool(str(Path(executable).resolve()), dotnet_directory),
                     'go': go_tool(str(Path(go_executable).resolve()))}
        for language, tool in cls.tools.items():
            probe = probe_tool(tool)
            if not probe.available:
                raise AssertionError('Actual pinned backend probe failed for ' + language + ': ' + probe.reason)

    def test_static_golden_rule_severity_region_and_snippet_manifest(self):
        manifest = json.loads((FIXTURES / 'expected.json').read_text(encoding='utf-8'))
        before = snapshot(FIXTURES)
        for case in manifest:
            with self.subTest(fixture=case['fixture'], target=case['target']):
                source = (FIXTURES / case['fixture']).read_text(encoding='utf-8')
                target = SourceTarget(case['target'], 'ready', case['language'], source.encode(), 'fixture')
                report = analyze_snapshot(self.tools[case['language']], target)
                self.assertTrue(report.complete, report.reason)
                actual = [{'rule_id': item.rule_id, 'severity': RULES[item.rule_id].severity.value,
                           'region': item.region.to_dict(),
                           'snippet': source[slice(*source_offsets(source, item.region))]}
                          for item in report.diagnostics]
                self.assertEqual(actual, case['diagnostics'])
        self.assertEqual(snapshot(FIXTURES), before)

    def test_real_git_bridge_keeps_unknown_and_stale_evidence_incomplete_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {'service.cs': ('csharp', (FIXTURES / 'positive.cs').read_bytes()),
                       'service.go': ('go', (FIXTURES / 'positive.go').read_bytes())}
            for path, (_, content) in sources.items():
                (root / path).write_bytes(content)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True).stdout
            git('init', '-q')
            git('config', 'user.name', 'Backend Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'core.autocrlf', 'false')
            git('add', 'service.cs', 'service.go')
            git('commit', '-qm', 'fixture')
            sha = git('rev-parse', 'HEAD').decode().strip()
            adapters = tuple(NativeAdapter(tool, repo_root=root, source_sha=sha) for tool in self.tools.values())
            before = snapshot(root)
            record = scan(root, sorted(sources), adapters=adapters)
            self.assertEqual(record['exit_code'], 2)
            self.assertEqual(record['enforced_count'], 0)
            self.assertEqual(len(record['findings']), 6)
            self.assertTrue(all(f['source']['status'] == 'VERIFIED' for f in record['findings']))
            self.assertTrue(all(f['lifecycle_class'] == 'UNKNOWN' for f in record['findings']))
            self.assertTrue(all(f['enforcement'] == 'incomplete' for f in record['findings']))
            self.assertEqual(snapshot(root), before)
            # The old commit cannot prove a snapshot that merely shares a snippet.
            for path, (_, content) in sources.items():
                (root / path).write_bytes(content + b'// current snapshot differs\n')
            changed = snapshot(root)
            stale = scan(root, sorted(sources), adapters=adapters)
            self.assertEqual(stale['exit_code'], 2)
            self.assertEqual(stale['enforced_count'], 0)
            self.assertTrue(stale['findings'])
            self.assertTrue(all(f['source']['status'] == 'SOURCE_UNRESOLVED' for f in stale['findings']))
            self.assertEqual(snapshot(root), changed)

    def test_source_startup_side_effects_are_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'SOURCE_WAS_EXECUTED'
            literal = json.dumps(str(marker))
            sources = {
                'csharp': 'class Program { static void Main() { System.IO.File.WriteAllText(' + literal + ', "bad"); } }',
                'go': 'package main; import "os"; func init(){ os.WriteFile(' + literal + ', []byte("bad"),0600) }; func main(){}',
            }
            for language, source in sources.items():
                with self.subTest(language=language):
                    target = SourceTarget('program.cs' if language == 'csharp' else 'program.go',
                                          'ready', language, source.encode(), 'fixture')
                    report = analyze_snapshot(self.tools[language], target)
                    self.assertTrue(report.complete, report.reason)
                    self.assertEqual(report.diagnostics, ())
                    self.assertFalse(marker.exists())
                    self.assertEqual(snapshot(root), {})

    def test_both_parser_failures_stay_incomplete_and_have_no_partial_findings(self):
        for language, source in (('csharp', 'class Broken { void Run( {'), ('go', 'package broken; func Run( {')):
            with self.subTest(language=language):
                target = SourceTarget('broken.cs' if language == 'csharp' else 'broken.go',
                                      'ready', language, source.encode(), 'fixture')
                report = analyze_snapshot(self.tools[language], target)
                self.assertFalse(report.complete)
                self.assertEqual(report.reason, 'PARSE_ERROR')
                self.assertEqual(report.diagnostics, ())

    def test_physical_unicode_columns_and_directives_match_both_native_engines(self):
        cases = (
            ('csharp', 'using System;\r\n#line 900 "fake.cs"\r\n'
             'class C { void Run(){ _ = "😀"; /*\u2028*/ Console.WriteLine("debug"); } }\r\n',
             'Console.WriteLine("debug")', 3),
            ('go', 'package p\r\nimport "fmt"\r\n//line fake.go:900\r\n'
             'func Run(){ _ = "😀"; /*\u2028*/ fmt.Println("debug") }\r\n',
             'fmt.Println("debug")', 4),
        )
        for language, source, snippet, line in cases:
            with self.subTest(language=language):
                target = SourceTarget('physical.cs' if language == 'csharp' else 'physical.go',
                                      'ready', language, source.encode(), 'fixture')
                report = analyze_snapshot(self.tools[language], target)
                self.assertTrue(report.complete, report.reason)
                self.assertEqual(len(report.diagnostics), 1)
                diagnostic = report.diagnostics[0]
                column = source.split('\n')[line - 1].index(snippet) + 1
                self.assertEqual(diagnostic.rule_id, 'LOG001')
                self.assertEqual(diagnostic.region.to_dict(), {
                    'start_line': line, 'start_column': column,
                    'end_line': line, 'end_column': column + len(snippet)})
                self.assertEqual(source[slice(*source_offsets(source, diagnostic.region))], snippet)


if __name__ == '__main__':
    unittest.main()
