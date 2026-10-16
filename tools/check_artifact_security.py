"""Read-only bounded ZIP text/known-shape inspection, never release approval."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import struct
import sys
import unicodedata
import zipfile
import zlib

# Trusted maintainer entrypoint, not the inspected archive or consumer cwd.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devsift.redaction import Redactor, RedactionError

MAX_ARCHIVE = 8_000_000
MAX_MEMBERS = 256
MAX_MEMBER = 1_000_000
MAX_TOTAL = 4_000_000
MAX_RATIO = 100
_PRIVATE = frozenset({'.env', '.npmrc', '.pypirc', '.netrc', '.git-credentials',
                      'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519', 'credentials',
                      'credentials.json', 'credentials.csv', 'secrets.json'})
_PRIVATE_DIRS = frozenset({'.git', '.ssh', '.aws', '.azure'})
_NESTED = ('.zip', '.whl', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar', '.jar', '.nupkg')
_BINARY = ('.exe', '.dll', '.so', '.dylib', '.pyd', '.node', '.pyc', '.pyo', '.class',
           '.o', '.a', '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.woff', '.woff2')
_BINARY_MAGIC = (b'MZ', b'\x7fELF', b'\x00asm', b'%PDF-', b'\x89PNG', b'\xff\xd8\xff', b'GIF87a', b'GIF89a')
_KEY_HEADERS = tuple('-----BEGIN ' + kind + 'PRIVATE KEY-----' for kind in ('', 'RSA ', 'EC ', 'OPENSSH ', 'ENCRYPTED '))
_REVIEW = frozenset({'RECOGNIZED_SENSITIVE_SHAPE', 'PRIVATE_FILE_NAME'})


def _result(issues=(), *, digest_verified=False, members=0, inspected=0, total=0):
    issues = sorted(set(issues))
    complete = not issues and digest_verified
    return {'schema_version': '1', 'scope': 'declared_zip_text_members_known_shapes',
            'status': 'no_detected_shapes_in_declared_archive' if complete else
                      'review_required' if set(issues) & _REVIEW else 'incomplete',
            'complete': complete, 'digest_verified': digest_verified,
            'declared_members': members, 'inspected_text_members': inspected, 'inspected_text_bytes': total,
            'issues': issues, 'release_review_required': True, 'publication_authorized': False,
            'writes_authorized': False, 'execution_authorized': False, 'exit_code': 0 if complete else 2}


def _require(ok):
    if not ok:
        raise ValueError()


def _plain(path, *, file=False):
    info = path.lstat()
    _require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 1024))
    _require(stat.S_ISREG(info.st_mode) if file else stat.S_ISDIR(info.st_mode))
    return info


def _capture(path):
    path = Path(path)
    _require(path.is_absolute())
    for part in reversed(tuple(path.parents)):
        _plain(part)
    before = _plain(path, file=True)
    _require(before.st_size <= MAX_ARCHIVE)
    with path.open('rb') as stream:
        raw = stream.read(MAX_ARCHIVE + 1)
    after = _plain(path, file=True)
    _require(len(raw) <= MAX_ARCHIVE and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
             == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
    return raw


def _directory_count(raw):
    # Bound actual central records before ZipFile allocates a member list.
    position = raw.rfind(b'PK\x05\x06', max(0, len(raw) - 65557))
    _require(position >= 0 and position + 22 <= len(raw))
    _, disk, central_disk, disk_count, count, size, offset, comment = struct.unpack_from('<4s4H2LH', raw, position)
    _require(disk == central_disk == 0 and disk_count == count and count <= MAX_MEMBERS
             and offset + size == position and position + 22 + comment == len(raw))
    _require(count != 65535 and size != 4294967295 and offset != 4294967295)
    cursor = offset
    for _ in range(count):
        _require(cursor + 46 <= position and raw[cursor:cursor+4] == b'PK\x01\x02')
        name, extra, note = struct.unpack_from('<3H', raw, cursor + 28)
        _require(name <= 1024)
        cursor += 46 + name + extra + note
        _require(cursor <= position)
    _require(cursor == position and (raw.startswith(b'PK\x03\x04') if count else position == 0))
    return count, bool(comment), offset


def _safe_name(name):
    _require(type(name) is str and 0 < len(name) <= 512 and '\\' not in name and ':' not in name)
    _require(not name.startswith('/') and not any(unicodedata.category(c).startswith('C') for c in name))
    normalized_name = name[:-1] if name.endswith('/') else name
    parts = normalized_name.split('/')
    _require(all(p not in {'', '.', '..'} and not p.endswith((' ', '.')) for p in parts))
    # Ignore no Windows stream/device/path aliases, even though nothing extracts.
    devices = {'con', 'prn', 'aux', 'nul'} | {p + str(n) for p in ('com', 'lpt') for n in range(1, 10)}
    _require(all(p.split('.')[0].casefold() not in devices for p in parts))
    return unicodedata.normalize('NFC', normalized_name).casefold(), parts


def _private(parts):
    folded = [p.casefold() for p in parts]
    name = folded[-1]
    return (name in _PRIVATE or name.startswith('.env.') or name.endswith(('.pem', '.key', '.pfx', '.p12'))
            or bool(set(folded) & _PRIVATE_DIRS) or folded[:2] == ['.devsift', 'local'])


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def inspect_archive(path, *, expected_sha256):
    """Inspect one captured immutable byte string; return static codes, no names.

    The expected hash must be independently trusted. Complete means only the
    supported bounded ZIP text/known-shape inspection completed, never safe to
    publish. This function does not inspect or execute nested/compiled content.
    """
    if type(expected_sha256) is not str or re.fullmatch('[0-9a-f]{64}', expected_sha256) is None:
        return _result(['EXPECTED_DIGEST_REQUIRED'])
    try:
        raw = _capture(path)
    except (OSError, ValueError, TypeError):
        return _result(['ARCHIVE_UNAVAILABLE_OR_EXCESSIVE'])
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        return _result(['ARCHIVE_DIGEST_MISMATCH'])
    issues, inspected, total, count = set(), 0, 0, 0
    try:
        count, comment, central_offset = _directory_count(raw)
        if comment:
            issues.add('UNINSPECTED_ZIP_METADATA')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            _require(len(entries) == count)
            seen, declared_total = {}, 0
            redactor = Redactor()
            # Validate every entry's structure before opening any member.
            for entry in entries:
                key, parts = _safe_name(entry.orig_filename)
                _require(key not in seen and entry.filename == entry.orig_filename)
                _require(not any(key.startswith(parent + '/') and not directory for parent, directory in seen.items()))
                _require(entry.is_dir() or not any(old.startswith(key + '/') for old in seen))
                seen[key] = entry.is_dir()
                if _private(parts):
                    issues.add('PRIVATE_FILE_NAME')
                if redactor.text(entry.filename) != entry.filename:
                    issues.add('RECOGNIZED_SENSITIVE_SHAPE')
                mode = stat.S_IFMT(entry.external_attr >> 16)
                _require(mode in ({0, stat.S_IFDIR} if entry.is_dir() else {0, stat.S_IFREG}))
                _require(not (entry.external_attr & 1024) and not (entry.flag_bits & ~0x080E))
                _require(not ((entry.external_attr & 16) and not entry.is_dir()))
                _require(entry.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
                _require(0 <= entry.file_size <= MAX_MEMBER and entry.compress_size >= 0)
                _require(entry.file_size <= max(1, entry.compress_size) * MAX_RATIO)
                _require(not entry.is_dir() or (entry.file_size == entry.compress_size == entry.CRC == 0
                         and entry.compress_type == zipfile.ZIP_STORED))
                declared_total += entry.file_size
                _require(declared_total <= MAX_TOTAL)
                if entry.extra or entry.comment:
                    issues.add('UNINSPECTED_ZIP_METADATA')
            cursor = 0
            for entry in sorted(entries, key=lambda item: item.header_offset):
                # Local-only extras/gaps are not silently classified as inspected.
                _require(entry.header_offset == cursor and cursor + 30 <= central_offset)
                fields = struct.unpack_from('<4s5H3L2H', raw, cursor)
                signature, _, flags, method, _, _, crc, compressed, size, name_len, extra_len = fields
                _require(signature == b'PK\x03\x04' and flags == entry.flag_bits and method == entry.compress_type)
                end_header = cursor + 30 + name_len + extra_len
                _require(end_header <= central_offset)
                encoding = 'utf-8' if flags & 0x800 else 'cp437'
                _require(raw[cursor+30:cursor+30+name_len].decode(encoding) == entry.orig_filename)
                if extra_len:
                    issues.add('UNINSPECTED_ZIP_METADATA')
                cursor = end_header + entry.compress_size
                _require(cursor <= central_offset)
                if flags & 8:
                    if raw[cursor:cursor+4] == b'PK\x07\x08':
                        cursor += 4
                    _require(cursor + 12 <= central_offset)
                    _require(struct.unpack_from('<3L', raw, cursor) == (entry.CRC, entry.compress_size, entry.file_size))
                    cursor += 12
                else:
                    _require((crc, compressed, size) == (entry.CRC, entry.compress_size, entry.file_size))
            _require(cursor == central_offset)
            for entry in entries:
                if entry.is_dir():
                    continue
                lower = entry.filename.casefold()
                if lower.endswith(_NESTED):
                    issues.add('NESTED_ARCHIVE_UNINSPECTED')
                    continue
                if lower.endswith(_BINARY):
                    issues.add('BINARY_OR_UNSUPPORTED_TEXT')
                    continue
                with archive.open(entry) as member:
                    data = member.read(MAX_MEMBER + 1)
                _require(len(data) == entry.file_size and len(data) <= MAX_MEMBER)
                if data.startswith((b'PK\x03\x04', b'PK\x05\x06', b'\x1f\x8b', b'7z\xbc\xaf\x27\x1c', b'Rar!', b'BZh', b'\xfd7zXZ\x00')) or data[257:262] == b'ustar':
                    issues.add('NESTED_ARCHIVE_UNINSPECTED')
                    continue
                if data.startswith(_BINARY_MAGIC):
                    issues.add('BINARY_OR_UNSUPPORTED_TEXT')
                    continue
                try:
                    text = data.decode('utf-8')
                    _require(not any(ord(c) < 32 and c not in '\t\r\n' for c in text))
                except (UnicodeError, ValueError):
                    issues.add('BINARY_OR_UNSUPPORTED_TEXT')
                    continue
                if redactor.text(text) != text or any(header in text for header in _KEY_HEADERS):
                    issues.add('RECOGNIZED_SENSITIVE_SHAPE')
                if lower.endswith('.json'):
                    try:
                        parsed = json.loads(text, object_pairs_hook=_pairs)
                        if redactor.redact(parsed) != parsed:
                            issues.add('RECOGNIZED_SENSITIVE_SHAPE')
                    except (ValueError, RecursionError, RedactionError):
                        issues.add('STRUCTURED_TEXT_UNINSPECTED')
                inspected += 1
                total += len(data)
    except (OSError, ValueError, TypeError, EOFError, RuntimeError, struct.error, zipfile.BadZipFile, zlib.error, RedactionError):
        issues.add('UNSUPPORTED_OR_MALFORMED_ZIP')
    return _result(issues, digest_verified=True, members=count, inspected=inspected, total=total)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError()


def main(argv=None):
    try:
        parser = _Parser(description=__doc__, allow_abbrev=False)
        parser.add_argument('--archive', required=True)
        parser.add_argument('--expected-sha256', required=True)
        args = parser.parse_args(argv)
        record = inspect_archive(args.archive, expected_sha256=args.expected_sha256)
    except (ValueError, TypeError):
        record = _result(['INVALID_INSPECTION_ARGUMENTS'])
    print(json.dumps(record, sort_keys=True))
    return record['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
