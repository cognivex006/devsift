"""Checksum-bound local fixture for all generated bootstrap variants."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from tools.build_installer import render_script
from terminal_support import assert_two_rows, capture, save_evidence

ROOT = Path(__file__).resolve().parents[1]


class BootstrapCases:
    suffix = None

    def run_bootstrap(self, operation='install', *, width=80, unknown=False, failure=None, resize=False,
                      redirected=False, bundle=None, broken_first=False):
        with tempfile.TemporaryDirectory(prefix='devsift-bootstrap-') as tmp:
            artifact_case = (failure or ('unknown' if unknown else 'ok')) + ('-actual-bundle' if bundle is not None else '-fixture')
            if broken_first:
                artifact_case += '-python-fallback'
            home = Path(tmp) / 'isolated home'
            home.mkdir()
            if bundle is None:
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, 'w') as archive:
                    transfers = ([(0, None), (25, None), (60, None), (120, None)] if unknown
                                 else [(0, 100), (25, 100), (60, None), (120, None)])
                    source = (
                        'import json,time\nfrom pathlib import Path\n'
                        '(Path.home()/"bootstrap-reached").touch()\n'
                        f'for received,total in {transfers!r}:\n'
                        ' print(json.dumps({"type":"progress","percent":0,"stage":"Downloading analyzer companion",'
                        '"elapsed":0.2,"kind":"transfer","received":received,"total":total}),flush=True)\n'
                        ' time.sleep(.08)\n'
                        'for n,stage in [(10,"Creating private environment"),(45,"Installing verified wheels"),'
                        '(65,"Checking CLI startup"),(70,"Installing skill: codex"),(72,"Installing skill: claude"),'
                        '(74,"Installing skill: gemini"),(76,"Installing skill: antigravity"),'
                        '(78,"Installing skill: cursor"),(80,"Installing skill: copilot")]:\n'
                        ' print(json.dumps({"type":"progress","percent":n,"stage":stage,"elapsed":0.2}),flush=True)\n'
                        ' time.sleep(.08)\n')
                    if failure == 'child':
                        source += 'raise SystemExit(7)\n'
                    elif failure == 'event':
                        source += 'print(json.dumps({"type":"progress","percent":"bad","stage":"invalid"}))\n'
                    elif failure == 'event-bool':
                        source += 'print(json.dumps({"type":"progress","percent":True,"stage":"invalid"}))\n'
                    else:
                        source += 'print(json.dumps({"type":"complete","state":{"version":"fixture","hosts":["codex","copilot"],"launcher":"fixture"}}))\n'
                    archive.writestr('install.py', source)
                    archive.writestr('../escape.txt' if failure == 'traversal' else 'padding.txt', b'x' * 131072)
                bundle = stream.getvalue()
            digest = '0' * 64 if failure == 'checksum' else hashlib.sha256(bundle).hexdigest()
            script = render_script(ROOT, operation + '.' + self.suffix)
            if self.suffix == 'ps1':
                persist = """[Environment]::SetEnvironmentVariable('Path', "$bin;$userPath", 'User')"""
                self.assertEqual(script.count(persist), 1)
                script = script.replace("[Environment]::GetFolderPath('UserProfile')", '$env:USERPROFILE')
                script = script.replace(persist, '$null = $bin')
            bodies = {'/devsift-install.zip': bundle,
                      '/devsift-install.zip.sha256': (digest + '  devsift-install.zip\n').encode()}

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    body = bodies[self.path]
                    self.send_response(200)
                    if not unknown:
                        self.send_header('Content-Length', str(len(body) + (32768 if failure == 'interrupted' and self.path.endswith('.zip') else 0)))
                    self.end_headers()
                    try:
                        # Keep small fixtures slow enough to observe transfer
                        # frames. Real runtime bundles are much larger and must
                        # not be artificially throttled for several minutes.
                        block = 16384 if len(body) < 1_000_000 else 262144
                        for pos in range(0, len(body), block):
                            self.wfile.write(body[pos:pos + block])
                            self.wfile.flush()
                            time.sleep(.03 if len(body) < 1_000_000 else .002)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

                def log_message(self, *args):
                    pass

            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                script = script.replace('https://github.com/orchex006/devsift/releases/latest/download', base)
                bodies['/bootstrap.' + self.suffix] = script.encode()
                env = {k: v for k, v in os.environ.items() if k.upper() != 'PSMODULEPATH'}
                env.update(USERPROFILE=str(home), HOME=str(home), TERM='xterm-256color')
                if broken_first:
                    commands = Path(tmp) / 'commands'
                    commands.mkdir()
                    (commands / 'python.cmd').write_text('@echo off\nexit /b 1\n')
                    (commands / 'python3.cmd').write_text('@echo off\n"' + sys.executable + '" %*\n')
                    env['PATH'] = str(commands) + os.pathsep + env['PATH']
                if self.suffix == 'ps1':
                    code = (
                        "$ErrorActionPreference='Stop'; "
                        "$before=[Environment]::GetEnvironmentVariable('Path','User'); "
                        f"irm '{base}/bootstrap.ps1' | iex; "
                        "if ([Environment]::GetEnvironmentVariable('Path','User') -ne $before) { throw 'User PATH changed' }")
                    argv = ['powershell', '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                            '-EncodedCommand', base64.b64encode(code.encode('utf-16-le')).decode()]
                else:
                    # Pipe context has no terminal stdin; stderr still owns the PTY.
                    argv = ['sh', '-c', f'curl -fsSL {base}/bootstrap.sh | sh']
                if redirected:
                    run = subprocess.run(argv, cwd=tmp, env=env, capture_output=True, text=True, timeout=150)
                    raw, status = run.stdout + run.stderr, run.returncode
                    self.assertNotRegex(raw, r'[\r\x1b]')
                    self.assertLess(len(raw.splitlines()), 80)
                    frames = []
                else:
                    raw, status = capture(argv, cwd=tmp, env=env, width=width, resize=resize,
                                          cancel=failure == 'cancel', timeout=150)
                    save_evidence(f'raw-{self.suffix}-{operation}-{width}-{artifact_case}', raw, [])
                    frames = assert_two_rows(self, raw, width)
                    save_evidence(f'{self.suffix}-{operation}-{width}-{artifact_case}' +
                                  ('-resize' if resize else ''), raw, frames)
                    if unknown:
                        self.assertTrue(any('size unknown' in f['lines'][0] for f in frames))
                        self.assertFalse(any(f['lines'][0].startswith('Downloading') and '%' in f['lines'][0] for f in frames))
                    else:
                        self.assertTrue(any(f['lines'][0].startswith('Downloading') and re.search(r'\b[1-9]\d?%',f['lines'][0]) for f in frames))
                    self.assertTrue(all(len(f['lines'][0]) <= f['columns'] - 1 for f in frames))
                self.assertNotIn('"type":', raw)
                self.assertNotIn('Successfully installed', raw)
                if failure:
                    self.assertNotEqual(status, 0, raw)
                    self.assertFalse(any(f['lines'][0].startswith('Overall setup') and '100%' in f['lines'][0] for f in frames))
                    self.assertNotIn(' ready.', raw)
                    if failure in {'checksum', 'interrupted', 'traversal'}:
                        self.assertFalse((home / 'bootstrap-reached').exists())
                    if failure == 'child':
                        self.assertIn('exit 7', raw)
                else:
                    self.assertEqual(status, 0, raw)
                    self.assertIn('ready.', raw)
                    if not redirected:
                        for label in ('Creating private', 'Installing verified', 'Checking CLI'):
                            if bundle is not None and not (home / 'bootstrap-reached').exists():
                                break  # actual bundle wording differs
                            self.assertIn(label[:16], raw)
                    statefile = home / '.local/share/devsift/installation.json'
                    if statefile.exists():
                        state = json.loads(statefile.read_text())
                        for skill in state['skills']:
                            self.assertTrue((Path(skill) / 'references/REPORT-TEMPLATE.md').is_file())
                return raw
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)

    def test_both_generated_variants_known_size_at_four_widths(self):
        for operation in ('install', 'update'):
            for width in (40, 48, 80, 120):
                with self.subTest(operation=operation, width=width):
                    self.run_bootstrap(operation, width=width)

    def test_unknown_checksum_interruption_for_both_variants(self):
        for operation in ('install', 'update'):
            for case in ('unknown', 'checksum', 'interrupted'):
                with self.subTest(operation=operation, case=case):
                    self.run_bootstrap(operation, unknown=case == 'unknown',
                                       failure=None if case == 'unknown' else case)

    def test_native_resize_for_both_variants(self):
        for operation in ('install', 'update'):
            self.run_bootstrap(operation, resize=True)

    def test_bad_event_child_failure_and_traversal(self):
        for case in ('event', 'event-bool', 'child', 'traversal'):
            self.run_bootstrap(failure=case)

    def test_cancellation_clears_both_variants(self):
        for operation in ('install', 'update'):
            self.run_bootstrap(operation, failure='cancel')

    def test_redirected_install_and_update_are_sparse(self):
        for operation in ('install', 'update'):
            self.run_bootstrap(operation, redirected=True)

    def test_actual_bundle_for_both_variants(self):
        import unittest
        path = os.environ.get('DEVSIFT_TEST_INSTALLER_BUNDLE')
        if not path:
            raise unittest.SkipTest('Explicit built bundle required')
        for operation in ('install', 'update'):
            self.run_bootstrap(operation, bundle=Path(path).read_bytes())
