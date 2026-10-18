"""Visual terminal behavior and unpolluted protocol/redirected output."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from tools.install_progress import Progress, cells
from terminal_support import assert_two_rows, capture, save_evidence


class Terminal(io.StringIO):
    def isatty(self):
        return True


class InstallProgressTests(unittest.TestCase):
    def test_two_active_rows_unicode_narrow_resize_and_spinner(self):
        for width in (40, 48, 80, 120):
            with self.subTest(width=width):
                display = Terminal()
                with patch('tools.install_progress.shutil.get_terminal_size', return_value=os.terminal_size((width, 24))):
                    with redirect_stdout(io.StringIO()), Progress(stream=display) as progress:
                        progress.update(10, 'Creating Python environment 界e\u0301' * 10)
                        for _ in range(10):
                            progress._draw()
                        progress.update(45, 'Installing verified wheel')
                        progress.transfer(50, 200, 'devsift-install.zip')
                        progress.transfer(75, None, 'bundle.zip')
                        progress.update(65, 'Validating CLI')
                        progress.finish(message='Ready.')
                raw = display.getvalue()
                frames = assert_two_rows(self, raw, width)
                self.assertTrue(any('25%' in f['lines'][0] for f in frames))
                self.assertTrue(any('size unknown' in f['lines'][0] for f in frames))
                self.assertEqual(len({f['lines'][1][0] for f in frames}), 4)
                save_evidence(f'python-simulated-{width}', raw, frames)

    def test_cleanup_on_exception_and_suspend_before_prompt(self):
        display = Terminal()
        with self.assertRaisesRegex(RuntimeError, 'fixture'):
            with Progress(stream=display) as progress:
                progress.update(20, 'Installing')
                with progress.suspend():
                    self.assertFalse(progress.active)
                    display.write('Prompt\n')
                    # Real prompts advance normally; start a fresh region below.
                raise RuntimeError('fixture')
        self.assertTrue(display.getvalue().endswith('\x1b[?25h'))
        self.assertFalse(progress.worker.is_alive())

    def test_sanitize_control_characters_and_cell_width(self):
        self.assertEqual(cells('界e\u0301界', 4), '界e\u0301')
        self.assertNotIn('\x1b', cells('\x1b[2J\r\n\t', 80))

    def test_json_protocol_preserves_stages(self):
        output = io.StringIO()
        with redirect_stdout(output), Progress('json') as progress:
            progress.update(10, 'Creating environment')
            progress.update(65, 'Checking CLI startup')
            progress.finish(state={'version': 'fixture'})
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1], {'type': 'complete', 'state': {'version': 'fixture'}})
        percentages = [e['percent'] for e in events if e['type'] == 'progress']
        self.assertEqual(percentages, sorted(percentages))
        self.assertNotIn('\x1b', output.getvalue())

    def test_redirected_console_has_bounded_stage_events_and_no_controls(self):
        display, output = io.StringIO(), io.StringIO()
        with redirect_stdout(output), Progress(stream=display) as progress:
            for i in range(100):
                progress.update(i, 'Stage ' + str(i))
                progress._draw()
            progress.finish(message='Ready.')
        self.assertLessEqual(len(display.getvalue().splitlines()), 24)
        self.assertNotRegex(display.getvalue(), r'[\r\x1b]')
        self.assertEqual(output.getvalue(), 'Ready.\n')

    def test_failure_clears_rows_without_ready(self):
        display = Terminal()
        with Progress(stream=display) as progress:
            progress.update(45, 'Verifying checksum')
            progress.fail(RuntimeError('Checksum mismatch'))
        raw = display.getvalue()
        self.assertIn('Setup failed while Verifying checksum: Checksum mismatch', raw)
        self.assertNotIn('100%', raw)
        self.assertLess(raw.index('\x1b[?25h'), raw.index('Setup failed'))
        self.assertFalse(progress.worker.is_alive())

    def test_direct_python_in_native_terminal(self):
        # This is the same renderer install.py uses; no network or user-home writes.
        with tempfile.TemporaryDirectory(prefix='devsift-direct-pty-') as tmp:
            source = Path(__file__).resolve().parents[1] / 'tools/install_progress.py'
            code = ("import sys,time; sys.path.insert(0," + repr(str(source.parent)) + "); "
                    "from install_progress import Progress; p=Progress(); p.__enter__(); "
                    "p.update(10,'Creating private Python environment'); time.sleep(.8); "
                    "p.update(45,'Installing wheels'); time.sleep(.5); p.finish(message='Fixture ready.')")
            for width in (40, 48, 80, 120):
                raw, status = capture([sys.executable, '-I', '-B', '-c', code], cwd=tmp,
                                      env=dict(os.environ), width=width)
                self.assertEqual(status, 0, raw)
                frames = assert_two_rows(self, raw, width)
                save_evidence(f'python-native-{os.name}-{width}', raw, frames)


if __name__ == '__main__':
    unittest.main()
