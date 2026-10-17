#!/bin/sh
set -eu
command -v python3 >/dev/null 2>&1 || { echo 'Install Python 3.12 or later first.' >&2; exit 1; }
python3 -I -B - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

interactive = sys.stderr.isatty()
width = 0
stage = 'Checking Python 3.12+'


def progress(percent, label):
    global width, stage
    stage = label
    if interactive:
        filled = int(percent) * 24 // 100
        line = '[{}{}] {:3d}% setup | {}'.format('#' * filled, '.' * (24 - filled), int(percent), label)
        sys.stderr.write('\r' + line.ljust(width))
        sys.stderr.flush()
        width = len(line)


def download(url, destination, start, end, label):
    progress(start, label + ' (connecting)')
    with urllib.request.urlopen(url, timeout=60) as response, destination.open('wb') as output:
        total = int(response.headers.get('Content-Length') or 0)
        received = 0
        if total > 0:
            progress(start, f'{label} | 0% (0 / {total} bytes)')
        while True:
            chunk = response.read(32768)
            if not chunk:
                break
            output.write(chunk)
            received += len(chunk)
            if total > 0:
                transfer = min(100, received * 100 // total)
                progress(start + (end - start) * transfer // 100,
                         f'{label} | {transfer}% ({received} / {total} bytes)')
            else:
                progress(start, f'{label} | size unknown ({received} bytes received)')
        if total > 0 and received != total:
            raise RuntimeError('Download ended before all declared bytes arrived.')
    progress(end, f'{label} complete ({received} bytes)')


def setup():
    progress(0, stage)
    if sys.version_info < (3, 12):
        raise RuntimeError('DevSift requires Python 3.12 or later.')
    base = 'https://github.com/orchex006/devsift/releases/latest/download/'
    with tempfile.TemporaryDirectory(prefix='devsift-') as tmp:
        archive = Path(tmp) / 'devsift-install.zip'
        download(base + archive.name, archive, 8, 40, 'Downloading DevSift')
        checksum_path = Path(tmp) / 'devsift-install.zip.sha256'
        download(base + checksum_path.name, checksum_path, 40, 44, 'Downloading checksum')
        progress(45, 'Verifying SHA256')
        checksum = checksum_path.read_text(encoding='utf-8')
        match = re.fullmatch(r'([a-f0-9]{64})  devsift-install\.zip\s*', checksum)
        if not match or hashlib.sha256(archive.read_bytes()).hexdigest() != match[1]:
            raise RuntimeError('Release checksum mismatch. Existing installation was not changed.')
        progress(50, 'Extracting verified bundle')
        bundle = Path(tmp) / 'bundle'
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if '\\' in name or name.startswith('/') or '..' in Path(name).parts:
                    raise RuntimeError('Unsafe release archive path.')
            z.extractall(bundle)
        progress(55, 'Starting installation')
        state = None
        with tempfile.TemporaryFile(mode='w+t') as errors:
            process = subprocess.Popen([sys.executable, '-I', '-B', str(bundle / 'install.py'), '--progress', 'json'],
                                       stdout=subprocess.PIPE, stderr=errors, stdin=subprocess.DEVNULL, text=True)
            try:
                for line in process.stdout:
                    event = json.loads(line)
                    if event['type'] == 'progress':
                        percent = 55 + 39 * max(0, min(100, int(event['percent']))) // 100
                        progress(percent, f"{event['stage']} | {event['elapsed']}s")
                    elif event['type'] == 'complete':
                        state = event['state']
                    elif event['type'] == 'error':
                        raise RuntimeError(f"{event['stage']}: {event['message']}")
                    else:
                        raise RuntimeError('Installer returned an unknown status message.')
                if process.wait() != 0 or state is None:
                    raise RuntimeError('DevSift installation did not complete.')
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait()
                process.stdout.close()
    progress(96, 'Configuring shell PATH')
    home = Path.home()
    path_line = '\n# DevSift CLI\nexport PATH="$HOME/.local/bin:$PATH"\n'
    for name in ('.profile', '.bashrc', '.zshrc'):
        profile = home / name
        text = profile.read_text() if profile.exists() else ''
        if '# DevSift CLI' not in text:
            with profile.open('a') as stream:
                stream.write(path_line)
    progress(100, 'Ready')
    if interactive:
        sys.stderr.write('\n')
    print(f"DevSift {state['version']} ready.\nCLI: {state['launcher']}\nSkills: {', '.join(state['hosts'])}\n"
          'Next: restart your terminal and agent, then run devsift --help.')


try:
    setup()
except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
    if interactive:
        sys.stderr.write('\n')
    print(f'DevSift setup failed while {stage}: {error}', file=sys.stderr)
    raise SystemExit(1)
PY
