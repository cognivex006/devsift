"""Complete native runs may wait for completion without losing cancellation."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from devsift import process_runner as runner
from devsift.process_runner import ProcessSpec, run_process


class CompleteExecutionTests(unittest.TestCase):
    def spec(self, code, timeout):
        return ProcessSpec(str(Path(sys.executable).resolve()), ('-I', '-B', '-c', code),
                           timeout_seconds=timeout)

    def test_explicit_completion_mode_does_not_use_a_finite_wall_deadline(self):
        process = run_process(self.spec('import time; time.sleep(.15); print("done")', None))
        self.assertEqual(process.status, 'completed')
        self.assertEqual(process.exit_code, 0)
        self.assertEqual(process.stdout.strip(), 'done')
        timed = run_process(self.spec('import time; time.sleep(5)', .05))
        self.assertEqual(timed.status, 'timeout')
        self.assertEqual(timed.reason, 'TIMEOUT')

    def test_cancellation_without_deadline_reaps_owned_child_and_closes_pipes(self):
        children = []
        actual = subprocess.Popen
        actual_sleep = runner.time.sleep
        interrupted = False

        def launch(*args, **kwargs):
            child = actual(*args, **kwargs)
            children.append(child)
            return child

        def interrupt_once(seconds):
            # subprocess.wait(timeout) also uses time.sleep on POSIX. Inject one
            # actual user cancellation, then allow owned-child cleanup to run.
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            actual_sleep(seconds)

        with patch.object(runner.subprocess, 'Popen', side_effect=launch), \
                patch.object(runner.time, 'sleep', side_effect=interrupt_once):
            with self.assertRaises(KeyboardInterrupt):
                run_process(self.spec('import time; time.sleep(30)', None))
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(all(stream.closed for stream in
                            (children[0].stdin, children[0].stdout, children[0].stderr)))


if __name__ == '__main__':
    unittest.main()
