"""Live progress replaces a line; automation receives structured events only."""
from contextlib import redirect_stdout
import io
import json
import unittest

from tools.install_progress import Progress


class Terminal(io.StringIO):
    def isatty(self):
        return True


class ProgressTests(unittest.TestCase):
    def test_console_reuses_one_line_and_emits_only_final_summary(self):
        display, output = Terminal(), io.StringIO()
        with redirect_stdout(output), Progress(stream=display) as progress:
            progress.update(8, 'Downloading | 0% (0 / 100 bytes)')
            progress.update(24, 'Downloading | 50% (50 / 100 bytes)')
            progress.update(40, 'Download complete')
            progress.finish(message='Setup ready.')
        self.assertEqual(display.getvalue().count('\n'), 1)
        self.assertGreaterEqual(display.getvalue().count('\r'), 4)
        self.assertIn(' 24%', display.getvalue())
        self.assertEqual(output.getvalue(), 'Setup ready.\n')

    def test_json_protocol_preserves_stages_and_does_not_print_pip_logs(self):
        output = io.StringIO()
        with redirect_stdout(output), Progress('json') as progress:
            progress.update(10, 'Creating environment')
            progress.update(65, 'Checking CLI startup')
            progress.finish(state={'version': '0.1.12'})
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1], {'type': 'complete', 'state': {'version': '0.1.12'}})
        percentages = [e['percent'] for e in events if e['type'] == 'progress']
        self.assertEqual(percentages, sorted(percentages))
        self.assertTrue({10, 65, 100}.issubset(percentages))
        self.assertTrue(set(percentages).issubset({0, 10, 65, 100}))

    def test_redirected_console_is_quiet_until_completion(self):
        display, output = io.StringIO(), io.StringIO()
        with redirect_stdout(output), Progress(stream=display) as progress:
            progress.update(10, 'Creating environment')
            progress.update(50, 'Installing CLI')
            self.assertEqual(output.getvalue(), '')
            self.assertEqual(display.getvalue(), '')
            progress.finish(message='Ready.')
        self.assertEqual(output.getvalue(), 'Ready.\n')

    def test_failed_work_never_emits_ready_or_100_percent(self):
        output = io.StringIO()
        with redirect_stdout(output), Progress('json') as progress:
            progress.update(45, 'Verifying checksum')
            progress.fail(RuntimeError('Checksum mismatch'))
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1]['type'], 'error')
        self.assertEqual(events[-1]['stage'], 'Verifying checksum')
        self.assertFalse(any(e.get('percent') == 100 or e['type'] == 'complete' for e in events))


if __name__ == '__main__':
    unittest.main()
