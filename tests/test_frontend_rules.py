"""Real ESTree context checks; unavailable setup is never silently accepted."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from devsift.inventory import SourceTarget
from devsift.native_host import NativeAdapter, analyze_snapshot, probe_tool
from devsift.scanner import scan
from devsift.evidence import Region, SourceEvidence, verify_source
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

    def test_actual_git_adapter_and_scanner_never_publish_credential_spans(self):
        cases = ["const options={access_token:'fixtureSensitiveValue'};",
                 "const apiKey='fixtureSensitiveValue';",
                 "client.authToken='fixtureSensitiveValue';",
                 "class C { clientSecret='fixtureSensitiveValue'; }",
                 "options['privateKey']='fixtureSensitiveValue';",
                 "const api\\u004bey='fixtureSensitiveValue';"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            git('init', '-q')
            for index, source in enumerate(cases):
                (root / f'case{index}.ts').write_text(source, encoding='utf-8')
            git('add', '*.ts')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
            sha = git('rev-parse', 'HEAD')
            adapter = NativeAdapter(self.tool, repo_root=root, source_sha=sha)
            for index, source in enumerate(cases):
                path = f'case{index}.ts'
                target = SourceTarget(path, 'ready', 'typescript', source.encode(), 'fixture')
                outcome = adapter.analyze(target)
                self.assertTrue(outcome.complete)
                self.assertEqual(len(outcome.findings), 1)
                self.assertEqual(outcome.findings[0].source.before, '[REDACTED]')
                self.assertEqual(outcome.findings[0].source.location.source_sha, sha)
                restored = SourceEvidence.from_dict(outcome.findings[0].source.to_dict(), repo_root=root)
                self.assertEqual(restored.status, 'VERIFIED')
                self.assertEqual(restored.before, '[REDACTED]')
            record = scan(root, adapters=(adapter,))
            self.assertEqual(len(record['findings']), len(cases))
            self.assertNotIn('fixtureSensitiveValue', json.dumps(record))
            self.assertEqual(record['exit_code'], 2)
            # Cropped evidence preserves immutable physical coordinates while
            # withholding every part of the credential, even without its name.
            source = cases[0]
            offset = source.index('fixtureSensitiveValue') + 3
            evidence = verify_source(root, 'local', sha, 'case0.ts',
                                     Region(1, offset+1, 1, offset+5), sensitive=True)
            self.assertEqual(evidence.status, 'VERIFIED')
            self.assertEqual(evidence.before, '[REDACTED]')
