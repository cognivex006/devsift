import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.adapters import AdapterCapability
from devsift.evidence import Region, SourceEvidence, verify_source
from devsift.redaction import Redactor
from devsift.scanner import AdapterOutcome, ScanFinding, scan


class Stub:
    def __init__(self, callback, *, available=True):
        self.capability = AdapterCapability('fixture-python', '1', ('python',), available)
        self.callback = callback
        self.calls = []

    def analyze(self, target):
        self.calls.append(target.path)
        return self.callback(target)


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'core.autocrlf', 'false')
        (self.root / 'a.py').write_bytes(b'print(1)\n')
        self.git('add', 'a.py')
        self.git('commit', '-qm', 'fixture')
        self.sha = self.git('rev-parse', 'HEAD').decode().strip()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], capture_output=True,
                              check=True).stdout

    def evidence(self, path='a.py'):
        return verify_source(self.root, 'fixture', self.sha, path, Region(1, 1, 1, 6))

    def finding(self, source=None, lifecycle='NEW'):
        return ScanFinding('CASE-1', 'HC001', self.evidence() if source is None else source,
                           message='Explain the case', lifecycle_class=lifecycle)

    def test_no_analyzers_and_empty_scope_never_pass(self):
        for candidates in (None, [], ['unknown.txt']):
            record = scan(self.root, candidates)
            self.assertEqual(record['exit_code'], 2)
            self.assertFalse(record['complete'])

    def test_actual_successful_adapter_execution_and_sorted_targets(self):
        (self.root / 'b.py').write_bytes(b'print(2)\n')
        adapter = Stub(lambda target: AdapterOutcome(True))
        record = scan(self.root, ['b.py', 'a.py'], adapters=(adapter,))
        self.assertEqual(adapter.calls, ['a.py', 'b.py'])
        self.assertEqual(record['exit_code'], 0)
        self.assertTrue(record['complete'])
        self.assertEqual([t['path'] for t in record['data']['targets']], ['a.py', 'b.py'])
        self.assertNotIn('print(1)', json.dumps(record))

    def test_verified_blocking_finding_and_missing_tool_precedence(self):
        adapter = Stub(lambda target: AdapterOutcome(True, (self.finding(),)))
        record = scan(self.root, ['a.py'], adapters=(adapter,))
        self.assertEqual(record['exit_code'], 1)
        self.assertEqual(record['findings'][0]['source']['status'], 'VERIFIED')
        (self.root / 'missing.ts').write_bytes(b'const x = 1;\n')
        mixed = scan(self.root, ['a.py', 'missing.ts'], adapters=(adapter,))
        self.assertEqual(mixed['exit_code'], 2)
        self.assertEqual(mixed['enforced_count'], 1)
        self.assertFalse(mixed['complete'])

    def test_unknown_and_unproven_sources_are_incomplete(self):
        for finding in (self.finding(lifecycle='UNKNOWN'), self.finding(SourceEvidence())):
            adapter = Stub(lambda target: AdapterOutcome(True, (finding,)))
            record = scan(self.root, ['a.py'], adapters=(adapter,))
            self.assertEqual(record['exit_code'], 2)
            self.assertEqual(record['enforced_count'], 0)
            self.assertEqual(record['data']['targets'][0]['execution_status'], 'incomplete')
            self.assertEqual(record['data']['counts']['incomplete'], 1)

    def test_legacy_attribution_is_advisory_and_default_is_unknown(self):
        finding = self.finding(lifecycle='LEGACY_UNCHANGED')
        record = scan(self.root, ['a.py'], adapters=(Stub(lambda t: AdapterOutcome(True, (finding,))),))
        self.assertEqual(record['exit_code'], 0)
        self.assertEqual(record['findings'][0]['enforcement'], 'advisory')
        self.assertEqual(ScanFinding('CASE-2', 'HC001', self.evidence()).lifecycle_class, 'UNKNOWN')

    def test_wrong_target_evidence_and_changed_during_execution_are_incomplete(self):
        finding = self.finding()
        (self.root / 'b.py').write_bytes(b'print(1)\n')
        record = scan(self.root, ['b.py'], adapters=(Stub(lambda t: AdapterOutcome(True, (finding,))),))
        self.assertEqual(record['exit_code'], 2)
        self.assertEqual(record['enforced_count'], 0)
        def mutate(_):
            (self.root / 'a.py').write_bytes(b'changed by trusted callback')
            return AdapterOutcome(True)
        record = scan(self.root, ['a.py'], adapters=(Stub(mutate),))
        self.assertEqual(record['exit_code'], 2)
        self.assertEqual(record['data']['targets'][0]['execution_status'], 'incomplete')

    def test_adapter_and_finding_order_and_redacted_output(self):
        class Alternate(Stub):
            def __init__(self):
                super().__init__(lambda _: AdapterOutcome(True))
                self.capability = AdapterCapability('zzz-unused', '1', ('python',), True)
        a = ScanFinding('Z', 'HC001', self.evidence(), 'private-fixture-secret', 'NEW')
        b = ScanFinding('A', 'HC001', self.evidence(), 'private-fixture-secret', 'NEW')
        selected = Stub(lambda _: AdapterOutcome(True, (a, b)))
        alternate = Alternate()
        options = {'redactor': Redactor(('private-fixture-secret',))}
        first = scan(self.root, ['a.py'], adapters=(alternate, selected), **options)
        second = scan(self.root, ['a.py'], adapters=(selected, alternate), **options)
        self.assertEqual(first, second)
        self.assertEqual(alternate.calls, [])
        self.assertEqual([f['case_id'] for f in first['findings']], ['A', 'Z'])
        self.assertNotIn('private-fixture-secret', json.dumps(first))

    def test_invalid_and_duplicate_adapter_inputs_and_case_ids(self):
        adapter = Stub(lambda _: AdapterOutcome(True, (self.finding(), self.finding())))
        record = scan(self.root, ['a.py'], adapters=(adapter,))
        self.assertEqual(record['exit_code'], 2)
        self.assertTrue(any(e['code'] == 'DUPLICATE_CASE_ID' for e in record['errors']))
        for adapters in ([adapter], (adapter, adapter), (object(),)):
            record = scan(self.root, ['a.py'], adapters=adapters)
            self.assertEqual(record['exit_code'], 2)
        record = scan(self.root, ['../outside.py'], adapters=(adapter,))
        self.assertEqual(record['exit_code'], 2)
        record = scan(self.root, ['a.py'], adapters=(adapter,), policy={'unknown': 'private-fixture-secret'})
        self.assertEqual(record['exit_code'], 2)
        self.assertNotIn('private-fixture-secret', json.dumps(record))

    def test_changed_worktree_cannot_use_old_verified_blob_to_block(self):
        finding = self.finding()
        (self.root / 'a.py').write_bytes(b'changed worktree\n')
        record = scan(self.root, ['a.py'], adapters=(Stub(lambda t: AdapterOutcome(True, (finding,))),))
        self.assertEqual(record['exit_code'], 2)
        self.assertEqual(record['enforced_count'], 0)
        self.assertEqual(record['findings'][0]['source']['status'], 'SOURCE_UNRESOLVED')

    def test_exception_and_invalid_outcomes_are_safe(self):
        def fail(_):
            raise RuntimeError('private-fixture-secret')
        for callback in (fail, lambda t: {'complete': True},
                         lambda t: AdapterOutcome('unknown'), lambda t: AdapterOutcome(False)):
            record = scan(self.root, ['a.py'], adapters=(Stub(callback),))
            self.assertEqual(record['exit_code'], 2)
            self.assertNotIn('private-fixture-secret', json.dumps(record))
        for bad in ('unknown', None, 1, 0, []):
            with self.assertRaises(ValueError):
                AdapterOutcome(bad)

    def test_adapter_python_debug_streams_are_not_public_scan_output(self):
        def noisy(_):
            print('private-fixture-secret')
            import sys
            print('private-fixture-secret', file=sys.stderr)
            raise RuntimeError('private-fixture-secret')
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            record = scan(self.root, ['a.py'], adapters=(Stub(noisy),))
        self.assertEqual(record['exit_code'], 2)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(stderr.getvalue(), '')

    def test_explicit_secret_matching_protocol_word_preserves_machine_keys(self):
        adapter = Stub(lambda _: AdapterOutcome(True))
        record = scan(self.root, ['a.py'], adapters=(adapter,), redactor=Redactor(('complete',)))
        self.assertTrue(record['complete'])
        self.assertEqual(record['status'], 'clean')

    def test_skips_missing_and_unavailable_counts(self):
        (self.root / 'notes.txt').write_bytes(b'notes')
        (self.root / 'binary.py').write_bytes(b'\x00')
        record = scan(self.root, ['a.py', 'notes.txt', 'binary.py', 'missing.py'],
                      adapters=(Stub(lambda t: AdapterOutcome(True), available=False),))
        self.assertEqual(record['exit_code'], 2)
        self.assertEqual(record['data']['counts']['skipped'], 2)
        self.assertEqual(record['data']['counts']['unavailable'], 1)
        self.assertEqual(record['data']['counts']['incomplete'], 1)

    def test_full_context_masked_before_is_valid_not_raw_hash_compared(self):
        (self.root / 'a.py').write_bytes(b'token = "private-fixture-secret"\n')
        self.git('add', 'a.py')
        self.git('commit', '-qm', 'secret fixture')
        self.sha = self.git('rev-parse', 'HEAD').decode().strip()
        source = verify_source(self.root, 'fixture', self.sha, 'a.py', Region(1, 12, 1, 18))
        self.assertEqual(source.before, '[REDACTED]')
        adapter = Stub(lambda t: AdapterOutcome(True, (self.finding(source),)))
        record = scan(self.root, ['a.py'], adapters=(adapter,),
                      redactor=Redactor(('private-fixture-secret',)))
        self.assertEqual(record['exit_code'], 1)
        self.assertNotIn('private-fixture-secret', json.dumps(record))

    def test_scan_preserves_source_config_and_directory_entries(self):
        (self.root / 'empty').mkdir()
        (self.root / 'config.json').write_bytes(b'{"fixture":true}\n')
        def snapshot():
            return {str(p.relative_to(self.root)): None if p.is_dir() else p.read_bytes()
                    for p in self.root.rglob('*')}
        before = snapshot()
        scan(self.root, adapters=(Stub(lambda t: AdapterOutcome(True)),))
        self.assertEqual(snapshot(), before)


if __name__ == '__main__':
    unittest.main()
from contextlib import redirect_stderr, redirect_stdout
import io
