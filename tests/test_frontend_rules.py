"""Real ESTree context checks; unavailable setup is never silently accepted."""
import os
from pathlib import Path
import shutil
import unittest

from devsift.inventory import SourceTarget
from devsift.native_host import analyze_snapshot, probe_tool
from devsift.typescript_adapter import make_tool


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_NATIVE') == '1', 'requires explicit native setup')
class FrontendRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.tool = make_tool(str(Path(os.environ.get('DEVSIFT_NODE_EXECUTABLE') or shutil.which('node')).resolve()),
                             Path(os.environ.get('DEVSIFT_FRONTEND_PACKAGE', root / 'native/frontend')).resolve())
        if not probe_tool(cls.tool).available:
            raise AssertionError('Pinned native frontend setup required')

    def report(self, source, path='src/client.ts'):
        report = analyze_snapshot(self.tool, SourceTarget(path, 'ready', 'typescript', source.encode(), 'fixture'))
        self.assertTrue(report.complete)
        return report

    def test_actual_fetch_and_imported_axios_alias_only(self):
        source = "import http from 'axios'; fetch('https://api.example.test/a'); http.get('https://api.example.test/b');"
        self.assertEqual([d.rule_id for d in self.report(source).diagnostics], ['HC001', 'HC001'])

    def test_endpoint_context_negatives_and_shadowing(self):
        sources = ["const url='https://api.example.test';",
                   "const fetch=(x:string)=>x; fetch('https://api.example.test');",
                   "import http from 'other'; http.get('https://api.example.test');",
                   "import http from 'axios'; function f(http:any){http.get('https://api.example.test');}",
                   "fetch(process.env.API_URL);",
                   "// fetch('https://api.example.test');\nconst x=1;",
                   "const text=\"fetch('https://api.example.test')\";"]
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(self.report(source).diagnostics, ())
        for path in ['src/environment.ts', 'config/network.ts', 'src/client.spec.ts', 'fixtures/client.ts']:
            self.assertEqual(self.report("fetch('https://api.example.test')", path).diagnostics, ())

    def test_credentials_assignments_properties_and_fields(self):
        for source in ["const apiKey='fixtureSensitiveValue';", "client.password='fixtureSensitiveValue';",
                       "const options={access_token:'fixtureSensitiveValue'};",
                       "class C {private clientSecret='fixtureSensitiveValue';}",
                       "options['apiKey']='fixtureSensitiveValue';"]:
            with self.subTest(source=source):
                report = self.report(source)
                self.assertEqual([d.rule_id for d in report.diagnostics], ['HC002'])
                self.assertNotIn('fixtureSensitiveValue', repr(report))
        self.assertEqual([d.rule_id for d in self.report("const apiKey='fixtureSensitiveValue';", 'tests/client.spec.ts').diagnostics], ['HC002'])

    def test_placeholders_env_and_computed_names_are_not_verified_secrets(self):
        for source in ["const apiKey='YOUR_API_KEY';", "const password='';", "const secretKey=process.env.SECRET;",
                       "const config={token:'example'};", "const options={[apiKey]:'ordinary'};",
                       "options[apiKey]='ordinary';", "const url='https://api.example.test';"]:
            with self.subTest(source=source):
                self.assertEqual(self.report(source).diagnostics, ())

    def test_physical_unicode_region_and_no_source_echo(self):
        source = "/* 😀\u2028 */\r\nfetch('https://api.example.test');"
        finding = self.report(source).diagnostics[0]
        self.assertEqual(finding.region.start_line, 2)
        self.assertEqual(source.split('\n')[1][finding.region.start_column-1:finding.region.end_column-1], "'https://api.example.test'")
