"""Actual child-process behavior; native analyzer semantics are separate."""
from pathlib import Path
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import subprocess

import devsift.process_runner as runner
from devsift.process_runner import ProcessSpec, run_process
from devsift.redaction import Redactor


class ProcessRunnerTests(unittest.TestCase):
    def spec(self, code, *args, **limits):
        return ProcessSpec(str(Path(sys.executable).resolve()), ('-I', '-B', '-c', code, *args), **limits)

    def test_real_execution_uses_literal_argv_and_owned_temporary_workdir(self):
        injection = 'value; echo injected & $(echo unsafe) | "quoted"'
        code = 'import sys,pathlib; print(sys.argv[1]); print(pathlib.Path.cwd().name)'
        result = run_process(self.spec(code, injection))
        self.assertEqual(result.status, 'completed')
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout.splitlines()[0], injection)
        self.assertTrue(result.stdout.splitlines()[1].startswith('devsift-process-'))
        self.assertEqual(result.stderr, '')

    def test_strict_argv_limits_and_safe_representations(self):
        private = 'private-fixture-argument'
        with self.assertRaisesRegex(ValueError, 'Invalid process specification') as error:
            ProcessSpec(str(Path(sys.executable).resolve()), private)
        self.assertNotIn(private, str(error.exception))
        for kwargs in ({'timeout_seconds': 0}, {'timeout_seconds': True},
                       {'max_stdout_bytes': 0}, {'max_stderr_bytes': '2'},
                       {'environment': {'X': private}}):
            with self.assertRaises(ValueError):
                self.spec('pass', **kwargs)
        spec = self.spec('print(1)', private)
        self.assertNotIn(private, repr(spec))
        with self.assertRaises(ValueError):
            ProcessSpec('python', ())
        for extension in ('.bat', '.cmd', '.ps1'):
            with self.assertRaises(ValueError):
                ProcessSpec(str(Path(tempfile.gettempdir()) / ('program' + extension)), ())

    def test_missing_executable_and_nonzero_exit_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = run_process(ProcessSpec(str(Path(directory) / 'nonexistent-program'), ()))
        self.assertEqual(missing.status, 'unavailable')
        self.assertIsNone(missing.exit_code)
        failed = run_process(self.spec('import sys; print("failure",file=sys.stderr); sys.exit(7)'))
        self.assertEqual(failed.status, 'failed')
        self.assertEqual(failed.exit_code, 7)
        self.assertEqual(failed.stderr.strip(), 'failure')

    @unittest.skipUnless(os.name == 'nt', 'Windows suspended assignment failure')
    def test_failed_job_assignment_terminates_owned_suspended_child(self):
        children = []
        actual_popen = subprocess.Popen
        def record_child(*args, **kwargs):
            child = actual_popen(*args, **kwargs)
            children.append(child)
            return child
        try:
            with patch.object(runner.subprocess, 'Popen', side_effect=record_child), \
                 patch.object(runner._WindowsJob, 'attach_and_resume', side_effect=OSError('private-fixture')):
                result = run_process(self.spec('import time; time.sleep(30)', timeout_seconds=0.2))
            self.assertEqual(result.status, 'failed')
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].poll())
            self.assertIsNotNone(result.exit_code)
            for stream in (children[0].stdin, children[0].stdout, children[0].stderr):
                self.assertTrue(stream.closed)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=2)

    @unittest.skipUnless(os.name == 'nt', 'Windows job termination failure')
    def test_failed_job_termination_still_reaps_owned_child(self):
        children = []
        actual_popen = subprocess.Popen
        def record_child(*args, **kwargs):
            child = actual_popen(*args, **kwargs)
            children.append(child)
            return child
        try:
            with patch.object(runner.subprocess, 'Popen', side_effect=record_child), \
                 patch.object(runner._WindowsJob, 'terminate', side_effect=OSError('private-fixture')):
                result = run_process(self.spec('import time; time.sleep(30)', timeout_seconds=0.2))
            self.assertEqual(result.status, 'failed')
            self.assertEqual(result.reason, 'TERMINATION_FAILED')
            self.assertIsNotNone(children[0].poll())
            self.assertEqual((result.stdout, result.stderr), ('', ''))
            self.assertNotIn('private-fixture', repr(result))
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=2)

    def test_stdin_and_simultaneous_streams_do_not_deadlock(self):
        code = ('import sys,threading; '
                't=threading.Thread(target=lambda:sys.stderr.buffer.write(b"e"*65536)); '
                't.start(); data=sys.stdin.buffer.read(); '
                'sys.stdout.buffer.write(data); t.join()')
        result = run_process(self.spec(code), stdin=b'x' * 65536)
        self.assertEqual(result.status, 'completed')
        self.assertEqual(len(result.stdout), 65536)
        self.assertEqual(len(result.stderr), 65536)
        with self.assertRaises(ValueError):
            run_process(self.spec('pass', max_stdin_bytes=2), stdin=b'private')

    def test_flooding_both_streams_is_bounded_and_discarded(self):
        code = ('import os,threading; '
                't=threading.Thread(target=lambda:[os.write(2,b"e"*8192) for _ in range(10000)]); '
                't.start(); [os.write(1,b"o"*8192) for _ in range(10000)]; t.join()')
        start = time.monotonic()
        result = run_process(self.spec(code, max_stdout_bytes=4096, max_stderr_bytes=4096))
        self.assertEqual(result.status, 'output_limit')
        self.assertLess(time.monotonic() - start, 8)
        self.assertEqual((result.stdout, result.stderr), ('', ''))

    def test_stderr_limit_and_blocked_stdin_are_independently_bounded(self):
        flooded = run_process(self.spec('import os; os.write(2,b"x"*65536)', max_stderr_bytes=16))
        self.assertEqual(flooded.status, 'output_limit')
        self.assertEqual(flooded.stderr, '')
        start = time.monotonic()
        blocked = run_process(self.spec('import time; time.sleep(30)', timeout_seconds=0.2),
                              stdin=b'x' * 1_000_000)
        self.assertEqual(blocked.status, 'timeout')
        self.assertLess(time.monotonic() - start, 5)

    def test_timeout_terminates_parent_and_descendant(self):
        # A surviving descendant would write outside the owned temp cwd later.
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'descendant-survived'
            child = 'import time,pathlib; time.sleep(1.2); pathlib.Path(' + repr(str(marker)) + ').write_text("alive")'
            code = ('import subprocess,sys,time; '
                    'subprocess.Popen([sys.executable,"-I","-B","-c",sys.argv[1]]); time.sleep(30)')
            result = run_process(self.spec(code, child, timeout_seconds=0.5))
            self.assertEqual(result.status, 'timeout')
            time.sleep(1.4)
            self.assertFalse(marker.exists())

    def test_parent_exit_does_not_leave_descendant_holding_pipes(self):
        child = 'import time; time.sleep(30)'
        code = 'import subprocess,sys; subprocess.Popen([sys.executable,"-I","-B","-c",sys.argv[1]])'
        start = time.monotonic()
        result = run_process(self.spec(code, child, timeout_seconds=0.7))
        self.assertLess(time.monotonic() - start, 5)
        self.assertIn(result.status, ('completed', 'timeout'))

    def test_output_is_redacted_and_not_in_result_repr(self):
        private = 'private-fixture-secret'
        code = 'import sys; print("token = " + sys.argv[1]); print(sys.argv[1],file=sys.stderr)'
        result = run_process(self.spec(code, private), redactor=Redactor((private,)))
        self.assertEqual(result.status, 'completed')
        self.assertNotIn(private, result.stdout + result.stderr + repr(result))
        self.assertIn('[REDACTED]', result.stdout)
        self.assertIn('[REDACTED]', result.stderr)

    def test_environment_is_stable_and_not_ambient_project_hooks(self):
        code = 'import os,json; print(json.dumps({k:os.environ.get(k) for k in ["LC_ALL","TZ","PYTHONPATH","DEVSIFT_PRIVATE","EXPLICIT","NODE_OPTIONS","DOTNET_STARTUP_HOOKS","GOFLAGS","LD_PRELOAD"]},sort_keys=True))'
        hooks = {key: 'private-env' for key in ('PYTHONPATH', 'DEVSIFT_PRIVATE', 'NODE_OPTIONS',
                                              'DOTNET_STARTUP_HOOKS', 'GOFLAGS', 'LD_PRELOAD')}
        with patch.dict(os.environ, hooks):
            result = run_process(self.spec(code, environment=(('EXPLICIT', 'fixed'),)))
        self.assertEqual(result.status, 'completed')
        self.assertIn('"LC_ALL": "C"', result.stdout)
        self.assertIn('"TZ": "UTC"', result.stdout)
        self.assertIn('"PYTHONPATH": null', result.stdout)
        self.assertIn('"DEVSIFT_PRIVATE": null', result.stdout)
        self.assertIn('"EXPLICIT": "fixed"', result.stdout)
        for key in ('NODE_OPTIONS', 'DOTNET_STARTUP_HOOKS', 'GOFLAGS', 'LD_PRELOAD'):
            self.assertIn('"' + key + '": null', result.stdout)


if __name__ == '__main__':
    unittest.main()
