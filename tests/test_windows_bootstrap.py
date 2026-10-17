"""Exercise the downloaded bootstrap through real Windows PowerShell 5.1."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
import io

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt' and shutil.which('powershell'), 'Windows PowerShell 5.1 required')
class WindowsBootstrapTests(unittest.TestCase):
    def run_bootstrap(self, script, *, broken_first=False, tampered=False, bundle_bytes=None, unknown_size=False, interrupted=False):
        with tempfile.TemporaryDirectory(prefix='devsift-powershell-') as tmp:
            home = Path(tmp) / 'isolated home'
            home.mkdir()
            commands = Path(tmp) / 'commands'
            commands.mkdir()
            # Force deterministic PATH selection while still running real Python.
            for name in ('python', 'python3'):
                content = ('@echo off\r\necho broken candidate 1>&2\r\nexit /b 1\r\n'
                           if broken_first and name == 'python' else
                           f'@echo off\r\n"{sys.executable}" %*\r\n')
                (commands / (name + '.cmd')).write_text(content, encoding='utf-8', newline='')
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:
                # The Python installer boundary is covered separately by real
                # wheel tests. Here a marker proves that the entire PS bootstrap
                # reached it, with HOME redirected and no host/registry writes.
                z.writestr('install.py', 'from pathlib import Path\n'
                           'import json,sys\n'
                           'home=Path.home()\n'
                           '(home/"bootstrap-reached.json").write_text(json.dumps({"home":str(home),"python":sys.executable}))\n'
                           'print(json.dumps({"type":"progress","percent":20,"stage":"Installing fixture","elapsed":1}))\n'
                           'print(json.dumps({"type":"complete","state":{"version":"fixture","hosts":["codex"],"launcher":str(home/".local/bin/devsift")}}))\n')
                z.writestr('download-padding.txt', b'x' * 131072)
            archive = stream.getvalue() if bundle_bytes is None else bundle_bytes
            resources = {
                '/' + script: (ROOT / 'scripts' / script).read_bytes(),
                '/devsift-install.zip': archive,
                '/devsift-install.zip.sha256': (('0' * 64 if tampered else hashlib.sha256(archive).hexdigest()) + '  devsift-install.zip\n').encode(),
            }

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    body = resources.get(self.path)
                    self.send_response(200 if body is not None else 404)
                    self.send_header('Content-Type', 'text/plain' if self.path.endswith(('.ps1', '.sha256')) else 'application/zip')
                    if body is not None and not unknown_size:
                        self.send_header('Content-Length', str(len(body) + (32768 if interrupted and self.path == '/devsift-install.zip' else 0)))
                    self.end_headers()
                    self.wfile.write(body or b'')

                def log_message(self, *args):
                    pass

            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                # Replace only the asset origin for a local, checksum-bound
                # fixture. The actual script body runs through irm | iex.
                body = resources['/' + script].decode('utf-8')
                persist = """[Environment]::SetEnvironmentVariable('Path', "$bin;$userPath", 'User')"""
                self.assertEqual(body.count("[Environment]::GetFolderPath('UserProfile')"), 1)
                self.assertEqual(body.count('[Environment]::SetEnvironmentVariable('), 1)
                self.assertEqual(body.count(persist), 1)
                # Redirect only OS user-home lookup and persistent registry
                # writes. Native invocation/download/hash/extraction are real.
                body = body.replace('https://github.com/orchex006/devsift/releases/latest/download', base)
                body = body.replace("[Environment]::GetFolderPath('UserProfile')", '$env:USERPROFILE')
                body = body.replace(persist, '$null = $bin')
                self.assertEqual(body.count('$showSetupProgress = -not [Console]::IsErrorRedirected'), 1)
                body = body.replace('$showSetupProgress = -not [Console]::IsErrorRedirected', '$showSetupProgress = $true')
                resources['/' + script] = body.encode('utf-8')
                code = r'''
$ErrorActionPreference = 'Stop'
$actualUserPathBefore = [System.Environment]::GetEnvironmentVariable('Path', 'User')
function Write-Progress {
    param([int] $Id, [string] $Activity, [string] $Status, [int] $PercentComplete, [switch] $Completed)
    if ($Id -ne 71) { return }
    @{percent=$PercentComplete; status=$Status; completed=[bool]$Completed} | ConvertTo-Json -Compress | Add-Content -LiteralPath $env:DEVSIFT_TEST_PROGRESS_CAPTURE -Encoding UTF8
}
irm '__SCRIPT_URL__' | iex
if ([System.Environment]::GetEnvironmentVariable('Path', 'User') -ne $actualUserPathBefore) { throw 'Actual user PATH changed' }
'''.replace('__SCRIPT_URL__', base + '/' + script)
                env = dict(os.environ, USERPROFILE=str(home), PATH=str(commands) + os.pathsep + os.environ['PATH'])
                capture = Path(tmp) / 'progress.jsonl'
                env['DEVSIFT_TEST_PROGRESS_CAPTURE'] = str(capture)
                # Do not inherit PowerShell 7's module search path when starting
                # the distinct Windows PowerShell 5.1 host.
                env = {key: value for key, value in env.items() if key.upper() != 'PSMODULEPATH'}
                encoded = base64.b64encode(code.encode('utf-16-le')).decode()
                run = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                      '-EncodedCommand', encoded], env=env, cwd=tmp, capture_output=True,
                                     text=True, timeout=120 if bundle_bytes is not None else 45)
                events = [json.loads(line) for line in capture.read_text(encoding='utf-8-sig').splitlines()]
                percentages = [event['percent'] for event in events if not event['completed']]
                self.assertEqual(percentages, sorted(percentages))
                self.assertTrue(events[-1]['completed'])
                if unknown_size:
                    self.assertTrue(any('size unknown' in event['status'] for event in events))
                    self.assertFalse(any(re.search(r'Downloading DevSift \| \d+%', event['status']) for event in events))
                else:
                    self.assertTrue(any(re.search(r'Downloading DevSift \| [1-9][0-9]?%', event['status']) for event in events))
                if tampered:
                    self.assertNotEqual(run.returncode, 0)
                    self.assertIn('checksum mismatch', run.stderr)
                    self.assertFalse((home / 'bootstrap-reached.json').exists())
                    self.assertNotIn(100, percentages)
                    return
                if interrupted:
                    self.assertNotEqual(run.returncode, 0)
                    self.assertNotIn(100, percentages)
                    self.assertFalse((home / 'bootstrap-reached.json').exists())
                    self.assertIn('failed during: Downloading DevSift', run.stdout)
                    return
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertEqual(percentages[-1], 100)
                self.assertNotIn('"type":', run.stdout)
                self.assertNotIn('Successfully installed', run.stdout)
                if bundle_bytes is not None:
                    state = json.loads((home / '.local/share/devsift/installation.json').read_text())
                    for skill in state['skills']:
                        self.assertTrue((Path(skill) / 'references/REPORT-TEMPLATE.md').is_file())
                    result = subprocess.run([state['launcher'], '--help'], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    return
                marker = json.loads((home / 'bootstrap-reached.json').read_text())
                self.assertEqual(Path(marker['home']), home)
                self.assertEqual(Path(marker['python']), Path(sys.executable))
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)

    def test_downloaded_install_runs_through_irm_iex(self):
        self.run_bootstrap('install.ps1')

    def test_downloaded_update_skips_broken_python_candidate(self):
        self.run_bootstrap('update.ps1', broken_first=True)

    def test_checksum_mismatch_stops_before_python_installer(self):
        self.run_bootstrap('install.ps1', tampered=True)

    def test_unknown_download_size_is_not_a_fabricated_transfer_percentage(self):
        self.run_bootstrap('install.ps1', unknown_size=True)

    def test_interrupted_download_retains_failed_stage_without_ready(self):
        self.run_bootstrap('install.ps1', interrupted=True)

    @unittest.skipUnless(os.environ.get('DEVSIFT_TEST_INSTALLER_BUNDLE'), 'explicit actual installer bundle path required')
    def test_actual_bundle_through_downloaded_windows_installer(self):
        self.run_bootstrap('install.ps1', bundle_bytes=Path(os.environ['DEVSIFT_TEST_INSTALLER_BUNDLE']).read_bytes())


if __name__ == '__main__':
    unittest.main()
