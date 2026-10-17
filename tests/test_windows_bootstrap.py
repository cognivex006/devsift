"""Exercise the downloaded bootstrap through real Windows PowerShell 5.1."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
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
    def run_bootstrap(self, script, *, broken_first=False, tampered=False):
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
                           '(home/"bootstrap-reached.json").write_text(json.dumps({"home":str(home),"python":sys.executable}))\n')
            archive = stream.getvalue()
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
                resources['/' + script] = body.encode('utf-8')
                code = r'''
$ErrorActionPreference = 'Stop'
$actualUserPathBefore = [System.Environment]::GetEnvironmentVariable('Path', 'User')
irm '__SCRIPT_URL__' | iex
if ([System.Environment]::GetEnvironmentVariable('Path', 'User') -ne $actualUserPathBefore) { throw 'Actual user PATH changed' }
'''.replace('__SCRIPT_URL__', base + '/' + script)
                env = dict(os.environ, USERPROFILE=str(home), PATH=str(commands) + os.pathsep + os.environ['PATH'])
                # Do not inherit PowerShell 7's module search path when starting
                # the distinct Windows PowerShell 5.1 host.
                env = {key: value for key, value in env.items() if key.upper() != 'PSMODULEPATH'}
                encoded = base64.b64encode(code.encode('utf-16-le')).decode()
                run = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                      '-EncodedCommand', encoded], env=env, capture_output=True,
                                     text=True, timeout=45)
                if tampered:
                    self.assertNotEqual(run.returncode, 0)
                    self.assertIn('checksum mismatch', run.stderr)
                    self.assertFalse((home / 'bootstrap-reached.json').exists())
                    return
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
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


if __name__ == '__main__':
    unittest.main()
