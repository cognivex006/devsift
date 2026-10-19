"""Installer failure boundaries and portable launcher behavior in disposable homes."""
import importlib.util
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('devsift_installer', ROOT / 'tools/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='devsift-installer-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / 'bundle'
        (self.bundle / 'wheels').mkdir(parents=True)
        (self.bundle / 'wheels/devsift-0.0.0-py3-none-any.whl').write_bytes(b'fixture')
        (self.bundle / 'skills/devsift/references').mkdir(parents=True)
        (self.bundle / 'skills/devsift/SKILL.md').write_text('consumer skill')
        (self.bundle / 'skills/devsift/references/USAGE.md').write_text('offline workflows')
        for name in ('.codex-plugin', '.claude-plugin', '.cursor-plugin'):
            (self.bundle / name).mkdir()
            (self.bundle / name / 'plugin.json').write_text('{"name":"devsift"}')
        (self.bundle / 'gemini-extension.json').write_text('{"name":"devsift"}')
        (self.bundle / 'plugin.json').write_text('{"name":"devsift"}')
        self.home = self.root / 'home with spaces'
        self.bin = self.home / '.local/bin'
        self.bin.mkdir(parents=True)
        self.launcher = self.bin / ('devsift.cmd' if os.name == 'nt' else 'devsift')
        self.launcher.write_text('previous working launcher')

    def test_failed_pip_keeps_existing_launcher_and_skills(self):
        dest = self.home / '.agents/skills/devsift'
        dest.mkdir(parents=True)
        (dest / '.devsift-managed').touch()
        (dest / 'SKILL.md').write_text('previous skill')
        def create(path, **kwargs):
            Path(path).mkdir(parents=True)
        with patch.object(installer.venv, 'create', side_effect=create), \
                patch.object(installer.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'pip')):
            with self.assertRaises(subprocess.CalledProcessError):
                installer.install(self.bundle, self.home, self.bin, ['codex'])
        self.assertEqual(self.launcher.read_text(), 'previous working launcher')
        self.assertEqual((dest / 'SKILL.md').read_text(), 'previous skill')
        self.assertEqual(list((self.home / '.local/share/devsift/versions').iterdir()), [])

    def test_unmanaged_skill_is_preserved_before_environment_creation(self):
        dest = self.home / '.cursor/skills/devsift'
        dest.mkdir(parents=True)
        (dest / 'SKILL.md').write_text('personal customization')
        with patch.object(installer.venv, 'create') as create:
            with self.assertRaisesRegex(RuntimeError, 'unmanaged'):
                installer.install(self.bundle, self.home, self.bin, ['cursor'])
            create.assert_not_called()
        self.assertEqual((dest / 'SKILL.md').read_text(), 'personal customization')

    def test_analyzer_readiness_failure_preserves_launcher_and_managed_skill(self):
        destination = self.home / '.agents/skills/devsift'
        destination.mkdir(parents=True)
        (destination / '.devsift-managed').touch()
        (destination / 'SKILL.md').write_text('previous skill')
        def create(path, **kwargs):
            Path(path).mkdir(parents=True)
        with patch.object(installer.venv, 'create', side_effect=create), \
                patch.object(installer.subprocess, 'run'), \
                patch.object(installer, '_analyzers', side_effect=RuntimeError('Analyzer readiness failed')):
            with self.assertRaisesRegex(RuntimeError, 'readiness'):
                installer.install(self.bundle, self.home, self.bin, ['codex'], require_analyzers=True)
        self.assertEqual(self.launcher.read_text(), 'previous working launcher')
        self.assertEqual((destination / 'SKILL.md').read_text(), 'previous skill')
        self.assertEqual(list((self.home / '.local/share/devsift/versions').iterdir()), [])

    def test_analyzer_download_feedback_uses_received_bytes_and_honest_unknown_total(self):
        data = b'owned download fixture' * 10000
        for total in (str(len(data)), None):
            with self.subTest(total=total):
                response = io.BytesIO(data)
                response.headers = {} if total is None else {'Content-Length': total}
                events = []
                output = self.root / ('unknown.zip' if total is None else 'known.zip')
                with patch.object(installer.urllib.request, 'urlopen', return_value=response):
                    installer._receive('https://example.invalid/owned.zip', output,
                        lambda received, expected, stage: events.append((received, expected, stage)), 'analyzers', len(data))
                self.assertEqual(output.read_bytes(), data)
                self.assertEqual(events[0], (0, None if total is None else len(data), 'analyzers'))
                self.assertEqual(events[-1][0], len(data))
                self.assertGreater(len(events), 2)
                self.assertTrue(all(a[0] < b[0] for a, b in zip(events, events[1:])))
                self.assertTrue(all(event[1] == (None if total is None else len(data)) for event in events))

    def test_analyzer_download_refuses_short_or_invalid_or_excessive_lengths(self):
        for number, header, limit in ((0, '12', 20), (1, '-1', 20), (2, 'bad', 20), (3, None, 2)):
            with self.subTest(header=header, limit=limit):
                response = io.BytesIO(b'1234')
                response.headers = {} if header is None else {'Content-Length': header}
                with patch.object(installer.urllib.request, 'urlopen', return_value=response):
                    with self.assertRaises((RuntimeError, ValueError)):
                        installer._receive('https://example.invalid/owned.zip', self.root / str(number),
                                           lambda *args: None, 'analyzers', limit)

    def test_failed_install_reports_stage_without_dumping_pip_output(self):
        def create(path, **kwargs):
            Path(path).mkdir(parents=True)
        output = io.StringIO()
        args = ['install.py', '--bundle', str(self.bundle), '--home', str(self.home), '--progress', 'json']
        failure = subprocess.CalledProcessError(1, ['pip'], output='UNWANTED_PIP_OUTPUT', stderr='UNWANTED_PIP_ERROR')
        with patch.object(sys, 'argv', args), patch.object(installer.venv, 'create', side_effect=create), \
                patch.object(installer.subprocess, 'run', side_effect=failure), redirect_stdout(output):
            self.assertEqual(installer.main(), 1)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1]['type'], 'error')
        self.assertEqual(events[-1]['stage'], 'Installing CLI from verified local wheel')
        self.assertNotIn('UNWANTED_PIP', output.getvalue())
        self.assertFalse(any(event.get('percent') == 100 for event in events))
        self.assertEqual(self.launcher.read_text(), 'previous working launcher')

    def test_all_hosts_receive_offline_guides_and_selected_state(self):
        if os.name == 'nt':
            # Hosted Windows TEMP may already use an 8.3 alias. Exercise that
            # spelling deliberately; installation records resolved paths.
            import ctypes
            buffer = ctypes.create_unicode_buffer(4096)
            if ctypes.windll.kernel32.GetShortPathNameW(str(self.home), buffer, len(buffer)):
                self.home = Path(buffer.value)
        def create(path, **kwargs):
            Path(path).mkdir(parents=True)
        with patch.object(installer.venv, 'create', side_effect=create), \
                patch.object(installer.subprocess, 'run'):
            state = installer.install(self.bundle, self.home, self.bin, list(installer.HOST_PATHS))
        self.assertEqual(len(state['skills']), 6)
        self.assertIn('copilot', state['hosts'])
        shared = (self.home / '.agents/skills/devsift').resolve()
        self.assertEqual(sum(Path(path).resolve() == shared for path in state['skills']), 1)
        for dest in state['skills']:
            self.assertEqual((Path(dest) / 'references/USAGE.md').read_text(), 'offline workflows')
            self.assertTrue((Path(dest) / '.devsift-managed').is_file())
        self.assertIn('-I -B -m devsift', self.launcher.read_text())
        recorded = json.loads((self.home / '.local/share/devsift/installation.json').read_text())
        self.assertEqual(recorded, state)
        self.assertTrue((Path(state['plugin']) / '.claude-plugin/plugin.json').is_file())

    def test_update_removes_obsolete_instructions_in_owned_directories(self):
        dest = self.home / '.agents/skills/devsift'
        dest.mkdir(parents=True)
        (dest / '.devsift-managed').touch()
        (dest / 'obsolete.md').write_text('stale instructions')
        plugin = self.home / '.local/share/devsift/plugin'
        plugin.mkdir(parents=True)
        (plugin / '.devsift-managed').touch()
        (plugin / 'obsolete.md').write_text('stale plugin instructions')
        def create(path, **kwargs):
            Path(path).mkdir(parents=True)
        with patch.object(installer.venv, 'create', side_effect=create), \
                patch.object(installer.subprocess, 'run'):
            installer.install(self.bundle, self.home, self.bin, ['codex'])
        self.assertFalse((dest / 'obsolete.md').exists())
        self.assertFalse((plugin / 'obsolete.md').exists())
        self.assertTrue((dest / 'references/USAGE.md').is_file())


if __name__ == '__main__':
    unittest.main()
