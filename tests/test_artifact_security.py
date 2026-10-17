"""Real ZIP byte fixtures; no extraction or execution of archive source."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile
import zlib

from tools import check_artifact_security as checker

ROOT = Path(__file__).resolve().parents[1]


def zipped(entries, *, compression=zipfile.ZIP_STORED, comment=b''):
    stream = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(stream, 'w', compression=compression) as archive:
        warnings.simplefilter('ignore', UserWarning)
        for name, data in entries:
            archive.writestr(name, data)
        archive.comment = comment
    return stream.getvalue()


def snapshot(root):
    return {p.relative_to(root).as_posix(): None if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*')}


class ArtifactSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='devsift-artifact-assurance-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'declared.whl'

    def inspect(self, data):
        self.archive.write_bytes(data)
        before = snapshot(self.root)
        record = checker.inspect_archive(self.archive, expected_sha256=hashlib.sha256(data).hexdigest())
        self.assertEqual(snapshot(self.root), before)
        for key in ('publication_authorized', 'writes_authorized', 'execution_authorized'):
            self.assertIs(record[key], False)
        self.assertIs(record['release_review_required'], True)
        self.assertEqual(record['exit_code'], 0 if record['complete'] else 2)
        return record

    def test_clean_text_wheel_scope_and_source_snippet_stays_data_without_git_changes(self):
        source = self.root / 'consumer'
        source.mkdir()
        (source / 'value.py').write_text('value = 1\n')
        # Background Git maintenance is unrelated to the archive inspection and
        # must not race the exact source/Git metadata nonmutation snapshot.
        for args in (('init', '-q'), ('config', 'maintenance.auto', 'false'),
                     ('config', 'gc.auto', '0'), ('add', '--all'), ('-c', 'user.name=Fixture',
                     '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgSign=false', 'commit', '-qm', 'fixture')):
            subprocess.run(['git', '-C', str(source), *args], check=True, capture_output=True)
        marker = self.root / 'ARCHIVE_SOURCE_EXECUTED'
        code = 'from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("executed")\n'
        before_source, before_checkout = snapshot(source), snapshot(ROOT)
        index = Path(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--path-format=absolute', '--git-path', 'index'], text=True).strip())
        before_index = index.read_bytes()
        before_head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'])
        data = zipped([('devsift/source.py', code), ('report.md', '```python\n' + code + '```\n'),
                       ('devsift-0.0.0.dist-info/METADATA', 'Metadata-Version: 2.4\nName: devsift\n')])
        record = self.inspect(data)
        self.assertTrue(record['complete'], record)
        self.assertEqual(record['status'], 'no_detected_shapes_in_declared_archive')
        self.assertEqual(record['inspected_text_members'], 3)
        self.assertFalse(marker.exists())
        self.assertEqual(snapshot(source), before_source)
        self.assertEqual(snapshot(ROOT), before_checkout)
        self.assertEqual(index.read_bytes(), before_index)
        self.assertEqual(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']), before_head)

    def test_known_credentials_keys_and_private_names_require_review_without_echo(self):
        credential = 'gh' + 'p_' + 'A' * 36  # Synthetic, no liveness assertion.
        fixtures = [('source.py', 'value = "' + credential + '"'),
                    ('source.txt', '-----BEGIN OPENSSH PRIVATE KEY-----\ntruncated'),
                    ('source.txt', '-----BEGIN ENCRYPTED PRIVATE KEY-----\ntruncated'),
                    ('settings.json', '{"token":"opaque_private_canary"}'),
                    ('.env.production', 'ordinary-value'), ('.aws/config', 'ordinary-value'),
                    (credential + '.txt', 'ordinary-value')]
        for name, content in fixtures:
            with self.subTest(case=name):
                record = self.inspect(zipped([(name, content)]))
                self.assertFalse(record['complete'])
                self.assertEqual(record['status'], 'review_required')
                wire = json.dumps(record)
                for private in (credential, name, 'opaque_private_canary', 'PRIVATE KEY', str(self.archive)):
                    self.assertNotIn(private, wire)

    def test_traversal_case_duplicate_controls_alias_and_special_entries_incomplete(self):
        cases = [[('../escape.py', 'value=1')], [('/absolute.py', 'value=1')],
                 [('C:/drive.py', 'value=1')], [('CON.txt', 'value=1')],
                 [('a//b.py', 'value=1')], [('a/./b.py', 'value=1')], [('a./b.py', 'value=1')],
                 [('a.py', 'x'), ('A.py', 'x')], [('a.py', 'x'), ('a.py', 'x')],
                 [('a', 'x'), ('a/b', 'x')], [('a/b', 'x'), ('a', 'x')], [('a\x1b.py', 'x')]]
        for entries in cases:
            with self.subTest(case=entries):
                self.assertFalse(self.inspect(zipped(entries))['complete'])
        # ZipInfo writers normalize Windows backslashes; mutate actual stored
        # filename bytes so the regression reaches the original central name.
        raw = zipped([('a/file.py', 'value=1')]).replace(b'a/file.py', b'a\\file.py')
        self.assertFalse(self.inspect(raw)['complete'])
        raw = zipped([('safe.txt', 'value=1')]).replace(b'safe.txt', b'saf\x00.txt')
        self.assertFalse(self.inspect(raw)['complete'])
        directory_payload = zipfile.ZipInfo('assets/')
        directory_payload.external_attr = (stat.S_IFDIR | 0o755) << 16 | 16
        self.assertFalse(self.inspect(zipped([(directory_payload, b'uninspected directory payload')]))['complete'])
        for kind in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR):
            entry = zipfile.ZipInfo('declared.txt')
            entry.create_system = 3
            entry.external_attr = (kind | 0o777) << 16
            self.assertFalse(self.inspect(zipped([(entry, b'target')]))['complete'])
        encrypted = bytearray(zipped([('source.py', 'value=1')]))
        central = encrypted.find(b'PK\x01\x02')
        struct.pack_into('<H', encrypted, 6, 1)
        struct.pack_into('<H', encrypted, central + 8, 1)
        self.assertFalse(self.inspect(bytes(encrypted))['complete'])

    def test_binary_nested_unsupported_encoding_and_uninspected_metadata_incomplete(self):
        fixtures = [zipped([('binary.dll', b'ascii is still a declared binary')]),
                    zipped([('data.bin', b'\x00\xff\x00')]),
                    zipped([('renamed.txt', b'%PDF-1.7 ordinary text is not supported document inspection')]),
                    zipped([('data.txt', 'text'.encode('utf-16'))]),
                    zipped([('nested.zip', zipped([('text.txt', 'nested')]))]),
                    zipped([('renamed.dat', zipped([('text.txt', 'nested')]))]),
                    zipped([('settings.json', '{"token":1,"token":2}')]),
                    zipped([('text.txt', 'ordinary')], comment=b'private uninspected comment')]
        for data in fixtures:
            self.assertFalse(self.inspect(data)['complete'])
        # Local-only extra metadata must not disappear behind central-directory APIs.
        data = bytearray(zipped([('text.txt', 'ordinary')]))
        insert = 30 + struct.unpack_from('<H', data, 26)[0]
        extra = struct.pack('<HH', 65535, 4) + b'hide'
        data[insert:insert] = extra
        struct.pack_into('<H', data, 28, len(extra))
        end = data.rfind(b'PK\x05\x06')
        old_offset = struct.unpack_from('<L', data, end + 16)[0]
        struct.pack_into('<L', data, end + 16, old_offset + len(extra))
        self.assertIn('UNINSPECTED_ZIP_METADATA', self.inspect(bytes(data))['issues'])

    def test_hash_required_before_parsing_tamper_and_same_captured_snapshot(self):
        data = zipped([('text.txt', 'ordinary')])
        self.archive.write_bytes(data)
        with patch.object(checker, '_capture', side_effect=AssertionError('must not read')):
            for invalid in (None, '', 'a' * 63, 'G' * 64):
                record = checker.inspect_archive(self.archive, expected_sha256=invalid)
                self.assertFalse(record['complete'])
                self.assertFalse(record['digest_verified'])
        self.archive.write_bytes(data + b'tamper')
        record = checker.inspect_archive(self.archive, expected_sha256=hashlib.sha256(data).hexdigest())
        self.assertEqual(record['issues'], ['ARCHIVE_DIGEST_MISMATCH'])
        self.archive.write_bytes(data)
        capture = checker._capture
        def swap_after_capture(path):
            raw = capture(path)
            self.archive.write_bytes(b'replaced after captured bytes')
            return raw
        with patch.object(checker, '_capture', side_effect=swap_after_capture):
            result = checker.inspect_archive(self.archive, expected_sha256=hashlib.sha256(data).hexdigest())
        self.assertTrue(result['complete'])  # Hash and parser consumed the same snapshot.

    def test_forged_stored_and_deflate_sizes_crc_and_trailing_streams_fail_closed(self):
        prefix = b'safe'
        canary = ('gh' + 'p_' + 'A' * 36).encode('ascii')
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            data = bytearray(zipped([('source.txt', prefix + canary)], compression=method))
            central = data.find(b'PK\x01\x02')
            crc = zlib.crc32(prefix)
            struct.pack_into('<L', data, 14, crc)
            struct.pack_into('<L', data, 22, len(prefix))
            struct.pack_into('<L', data, central + 16, crc)
            struct.pack_into('<L', data, central + 24, len(prefix))
            forged = bytes(data)
            # Reproduce the reviewer: stdlib member reading trusts forged size.
            with zipfile.ZipFile(io.BytesIO(forged)) as archive:
                self.assertEqual(archive.read('source.txt'), prefix)
            with self.subTest(method=method):
                record = self.inspect(forged)
                self.assertFalse(record['complete'])
                self.assertEqual(record['status'], 'incomplete')
                self.assertNotIn(canary.decode(), json.dumps(record))
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            data = bytearray(zipped([('source.txt', prefix)], compression=method))
            central = data.find(b'PK\x01\x02')
            struct.pack_into('<L', data, 14, 0)
            struct.pack_into('<L', data, central + 16, 0)
            with self.subTest(actual_crc=method):
                self.assertFalse(self.inspect(bytes(data))['complete'])
        class NonSeekable(io.BytesIO):
            def seek(self, *args):
                raise OSError('nonseekable fixture')
        stream = NonSeekable()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('source.txt', prefix)
        self.assertTrue(self.inspect(stream.getvalue())['complete'])
        compressor = zlib.compressobj(wbits=-15)
        second = compressor.compress(canary) + compressor.flush()
        for suffix in (b'raw trailing private canary', second, None):
            data = bytearray(zipped([('source.txt', prefix)], compression=zipfile.ZIP_DEFLATED))
            length = struct.unpack_from('<L', data, 18)[0]
            start = 30 + struct.unpack_from('<H', data, 26)[0] + struct.unpack_from('<H', data, 28)[0]
            end = start + length
            if suffix is None:
                del data[end-1:end]  # Remove the deflate end marker byte.
                delta = -1
            else:
                data[end:end] = suffix
                delta = len(suffix)
            struct.pack_into('<L', data, 18, length + delta)
            central = data.find(b'PK\x01\x02')
            struct.pack_into('<L', data, central + 20, length + delta)
            eocd = data.rfind(b'PK\x05\x06')
            struct.pack_into('<L', data, eocd + 16, central)
            with self.subTest(suffix_kind='truncated' if suffix is None else 'concatenated' if suffix == second else 'trailing'):
                self.assertFalse(self.inspect(bytes(data))['complete'])

    def test_windows_superscript_device_aliases_rejected_as_actual_zip_names(self):
        for prefix in ('COM', 'LPT'):
            for digit in ('\u00b9', '\u00b2', '\u00b3'):
                for extension in ('', '.txt', '.tar.gz'):
                    with self.subTest(prefix=prefix, digit=digit, extension=extension):
                        self.assertFalse(self.inspect(zipped([(prefix + digit + extension, 'ordinary')]))['complete'])

        # Do not broaden this documented six-name exception to other superscripts.
        self.assertTrue(self.inspect(zipped([('COM\u2074.txt', 'ordinary')]))['complete'])

    def test_actual_size_member_count_total_ratio_and_malformed_limits(self):
        fixtures = [b'not a zip', b'x' * (checker.MAX_ARCHIVE + 1),
                    zipped([('large.txt', b'x' * (checker.MAX_MEMBER + 1))]),
                    zipped([(str(n) + '.txt', 'x') for n in range(checker.MAX_MEMBERS + 1)]),
                    zipped([(str(n) + '.txt', b'x' * 900000) for n in range(5)]),
                    zipped([('compressed.txt', b'x' * 100000)], compression=zipfile.ZIP_DEFLATED)]
        for data in fixtures:
            record = self.inspect(data)
            self.assertFalse(record['complete'])
            self.assertEqual(record['exit_code'], 2)
        supported = zipped([('text.txt', 'plain unique text ' + ''.join(chr(33 + n % 90) for n in range(100)))], compression=zipfile.ZIP_DEFLATED)
        self.assertTrue(self.inspect(supported)['complete'])

    @unittest.skipUnless(os.name == 'nt', 'actual Windows junction fixture')
    def test_windows_junction_path_is_rejected_without_reading_or_writing_target(self):
        directory = self.root / 'physical-directory'
        directory.mkdir()
        data = zipped([('text.txt', 'ordinary')])
        archive = directory / 'archive.zip'
        archive.write_bytes(data)
        junction = self.root / 'junction'
        run = subprocess.run(['cmd', '/d', '/c', 'mklink', '/J', str(junction), str(directory)],
                             capture_output=True, timeout=30)
        if run.returncode:
            self.skipTest('Host disallows actual junction creation')
        before = snapshot(directory)
        result = checker.inspect_archive(junction / 'archive.zip', expected_sha256=hashlib.sha256(data).hexdigest())
        self.assertFalse(result['complete'])
        self.assertFalse(result['digest_verified'])
        self.assertEqual(snapshot(directory), before)

    def test_actual_cli_static_json_and_filesystem_links_are_read_only(self):
        data = zipped([('text.txt', 'ordinary')])
        self.archive.write_bytes(data)
        command = [sys.executable, '-I', '-B', str(ROOT / 'tools/check_artifact_security.py')]
        run = subprocess.run([*command, '--archive', str(self.archive), '--expected-sha256', hashlib.sha256(data).hexdigest()],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)['complete'])
        bad = subprocess.run([*command, '--private-sensitive-argument'], capture_output=True, text=True, timeout=30)
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn('private-sensitive-argument', bad.stdout + bad.stderr)
        link = self.root / 'linked.zip'
        try:
            link.symlink_to(self.archive)
        except OSError as error:
            self.skipTest('Host disallows actual symbolic links: ' + type(error).__name__)
        before = self.archive.read_bytes()
        result = checker.inspect_archive(link, expected_sha256=hashlib.sha256(data).hexdigest())
        self.assertFalse(result['complete'])
        directory_link = self.root / 'directory-alias'
        directory_link.symlink_to(self.root, target_is_directory=True)
        self.assertFalse(checker.inspect_archive(directory_link / self.archive.name,
                         expected_sha256=hashlib.sha256(data).hexdigest())['complete'])
        self.assertEqual(self.archive.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
