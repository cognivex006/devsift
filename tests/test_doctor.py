from dataclasses import replace
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from devsift.doctor import run_doctor
from devsift.native_host import ProbeResult, ToolDefinition, file_digest
from devsift.native_manifest import ConfiguredTool, manifest_bytes
from devsift.process_runner import ProcessSpec


class DoctorDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='devsift-doctor-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def tool(self, languages=('python',), identity='fixture-provider'):
        script = self.root / (identity + '.py')
        reply = {'protocol_version': '1', 'tool_id': identity, 'tool_version': '1.2.3',
                 'languages': list(languages), 'engine_versions': {'fixture': '2.0.0'}}
        script.write_text('import json,sys\nassert sys.argv[1:] == ["--probe"]\nprint(json.dumps(' + repr(reply) + '))\n', encoding='utf-8')
        return ToolDefinition(identity, '1.2.3', languages,
            ProcessSpec(str(Path(sys.executable).resolve()), ('-I', '-B', str(script)), timeout_seconds=100),
            file_digest(sys.executable), ((str(script), file_digest(script)),), (('fixture', '2.0.0'),))

    def manifest(self, tools):
        entries = tuple(ConfiguredTool(tool, 'tsql150' if 'sql' in tool.languages else None) for tool in tools)
        path = self.root / 'native-manifest.json'
        raw = manifest_bytes(entries)
        path.write_bytes(raw)
        return path, hashlib.sha256(raw).hexdigest()

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file()}

    def test_default_discovers_metadata_without_executing_path_candidates(self):
        shadow = self.root / ('git.exe' if os.name == 'nt' else 'git')
        shadow.write_text('untrusted executable candidate must never run', encoding='utf-8')
        shadow.chmod(0o700)
        before = self.snapshot()
        with patch('subprocess.Popen', side_effect=AssertionError('default must never execute')), \
                patch('devsift.doctor.probe_tool', side_effect=AssertionError('no authorization')):
            record = run_doctor(search_path=str(self.root))
        self.assertEqual(record['command'], 'doctor')
        self.assertEqual(record['schema_version'], '1.0')
        self.assertEqual(record['exit_code'], 2)
        self.assertFalse(record['complete'])
        self.assertEqual(record['data']['runtime']['version'], '.'.join(map(str, sys.version_info[:3])))
        git = next(item for item in record['data']['host_tools'] if item['tool_id'] == 'git')
        self.assertTrue(git['detected'])
        self.assertEqual(git['status'], 'discovered_unverified')
        self.assertIsNone(git['version'])
        self.assertTrue(git['action'])
        self.assertTrue(all(not item['available'] for item in record['data']['providers']))
        self.assertEqual(before, self.snapshot())
        self.assertNotIn(str(self.root), json.dumps(record))

    def test_empty_environment_explains_missing_tools_and_analyzers_not_pass(self):
        record = run_doctor(search_path='')
        self.assertEqual(record['exit_code'], 2)
        self.assertEqual({item['language'] for item in record['data']['providers']},
                         {'python', 'go', 'sql', 'csharp', 'typescript', 'javascript'})
        for item in record['data']['host_tools']:
            self.assertFalse(item['detected'])
            self.assertEqual(item['status'], 'missing')
            self.assertIsNone(item['version'])
            self.assertTrue(item['action'])

    def test_real_trusted_probe_returns_verified_versions_and_partial_coverage(self):
        tool = self.tool()
        path, digest = self.manifest((tool,))
        before = self.snapshot()
        record = run_doctor(native_manifest=path, native_manifest_digest=digest, search_path='')
        python = next(item for item in record['data']['providers'] if item['language'] == 'python')
        self.assertTrue(python['available'])
        self.assertEqual(python['version'], '1.2.3')
        self.assertEqual(python['engine_versions'], {'fixture': '2.0.0'})
        self.assertEqual(python['reason'], 'READY')
        self.assertEqual(record['exit_code'], 2)  # Other language providers remain unavailable.
        self.assertEqual(before, self.snapshot())

    def test_all_languages_verified_is_discovery_complete_not_scan_coverage(self):
        tool = self.tool(('csharp', 'go', 'javascript', 'python', 'sql', 'typescript'))
        path, digest = self.manifest((tool,))
        record = run_doctor(native_manifest=path, native_manifest_digest=digest, search_path='')
        self.assertEqual(record['exit_code'], 0)
        self.assertTrue(record['complete'])
        self.assertEqual(record['data']['scope'], 'provider_discovery_only')
        self.assertEqual(record['findings'], [])
        sql = next(item for item in record['data']['providers'] if item['language'] == 'sql')
        self.assertEqual(sql['dialect'], 'tsql150')

    def test_invalid_pair_digest_or_late_entry_prevents_every_probe_and_leaks_no_values(self):
        path, digest = self.manifest((self.tool(),))
        invalid = [dict(native_manifest=path), dict(native_manifest_digest=digest),
                   dict(native_manifest=path, native_manifest_digest='private-secret'),
                   dict(native_manifest=path, native_manifest_digest='0' * 64)]
        wire = json.loads(path.read_bytes())
        late = copy.deepcopy(wire['tools'][0])
        late['private-secret'] = 'do not reflect'
        wire['tools'].append(late)
        raw = json.dumps(wire).encode()
        malformed = self.root / 'private-secret.json'
        malformed.write_bytes(raw)
        invalid.append(dict(native_manifest=malformed, native_manifest_digest=hashlib.sha256(raw).hexdigest()))
        with patch('devsift.doctor.probe_tool', side_effect=AssertionError('must validate all first')):
            for options in invalid:
                with self.subTest(options=list(options)):
                    record = run_doctor(search_path='', **options)
                    self.assertEqual(record['exit_code'], 2)
                    self.assertFalse(record['complete'])
                    self.assertNotIn('private-secret', json.dumps(record))
                    self.assertNotIn(str(self.root), json.dumps(record))

    def test_changed_artifact_never_executes_or_replaces_stored_pins(self):
        tool = self.tool()
        path, digest = self.manifest((tool,))
        Path(tool.artifacts[0][0]).write_text('changed helper bytes', encoding='utf-8')
        before = self.snapshot()
        with patch('devsift.native_host.run_process', side_effect=AssertionError('changed artifact must not run')):
            record = run_doctor(native_manifest=path, native_manifest_digest=digest, search_path='')
        item = record['data']['native_tools'][0]
        self.assertFalse(item['available'])
        self.assertIsNone(item['version'])
        self.assertEqual(item['reason'], 'ARTIFACT_UNAVAILABLE_OR_CHANGED')
        self.assertTrue(item['action'])
        self.assertEqual(before, self.snapshot())

    def test_doctor_caps_trusted_process_limits_without_altering_original(self):
        original = self.tool()
        for timeout in (100, None):
            tool = replace(original, process=replace(original.process, timeout_seconds=timeout))
            path, digest = self.manifest((tool,))
            with patch('devsift.doctor.probe_tool', return_value=ProbeResult(False, 'PROBE_UNAVAILABLE')) as probe:
                record = run_doctor(native_manifest=path, native_manifest_digest=digest, search_path='')
            process = probe.call_args.args[0].process
            self.assertLessEqual(process.timeout_seconds, 5)
            self.assertLessEqual(process.max_stdout_bytes, 32768)
            self.assertLessEqual(process.max_stderr_bytes, 16384)
            self.assertEqual(tool.process.timeout_seconds, timeout)
            self.assertEqual(record['exit_code'], 2)

    def test_unsupported_python_is_explicitly_incomplete(self):
        with patch('devsift.doctor.sys.version_info', (3, 11, 9)):
            record = run_doctor(search_path='')
        self.assertFalse(record['data']['runtime']['supported'])
        self.assertEqual(record['exit_code'], 2)
        self.assertTrue(record['data']['runtime']['action'])


if __name__ == '__main__':
    unittest.main()
