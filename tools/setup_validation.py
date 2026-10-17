"""Explicit network setup for the pinned official SARIF validation schema."""
import hashlib
from pathlib import Path
import sys
import urllib.request

if __package__:
    from .install_progress import Progress
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from install_progress import Progress

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_URL = 'https://raw.githubusercontent.com/oasis-tcs/sarif-spec/1742a253eb654bf8a4ed7c60eaef7412b2c23553/sarif-2.1/schema/sarif-schema-2.1.0.json'
SCHEMA_SHA256 = 'c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e'
SCHEMA_BYTES = 112768
SCHEMA_PATH = ROOT / '.devsift/local/schemas/sarif-2.1.0.json'


def setup_schema(*, progress=None):
    """Download only during explicit setup; verify exact bytes before storing."""
    try:
        report = progress if progress is not None else lambda percent, stage: None
        report(0, 'Checking pinned schema cache')
        if SCHEMA_PATH.is_file():
            with SCHEMA_PATH.open('rb') as stream:
                cached = stream.read(SCHEMA_BYTES + 1)
            if len(cached) == SCHEMA_BYTES and hashlib.sha256(cached).hexdigest() == SCHEMA_SHA256:
                report(100, 'Pinned schema already available')
                return SCHEMA_PATH
        report(5, 'Downloading SARIF schema (connecting)')
        with urllib.request.urlopen(SCHEMA_URL, timeout=30) as response:
            received = bytearray()
            while len(received) <= SCHEMA_BYTES:
                chunk = response.read(min(32768, SCHEMA_BYTES + 1 - len(received)))
                if not chunk:
                    break
                received.extend(chunk)
                transfer = min(100, len(received) * 100 // SCHEMA_BYTES)
                report(5 + 80 * transfer // 100,
                       f'Downloading SARIF schema | {transfer}% ({len(received)} / {SCHEMA_BYTES} expected bytes)')
            raw = bytes(received)
        report(90, 'Verifying pinned schema checksum')
        if len(raw) != SCHEMA_BYTES or hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
            raise ValueError()
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        report(95, 'Saving verified schema')
        SCHEMA_PATH.write_bytes(raw)
        report(100, 'Pinned schema ready')
        return SCHEMA_PATH
    except (OSError, ValueError):
        raise RuntimeError('Validation schema setup unavailable') from None


if __name__ == '__main__':
    with Progress() as progress:
        try:
            setup_schema(progress=progress.update)
            progress.finish(message='Pinned official SARIF validation schema ready.')
        except RuntimeError as error:
            progress.fail(error)
            raise SystemExit(1) from None
