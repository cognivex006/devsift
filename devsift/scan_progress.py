"""Two reserved stderr rows for human full scans; machine streams stay clean."""
import os
import shutil
import sys
import threading
import time
import unicodedata


def _clip(value, width):
    pieces, used = [], 0
    for char in value:
        if unicodedata.category(char) in {'Cc', 'Cf', 'Cs'}:
            char = '?'
        cells = 0 if unicodedata.category(char).startswith('M') else 2 if unicodedata.east_asian_width(char) in {'W', 'F'} else 1
        if used + cells > width:
            break
        pieces.append(char)
        used += cells
    return ''.join(pieces)


class ScanProgress:
    def __init__(self, stream=None, *, interval=.1, columns=None):
        # Retain the original stream: adapter redirect_stderr must not capture
        # the renderer thread, and no child owns these console rows.
        self.stream = sys.stderr if stream is None else stream
        self.active = bool(self.stream.isatty()) and (os.name == 'nt' or os.environ.get('TERM') != 'dumb')
        self.console_mode = None
        self.interval, self.columns = interval, columns
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread = None
        self.stage = 'Checking configured analyzers'
        self.processed = self.findings = self.tick = 0
        self.started = time.monotonic()

    def update(self, stage):
        with self.lock:
            self.stage = stage

    def advance(self, targets, findings=0):
        with self.lock:
            self.processed += targets
            self.findings += findings

    def frame(self):
        try:
            columns = os.get_terminal_size(self.stream.fileno()).columns
        except (OSError, ValueError, AttributeError):
            columns = shutil.get_terminal_size((80, 24)).columns
        width = max(1, (self.columns if self.columns is not None else columns) - 1)
        with self.lock:
            elapsed = int(time.monotonic() - self.started)
            top = f'Analysis | files {self.processed} | new cases {self.findings} | {elapsed}s'
            bottom = '|/-\\'[self.tick % 4] + ' ' + self.stage
            self.tick += 1
        self.stream.write('\r\x1b[1A\x1b[2K' + _clip(top, width) + '\r\n\x1b[2K'
                          + _clip(bottom, width) + '\r')
        self.stream.flush()

    def _heartbeat(self):
        while not self.stopping.wait(self.interval):
            try:
                self.frame()
            except (OSError, ValueError):
                return

    def __enter__(self):
        if self.active and os.name == 'nt' and self.stream is sys.stderr:
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.GetStdHandle.restype = ctypes.c_void_p
            handle = kernel.GetStdHandle(-12)
            mode = ctypes.c_ulong()
            if (kernel.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode))
                    and kernel.SetConsoleMode(ctypes.c_void_p(handle), mode.value | 4)):
                self.console_mode = kernel, handle, mode.value
            else:
                self.active = False
        if self.active:
            try:
                self.stream.write('\x1b[?25l\r\n')
                self.frame()
                self.thread = threading.Thread(target=self._heartbeat, daemon=True)
                self.thread.start()
            except (OSError, ValueError):
                self.__exit__()
                self.active = False
        return self

    def __exit__(self, *_):
        if self.active:
            self.stopping.set()
            if self.thread is not None:
                self.thread.join()
            try:
                self.stream.write('\r\x1b[2K\x1b[1A\r\x1b[2K\x1b[?25h')
                self.stream.flush()
            except (OSError, ValueError):
                pass
        if self.console_mode is not None:
            import ctypes
            kernel, handle, mode = self.console_mode
            kernel.SetConsoleMode(ctypes.c_void_p(handle), mode)
            self.console_mode = None
