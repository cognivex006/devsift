"""Actual ESLint/TypeScript parser checks enabled by explicit native setup."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from devsift.inventory import SourceTarget
from devsift.native_host import NativeAdapter, analyze_snapshot, probe_tool
from devsift.scanner import scan
from devsift.typescript_adapter import make_tool


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_NATIVE') == '1', 'requires explicit native setup')
class TypeScriptAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        node = os.environ.get('DEVSIFT_NODE_EXECUTABLE') or shutil.which('node')
        if not node:
            raise AssertionError('Native frontend tests require Node')
        package = Path(os.environ.get('DEVSIFT_FRONTEND_PACKAGE', str(ROOT / 'native/frontend')))
        cls.tool = make_tool(str(Path(node).resolve()), package.resolve())
        if not probe_tool(cls.tool).available:
            raise AssertionError('Pinned frontend packages must be installed before native tests')

    def report(self, source, path='src/sample.ts', language='typescript'):
        return analyze_snapshot(self.tool, SourceTarget(path, 'ready', language, source.encode('utf-8'), 'fixture'))

    def test_real_pinned_parser_and_angular_next_jsx_inputs(self):
        cases = [
            ('src/component.ts', 'typescript', "@Component({selector:'x'}) export class C { f(){try{work()}catch{}} }"),
            ('src/page.tsx', 'typescript', "export default function Page(){try{return <main>ok</main>}catch{}}"),
            ('src/page.jsx', 'javascript', "export function Page(){try{return <div>ok</div>}catch{}}"),
        ]
        for path, language, source in cases:
            with self.subTest(path=path):
                report = self.report(source, path, language)
                self.assertTrue(report.complete)
                self.assertEqual([finding.rule_id for finding in report.diagnostics], ['LOG002'])

    def test_comments_literals_and_nonempty_catches_are_not_empty_catch_findings(self):
        report = self.report("// try{}catch{}\nconst text='try{}catch{}';try{work()}catch(e){throw e}")
        self.assertTrue(report.complete)
        self.assertEqual(report.diagnostics, ())

    def test_source_inline_disable_cannot_bypass_controlled_rules(self):
        report = self.report("/* eslint-disable devsift/empty-catch */ try{work()}catch{}")
        self.assertTrue(report.complete)
        self.assertEqual(len(report.diagnostics), 1)

    def test_unicode_and_logical_line_separators_keep_physical_source_coordinates(self):
        source = "/* 😀\u2028source */\r\ntry{work()}catch{}"
        report = self.report(source)
        self.assertTrue(report.complete)
        region = report.diagnostics[0].region
        self.assertEqual(region.start_line, 2)
        line = source.split('\n')[1]
        self.assertEqual(line[region.start_column - 1:region.end_column - 1], 'catch{}')

    def test_invalid_syntax_is_incomplete_without_source_echo(self):
        report = self.report("const = privateFixtureSyntaxValue;")
        self.assertFalse(report.complete)
        self.assertEqual(report.reason, 'PARSE_ERROR')
        self.assertNotIn('privateFixtureSyntaxValue', repr(report))

    def test_target_scripts_and_project_configs_are_never_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'must-not-execute'
            (root / 'eslint.config.js').write_text("require('fs').writeFileSync(" + json.dumps(str(marker)) + ",'bad')")
            source = "require('fs').writeFileSync(" + json.dumps(str(marker)) + ",'bad'); try{work()}catch{}"
            (root / 'source.ts').write_text(source)
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            report = self.report(source)
            self.assertTrue(report.complete)
            self.assertFalse(marker.exists())
            self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, before)

    def test_real_git_bridge_keeps_unknown_lifecycle_and_target_metadata_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            git('init', '-q')
            git('config', 'user.name', 'Frontend Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'core.autocrlf', 'false')
            (root / 'source.ts').write_bytes(b'try{work()}catch{}\n')
            git('add', 'source.ts')
            git('commit', '-qm', 'fixture')
            adapter = NativeAdapter(self.tool, repo_root=root, source_sha=git('rev-parse', 'HEAD'))
            def snapshot():
                return {str(path.relative_to(root)): None if path.is_dir() else path.read_bytes()
                        for path in root.rglob('*')}
            before = snapshot()
            record = scan(root, ['source.ts'], adapters=(adapter,))
            self.assertEqual(record['exit_code'], 2)
            self.assertEqual(record['findings'][0]['source']['status'], 'VERIFIED')
            self.assertEqual(record['findings'][0]['lifecycle_class'], 'UNKNOWN')
            self.assertEqual(snapshot(), before)


if __name__ == '__main__':
    unittest.main()
