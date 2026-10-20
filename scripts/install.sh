#!/bin/sh
set -eu
command -v python3 >/dev/null 2>&1 || { echo 'Install Python 3.12 or later first.' >&2; exit 1; }
python3 -I -B - <<'PY'
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

if sys.version_info < (3, 12):
    raise SystemExit('DevSift requires Python 3.12 or later.')
base = 'https://github.com/cognivex006/devsift/releases/latest/download/'
with tempfile.TemporaryDirectory(prefix='devsift-') as tmp:
    archive = Path(tmp) / 'devsift-install.zip'
    urllib.request.urlretrieve(base + archive.name, archive)
    checksum = urllib.request.urlopen(base + archive.name + '.sha256', timeout=60).read(1024).decode()
    match = re.fullmatch(r'([a-f0-9]{64})  devsift-install\.zip\s*', checksum)
    if not match or hashlib.sha256(archive.read_bytes()).hexdigest() != match[1]:
        raise SystemExit('Release checksum mismatch. Existing installation was not changed.')
    bundle = Path(tmp) / 'bundle'
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if '\\' in name or name.startswith('/') or '..' in Path(name).parts:
                raise SystemExit('Unsafe release archive path.')
        z.extractall(bundle)
    subprocess.run([sys.executable, '-I', '-B', str(bundle / 'install.py')], check=True)
home = Path.home()
path_line = '\n# DevSift CLI\nexport PATH="$HOME/.local/bin:$PATH"\n'
for name in ('.profile', '.bashrc', '.zshrc'):
    profile = home / name
    text = profile.read_text() if profile.exists() else ''
    if '# DevSift CLI' not in text:
        with profile.open('a') as stream:
            stream.write(path_line)
print('Ready. Open a new terminal, or run: export PATH="$HOME/.local/bin:$PATH"')
PY
