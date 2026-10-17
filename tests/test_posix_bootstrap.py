"""The POSIX download UI and protocol run against a local HTTP fixture."""
import errno
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix', 'POSIX terminal required')
class PosixBootstrapTests(unittest.TestCase):
    def run_bootstrap(self, *, unknown=False, tampered=False, bundle=None):
        import pty
        import select
        import termios
        import time
        with tempfile.TemporaryDirectory(prefix='devsift-posix-') as tmp:
            home = Path(tmp) / 'home'
            home.mkdir()
            if bundle is None:
                data = io.BytesIO()
                with zipfile.ZipFile(data, 'w') as archive:
                    archive.writestr('install.py', 'import json\nfrom pathlib import Path\n'
                                     '(Path.home()/"reached").touch()\n'
                                     'print(json.dumps({"type":"progress","percent":50,"stage":"Installing fixture","elapsed":0.5}))\n'
                                     'print(json.dumps({"type":"complete","state":{"version":"fixture","hosts":["codex"],"launcher":"fixture/bin/devsift"}}))\n')
                    archive.writestr('padding.txt', b'x' * 131072)
                bundle = data.getvalue()
            digest = '0' * 64 if tampered else hashlib.sha256(bundle).hexdigest()
            payloads = {'/devsift-install.zip': bundle,
                        '/devsift-install.zip.sha256': (digest + '  devsift-install.zip\n').encode()}

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    body = payloads[self.path]
                    self.send_response(200)
                    if not unknown:
                        self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *args):
                    pass

            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            process = None
            master, slave = pty.openpty()
            termios.tcsetwinsize(slave, (24, 72))
            try:
                script = Path(tmp) / 'install.sh'
                script.write_text((ROOT / 'scripts/install.sh').read_text().replace(
                    'https://github.com/orchex006/devsift/releases/latest/download/',
                    f'http://127.0.0.1:{server.server_port}/'))
                process = subprocess.Popen(['sh', str(script)], cwd=tmp, env=dict(os.environ, HOME=str(home)),
                                           stdin=subprocess.DEVNULL, stdout=slave, stderr=slave)
                os.close(slave)
                slave = None
                parts = []
                deadline = time.monotonic() + 120
                while True:
                    self.assertLess(time.monotonic(), deadline, 'Bootstrap exceeded its test deadline')
                    if not select.select([master], [], [], 1)[0]:
                        continue
                    try:
                        chunk = os.read(master, 8192)
                    except OSError as error:
                        if error.errno == errno.EIO:
                            break
                        raise
                    if not chunk:
                        break
                    parts.append(chunk)
                status = process.wait(timeout=60)
                output = b''.join(parts).decode()
                self.assertIn('\r', output)
                self.assertIn('% setup', output)
                frames = [frame.split('\n', 1)[0] for frame in output.split('\r') if '% setup' in frame]
                self.assertTrue(all(len(frame) <= 71 for frame in frames))
                if unknown:
                    self.assertIn('size unknown', output)
                    self.assertNotRegex(output, r'Downloading DevSift \| \d+%')
                else:
                    self.assertRegex(output, r'Downloading DevSift \| [1-9][0-9]?%')
                if tampered:
                    self.assertNotEqual(status, 0)
                    self.assertNotIn('100% setup', output)
                    self.assertNotIn('ready.', output)
                    self.assertFalse((home / 'reached').exists())
                    return
                self.assertEqual(status, 0, output)
                self.assertIn('100% setup', output)
                self.assertIn('ready.', output)
                self.assertNotIn('"type":', output)
                self.assertNotIn('Successfully installed', output)
                self.assertIn('# DevSift CLI', (home / '.profile').read_text())
                if bundle is not None and (home / '.local/share/devsift/installation.json').exists():
                    state = json.loads((home / '.local/share/devsift/installation.json').read_text())
                    self.assertTrue(all((Path(skill) / 'references/REPORT-TEMPLATE.md').is_file() for skill in state['skills']))
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait()
                os.close(master)
                if slave is not None:
                    os.close(slave)
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_known_transfer_updates_one_live_display_without_logs(self):
        self.run_bootstrap()

    def test_unknown_size_does_not_claim_a_transfer_percentage(self):
        self.run_bootstrap(unknown=True)

    def test_checksum_failure_never_claims_ready(self):
        self.run_bootstrap(tampered=True)

    @unittest.skipUnless(os.environ.get('DEVSIFT_TEST_INSTALLER_BUNDLE'), 'explicit installer bundle required')
    def test_actual_bundle(self):
        self.run_bootstrap(bundle=Path(os.environ['DEVSIFT_TEST_INSTALLER_BUNDLE']).read_bytes())


if __name__ == '__main__':
    unittest.main()
