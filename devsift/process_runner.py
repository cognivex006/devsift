"""Bounded native execution for explicitly trusted programs, never a sandbox."""
from dataclasses import dataclass, field
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time

from .redaction import Redactor


@dataclass(frozen=True)
class ProcessSpec:
    executable: str = field(repr=False)
    argv: tuple[str, ...] = field(default=(), repr=False)
    timeout_seconds: float | None = 10
    max_stdout_bytes: int = 1_048_576
    max_stderr_bytes: int = 1_048_576
    max_stdin_bytes: int = 1_048_576
    environment: tuple[tuple[str, str], ...] = field(default=(), repr=False)

    def __post_init__(self):
        valid = (type(self.executable) is str and bool(self.executable)
                 and '\0' not in self.executable and Path(self.executable).is_absolute()
                 and Path(self.executable).suffix.lower() not in {'.bat', '.cmd', '.ps1'}
                 and type(self.argv) is tuple
                 and all(type(arg) is str and '\0' not in arg for arg in self.argv)
                 and len(self.argv) <= 4096
                 and sum(len(arg) for arg in self.argv) <= 1_048_576
                 and (self.timeout_seconds is None or (
                     type(self.timeout_seconds) in (int, float)
                     and math.isfinite(self.timeout_seconds) and 0 < self.timeout_seconds <= 3600))
                 and all(type(value) is int and 0 < value <= 2_000_000 for value in (
                     self.max_stdout_bytes, self.max_stderr_bytes, self.max_stdin_bytes))
                 and type(self.environment) is tuple and len(self.environment) <= 256)
        if valid:
            valid = all(type(pair) is tuple and len(pair) == 2
                        and all(type(value) is str and '\0' not in value for value in pair)
                        and pair[0] and '=' not in pair[0]
                        and sum(len(value) for value in pair) <= 8192 for pair in self.environment)
        if valid:
            keys = [pair[0].upper() if os.name == 'nt' else pair[0] for pair in self.environment]
            valid = len(set(keys)) == len(keys)
        if not valid:
            raise ValueError('Invalid process specification') from None
        # Fixed caller-configured identity; do not discover commands through PATH.
        try:
            resolved = Path(self.executable).resolve()
            if resolved.suffix.lower() in {'.bat', '.cmd', '.ps1'}:
                raise ValueError('Invalid process specification')
            object.__setattr__(self, 'executable', str(resolved))
        except (OSError, ValueError, RuntimeError):
            raise ValueError('Invalid process specification') from None


@dataclass(frozen=True)
class ProcessResult:
    status: str
    exit_code: int | None
    stdout: str = field(default='', repr=False)
    stderr: str = field(default='', repr=False)
    reason: str = ''


class _WindowsJob:
    """Assign a suspended child before resuming its primary thread."""

    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        self.c = c
        self.kernel = k = c.WinDLL('kernel32', use_last_error=True)
        class Basic(c.Structure):
            _fields_ = [('ProcessTime', c.c_longlong), ('JobTime', c.c_longlong),
                        ('Flags', w.DWORD), ('MinWorking', c.c_size_t), ('MaxWorking', c.c_size_t),
                        ('Active', w.DWORD), ('Affinity', c.c_size_t),
                        ('Priority', w.DWORD), ('Scheduling', w.DWORD)]
        class Extended(c.Structure):
            _fields_ = [('Basic', Basic), ('IO', c.c_ulonglong * 6),
                        ('ProcessMemory', c.c_size_t), ('JobMemory', c.c_size_t),
                        ('PeakProcess', c.c_size_t), ('PeakJob', c.c_size_t)]
        class ThreadEntry(c.Structure):
            _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('threadID', w.DWORD),
                        ('ownerPID', w.DWORD), ('basePriority', w.LONG),
                        ('deltaPriority', w.LONG), ('flags', w.DWORD)]
        self.ThreadEntry = ThreadEntry
        definitions = {
            'CreateJobObjectW': ([c.c_void_p, w.LPCWSTR], w.HANDLE),
            'SetInformationJobObject': ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            'AssignProcessToJobObject': ([w.HANDLE, w.HANDLE], w.BOOL),
            'TerminateJobObject': ([w.HANDLE, w.UINT], w.BOOL),
            'CloseHandle': ([w.HANDLE], w.BOOL),
            'CreateToolhelp32Snapshot': ([w.DWORD, w.DWORD], w.HANDLE),
            'Thread32First': ([w.HANDLE, c.POINTER(ThreadEntry)], w.BOOL),
            'Thread32Next': ([w.HANDLE, c.POINTER(ThreadEntry)], w.BOOL),
            'OpenThread': ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            'ResumeThread': ([w.HANDLE], w.DWORD),
        }
        for name, (args, returns) in definitions.items():
            function = getattr(k, name)
            function.argtypes, function.restype = args, returns
        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError('Process containment unavailable')
        limits = Extended()
        limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits)):
            self.close()
            raise OSError('Process containment unavailable')

    def attach_and_resume(self, process):
        c, k = self.c, self.kernel
        if not k.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise OSError('Process containment unavailable')
        snapshot = k.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD
        if snapshot == c.c_void_p(-1).value:
            raise OSError('Process containment unavailable')
        resumed = False
        try:
            entry = self.ThreadEntry()
            entry.dwSize = c.sizeof(entry)
            more = k.Thread32First(snapshot, c.byref(entry))
            while more:
                if entry.ownerPID == process.pid:
                    thread = k.OpenThread(0x0002, False, entry.threadID)
                    if thread:
                        try:
                            resumed = k.ResumeThread(thread) != 0xFFFFFFFF or resumed
                        finally:
                            k.CloseHandle(thread)
                more = k.Thread32Next(snapshot, c.byref(entry))
        finally:
            k.CloseHandle(snapshot)
        if not resumed:
            raise OSError('Process containment unavailable')

    def terminate(self):
        if self.handle and not self.kernel.TerminateJobObject(self.handle, 1):
            raise OSError('Process termination failed')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _environment(spec, directory):
    environment = {'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC',
                   'HOME': directory, 'USERPROFILE': directory,
                   'TMP': directory, 'TEMP': directory, 'TMPDIR': directory,
                   'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1', 'PYTHONSAFEPATH': '1'}
    if os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if not ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer)):
            raise OSError('Stable environment unavailable')
        environment.update(SystemRoot=buffer.value, WINDIR=buffer.value,
                           PATH=str(Path(buffer.value) / 'System32'))
    else:
        environment['PATH'] = '/usr/bin:/bin'
    # Explicit trusted caller configuration only; never inherit source env hooks.
    for key, value in spec.environment:
        if os.name == 'nt':
            for existing in tuple(environment):
                if existing.upper() == key.upper():
                    del environment[existing]
        environment[key] = value
    return environment


def run_process(spec: ProcessSpec, *, stdin: bytes = b'', redactor: Redactor | None = None) -> ProcessResult:
    if (type(spec) is not ProcessSpec or type(stdin) is not bytes
            or len(stdin) > spec.max_stdin_bytes
            or (redactor is not None and type(redactor) is not Redactor)):
        raise ValueError('Invalid process input') from None
    redactor = redactor or Redactor()
    try:
        available = Path(spec.executable).is_file()
    except OSError:
        available = False
    if not available:
        return ProcessResult('unavailable', None, reason='EXECUTABLE_UNAVAILABLE')
    buffers = [bytearray(), bytearray()]
    overflow, io_failure = threading.Event(), threading.Event()
    process, job, threads = None, None, []
    status, reason = 'failed', 'EXECUTION_FAILED'
    exit_code = None

    def drain(stream, index, limit):
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    return
                remaining = limit - len(buffers[index])
                if len(chunk) > remaining:
                    overflow.set()
                    return
                buffers[index].extend(chunk)
        except Exception:
            io_failure.set()

    def feed():
        try:
            for offset in range(0, len(stdin), 8192):
                view = memoryview(stdin)[offset:offset + 8192]
                while view:
                    written = process.stdin.write(view)
                    if not written:
                        raise OSError('Input unavailable')
                    view = view[written:]
        except BrokenPipeError:
            pass  # A native program may intentionally ignore stdin.
        except Exception:
            io_failure.set()
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    def terminate_tree():
        if job is not None:
            job.terminate()
        elif process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    try:
        with tempfile.TemporaryDirectory(prefix='devsift-process-', ignore_cleanup_errors=True) as directory:
            try:
                if os.name == 'nt':
                    job = _WindowsJob()
                deadline = None if spec.timeout_seconds is None else time.monotonic() + spec.timeout_seconds
                process = subprocess.Popen([spec.executable, *spec.argv], shell=False,
                                           cwd=directory, env=_environment(spec, directory),
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, bufsize=0,
                                           start_new_session=os.name != 'nt',
                                           creationflags=(0x4 | 0x08000000) if os.name == 'nt' else 0)
                if job is not None:
                    job.attach_and_resume(process)
                threads = [threading.Thread(target=drain, args=(process.stdout, 0, spec.max_stdout_bytes), daemon=True),
                           threading.Thread(target=drain, args=(process.stderr, 1, spec.max_stderr_bytes), daemon=True),
                           threading.Thread(target=feed, daemon=True)]
                for thread in threads:
                    thread.start()
                while True:
                    exit_code = process.poll()
                    if overflow.is_set():
                        status, reason = 'output_limit', 'OUTPUT_LIMIT'
                        break
                    if io_failure.is_set():
                        status, reason = 'failed', 'PIPE_FAILED'
                        break
                    if exit_code is not None and all(not thread.is_alive() for thread in threads):
                        status, reason = ('completed', 'COMPLETED') if exit_code == 0 else ('failed', 'NONZERO_EXIT')
                        break
                    if deadline is not None and time.monotonic() >= deadline:
                        status, reason = 'timeout', 'TIMEOUT'
                        break
                    time.sleep(0.005)
            except FileNotFoundError:
                status, reason = 'unavailable', 'EXECUTABLE_UNAVAILABLE'
            except Exception:
                status, reason = 'failed', 'EXECUTION_FAILED'
            finally:
                if process is not None:
                    try:
                        terminate_tree()
                    except OSError:
                        status, reason = 'failed', 'TERMINATION_FAILED'
                    if job is not None:
                        job.close()
                    # A failed assignment can leave a suspended process outside
                    # an otherwise successfully terminated *empty* Windows job.
                    # Always clean up the exact Popen child as well as its tree.
                    if process.poll() is None:
                        try:
                            process.kill()
                        except OSError:
                            status, reason = 'failed', 'TERMINATION_FAILED'
                    try:
                        process.wait(timeout=2)
                        exit_code = process.returncode
                    except (OSError, subprocess.TimeoutExpired):
                        status, reason = 'failed', 'TERMINATION_FAILED'
                        # A failed wait is not evidence of termination. Retry
                        # direct owned-child termination and a bounded reap.
                        try:
                            process.kill()
                            process.wait(timeout=2)
                            exit_code = process.returncode
                        except (OSError, subprocess.TimeoutExpired):
                            pass
                    for thread in threads:
                        if thread.ident is not None:
                            thread.join(timeout=1)
                    if any(thread.is_alive() for thread in threads):
                        status, reason = 'failed', 'PIPE_FAILED'
                    for stream in (process.stdin, process.stdout, process.stderr):
                        stream.close()
                elif job is not None:
                    job.close()
    except Exception:
        status, reason = 'failed', 'EXECUTION_FAILED'
    if reason not in {'COMPLETED', 'NONZERO_EXIT'}:
        return ProcessResult(status, exit_code, reason=reason)
    try:
        stdout, stderr = (redactor.text(bytes(buffer).decode('utf-8', errors='replace')) for buffer in buffers)
        return ProcessResult(status, exit_code, stdout, stderr, reason)
    except ValueError:
        return ProcessResult('failed', exit_code, reason='REDACTION_FAILED')
