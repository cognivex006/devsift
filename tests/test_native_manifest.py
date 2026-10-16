import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from devsift.cli_scan import run_scan
from devsift.native_host import ToolDefinition, file_digest
from devsift.native_manifest import ConfiguredTool, ManifestError, load_manifest, manifest_bytes
from devsift.process_runner import ProcessSpec

ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repository = self.root / 'source'
        self.repository.mkdir()
        self.marker = self.root / 'TOOL_WAS_EXECUTED'
        self.helper = self.root / 'probe.py'
        self.helper.write_text('from pathlib import Path\nPath(' + repr(str(self.marker)) + ').write_text("executed")\n', encoding='utf-8')
        self.tool = ToolDefinition('fixture-tool', '1', ('python',),
                                   ProcessSpec(str(Path(sys.executable).resolve()), ('-I', '-B', str(self.helper))),
                                   file_digest(sys.executable), ((str(self.helper), file_digest(self.helper)),), ())
        (self.repository / 'code.py').write_bytes(b'print(1)\n')
        for args in (('init', '-q'), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@example.invalid'), ('add', 'code.py'), ('commit', '-qm', 'fixture')):
            subprocess.run(['git', '-C', str(self.repository), *args], check=True, capture_output=True)

    def persist(self, raw):
        path = self.root / 'manifest.json'
        path.write_bytes(raw)
        return path, hashlib.sha256(raw).hexdigest()

    def test_round_trip_preserves_stored_pins_without_any_execution(self):
        raw = manifest_bytes((ConfiguredTool(self.tool),))
        path, digest = self.persist(raw)
        loaded = load_manifest(path, digest)
        self.assertEqual(loaded[0].tool, self.tool)
        self.assertFalse(self.marker.exists())
        no_source = run_scan(self.root, all_scope=True, native_manifest=path, native_manifest_digest=digest)
        self.assertEqual(no_source['exit_code'], 2)
        self.assertFalse(self.marker.exists())
        wire = json.loads(raw)
        wire['tools'][0]['definition']['executable_digest'] = '0' * 64
        path, digest = self.persist(json.dumps(wire).encode())
        self.assertEqual(load_manifest(path, digest)[0].tool.executable_digest, '0' * 64)
        record = run_scan(self.repository, all_scope=True, native_manifest=path, native_manifest_digest=digest)
        self.assertEqual(record['exit_code'], 2)
        self.assertFalse(self.marker.exists())

    def test_all_entries_validate_before_first_native_probe(self):
        original = json.loads(manifest_bytes((ConfiguredTool(self.tool),)))
        malformed = []
        duplicate = copy.deepcopy(original)
        duplicate['tools'].append(copy.deepcopy(duplicate['tools'][0]))
        malformed.append(duplicate)
        overlap = copy.deepcopy(duplicate)
        overlap['tools'][1]['definition']['tool_id'] = 'second-id'
        malformed.append(overlap)
        late_bad = copy.deepcopy(duplicate)
        late_bad['tools'][1]['definition']['languages'] = ['go']
        late_bad['tools'][1]['definition']['tool_id'] = 'second-id'
        late_bad['tools'][1]['definition']['process']['timeout_seconds'] = True
        malformed.append(late_bad)
        sql_missing_dialect = copy.deepcopy(original)
        sql_missing_dialect['tools'][0]['definition']['languages'] = ['sql']
        malformed.append(sql_missing_dialect)
        extra = copy.deepcopy(original)
        extra['tools'][0]['definition']['private-fixture-secret'] = True
        malformed.append(extra)
        relative = copy.deepcopy(original)
        relative['tools'][0]['definition']['process']['executable'] = 'private-relative-executable'
        malformed.append(relative)
        unrelated_dialect = copy.deepcopy(original)
        unrelated_dialect['tools'][0]['dialect'] = 'tsql160'
        malformed.append(unrelated_dialect)
        for wire in malformed:
            path, digest = self.persist(json.dumps(wire).encode())
            record = run_scan(self.repository, all_scope=True, native_manifest=path, native_manifest_digest=digest)
            self.assertEqual(record['exit_code'], 2)
            self.assertEqual(record['errors'][0]['code'], 'NATIVE_MANIFEST_UNAVAILABLE')
            self.assertNotIn('private-fixture-secret', json.dumps(record))
            self.assertFalse(self.marker.exists())

    def test_duplicate_json_tampered_manifest_and_changed_artifact_fail_closed(self):
        raw = manifest_bytes((ConfiguredTool(self.tool),))
        for bad in (b'{"schema_version":"1","schema_version":"1","tools":[]}',
                    raw.replace(b'"timeout_seconds":10', b'"timeout_seconds":NaN'),
                    raw.replace(b'"timeout_seconds":10', b'"timeout_seconds":10,"timeout_seconds":1'),
                    b' ' * 2_000_001):
            path, digest = self.persist(bad)
            with self.assertRaises(ManifestError):
                load_manifest(path, digest)
        path, digest = self.persist(raw)
        path.write_bytes(raw + b' ')
        with self.assertRaises(ManifestError):
            load_manifest(path, digest)
        path, digest = self.persist(raw)
        with self.helper.open('ab') as stream:
            stream.write(b'\n# artifact changed\n')
        record = run_scan(self.repository, all_scope=True, native_manifest=path, native_manifest_digest=digest)
        self.assertEqual(record['exit_code'], 2)
        self.assertFalse(self.marker.exists())

    def test_cli_pair_and_format_misuse(self):
        for options in (('--native-manifest', str(self.root / 'manifest.json')),
                        ('--native-manifest-digest', '0' * 64),
                        ('--native-manifest', 'relative.json', '--native-manifest-digest', '0' * 64)):
            completed = subprocess.run([sys.executable, '-B', '-m', 'devsift', 'scan', *options],
                                       cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 3)
            self.assertEqual(json.loads(completed.stderr)['status'], 'misuse')


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_NATIVE') == '1', 'requires explicitly built real native parsers')
class ActualManifestCliTests(unittest.TestCase):
    def test_actual_go_cli_can_complete_a_committed_clean_snapshot(self):
        from devsift.go_adapter import make_tool
        executable = os.environ.get('DEVSIFT_GO_ARTIFACT') or str(
            ROOT / '.devsift/local/tools/go' / ('devsift-go.exe' if os.name == 'nt' else 'devsift-go'))
        tool = make_tool(str(Path(executable).resolve()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / 'source'
            repository.mkdir()
            (repository / 'pure.go').write_bytes(b'package sample\nfunc Twice(x int) int { return x * 2 }\n')
            for args in (('init', '-q'), ('config', 'user.name', 'Fixture'),
                         ('config', 'user.email', 'fixture@example.invalid'), ('add', 'pure.go'), ('commit', '-qm', 'fixture')):
                subprocess.run(['git', '-C', str(repository), *args], check=True, capture_output=True)
            raw = manifest_bytes((ConfiguredTool(tool),))
            manifest = root / 'manifest.json'
            manifest.write_bytes(raw)
            environment = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1')
            executed = subprocess.run([sys.executable, '-B', '-m', 'devsift', 'scan', '--all',
                                      '--native-manifest', str(manifest), '--native-manifest-digest', hashlib.sha256(raw).hexdigest()],
                                     cwd=repository, env=environment, capture_output=True, text=True)
            self.assertEqual(executed.returncode, 0, executed.stderr)
            record = json.loads(executed.stdout)
            self.assertTrue(record['complete'])
            self.assertEqual(record['data']['counts']['executed'], 1)
            self.assertEqual(record['findings'], [])
            # A failed configured language remains incomplete even without any
            # target of that language; the working Go tool must not hide it.
            unavailable = ToolDefinition('unavailable-python', '1', ('python',), tool.process,
                                         '0' * 64, tool.artifacts, ())
            raw = manifest_bytes((ConfiguredTool(tool), ConfiguredTool(unavailable)))
            manifest.write_bytes(raw)
            repeated = subprocess.run([sys.executable, '-B', '-m', 'devsift', 'scan', '--all',
                                      '--native-manifest', str(manifest), '--native-manifest-digest', hashlib.sha256(raw).hexdigest()],
                                     cwd=repository, env=environment, capture_output=True, text=True)
            self.assertEqual(repeated.returncode, 2, repeated.stderr)
            incomplete = json.loads(repeated.stdout)
            self.assertEqual(incomplete['data']['counts']['executed'], 1)
            self.assertTrue(any(e['code'] == 'NATIVE_TOOL_UNAVAILABLE' for e in incomplete['errors']))

    def test_real_sql_cli_security_unknown_is_not_clean_and_does_not_write(self):
        from devsift.sql_adapter import make_tool
        dotnet = os.environ.get('DEVSIFT_DOTNET_EXECUTABLE') or shutil.which('dotnet')
        directory = Path(os.environ.get('DEVSIFT_SQL_ARTIFACT_DIR', ROOT / '.devsift/local/tools/sql')).resolve()
        tool = make_tool(str(Path(dotnet).resolve()), directory)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / 'source'
            repository.mkdir()
            (repository / 'query.sql').write_bytes(b"DECLARE @sql nvarchar(max) = N'SELECT ' + @input; EXEC(@sql);\n")
            for args in (('init', '-q'), ('config', 'user.name', 'Fixture'),
                         ('config', 'user.email', 'fixture@example.invalid'), ('config', 'core.autocrlf', 'false'),
                         ('add', 'query.sql'), ('commit', '-qm', 'fixture')):
                subprocess.run(['git', '-C', str(repository), *args], check=True, capture_output=True)
            raw = manifest_bytes((ConfiguredTool(tool, 'tsql160'),))
            path = root / 'manifest.json'
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            before = {str(p.relative_to(root)): None if p.is_dir() else p.read_bytes() for p in root.rglob('*')}
            environment = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1')
            completed = subprocess.run([sys.executable, '-B', '-m', 'devsift', 'scan', '--all',
                                        '--native-manifest', str(path), '--native-manifest-digest', digest],
                                       cwd=repository, env=environment, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertEqual(completed.stderr, '')
            record = json.loads(completed.stdout)
            self.assertTrue(record['findings'], record['errors'])
            finding = next(f for f in record['findings'] if f['rule_id'] == 'SEC003')
            self.assertEqual(finding['source']['status'], 'VERIFIED')
            self.assertEqual(finding['lifecycle_class'], 'UNKNOWN')
            self.assertEqual(finding['enforcement'], 'incomplete')
            self.assertTrue(finding['security_escalation'])
            self.assertEqual(record['enforced_count'], 0)
            self.assertEqual(before, {str(p.relative_to(root)): None if p.is_dir() else p.read_bytes()
                                      for p in root.rglob('*')})


if __name__ == '__main__':
    unittest.main()
