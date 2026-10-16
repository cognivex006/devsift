"""Explicit network setup for the pinned official SARIF validation schema."""
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_URL = 'https://raw.githubusercontent.com/oasis-tcs/sarif-spec/1742a253eb654bf8a4ed7c60eaef7412b2c23553/sarif-2.1/schema/sarif-schema-2.1.0.json'
SCHEMA_SHA256 = 'c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e'
SCHEMA_BYTES = 112768
SCHEMA_PATH = ROOT / '.devsift/local/schemas/sarif-2.1.0.json'


def setup_schema():
    """Download only during explicit setup; verify exact bytes before storing."""
    try:
        if SCHEMA_PATH.is_file():
            with SCHEMA_PATH.open('rb') as stream:
                cached = stream.read(SCHEMA_BYTES + 1)
            if len(cached) == SCHEMA_BYTES and hashlib.sha256(cached).hexdigest() == SCHEMA_SHA256:
                return SCHEMA_PATH
        with urllib.request.urlopen(SCHEMA_URL, timeout=30) as response:
            raw = response.read(SCHEMA_BYTES + 1)
        if len(raw) != SCHEMA_BYTES or hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
            raise ValueError()
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_PATH.write_bytes(raw)
        return SCHEMA_PATH
    except (OSError, ValueError):
        raise RuntimeError('Validation schema setup unavailable') from None


if __name__ == '__main__':
    try:
        setup_schema()
        print('Pinned official SARIF validation schema ready.')
    except RuntimeError:
        raise SystemExit('Validation schema setup unavailable') from None
