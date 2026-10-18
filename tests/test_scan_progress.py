"""Full scan heartbeat has exactly two live rows and restores the real console."""
import io
import os
from pathlib import Path
import sys
import unittest

from devsift.scan_progress import ScanProgress, _clip
from terminal_support import capture, save_evidence, screens


ROOT = Path(__file__).resolve().parents[1]


class Terminal(io.StringIO):
    def isatty(self):
        return True


class ScanProgressTests(unittest.TestCase):
    def test_every_frame_is_two_rows_with_no_animation_scrollback(self):
        for width in (40, 48, 80, 120):
            terminal = Terminal()
            with ScanProgress(terminal, interval=60, columns=width) as progress:
                progress.update('Analyzing 界e\u0301/' * 40)
                for _ in range(12):
                    progress.advance(1, 2)
                    progress.frame()
                progress.update('Writing report pages')
                progress.frame()
            raw = terminal.getvalue()
            frames, final = screens(raw, width)
            self.assertGreater(len(frames), 12)
            for frame in frames:
                self.assertEqual(len(frame['lines']), 2, frame)
                self.assertEqual(frame['rows'], [0, 1], frame)
                self.assertEqual(frame['history'], 0, frame)
                self.assertEqual(frame['cursor'], (0, 1), frame)
                self.assertTrue(frame['lines'][0].startswith('Analysis'), frame)
            self.assertEqual(len({frame['lines'][1][0] for frame in frames}), 4)
            self.assertFalse(final.cursor.hidden)
            self.assertFalse(any(line.strip() for line in final.display))
            save_evidence(f'scan-simulated-{width}', raw, frames)

    def test_redirected_stream_has_no_frames_or_animation_logs(self):
        terminal = io.StringIO()
        with ScanProgress(terminal) as progress:
            progress.update('Analyzing source')
            progress.advance(1000, 100)
        self.assertEqual(terminal.getvalue(), '')
        self.assertEqual(_clip('\x1b\nfile', 80), '??file')

    def test_exception_stops_heartbeat_and_restores_cursor(self):
        terminal = Terminal()
        with self.assertRaises(KeyboardInterrupt):
            with ScanProgress(terminal, interval=.01) as progress:
                raise KeyboardInterrupt
        self.assertFalse(progress.thread.is_alive())
        self.assertTrue(terminal.getvalue().endswith('\x1b[?25h'))

    def test_native_console_width_resize_and_cancellation(self):
        code = '''import time
from devsift.scan_progress import ScanProgress
try:
    with ScanProgress() as progress:
        progress.update('Analyzing source with Unicode 界e\\u0301 ' * 12)
        for _ in range(12):
            progress.advance(1, 2)
            time.sleep(.1)
    print('Done.')
except KeyboardInterrupt:
    print('Interrupted.')
    raise SystemExit(2)
'''
        for width, resize, cancel in ((40, False, False), (48, False, False),
                                      (80, True, False), (120, False, True)):
            raw, status = capture([str(Path(sys.executable).resolve()), '-P', '-B', '-c', code],
                                  cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT)), width=width,
                                  resize=resize, cancel=cancel, resize_trigger='Analyzing source',
                                  cancel_trigger='Analyzing source', timeout=30)
            self.assertEqual(status, 2 if cancel else 0, raw[-2000:])
            frames, final = screens(raw, width)
            self.assertIn('\x1b[?25l', raw)
            self.assertIn('\x1b[?25h', raw)
            self.assertFalse(final.cursor.hidden)
            self.assertEqual(len(final.history.top), 0)
            active = [line.strip() for line in final.display if line.strip()]
            self.assertEqual(active, ['Interrupted.' if cancel else 'Done.'])
            save_evidence(f'scan-native-{width}', raw, frames)


if __name__ == '__main__':
    unittest.main()
