"""Real pinned Roslyn tests: opt in after explicitly building the trusted helper."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from devsift.dotnet_adapter import make_tool
from devsift.inventory import SourceTarget
from devsift.native_host import NativeAdapter, analyze_snapshot, probe_tool, source_offsets

ROOT = Path(__file__).resolve().parents[1]


class DotnetConfigurationTests(unittest.TestCase):
    def test_requires_explicit_built_artifacts_and_absolute_paths(self):
        with self.assertRaises(ValueError):
            make_tool('dotnet', Path('relative'))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'Pinned Roslyn artifacts unavailable'):
                make_tool(str(Path(directory) / 'missing'), Path(directory))


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_NATIVE') == '1', 'requires explicit native setup')
class RoslynNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = os.environ.get('DEVSIFT_DOTNET_EXECUTABLE') or shutil.which('dotnet')
        if not executable:
            raise AssertionError('Configured dotnet executable required')
        artifacts = Path(os.environ.get('DEVSIFT_ROSLYN_ARTIFACT_DIR', ROOT / '.devsift/local/tools/dotnet')).resolve()
        cls.tool = make_tool(str(Path(executable).resolve()), artifacts)
        probe = probe_tool(cls.tool)
        if not probe.available:
            raise AssertionError('Pinned actual Roslyn probe failed: ' + probe.reason)

    def analyze(self, source, path='src/Service.cs'):
        return analyze_snapshot(self.tool, SourceTarget(path, 'ready', 'csharp', source.encode('utf-8'), 'fixture'))

    def snippets(self, source, report):
        return [(item.rule_id, source[slice(*source_offsets(source, item.region))]) for item in report.diagnostics]

    def test_actual_probe_and_runtime_endpoint_catch_console_spans(self):
        source = ('using System; using System.Net.Http; class C { async System.Threading.Tasks.Task M() { '
                  'using var client = new HttpClient(); await client.GetAsync("https://production.example/api"); '
                  'try { throw new Exception(); } catch(Exception) {} Console.WriteLine("debug"); }}')
        report = self.analyze(source)
        self.assertTrue(report.complete, report.reason)
        self.assertEqual(self.snippets(source, report), [
            ('HC001', '"https://production.example/api"'), ('LOG002', 'catch(Exception) {}'),
            ('LOG001', 'Console.WriteLine("debug")')])

    def test_framework_named_source_lookalikes_do_not_prove_runtime_calls(self):
        source = ('namespace System { class Console { public static void WriteLine(string s) {} } } '
                  'namespace System.Net.Http { class HttpClient { public void GetAsync(string s) {} } } '
                  'class C { void M() { System.Console.WriteLine("debug"); '
                  'new System.Net.Http.HttpClient().GetAsync("https://production.example/api"); }}')
        report = self.analyze(source)
        self.assertTrue(report.complete, report.reason)
        self.assertEqual(report.diagnostics, ())

    def test_comments_strings_constants_configuration_and_tests_are_not_endpoint_findings(self):
        source = ('using System.Net.Http; class C { const string Protocol = "https://schema.example"; '
                  'void M() { var example = "Console.WriteLine(fake)"; '
                  '// catch(Exception) {}\n/* client.GetAsync("https://fake.example") */ } }')
        self.assertEqual(self.analyze(source).diagnostics, ())
        endpoint = ('using System.Net.Http; class C { void M() { '
                    'new HttpClient().GetAsync("https://production.example/api"); }}')
        for path in ('tests/Fixture.cs', 'src/ClientTests.cs', 'config/Fixture.cs'):
            report = self.analyze(endpoint, path)
            self.assertTrue(report.complete)
            self.assertEqual(report.diagnostics, ())
        options = endpoint.replace('class C', 'class ClientOptions')
        self.assertEqual(self.analyze(options).diagnostics, ())

    def test_cancellation_and_nonempty_catch_are_not_empty_catch_findings(self):
        source = ('using System; using System.Threading.Tasks; class C { void M() { '
                  'try {} catch(OperationCanceledException) {} '
                  'try {} catch(TaskCanceledException) {} try {} catch(Exception) { throw; } }}')
        report = self.analyze(source)
        self.assertTrue(report.complete)
        self.assertEqual(report.diagnostics, ())

    def test_source_named_cancellation_type_does_not_suppress_empty_catch(self):
        source = ('namespace System { class OperationCanceledException : Exception {} } '
                  'class C { void M() { try {} catch(System.OperationCanceledException) {} }}')
        report = self.analyze(source)
        self.assertTrue(report.complete)
        self.assertEqual([d.rule_id for d in report.diagnostics], ['LOG002'])

    def test_syntax_errors_are_incomplete(self):
        report = self.analyze('class C { void M( {')
        self.assertFalse(report.complete)
        self.assertEqual(report.reason, 'PARSE_ERROR')
        self.assertEqual(report.diagnostics, ())

    def test_factory_pins_every_trusted_helper_and_roslyn_artifact(self):
        self.assertEqual(len(self.tool.artifacts), 5)
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)
            for path, _ in self.tool.artifacts:
                shutil.copy2(path, copied / Path(path).name)
            tool = make_tool(self.tool.process.executable, copied)
            assembly = copied / 'Microsoft.CodeAnalysis.CSharp.dll'
            with assembly.open('ab') as stream:
                stream.write(b'changed')
            probe = probe_tool(tool)
            self.assertFalse(probe.available)
            self.assertEqual(probe.reason, 'ARTIFACT_UNAVAILABLE_OR_CHANGED')

    def test_physical_lf_crlf_emoji_unicode_separator_and_line_directive(self):
        source = ('using System;\r\n#line 800 "not-physical.cs"\r\n'
                  'class C { void M() { var text = "😀"; /*\u2028*/ Console.WriteLine(text); } }\r\n')
        report = self.analyze(source)
        self.assertTrue(report.complete, report.reason)
        self.assertEqual(self.snippets(source, report), [('LOG001', 'Console.WriteLine(text)')])
        region = report.diagnostics[0].region
        self.assertEqual(region.start_line, 3)
        self.assertEqual(region.start_column, source.split('\n')[2].index('Console') + 1)

    def test_actual_native_adapter_uses_verified_source_and_default_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = 'using System; class C { void M() { Console.WriteLine("debug"); } }\n'
            (root / 'Service.cs').write_bytes(source.encode())
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True).stdout
            git('init', '-q')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'core.autocrlf', 'false')
            git('add', 'Service.cs')
            git('commit', '-qm', 'fixture')
            sha = git('rev-parse', 'HEAD').decode().strip()
            adapter = NativeAdapter(self.tool, repo_root=root, source_sha=sha)
            before = {str(p.relative_to(root)): None if p.is_dir() else p.read_bytes() for p in root.rglob('*')}
            outcome = adapter.analyze(SourceTarget('Service.cs', 'ready', 'csharp', source.encode(), 'fixture'))
            self.assertTrue(outcome.complete)
            self.assertEqual(len(outcome.findings), 1)
            self.assertEqual(outcome.findings[0].source.status, 'VERIFIED')
            self.assertEqual(outcome.findings[0].lifecycle_class, 'UNKNOWN')
            self.assertEqual(before, {str(p.relative_to(root)): None if p.is_dir() else p.read_bytes()
                                      for p in root.rglob('*')})


if __name__ == '__main__':
    unittest.main()
