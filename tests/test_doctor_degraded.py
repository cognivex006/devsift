"""Degraded host matrix using existing doctor fixtures and real trusted probes."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_doctor as discovery_fixtures
from devsift.doctor import run_doctor
from devsift.native_host import file_digest


ROOT = Path(__file__).resolve().parents[1]
ALL_LANGUAGES = ('csharp', 'go', 'javascript', 'python', 'sql', 'typescript')


class DegradedDoctorTests(unittest.TestCase):
    def setUp(self):
        # Compose the existing fixture owner without inheriting/re-running its tests.
        self.fixture = discovery_fixtures.DoctorDiscoveryTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def assert_incomplete(self, record):
        self.assertEqual(record['command'], 'doctor')
        self.assertEqual(record['status'], 'incomplete')
        self.assertEqual(record['exit_code'], 2)
        self.assertFalse(record['complete'])
        self.assertFalse(record['data']['analysis_performed'])
        self.assertEqual(record['findings'], [])
        for item in record['data']['providers']:
            if not item['available']:
                self.assertIsNone(item['version'])
                self.assertEqual(item['engine_versions'], {})
                self.assertTrue(item['reason'])
                self.assertTrue(item['action'])
        serialized = json.dumps(record)
        self.assertNotIn('private-probe-value', serialized)
        self.assertNotIn(str(self.root), serialized)

    def script_tool(self, source, *, identity='degraded-provider', languages=('python',), timeout=1):
        tool = self.fixture.tool(languages, identity)
        script = Path(tool.artifacts[0][0])
        script.write_text(source, encoding='utf-8')
        return replace(tool, process=replace(tool.process, timeout_seconds=timeout),
                       artifacts=((str(script), file_digest(script)),))

    def invoke_cli(self, *options, search_path=''):
        # Isolate Python startup from the intentionally untrusted fixture cwd.
        # This harness choice does not claim ordinary Python startup is sandboxed.
        bootstrap = ('import sys;sys.path.insert(0,sys.argv.pop(1));'
                     'from devsift.cli import main;raise SystemExit(main(sys.argv[1:]))')
        return subprocess.run([sys.executable, '-I', '-B', '-c', bootstrap,
                               str(ROOT), 'doctor', *options], cwd=self.root,
                              env=dict(os.environ, PATH=search_path), capture_output=True,
                              text=True, timeout=15)

    def test_empty_invalid_and_excessive_path_never_executes_or_infers_versions(self):
        cases = [('', 'missing'), ('private-probe-value\0invalid', 'discovery_unavailable'),
                 ('x' * 32769, 'discovery_unavailable'),
                 (os.pathsep.join(['x'] * 513), 'discovery_unavailable')]
        before = self.fixture.snapshot()
        with patch('subprocess.Popen', side_effect=AssertionError('metadata cannot launch a process')):
            for path, expected in cases:
                with self.subTest(status=expected, path_length=len(path)):
                    record = run_doctor(root=self.root, search_path=path)
                    self.assert_incomplete(record)
                    self.assertTrue(all(item['status'] == expected and item['version'] is None
                                        and not item['detected'] for item in record['data']['host_tools']))
        self.assertEqual(before, self.fixture.snapshot())

    def test_real_probe_failure_matrix_is_bounded_and_never_publishes_private_output(self):
        valid_reply = {'protocol_version': '1', 'tool_id': 'degraded-provider', 'tool_version': '1.2.3',
                       'languages': ['python'], 'engine_versions': {'fixture': '2.0.0'}}
        bad_version = dict(valid_reply, tool_version='9.9.9')
        bad_engine = dict(valid_reply, engine_versions={'fixture': '9.9.9'})
        cases = [
            ('tool-version', 'import json\nprint(json.dumps(' + repr(bad_version) + '))\n', 1, 'PROBE_PROTOCOL_OR_VERSION_MISMATCH'),
            ('engine-version', 'import json\nprint(json.dumps(' + repr(bad_engine) + '))\n', 1, 'PROBE_PROTOCOL_OR_VERSION_MISMATCH'),
            ('bad-json', 'print("private-probe-value invalid JSON")\n', 1, 'PROBE_PROTOCOL_OR_VERSION_MISMATCH'),
            ('nonzero', 'import sys\nprint("private-probe-value",file=sys.stderr)\nsys.exit(7)\n', 1, 'PROBE_UNAVAILABLE'),
            ('excessive-output', 'print("private-probe-value" * 5000)\n', 1, 'PROBE_UNAVAILABLE'),
            ('timeout', 'import time\ntime.sleep(5)\n', .05, 'PROBE_UNAVAILABLE'),
        ]
        for name, source, timeout, reason in cases:
            with self.subTest(case=name):
                tool = self.script_tool(source, timeout=timeout)
                manifest, digest = self.fixture.manifest((tool,))
                before = self.fixture.snapshot()
                record = run_doctor(root=self.root, native_manifest=manifest,
                                    native_manifest_digest=digest, search_path='')
                self.assert_incomplete(record)
                native = record['data']['native_tools'][0]
                self.assertEqual(native['reason'], reason)
                self.assertEqual(native['configured_version'], '1.2.3')
                self.assertIsNone(native['version'])
                self.assertTrue(native['action'])
                self.assertEqual(before, self.fixture.snapshot())

    def test_missing_executable_or_artifact_is_not_installed_rebuilt_or_executed(self):
        for missing in ('executable', 'artifact'):
            with self.subTest(missing=missing):
                tool = self.fixture.tool(identity='missing-' + missing)
                if missing == 'executable':
                    tool = replace(tool, process=replace(tool.process,
                        executable=str(self.root / 'private-probe-value-missing-executable')),
                        executable_digest='0' * 64)
                manifest, digest = self.fixture.manifest((tool,))
                if missing == 'artifact':
                    Path(tool.artifacts[0][0]).unlink()  # Deliberate removal of owned disposable fixture only.
                before = self.fixture.snapshot()
                with patch('devsift.native_host.run_process', side_effect=AssertionError('missing artifact cannot execute')):
                    record = run_doctor(root=self.root, native_manifest=manifest,
                                        native_manifest_digest=digest, search_path='')
                self.assert_incomplete(record)
                self.assertEqual(record['data']['native_tools'][0]['reason'], 'ARTIFACT_UNAVAILABLE_OR_CHANGED')
                self.assertEqual(before, self.fixture.snapshot())

    def test_mixed_real_ready_and_version_mismatched_providers_never_pass(self):
        ready = self.fixture.tool(('go',), identity='healthy-go')
        wrong = {'protocol_version': '1', 'tool_id': 'degraded-sql', 'tool_version': '9.9.9',
                 'languages': ['sql'], 'engine_versions': {'fixture': '2.0.0'}}
        failed = self.script_tool('import json\nprint(json.dumps(' + repr(wrong) + '))\n',
                                  identity='degraded-sql', languages=('sql',))
        manifest, digest = self.fixture.manifest((ready, failed))
        before = self.fixture.snapshot()
        record = run_doctor(root=self.root, native_manifest=manifest,
                            native_manifest_digest=digest, search_path='')
        self.assert_incomplete(record)
        providers = {item['language']: item for item in record['data']['providers']}
        self.assertTrue(providers['go']['available'])
        self.assertEqual(providers['go']['version'], '1.2.3')
        self.assertFalse(providers['sql']['available'])
        self.assertEqual(providers['sql']['dialect'], 'tsql150')
        self.assertTrue(all(not providers[language]['available'] for language in ('csharp', 'javascript', 'python', 'typescript')))
        self.assertEqual(before, self.fixture.snapshot())

    def test_unsupported_runtime_cannot_pass_even_otherwise_ready_real_native_probes(self):
        tool = self.fixture.tool(ALL_LANGUAGES)
        manifest, digest = self.fixture.manifest((tool,))
        with patch('devsift.doctor.sys.version_info', (3, 11, 9)):
            record = run_doctor(root=self.root, native_manifest=manifest,
                                native_manifest_digest=digest, search_path='')
        self.assert_incomplete(record)
        self.assertTrue(all(item['available'] for item in record['data']['providers']))
        self.assertFalse(record['data']['runtime']['supported'])
        self.assertTrue(record['data']['runtime']['action'])
        self.assertIn('PYTHON_RUNTIME_UNSUPPORTED', {error['code'] for error in record['errors']})

    def test_bad_config_suppresses_otherwise_proven_real_native_provider(self):
        tool = self.fixture.tool(ALL_LANGUAGES)
        manifest, digest = self.fixture.manifest((tool,))
        good = run_doctor(root=self.root, native_manifest=manifest, native_manifest_digest=digest, search_path='')
        self.assertEqual(good['exit_code'], 0)  # Proves the precondition, not product rule coverage.
        self.assertFalse(good['data']['analysis_performed'])
        policy = self.root / 'policy.json'
        policy.write_text('{"private-probe-value":"not accepted policy"}', encoding='utf-8')
        before = self.fixture.snapshot()
        with patch('devsift.native_host.run_process', side_effect=AssertionError('bad config must suppress probes')):
            record = run_doctor(root=self.root, policy_path=policy, native_manifest=manifest,
                                native_manifest_digest=digest, search_path='')
        self.assert_incomplete(record)
        self.assertEqual(record['data']['native_tools'][0]['reason'], 'DOCTOR_CONFIG_UNAVAILABLE')
        self.assertEqual(before, self.fixture.snapshot())

    def test_actual_cli_empty_or_shadow_path_ignores_project_hooks_and_missing_manifest(self):
        (self.root / '.devsift').mkdir()
        (self.root / '.devsift/native-manifest.json').write_text('{"private-probe-value":"untrusted"}')
        (self.root / 'package.json').write_text('{"scripts":{"postinstall":"private-probe-value"}}')
        shadow = self.root / ('git.exe' if os.name == 'nt' else 'git')
        shadow.write_text('private-probe-value untrusted command')
        shadow.chmod(0o700)
        before = self.fixture.snapshot()
        for path in ('', str(self.root)):
            with self.subTest(path='empty' if not path else 'shadow'):
                completed = self.invoke_cli(search_path=path)
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assertEqual(completed.stderr, '')
                self.assert_incomplete(json.loads(completed.stdout))
        missing = self.root / 'private-probe-value-missing-manifest.json'
        completed = self.invoke_cli('--native-manifest', str(missing), '--native-manifest-digest', '0' * 64)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assert_incomplete(json.loads(completed.stdout))
        self.assertEqual(before, self.fixture.snapshot())

    def test_actual_cli_trusted_probe_error_stays_machine_readable_and_incomplete(self):
        tool = self.script_tool('import sys\nprint("private-probe-value",file=sys.stderr)\nsys.exit(9)\n')
        manifest, digest = self.fixture.manifest((tool,))
        before = self.fixture.snapshot()
        completed = self.invoke_cli('--native-manifest', str(manifest), '--native-manifest-digest', digest)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(completed.stderr, '')
        record = json.loads(completed.stdout)
        self.assert_incomplete(record)
        self.assertEqual(record['data']['native_tools'][0]['reason'], 'PROBE_UNAVAILABLE')
        self.assertEqual(before, self.fixture.snapshot())


if __name__ == '__main__':
    unittest.main()
