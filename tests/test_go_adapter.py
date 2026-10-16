"""Real Go AST fixture tests, enabled only after explicit trusted native setup."""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from devsift.go_adapter import make_tool
from devsift.inventory import SourceTarget
from devsift.native_host import analyze_snapshot, probe_tool, source_offsets

ROOT = Path(__file__).resolve().parents[1]


class GoConfigurationTests(unittest.TestCase):
    def test_missing_or_relative_native_binary_fails_explicitly(self):
        with self.assertRaises(ValueError):
            make_tool('relative-program')
        with self.assertRaises(ValueError):
            make_tool(str(ROOT / '.devsift/local/nonexistent-native-go'))


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_NATIVE') == '1', 'requires explicit native setup')
class GoNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = os.environ.get('DEVSIFT_GO_ARTIFACT') or str(
            ROOT / '.devsift/local/tools/go' / ('devsift-go.exe' if os.name == 'nt' else 'devsift-go'))
        cls.tool = make_tool(str(Path(executable).resolve()))
        probe = probe_tool(cls.tool)
        if not probe.available:
            raise AssertionError('Actual pinned Go helper probe failed: ' + probe.reason)

    def analyze(self, source, path='src/service.go'):
        return analyze_snapshot(self.tool, SourceTarget(path, 'ready', 'go', source.encode(), 'fixture'))

    def snippets(self, source, report):
        return [(d.rule_id, source[slice(*source_offsets(source, d.region))]) for d in report.diagnostics]

    def test_actual_aliases_endpoint_debug_and_error_parameter_regions(self):
        source = ('package p\nimport (h "net/http"; f "fmt")\n'
                  'func run(err error) { h.Get("https://production.example/api"); '
                  'if err != nil {} ; f.Println("debug") }\n')
        report = self.analyze(source)
        self.assertTrue(report.complete, report.reason)
        self.assertEqual(self.snippets(source, report), [
            ('HC001', '"https://production.example/api"'), ('LOG002', 'if err != nil {}'),
            ('LOG001', 'f.Println("debug")')])

    def test_import_shadowing_and_nonstandard_package_lookalikes_are_excluded(self):
        for source in (
            'package p; import "fmt"; func run(fmt interface{ Println(string) }) { fmt.Println("x") }',
            'package p; import "net/http"; func run(http interface{ Get(string) }) { http.Get("https://prod.example") }',
            'package p; import f "example.invalid/fmt"; func run() { f.Println("x") }',
            'package p; import h "example.invalid/http"; func run() { h.Get("https://prod.example") }',
            'package p; import "fmt"; func run() { fmt := struct{ Println func(string) }{}; fmt.Println("x") }',
        ):
            with self.subTest(source=source):
                report = self.analyze(source)
                self.assertTrue(report.complete, report.reason)
                self.assertEqual(report.diagnostics, ())

    def test_comments_strings_constants_tests_and_configuration_exclude_endpoint_false_positives(self):
        source = ('package p; const endpoint = "https://schema.example"; '
                  'var example = `fmt.Println("x"); if err != nil {}`; '
                  '// http.Get("https://comment.example")\n')
        self.assertEqual(self.analyze(source).diagnostics, ())
        endpoint = 'package p; import "net/http"; func f(){ http.Get("https://prod.example") }'
        for path in ('testdata/sample.go', 'tests/sample.go', 'src/client_test.go', 'config/sample.go'):
            report = self.analyze(endpoint, path)
            self.assertTrue(report.complete)
            self.assertEqual(report.diagnostics, ())

    def test_empty_error_branch_requires_grounded_error_not_variable_name(self):
        sources = (
            ('package p; func f(err *int) { if err != nil {} }', ()),
            ('package p; type error *int; func f(err error) { if err != nil {} }', ()),
            ('package p; func f(err error) { if err == nil {} }', ()),
            ('package p; func f(err error) { if err != nil { return } }', ()),
            ('package p; import "errors"; func f() { err := errors.New("x"); if err != nil {} }', ('LOG002',)),
            ('package p; import "fmt"; func f() { err := fmt.Errorf("x"); if err != nil {} }', ('LOG002',)),
            ('package p; import "errors"; func f() { if err := errors.New("x"); err != nil {} }', ('LOG002',)),
            ('package p; import "errors"; func f(errors interface{New(string) error}) { err := errors.New("x"); if err != nil {} }', ()),
            ('package p; import "errors"; func f() { var value interface{} = errors.New("x"); value = new(int); if value != nil {} }', ()),
        )
        for source, expected in sources:
            with self.subTest(source=source):
                report = self.analyze(source)
                self.assertTrue(report.complete, report.reason)
                self.assertEqual(tuple(d.rule_id for d in report.diagnostics), expected)

    def test_physical_crlf_unicode_codepoint_columns_and_line_directive(self):
        source = ('package p\r\nimport "fmt"\r\n//line fake.go:900\r\n'
                  'func f(){ _ = "😀"; /*\u2028*/ fmt.Println("x") }\r\n')
        report = self.analyze(source)
        self.assertTrue(report.complete, report.reason)
        self.assertEqual(self.snippets(source, report), [('LOG001', 'fmt.Println("x")')])
        self.assertEqual(report.diagnostics[0].region.start_line, 4)
        self.assertEqual(report.diagnostics[0].region.start_column, source.split('\n')[3].index('fmt') + 1)

    def test_parse_failure_is_incomplete(self):
        report = self.analyze('package p; func broken( {')
        self.assertFalse(report.complete)
        self.assertEqual(report.reason, 'PARSE_ERROR')
        self.assertEqual(report.diagnostics, ())

    def test_binary_integrity_pin_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / Path(self.tool.process.executable).name
            shutil.copy2(self.tool.process.executable, executable)
            tool = make_tool(str(executable))
            with executable.open('ab') as stream:
                stream.write(b'changed')
            probe = probe_tool(tool)
            self.assertFalse(probe.available)
            self.assertEqual(probe.reason, 'ARTIFACT_UNAVAILABLE_OR_CHANGED')


if __name__ == '__main__':
    unittest.main()
