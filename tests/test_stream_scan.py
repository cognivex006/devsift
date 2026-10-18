import gc
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import weakref

from devsift.adapters import AdapterCapability
from devsift.evidence import SourceEvidence
from devsift.inventory import inventory, iter_inventory, _read_bytes
from devsift.redaction import Redactor
from devsift.scanner import AdapterOutcome, ScanFinding, iter_scan, scan


class CleanAdapter:
    capability = AdapterCapability('stream-fixture', '1', ('python',), True)

    def analyze(self, target):
        return AdapterOutcome(True)


class StreamScanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def source(self, name, content=b'print(1)\n'):
        (self.root / name).write_bytes(content)

    def test_inventory_does_not_read_ahead_and_close_releases_snapshot(self):
        self.source('a.py')
        self.source('b.py')
        with patch('devsift.inventory._read_bytes', wraps=_read_bytes) as reader:
            targets = iter_inventory(self.root)
            self.assertEqual(reader.call_count, 0)
            target = next(targets)
            self.assertEqual(target.path, 'a.py')
            self.assertEqual(reader.call_count, 1)
            reference = weakref.ref(target)
            del target
            targets.close()
            gc.collect()
            self.assertIsNone(reference())
            self.assertEqual(reader.call_count, 1)

    def test_unlimited_stream_accepts_source_above_compatibility_cap(self):
        content = b'#' * (4 * 1024 * 1024 + 1)
        self.source('large.py', content)
        self.assertEqual(inventory(self.root).targets[0].status, 'too_large')
        self.assertEqual(next(iter_inventory(self.root)).content, content)
        records = list(iter_scan(self.root, adapters=(CleanAdapter(),)))
        self.assertTrue(records[0]['complete'])
        self.assertEqual(records[0]['data']['targets'][0]['byte_count'], len(content))
        capped = list(iter_scan(self.root, adapters=(CleanAdapter(),), max_bytes=1))
        self.assertEqual(capped[0]['data']['targets'][0]['status'], 'too_large')
        self.assertFalse(capped[0]['complete'])

    def test_scan_one_target_at_a_time_and_retains_no_prior_source(self):
        for name in ('a.py', 'b.py', 'c.py'):
            self.source(name)
        references = []

        class TrackingAdapter(CleanAdapter):
            def analyze(inner, target):
                gc.collect()
                self.assertTrue(all(reference() is None for reference in references))
                references.append(weakref.ref(target))
                return AdapterOutcome(True)

        with patch('devsift.inventory._read_bytes', wraps=_read_bytes) as reader:
            stream = iter_scan(self.root, adapters=(TrackingAdapter(),))
            first = next(stream)
            self.assertEqual(reader.call_count, 2)  # snapshot plus mutation check
            self.assertEqual(len(first['data']['targets']), 1)
            self.assertEqual(first['data']['counts'], {
                'executed': 1, 'skipped': 0, 'unavailable': 0, 'incomplete': 0})
            self.assertEqual([r['data']['targets'][0]['path'] for r in stream], ['b.py', 'c.py'])
            self.assertEqual(reader.call_count, 6)
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))

    def test_empty_scope_keeps_missing_analyzer_failure(self):
        for candidates in (None, []):
            records = list(iter_scan(self.root, candidates))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['exit_code'], 2)
            self.assertEqual(records[0]['data']['targets'], [])
            self.assertEqual(records[0]['errors'][0]['code'], 'NO_AVAILABLE_ANALYZER')
        self.assertTrue(list(iter_scan(self.root, [], adapters=(CleanAdapter(),)))[0]['complete'])

    def test_status_counts_and_existing_api_match_per_target(self):
        self.source('a.py')
        self.source('b.py', b'\x00')
        self.source('c.txt')
        (self.root / 'node_modules').mkdir()
        candidates = ['a.py', 'b.py', 'c.txt', 'missing.py', 'node_modules']
        for adapters in ((), (CleanAdapter(),)):
            actual = list(iter_scan(self.root, candidates, adapters=adapters))
            self.assertEqual(len(actual), len(candidates))
            for name, record in zip(sorted(candidates), actual):
                self.assertEqual(record, scan(self.root, [name], adapters=adapters))
                self.assertEqual(len(record['data']['targets']), 1)

    def test_findings_are_masked_and_duplicates_are_only_local(self):
        self.source('a.py')
        self.source('b.py')

        class FindingsAdapter(CleanAdapter):
            def analyze(inner, target):
                finding = ScanFinding('same-case', 'HC001', SourceEvidence(),
                                      message='private marker')
                return AdapterOutcome(False, (finding, finding))

        records = list(iter_scan(self.root, adapters=(FindingsAdapter(),),
                                 redactor=Redactor(('private marker',))))
        for record in records:
            self.assertEqual(len(record['findings']), 1)
            self.assertNotIn('private marker', json.dumps(record))
            self.assertEqual(record['data']['counts']['executed'], 1)
            self.assertEqual(record['data']['counts']['incomplete'], 1)
            self.assertEqual({e['code'] for e in record['errors']}, {
                'ADAPTER_INCOMPLETE', 'FINDING_UNRESOLVED', 'DUPLICATE_CASE_ID'})

    def test_unsafe_candidates_rejected_before_source_reads(self):
        self.source('a.py')
        with patch('devsift.inventory._read_bytes', wraps=_read_bytes) as reader:
            with self.assertRaises(ValueError):
                list(iter_inventory(self.root, ['a.py', '../outside.py']))
            self.assertEqual(reader.call_count, 0)
            records = list(iter_scan(self.root, ['a.py', '../outside.py']))
            self.assertEqual(records[0]['errors'][0]['code'], 'INVALID_SCAN_INPUT')
            self.assertEqual(reader.call_count, 0)

    def test_symlink_is_not_followed(self):
        self.source('a.py')
        try:
            (self.root / 'link.py').symlink_to(self.root / 'a.py')
        except OSError:
            self.skipTest('Host cannot create symlinks')
        record = list(iter_scan(self.root, ['link.py'], adapters=(CleanAdapter(),)))[0]
        self.assertEqual(record['data']['targets'][0]['status'], 'unsafe')
        self.assertFalse(record['complete'])

    def test_cancellation_closes_inventory_without_reading_next_file(self):
        self.source('a.py')
        self.source('b.py')
        closed = []
        original = iter_inventory

        def tracking(*args, **kwargs):
            try:
                yield from original(*args, **kwargs)
            finally:
                closed.append(True)

        with patch('devsift.scanner.iter_inventory', side_effect=tracking), patch(
                'devsift.inventory._read_bytes', wraps=_read_bytes) as reader:
            stream = iter_scan(self.root, adapters=(CleanAdapter(),))
            next(stream)
            stream.close()
            self.assertEqual(reader.call_count, 2)
            self.assertEqual(closed, [True, True])  # mutation check and outer stream

    def test_keyboard_interrupt_is_propagated_and_closes_source(self):
        self.source('a.py')

        class Interrupted(CleanAdapter):
            def analyze(self, target):
                raise KeyboardInterrupt

        stream = iter_scan(self.root, adapters=(Interrupted(),))
        with self.assertRaises(KeyboardInterrupt):
            next(stream)
        self.assertIsNone(stream.gi_frame)


if __name__ == '__main__':
    unittest.main()
