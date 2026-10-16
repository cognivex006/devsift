import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from devsift.doctor import run_doctor
from devsift.native_host import ToolDefinition, file_digest
from devsift.native_manifest import ConfiguredTool
from devsift.process_runner import ProcessSpec


class DoctorConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='devsift-doctor-config-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix():
                ('directory' if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest())
                for p in self.root.rglob('*') if not p.is_symlink() and not p.is_junction()}

    def doctor(self, **options):
        return run_doctor(root=self.root, search_path='', **options)

    def test_default_policy_is_in_memory_and_no_project_config_or_cache_discovery(self):
        (self.root / '.devsift.yml').write_text('execute: private-secret-program', encoding='utf-8')
        (self.root / 'devsift.json').write_text('not valid JSON; must not be discovered', encoding='utf-8')
        before = self.snapshot()
        with patch('subprocess.Popen', side_effect=AssertionError('no executable authorized')):
            record = self.doctor()
        self.assertEqual(record['data']['config_checks']['status'], 'default')
        self.assertEqual(record['data']['config_checks']['policy_schema_version'], '1')
        self.assertEqual(record['data']['cache_checks']['status'], 'not_requested')
        self.assertEqual(record['exit_code'], 2)
        self.assertEqual(before, self.snapshot())
        self.assertNotIn('private-secret', json.dumps(record))

    def test_missing_cache_is_informational_and_never_created(self):
        before = self.snapshot()
        record = self.doctor(cache_path='absent-parent/cache')
        self.assertEqual(record['data']['cache_checks']['status'], 'missing')
        self.assertFalse(any(error['code'] == 'DOCTOR_CACHE_UNAVAILABLE' for error in record['errors']))
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.root / 'absent-parent').exists())

    def test_valid_json_and_cache_metadata_preserve_bytes_without_enumerating_children(self):
        policy = self.root / 'policy.json'
        policy.write_text('{"rules":{"HC001":{"severity":"Warning"}}}', encoding='utf-8')
        cache = self.root / 'cache'
        cache.mkdir()
        (cache / 'private-secret.bin').write_bytes(b'opaque cache content must not be read')
        before = self.snapshot()
        with patch('os.scandir', side_effect=AssertionError('cache children must not be enumerated')):
            record = self.doctor(policy_path='policy.json', cache_path=cache)
        self.assertEqual(record['data']['config_checks']['status'], 'valid')
        self.assertEqual(record['data']['cache_checks']['status'], 'present')
        self.assertEqual(record['exit_code'], 2)  # Valid optional files cannot create missing providers.
        self.assertEqual(before, self.snapshot())
        self.assertNotIn('private-secret', json.dumps(record))
        self.assertNotIn(str(self.root), json.dumps(record))

    def test_malformed_duplicate_unknown_nonfinite_or_secret_policy_fails_safely(self):
        path = self.root / 'policy.json'
        for payload in [b'null', b'[]', b'{', b'{"rules":{},"rules":{}}',
                        b'{"rules":{"HC001":{"severity":"Error","severity":"Warning"}}}',
                        b'{"private-secret-key":"Bearer synthetic-private-value"}',
                        b'{"quality_gate":{"block_on":[NaN]}}', b'\xff']:
            with self.subTest(payload_length=len(payload)):
                path.write_bytes(payload)
                before = self.snapshot()
                record = self.doctor(policy_path=path)
                self.assertEqual(record['data']['config_checks']['status'], 'incomplete')
                self.assertEqual(record['exit_code'], 2)
                self.assertNotIn('private-secret', json.dumps(record))
                self.assertNotIn(str(self.root), json.dumps(record))
                self.assertEqual(before, self.snapshot())

    def test_oversized_missing_nonregular_yaml_and_unreadable_explicit_files_are_incomplete(self):
        path = self.root / 'large.json'
        path.write_bytes(b' ' * (1048576 + 1))
        with patch('devsift.doctor.os.open', side_effect=AssertionError('oversized file must not open')):
            self.assertEqual(self.doctor(policy_path=path)['data']['config_checks']['status'], 'incomplete')
        for name in ['missing.json', '.', 'policy.yaml']:
            self.assertEqual(self.doctor(policy_path=name)['data']['config_checks']['status'], 'incomplete')
        valid = self.root / 'valid.json'
        valid.write_text('{}')
        with patch('devsift.doctor.os.open', side_effect=PermissionError('private-secret-os-error')):
            record = self.doctor(policy_path=valid)
        self.assertEqual(record['data']['config_checks']['status'], 'incomplete')
        self.assertNotIn('private-secret', json.dumps(record))

    def test_outside_and_parent_traversal_paths_refused_before_read(self):
        outside = self.root.parent / 'private-secret-outside.json'
        with patch('devsift.doctor.os.open', side_effect=AssertionError('unsafe path must not open')):
            for path in [outside, '../private-secret-outside.json', 'missing/../policy.json']:
                self.assertEqual(self.doctor(policy_path=path)['data']['config_checks']['status'], 'incomplete')
            self.assertEqual(self.doctor(cache_path=self.root.parent)['data']['cache_checks']['status'], 'incomplete')

    def test_open_handle_identity_mismatch_is_rejected_before_content_read(self):
        policy = self.root / 'policy.json'
        policy.write_text('{}')
        info = policy.stat()
        changed = SimpleNamespace(st_mode=info.st_mode, st_dev=info.st_dev,
            st_ino=info.st_ino + 1, st_size=info.st_size, st_mtime_ns=info.st_mtime_ns)
        with patch('devsift.doctor.os.fstat', return_value=changed), \
                patch('devsift.doctor.os.read', side_effect=AssertionError('mismatched handle must not read')):
            record = self.doctor(policy_path=policy)
        self.assertEqual(record['data']['config_checks']['status'], 'incomplete')
        self.assertEqual(policy.read_text(), '{}')

    def test_cache_wrong_type_unreadable_or_invalid_root_is_incomplete(self):
        file = self.root / 'not-directory'
        file.write_text('preserve')
        self.assertEqual(self.doctor(cache_path=file)['data']['cache_checks']['status'], 'incomplete')
        cache = self.root / 'cache'
        cache.mkdir()
        with patch('devsift.doctor.os.access', return_value=False):
            self.assertEqual(self.doctor(cache_path=cache)['data']['cache_checks']['status'], 'incomplete')
        record = run_doctor(root=file, search_path='')
        self.assertEqual(record['data']['config_checks']['status'], 'incomplete')
        self.assertEqual(record['exit_code'], 2)

    def test_actual_symlink_file_and_parent_are_rejected(self):
        target = self.root / 'real'
        target.mkdir()
        (target / 'policy.json').write_text('{}')
        link = self.root / 'link'
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest('Host symlink creation unavailable: ' + type(error).__name__)
        self.assertEqual(self.doctor(policy_path=link / 'policy.json')['data']['config_checks']['status'], 'incomplete')
        self.assertEqual(self.doctor(cache_path=link)['data']['cache_checks']['status'], 'incomplete')
        self.assertEqual(run_doctor(root=link, search_path='')['data']['config_checks']['status'], 'incomplete')

    @unittest.skipUnless(os.name == 'nt', 'Windows reparse/junction check')
    def test_actual_junction_parent_cannot_redirect_policy_or_cache(self):
        import _winapi
        target = self.root / 'real'
        target.mkdir()
        (target / 'policy.json').write_text('{}')
        link = self.root / 'junction'
        _winapi.CreateJunction(str(target), str(link))
        try:
            self.assertTrue(link.is_junction())
            self.assertEqual(self.doctor(policy_path=link / 'policy.json')['data']['config_checks']['status'], 'incomplete')
            self.assertEqual(self.doctor(cache_path=link)['data']['cache_checks']['status'], 'incomplete')
        finally:
            link.rmdir()

    def test_invalid_optional_configuration_skips_even_explicit_native_probes(self):
        policy = self.root / 'policy.json'
        policy.write_text('{"private-secret":"invalid"}')
        tool = ToolDefinition('fixture-provider', '1', ('csharp', 'go', 'javascript', 'python', 'sql', 'typescript'),
            ProcessSpec(str(Path(sys.executable).resolve())), file_digest(sys.executable),
            ((str(policy), file_digest(policy)),), ())
        with patch('devsift.doctor.load_manifest', return_value=(ConfiguredTool(tool, 'tsql160'),)), \
                patch('devsift.doctor.probe_tool', side_effect=AssertionError('invalid config must not execute')):
            record = self.doctor(policy_path=policy, native_manifest='explicit', native_manifest_digest='a' * 64)
        self.assertEqual(record['exit_code'], 2)
        self.assertFalse(record['data']['capabilities']['analyzers'])


if __name__ == '__main__':
    unittest.main()
