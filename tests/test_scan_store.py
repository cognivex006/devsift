import io
import os
import stat
import json
from pathlib import Path
import tempfile
import unittest

from devsift.adapters import AdapterCapability
from devsift.scanner import AdapterOutcome, iter_scan
from devsift.scan_store import run_streamed, StoreError


class Clean:
    capability = AdapterCapability('clean', '1', ('python',), True)

    def __init__(self):
        self.calls = []

    def analyze(self, target):
        self.calls.append(target.path)
        return AdapterOutcome(True)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'source'
        self.root.mkdir()
        self.destination = self.base / 'scan'
        self.adapter = Clean()

    def run_scan(self, **kwargs):
        return run_streamed(self.root, lambda callback: iter_scan(
            self.root, adapters=(self.adapter,), should_scan=callback),
            destination=self.destination, **kwargs)

    def test_result_streaming_inline_reports_and_resume_skip(self):
        (self.root / 'a.py').write_text('print(1)')
        stored = self.run_scan()
        self.assertEqual(stored.exit_code, 0)
        output = io.StringIO()
        stored.write_json(output)
        record = json.loads(output.getvalue())
        self.assertEqual(record['data']['target_count'], 1)
        self.assertEqual(record['data']['execution'], {'fresh_targets': 1, 'reused_targets': 0})
        self.assertEqual(set(record['data']['reports']), {'json', 'markdown', 'sarif'})
        stored.close()
        self.adapter.calls.clear()
        stored = self.run_scan(resume=True)
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(stored.summary()['data']['execution'], {'fresh_targets': 0, 'reused_targets': 1})
        self.assertEqual(stored.summary()['data']['target_count'], 1)
        stored.close()

    def test_streamed_exit_code_matches_emitted_snapshot_if_artifact_changes_during_write(self):
        stored = self.run_scan()
        self.addCleanup(stored.close)
        page = json.loads(stored.connection.execute('SELECT payload FROM report_pages').fetchone()[0])
        artifact = Path(stored.bundle['index']).parent / page['files'][0]['file']

        class ChangingStream(io.StringIO):
            def write(inner, value):
                written = super().write(value)
                # Remove an already-consumed artifact after the JSON snapshot's
                # final frame; a later verification must fail independently.
                if value == ']}}\n':
                    artifact.unlink()
                return written

        output = ChangingStream()
        emitted_exit = stored.write_json(output)
        self.assertEqual(emitted_exit, json.loads(output.getvalue())['exit_code'])
        self.assertEqual(emitted_exit, 0)
        self.assertEqual(stored.exit_code, 2)

    def test_actual_ci_cached_security_escalation_preserves_independent_review_metadata(self):
        from test_ci_gate import CiGateTests
        from devsift.ci_gate import GateConfig, run_ci
        fixture = CiGateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.source('apiKey=' + repr('gh' + 'p_' + 'a' * 36) + '\n')
        destination = fixture.directory / 'reports'
        policy = GateConfig().policy()
        configuration = {'command': 'ci', 'head': fixture.git('rev-parse', 'HEAD'),
                         'base': fixture.base, 'native_digest': fixture.digest, 'policy': policy}

        def factory(callback):
            return run_ci(fixture.root, native_manifest=fixture.manifest,
                          native_manifest_digest=fixture.digest, base_ref=fixture.base,
                          all_scope=True, stream=True, should_scan=callback)

        for resume in (False, True):
            stored = run_streamed(fixture.root, factory, destination=destination, resume=resume,
                                  configuration=configuration, policy=policy, trusted_lifecycles=True)
            try:
                summary = stored.summary()
                self.assertEqual(summary['exit_code'], 1)
                self.assertEqual(summary['enforced_count'], 1)
                self.assertTrue(summary['data']['quality_gate']['security_review_required'])
                index = json.loads(Path(stored.bundle['index']).read_text())
                self.assertTrue(index['quality_gate']['security_review_required'])
                output = io.StringIO()
                self.assertEqual(stored.write_json(output), 1)
                complete = json.loads(output.getvalue())
                self.assertTrue(complete['data']['quality_gate']['security_review_required'])
                self.assertTrue(complete['findings'][0]['security_escalation'])
                self.assertIn('json', complete['data']['reports'])
                if resume:
                    self.assertEqual(summary['data']['execution'], {'fresh_targets': 0, 'reused_targets': 3})
            finally:
                stored.close()
        original = (fixture.root / 'code.py').read_bytes()
        (fixture.root / 'code.py').unlink()
        deleted = run_streamed(fixture.root, factory, destination=destination, resume=True,
                               configuration=configuration, policy=policy, trusted_lifecycles=True)
        try:
            summary = deleted.summary()
            self.assertEqual(summary['exit_code'], 0)
            self.assertEqual(summary['data']['finding_count'], 0)
            self.assertFalse(summary['data']['quality_gate']['security_review_required'])
            index = json.loads(Path(deleted.bundle['index']).read_text())
            self.assertFalse(index['quality_gate']['security_review_required'])
            self.assertEqual(summary['data']['execution'], {'fresh_targets': 0, 'reused_targets': 2})
        finally:
            deleted.close()
        (fixture.root / 'code.py').write_bytes(original)
        restored = run_streamed(fixture.root, factory, destination=destination, resume=True,
                               configuration=configuration, policy=policy, trusted_lifecycles=True)
        try:
            summary = restored.summary()
            self.assertEqual(summary['exit_code'], 1)
            self.assertEqual(summary['data']['finding_count'], 1)
            self.assertTrue(summary['data']['quality_gate']['security_review_required'])
            self.assertEqual(summary['data']['execution'], {'fresh_targets': 1, 'reused_targets': 2})
        finally:
            restored.close()

    def test_cached_resume_rechecks_current_provider_availability_and_recovery(self):
        (self.root / 'a.py').write_text('print(1)')
        stored = self.run_scan()
        self.assertEqual(stored.exit_code, 0)
        stored.close()
        self.adapter.calls.clear()
        self.adapter.capability = AdapterCapability('clean', '1', ('python',), False)
        stored = self.run_scan(resume=True)
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(stored.summary()['data']['target_count'], 1)
        self.assertEqual(stored.exit_code, 2)
        self.assertIn('NO_AVAILABLE_ANALYZER', [error['code'] for error in stored.summary()['errors']])
        stored.close()
        self.adapter.capability = AdapterCapability('clean', '1', ('python',), True)
        stored = self.run_scan(resume=True)
        self.assertEqual(stored.exit_code, 0)
        self.assertEqual(self.adapter.calls, [])
        stored.close()

    def test_changed_retry_and_deleted_data_is_removed(self):
        for name in ('a.py', 'b.py'):
            (self.root / name).write_text('print(1)')
        stored = self.run_scan()
        stored.close()
        self.adapter.calls.clear()
        (self.root / 'a.py').write_text('print(2)')
        (self.root / 'b.py').unlink()
        stored = self.run_scan(resume=True)
        self.assertEqual(self.adapter.calls, ['a.py'])
        self.assertEqual(stored.summary()['data']['target_count'], 1)
        self.assertEqual(stored.connection.execute("SELECT count(*) FROM targets WHERE identity<>'empty-scope'").fetchone()[0], 1)
        stored.close()

    def test_interruption_retains_complete_work_and_resume(self):
        for name in ('a.py', 'b.py'):
            (self.root / name).write_text('print(1)')

        def interrupted(callback):
            for record in iter_scan(self.root, adapters=(self.adapter,), should_scan=callback):
                yield record
                if record['data'].get('targets'):
                    raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            run_streamed(self.root, interrupted, destination=self.destination)
        self.assertFalse((self.destination / '.lock').exists())
        self.adapter.calls.clear()
        stored = self.run_scan(resume=True)
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual(stored.summary()['data']['target_count'], 2)
        self.assertEqual(stored.exit_code, 0)
        stored.close()

    def test_source_directory_foreign_directory_configuration_and_symlinks_refused(self):
        with self.assertRaises(StoreError):
            run_streamed(self.root, lambda _: (), destination=self.root / 'output')
        self.destination.mkdir()
        (self.destination / 'foreign').write_text('keep')
        with self.assertRaises(StoreError):
            self.run_scan()
        self.assertEqual((self.destination / 'foreign').read_text(), 'keep')
        (self.destination / 'foreign').unlink()
        self.destination.rmdir()
        stored = self.run_scan(configuration={'trusted': 'first'})
        stored.close()
        with self.assertRaises(StoreError):
            self.run_scan(resume=True, configuration={'trusted': 'different'})
        link = self.base / 'linked'
        try:
            link.symlink_to(self.destination, target_is_directory=True)
        except OSError:
            return
        with self.assertRaises(StoreError):
            run_streamed(self.root, lambda _: (), destination=link, resume=True)

    def test_active_session_lock_blocks_resume_until_close(self):
        stored = self.run_scan()
        with self.assertRaises(StoreError):
            self.run_scan(resume=True)
        self.assertEqual(stored.exit_code, 0)
        stored.close()
        resumed = self.run_scan(resume=True)
        resumed.close()

    def test_incomplete_targets_retry_and_root_identity_is_enforced(self):
        (self.root / 'a.py').write_text('print(1)')
        self.adapter.analyze = lambda target: AdapterOutcome(False)
        stored = self.run_scan()
        self.assertEqual(stored.exit_code, 2)
        stored.close()
        self.adapter = Clean()
        stored = self.run_scan(resume=True)
        self.assertEqual(self.adapter.calls, ['a.py'])
        self.assertEqual(stored.exit_code, 0)
        stored.close()
        other = self.base / 'different-root'
        other.mkdir()
        with self.assertRaises(StoreError):
            run_streamed(other, lambda _: (), destination=self.destination, resume=True)

    def test_hardlinked_marker_and_special_marker_are_refused(self):
        import os
        stored = self.run_scan()
        stored.close()
        marker = self.destination / 'ownership.json'
        linked = self.base / 'hardlink'
        try:
            os.link(marker, linked)
        except OSError:
            self.skipTest('Hardlinks unavailable')
        with self.assertRaises(StoreError):
            self.run_scan(resume=True)
        linked.unlink()
        if hasattr(os, 'mkfifo'):
            marker.unlink()
            os.mkfifo(marker)
            with self.assertRaises(StoreError):
                self.run_scan(resume=True)

    def test_repeated_unsafe_diagnostics_and_security_gate_are_not_lost(self):
        from devsift.inventory import SourceTarget
        from devsift.output import result

        def factory(callback):
            for index in range(3):
                target = SourceTarget('.', 'unsafe', None, None, 'noncanonical entry')
                self.assertTrue(callback(target))
                yield result('scan', complete=False, data={
                    'targets': [{'path': '.', 'status': 'unsafe'}],
                    'counts': {'executed': 0, 'skipped': 0, 'unavailable': 0, 'incomplete': 1},
                    'quality_gate': {'security_review_required': index == 0}})

        stored = run_streamed(self.root, factory, destination=self.destination)
        self.addCleanup(stored.close)
        self.assertEqual(stored.summary()['data']['target_count'], 3)
        self.assertEqual(stored.summary()['data']['counts']['incomplete'], 3)
        self.assertTrue(stored.summary()['data']['quality_gate']['security_review_required'])

    @unittest.skipUnless(os.name == 'posix', 'POSIX permission semantics required')
    def test_owned_scan_artifacts_are_private_even_with_permissive_umask(self):
        old_mask = os.umask(0)
        try:
            stored = self.run_scan()
            self.addCleanup(stored.close)
            for entry in (self.destination, *self.destination.rglob('*')):
                mode = stat.S_IMODE(entry.stat().st_mode)
                self.assertEqual(mode, 0o700 if entry.is_dir() else 0o600, str(entry))
        finally:
            os.umask(old_mask)

    def test_missing_page_downgrades_exit_and_never_inlines_unverified_data(self):
        stored = self.run_scan()
        page = json.loads(stored.connection.execute('SELECT payload FROM report_pages').fetchone()[0])
        artifact = Path(stored.bundle['index']).parent / page['files'][0]['file']
        artifact.unlink()
        self.assertEqual(stored.exit_code, 2)
        self.assertIn('REPORT_UNAVAILABLE', [error['code'] for error in stored.summary()['errors']])
        output = io.StringIO()
        stored.write_json(output)
        self.assertEqual(json.loads(output.getvalue())['data']['reports'], {})
        stored.close()


if __name__ == '__main__':
    unittest.main()
