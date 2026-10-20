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

# @DEVSIFT_PROGRESS@

ui = Progress(operation='@DEVSIFT_OPERATION@')
ui.__enter__()
stage = 'Checking Python 3.12+'


def progress(percent, label):
    global stage
    stage = label
    ui.update(percent, label)


def download(url, destination, start, end, label):
    progress(start, label + ' (connecting)')
    with urllib.request.urlopen(url, timeout=60) as response, destination.open('wb') as output:
        total = int(response.headers.get('Content-Length') or 0)
        received = 0
        ui.transfer(0, total, label)
        while True:
            chunk = response.read(32768)
            if not chunk:
                break
            output.write(chunk)
            received += len(chunk)
            ui.transfer(received, total, label)
        if total > 0 and received != total:
            raise RuntimeError('Download ended before all declared bytes arrived.')
    progress(end, f'{label} complete ({received} bytes)')


def setup():
    progress(0, stage)
    if sys.version_info < (3, 12):
        raise RuntimeError('DevSift requires Python 3.12 or later.')
    base = 'https://github.com/cognivex006/devsift/releases/latest/download/'
    with tempfile.TemporaryDirectory(prefix='devsift-') as tmp:
        archive = Path(tmp) / 'devsift-install.zip'
        download(base + archive.name, archive, 8, 40, 'devsift-install.zip')
        checksum_path = Path(tmp) / 'devsift-install.zip.sha256'
        download(base + checksum_path.name, checksum_path, 40, 44, 'devsift-install.zip.sha256')
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
        progress(55, 'Starting @DEVSIFT_OPERATION@')
        state = None
        with tempfile.TemporaryFile(mode='w+t') as errors:
            process = subprocess.Popen([sys.executable, '-I', '-B', str(bundle / 'install.py'), '--progress', 'json'],
                                       stdout=subprocess.PIPE, stderr=errors, stdin=subprocess.DEVNULL, text=True)
            try:
                while True:
                    line = process.stdout.readline(16385)
                    if not line:
                        break
                    if len(line) > 16384:
                        raise RuntimeError('Installer status message exceeded the size limit.')
                    event = json.loads(line)
                    if event['type'] == 'progress':
                        if (type(event.get('percent')) not in (int, float) or not 0 <= event['percent'] <= 100
                                or not isinstance(event.get('stage'), str) or len(event['stage']) > 2048):
                            raise RuntimeError('Installer returned an invalid progress event.')
                        if event.get('kind') == 'transfer':
                            received, total = event.get('received'), event.get('total')
                            if (type(received) is not int or received < 0 or
                                    (total is not None and (type(total) is not int or total <= 0))):
                                raise RuntimeError('Installer returned an invalid transfer event.')
                            ui.transfer(received, total, event['stage'])
                        else:
                            percent = 55 + 39 * max(0, min(100, int(event['percent']))) // 100
                            progress(percent, event['stage'])
                    elif event['type'] == 'complete':
                        state = event['state']
                    elif event['type'] == 'error':
                        raise RuntimeError(f"{event['stage']}: {event['message']}")
                    else:
                        raise RuntimeError('Installer returned an unknown status message.')
                status = process.wait()
                if status:
                    raise RuntimeError(f'DevSift installer failed (exit {status}).')
                if not isinstance(state, dict) or not state.get('version') or not state.get('hosts'):
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
    ui.close()
    print(f"DevSift {state['version']} ready.\nCLI: {state['launcher']}\nSkills: {', '.join(state['hosts'])}\n"
          'Next: restart your terminal and agent, then run devsift --help.')


try:
    setup()
except KeyboardInterrupt:
    ui.fail('Cancelled.')
    raise SystemExit(130)
except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
    ui.fail(error)
    raise SystemExit(1)
finally:
    ui.close()
PY
