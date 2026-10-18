"""Large committed source is proved in bounded chunks and displayed fully masked."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from devsift import evidence
from devsift.evidence import Region, SourceEvidence, verify_source
from devsift.redaction import Redactor


class LargeSourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='devsift-large-evidence-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        for name, value in [('user.name', 'Fixture'), ('user.email', 'fixture@example.invalid'),
                            ('core.autocrlf', 'false'), ('core.fsmonitor', 'false'),
                            ('maintenance.auto', 'false'), ('gc.auto', '0'),
                            ('core.hooksPath', str(self.root / 'no-hooks'))]:
            self.git('config', name, value)

    def git(self, *args, data=None):
        options = {'input': data} if data is not None else {'stdin': subprocess.DEVNULL}
        return subprocess.run(['git', '-C', str(self.root), *args], capture_output=True,
                              check=True, timeout=20, **options).stdout

    def commit(self, data, name='large.py'):
        (self.root / name).write_bytes(data)
        self.git('add', '--', name)
        self.git('-c', 'commit.gpgSign=false', 'commit', '-qm', 'large source fixture')
        return self.git('rev-parse', 'HEAD').decode().strip()

    def prove(self, sha, region=None, **options):
        return verify_source(self.root, 'fixture/repo', sha, 'large.py',
                             region or Region(1, 1, 1, 2), **options)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file()}

    def test_large_utf8_long_line_crlf_and_immutable_reproof_are_read_only(self):
        # One very long line, split multibyte code points and CRLF across chunks.
        repeats = (65_537 * 35 - 1) // 6  # six UTF-8 bytes, two code points
        raw = ('α😀' * repeats + '\r\nไทยe\u0301\r\nlast\r').encode()
        sha = self.commit(raw)
        (self.root / 'large.py').write_bytes(b'dirty working copy is not source proof\n')
        before = self.snapshot()
        with patch('devsift.evidence._SOURCE_CHUNK_BYTES', 65_537):
            first = self.prove(sha, Region(1, repeats * 2 - 1, 1, repeats * 2 + 1))
            second = self.prove(sha, Region(2, 1, 2, 6))
            last = self.prove(sha, Region(3, 1, 3, 6))
        for value in (first, second, last):
            self.assertEqual(value.status, 'VERIFIED')
            self.assertEqual(value.before, '[REDACTED]')
            self.assertEqual(value.location.source_sha, sha)
            self.assertEqual(SourceEvidence.from_dict(value.to_dict(), repo_root=self.root), value)
        self.assertEqual(self.snapshot(), before)

    def test_large_region_bounds_match_lf_and_unicode_codepoints(self):
        sha = self.commit(('α😀' * 400_000 + '\r\nไทยe\u0301\r\n').encode())
        for region in (Region(1, 800_002, 1, 800_002), Region(2, 1, 2, 7),
                       Region(3, 1, 3, 1), Region(9, 1, 9, 1)):
            with self.subTest(region=region):
                value = self.prove(sha, region)
                self.assertEqual(value.reason, 'REGION_UNAVAILABLE')
                self.assertIsNone(value.location)
                self.assertIsNone(value.before)
        self.assertEqual(self.prove(sha, Region(2, 6, 2, 6)).status, 'VERIFIED')

    def test_full_stream_rejects_late_nul_and_invalid_utf8_after_valid_region(self):
        for index, bad in enumerate((b'\0late', b'\xff', b'\xf0\x9f')):
            with self.subTest(bad=index):
                sha = self.commit(b'x' * 2_100_000 + bad)
                value = self.prove(sha)
                self.assertEqual(value.status, 'SOURCE_UNRESOLVED')
                self.assertIsNone(value.location)
                self.assertIsNone(value.before)

    def test_large_display_and_expected_before_never_certify_imported_plaintext(self):
        secret = 'gh' + 'p_' + 'a' * 36
        sha = self.commit(('visible\n' + 'x' * 2_100_000 + '\npassword=' + secret).encode())
        for sensitive in (False, True):
            good = self.prove(sha, expected_before='[REDACTED]', sensitive=sensitive)
            self.assertEqual(good.status, 'VERIFIED')
            self.assertEqual(good.before, '[REDACTED]')
            for expected in ('v', 'visible', secret, 'password=' + secret):
                with self.subTest(sensitive=sensitive, expected_length=len(expected)):
                    bad = self.prove(sha, expected_before=expected, sensitive=sensitive,
                                     redactor=Redactor((secret,)))
                    self.assertEqual(bad.reason, 'SOURCE_MISMATCH')
                    self.assertNotIn(secret, json.dumps(bad.to_dict()))

    def test_symlink_and_gitlink_modes_are_refused_without_reading_targets(self):
        sha = self.commit(b'x' * 2_100_000)
        blob = self.git('hash-object', '-w', '--stdin', data=b'/outside/private/source').decode().strip()
        for mode, object_id in [('120000', blob), ('160000', sha)]:
            with self.subTest(mode=mode):
                self.git('update-index', '--add', '--cacheinfo', mode + ',' + object_id + ',large.py')
                self.git('-c', 'commit.gpgSign=false', 'commit', '-qm', 'link mode fixture')
                link_sha = self.git('rev-parse', 'HEAD').decode().strip()
                with patch('devsift.evidence._stream_region', side_effect=AssertionError('link was read')):
                    result = self.prove(link_sha)
                self.assertEqual(result.reason, 'UNSUPPORTED_SOURCE')
                self.assertNotEqual(sha, link_sha)

    def test_raw_git_stream_does_not_run_filters_and_has_bounded_reads(self):
        sha = self.commit(b'x' * 2_100_000)
        real_popen = subprocess.Popen
        processes, lengths = [], []

        class Stream:
            def __init__(self, wrapped):
                self.wrapped = wrapped

            def read(self, size):
                lengths.append(size)
                return self.wrapped.read(size)

            def close(self):
                self.wrapped.close()

        def tracked(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            # subprocess.run also uses Popen; inspect only the raw streaming call.
            if kwargs.get('bufsize') == 0:
                self.assertEqual(kwargs['env']['GIT_NO_LAZY_FETCH'], '1')
                self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
                self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
                self.assertIn('--no-pager', args[0])
                self.assertNotIn('--filters', args[0])
                self.assertNotIn('--textconv', args[0])
                process.stdout = Stream(process.stdout)
                processes.append(process)
            return process

        with patch('devsift.evidence.subprocess.Popen', side_effect=tracked):
            result = self.prove(sha)
        self.assertEqual(result.status, 'VERIFIED')
        self.assertTrue(lengths)
        self.assertEqual(set(lengths), {65_536})
        self.assertTrue(all(process.poll() == 0 for process in processes))

    def test_timeout_and_cancellation_kill_reap_and_close_owned_stream(self):
        class BlockingStream:
            def __init__(self, stopped):
                self.stopped = stopped
                self.closed = False

            def read(self, size):
                self.stopped.wait(5)
                return b''

            def close(self):
                self.closed = True

        class Process:
            def __init__(self):
                self.stopped = threading.Event()
                self.stdout = BlockingStream(self.stopped)
                self.returncode = None
                self.killed = self.waited = False

            def poll(self):
                return self.returncode

            def kill(self):
                self.killed = True
                self.returncode = -9
                self.stopped.set()

            def wait(self, timeout=None):
                self.waited = True
                return self.returncode

        for cancelled in (False, True):
            process = Process()
            patches = [patch('devsift.evidence.subprocess.Popen', return_value=process)]
            if cancelled:
                patches.append(patch('devsift.evidence.time.monotonic', side_effect=[0, KeyboardInterrupt]))
            else:
                patches.append(patch('devsift.evidence.time.monotonic', side_effect=[0, 1]))
            with patches[0], patches[1]:
                with self.assertRaises(KeyboardInterrupt if cancelled else subprocess.TimeoutExpired):
                    evidence._stream_region(self.root, 'a' * 40, 2_100_000, Region(1, 1, 1, 2),
                                            timeout_seconds=0.1)
            self.assertTrue(process.killed)
            self.assertTrue(process.waited)
            self.assertTrue(process.stdout.closed)
        self.assertFalse(any(t.name == 'devsift-source-proof' for t in threading.enumerate()))

    def test_streamed_object_digest_rejects_same_size_byte_tampering(self):
        sha = self.commit(b'x' * 2_100_000)
        real_popen = subprocess.Popen

        class ChangedStream:
            def __init__(self, stream):
                self.stream = stream
                self.changed = False

            def read(self, size):
                chunk = self.stream.read(size)
                if chunk and not self.changed:
                    self.changed = True
                    return b'y' + chunk[1:]
                return chunk

            def close(self):
                self.stream.close()

        def changed(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            if kwargs.get('bufsize') == 0:
                process.stdout = ChangedStream(process.stdout)
            return process

        with patch('devsift.evidence.subprocess.Popen', side_effect=changed):
            value = self.prove(sha)
        self.assertEqual(value.status, 'SOURCE_UNRESOLVED')
        self.assertIsNone(value.before)

    def test_cancelled_real_git_child_is_reaped_and_its_pipe_closed(self):
        sha = self.commit(b'x' * 2_100_000)
        blob = self.git('rev-parse', sha + ':large.py').decode().strip()
        real_popen = subprocess.Popen
        processes = []
        stopped = threading.Event()

        class SlowStream:
            def __init__(self, stream):
                self.stream = stream

            def read(self, size):
                chunk = self.stream.read(size)
                stopped.wait(5)
                return chunk

            def close(self):
                self.stream.close()

        def slow(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            process.stdout = SlowStream(process.stdout)
            real_kill = process.kill

            def kill():
                try:
                    real_kill()
                finally:
                    stopped.set()

            process.kill = kill
            processes.append(process)
            return process

        import _thread
        interrupt = threading.Timer(0.1, _thread.interrupt_main)
        try:
            with patch('devsift.evidence.subprocess.Popen', side_effect=slow):
                interrupt.start()
                with self.assertRaises(KeyboardInterrupt):
                    evidence._stream_region(self.root, blob, 2_100_000, Region(1, 1, 1, 2),
                                            timeout_seconds=None)
        finally:
            interrupt.cancel()
            interrupt.join()
        self.assertTrue(processes)
        self.assertTrue(all(p.poll() is not None and p.stdout.stream.closed for p in processes))
        self.assertFalse(any(t.name == 'devsift-source-proof' for t in threading.enumerate()))

    def test_explicit_wait_for_completion_proves_large_source_and_forwards_reproof(self):
        sha = self.commit(b'x' * 2_100_000 + b'\nlate\n')
        with patch('devsift.evidence.time.monotonic', side_effect=AssertionError('unexpected deadline')):
            value = self.prove(sha, source_timeout_seconds=None)
            again = SourceEvidence.from_dict(value.to_dict(), repo_root=self.root,
                                             source_timeout_seconds=None)
        self.assertEqual(value.status, 'VERIFIED')
        self.assertEqual(again, value)
        # A normal invocation still selects the finite ten-second default.
        original = evidence._stream_region
        with patch('devsift.evidence._stream_region', wraps=original) as streamed:
            self.assertEqual(self.prove(sha).status, 'VERIFIED')
        self.assertEqual(streamed.call_args.kwargs['timeout_seconds'], 10)

    def test_source_timeout_contract_is_explicit_bounded_and_not_wire_controlled(self):
        sha = self.commit(b'x' * 2_100_000)
        value = self.prove(sha)
        for invalid in (True, False, 0, -1, 3601, 10 ** 1000, float('nan'), float('inf'), '10', object()):
            with self.subTest(type=type(invalid).__name__):
                with self.assertRaises(evidence.EvidenceError):
                    self.prove(sha, source_timeout_seconds=invalid)
                with self.assertRaises(evidence.EvidenceError):
                    SourceEvidence.from_dict(value.to_dict(), repo_root=self.root,
                                             source_timeout_seconds=invalid)
        wire = value.to_dict()
        wire['source_timeout_seconds'] = None
        with self.assertRaises(evidence.EvidenceError):
            SourceEvidence.from_dict(wire, repo_root=self.root)
        for valid in (0.1, 3600, None):
            with self.subTest(timeout=valid), patch('devsift.evidence._stream_region', return_value=True) as streamed:
                self.assertEqual(self.prove(sha, source_timeout_seconds=valid).status, 'VERIFIED')
                self.assertEqual(streamed.call_args.kwargs['timeout_seconds'], valid)


if __name__ == '__main__':
    unittest.main()
