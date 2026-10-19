"""Actual one-time setup -> ordinary CLI scans, without project code execution."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import struct
import unittest
import zipfile

from devsift.analyzer_setup import SetupError, deploy, registered, registry_path

ROOT = Path(__file__).resolve().parents[1]


class AnalyzerSetupTests(unittest.TestCase):
    def setUp(self):
        from test_ci_gate import CiGateTests
        self.fixture = CiGateTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.home = self.fixture.directory / 'user home'
        self.home.mkdir()

    def invoke(self, *args):
        run = subprocess.run([sys.executable, '-P', '-B', '-m', 'devsift', *args],
            cwd=self.fixture.root, env=dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                                           PYTHONPATH=str(ROOT)), capture_output=True, encoding='utf-8', timeout=120)
        self.assertEqual(run.stderr, '')
        value = json.loads(run.stdout)
        self.assertEqual(run.returncode, value['exit_code'])
        return value

    def configure(self):
        value = self.invoke('setup', '--native-manifest', str(self.fixture.manifest),
                            '--native-manifest-digest', self.fixture.digest)
        self.assertEqual(value['exit_code'], 0, value)
        self.assertTrue(value['data']['analysis_ready'])
        return value

    def test_register_once_then_ordinary_scan_and_ci_analyze_real_source(self):
        self.fixture.source('try:\n    work()\nexcept:\n    pass\n')
        before = self.fixture.git('status', '--porcelain=v1')
        self.configure()
        report = self.invoke('scan', '--all', '--summary', '--report-language', 'th')
        self.assertEqual(report['data']['counts']['executed'], 1)
        self.assertEqual(report['data']['finding_count'], 1)
        self.assertTrue(report['data']['report_bundle']['reports_complete'])
        text = Path(report['data']['report_bundle']['report']).read_text(encoding='utf-8')
        self.assertIn('LOG002', text)
        self.assertIn('code.py', text)
        self.assertIn('except', text)
        self.assertTrue(any('\u0e00' <= char <= '\u0e7f' for char in text))
        gate = self.invoke('ci', '--all', '--base', 'HEAD', '--summary')
        self.assertEqual(gate['data']['counts']['executed'], 1)
        self.assertEqual(gate['data']['finding_count'], 1)
        self.assertEqual(self.fixture.git('status', '--porcelain=v1'), before)

    def test_changed_helper_is_not_reapproved_and_old_registration_survives(self):
        self.configure()
        path = registry_path(self.home)
        original = path.read_bytes()
        self.fixture.helper.write_bytes(self.fixture.helper.read_bytes() + b'\n# changed\n')
        denied = self.invoke('setup', '--native-manifest', str(self.fixture.manifest),
                              '--native-manifest-digest', self.fixture.digest)
        self.assertEqual(denied['exit_code'], 2)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.invoke('setup', '--status')['exit_code'], 2)

    def test_invalid_user_registration_fails_closed_and_explicit_pair_overrides(self):
        self.fixture.source('value = 1\n')
        self.configure()
        path = registry_path(self.home)
        path.write_text('{"private":"never-echo-this"}', encoding='utf-8')
        failed = self.invoke('scan', '--all', '--summary')
        self.assertEqual(failed['exit_code'], 2)
        self.assertIn('REGISTERED_ANALYZERS_UNAVAILABLE', {x['code'] for x in failed['errors']})
        self.assertNotIn('never-echo-this', json.dumps(failed))
        explicit = self.invoke('scan', '--all', '--summary', '--native-manifest', str(self.fixture.manifest),
                               '--native-manifest-digest', self.fixture.digest)
        self.assertEqual(explicit['data']['counts']['executed'], 1)

    def test_no_registration_has_a_readable_setup_report_and_no_invented_findings(self):
        self.fixture.source('value = 1\n')
        # Project-local executable configuration must not become trusted setup.
        local = self.fixture.root / '.devsift'
        local.mkdir()
        (local / 'native-manifest.json').write_bytes(self.fixture.manifest.read_bytes())
        result = self.invoke('scan', '--all', '--summary', '--report-language', 'th')
        self.assertEqual(result['exit_code'], 2)
        self.assertEqual(result['data']['finding_count'], 0)
        self.assertEqual(result['data']['counts']['executed'], 0)
        self.assertIn('NO_AVAILABLE_ANALYZER', {x['code'] for x in result['errors']})
        text = Path(result['data']['report_bundle']['report']).read_text(encoding='utf-8')
        self.assertIn('devsift', text)
        self.assertIn('NO_AVAILABLE_ANALYZER', text.replace('\\_', '_'))
        self.assertIsNone(registered(self.home))

    def test_malicious_archives_never_escape_or_activate(self):
        self.configure()
        original = registry_path(self.home).read_bytes()
        for member in ('../escaped', '/absolute', 'C:/drive', 'nested/CON', 'x/../escaped',
                       'nested/COM\u00b9', 'nested/LPT\u00b2.txt', 'nested/COM\u00b3'):
            with self.subTest(member=member):
                archive = self.fixture.directory / 'unsafe.zip'
                with zipfile.ZipFile(archive, 'w') as bundle:
                    bundle.writestr(member, b'not code')
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                with self.assertRaises((SetupError, ValueError)):
                    deploy(archive, digest, home=self.home)
                self.assertEqual(registry_path(self.home).read_bytes(), original)
                self.assertFalse((self.fixture.directory / 'escaped').exists())

    def test_tampered_archive_refused_before_extracting(self):
        archive = self.fixture.directory / 'wrong.zip'
        archive.write_bytes(b'not a trusted archive')
        with self.assertRaises(SetupError):
            deploy(archive, 'a' * 64, home=self.home)
        self.assertFalse(registry_path(self.home).exists())

    def test_malformed_portable_argv_returns_safe_cli_error_and_keeps_registration(self):
        self.configure()
        original = registry_path(self.home).read_bytes()
        from devsift.analyzer_setup import platform_id
        for argv in ([None], 'not-a-list', {'key': 'value'}):
            with self.subTest(argv=argv):
                definition = json.loads(self.fixture.manifest.read_bytes())['tools'][0]['definition']
                definition['process']['argv'] = argv
                data = {'schema_version': '1', 'platform': platform_id(),
                        'tools': [{'definition': definition, 'dialect': None}] * 4}
                archive = self.fixture.directory / 'malformed.zip'
                with zipfile.ZipFile(archive, 'w') as bundle:
                    bundle.writestr('manifest-template.json', json.dumps(data))
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                denied = self.invoke('setup', '--analyzer-bundle', str(archive), '--bundle-digest', digest)
                self.assertEqual(denied['exit_code'], 2)
                self.assertEqual(denied['errors'][0]['code'], 'ANALYZER_SETUP_UNAVAILABLE')
                self.assertEqual(registry_path(self.home).read_bytes(), original)

    def test_unsupported_and_corrupt_zip_streams_return_safe_errors(self):
        self.configure()
        original = registry_path(self.home).read_bytes()
        archive = self.fixture.directory / 'unsupported.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('manifest-template.json', b'{}' * 500)
        raw = bytearray(archive.read_bytes())
        central = raw.index(b'PK\x01\x02')
        unsupported = bytearray(raw)
        struct.pack_into('<H', unsupported, 8, 99)
        struct.pack_into('<H', unsupported, central + 10, 99)
        corrupt = bytearray(raw)
        start = 30 + struct.unpack_from('<H', raw, 26)[0] + struct.unpack_from('<H', raw, 28)[0]
        corrupt[start] ^= 0xff
        for body in (unsupported, corrupt):
            archive.write_bytes(body)
            denied = self.invoke('setup', '--analyzer-bundle', str(archive),
                                 '--bundle-digest', hashlib.sha256(body).hexdigest())
            self.assertEqual(denied['exit_code'], 2)
            self.assertEqual(denied['errors'][0]['code'], 'ANALYZER_SETUP_UNAVAILABLE')
            self.assertEqual(registry_path(self.home).read_bytes(), original)
