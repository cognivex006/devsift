"""Two reserved terminal rows; JSON transport has no terminal side effects.

This stdlib-only module is embedded verbatim in generated POSIX bootstraps.
"""
from contextlib import contextmanager
import json
import os
import shutil
import sys
import threading
import time
import unicodedata


def cells(text, limit):
    """Conservative display-cell clipping; never emit untrusted terminal controls."""
    result, used = [], 0
    for char in str(text):
        category = unicodedata.category(char)
        if category.startswith('C') or char in '\r\n\t':
            char, width = ' ', 1
        else:
            width = 0 if category.startswith('M') else 2 if unicodedata.east_asian_width(char) in 'WF' else 1
        if used + width > limit:
            break
        result.append(char)
        used += width
    return ''.join(result)


class Progress:
    def __init__(self, mode='console', *, stream=None, operation='install'):
        self.mode = mode
        self.stream = stream if stream is not None else sys.stderr
        self.interactive = mode == 'console' and self.stream.isatty() and (os.name == 'nt' or os.environ.get('TERM') != 'dumb')
        self.operation = operation
        self.percent, self.stage = 0, 'Checking installation'
        self.received, self.total = None, None
        self.started = time.monotonic()
        self.tick, self.stage_events = 0, 0
        self.last_stage = None
        self.active = self.closed = self.paused = False
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.worker = None
        self.console_mode = None

    def __enter__(self):
        if self.interactive and os.name == 'nt' and self.stream is sys.stderr:
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.GetStdHandle.restype = ctypes.c_void_p
            handle = kernel.GetStdHandle(-12)
            mode = ctypes.c_ulong()
            if kernel.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode)) and kernel.SetConsoleMode(ctypes.c_void_p(handle), mode.value | 4):
                self.console_mode = kernel, handle, mode.value
            else:
                self.interactive = False
        if self.mode == 'json' or self.interactive:
            self.worker = threading.Thread(target=self._heartbeat, daemon=True)
            self.worker.start()
        return self

    def _heartbeat(self):
        while not self.stop.wait(0.2):
            with self.lock:
                if not self.paused and not self.closed:
                    self._draw()

    def _emit(self, value):
        print(json.dumps(value, ensure_ascii=True), flush=True)

    def _draw(self):
        if self.closed or self.paused:
            return
        elapsed = round(time.monotonic() - self.started, 1)
        if self.mode == 'json':
            event = {'type': 'progress', 'percent': self.percent, 'stage': self.stage, 'elapsed': elapsed}
            if self.received is not None:
                event.update(kind='transfer', received=self.received, total=self.total)
            self._emit(event)
        elif self.interactive:
            try:
                columns = os.get_terminal_size(self.stream.fileno()).columns
            except (OSError, ValueError, AttributeError):
                columns = shutil.get_terminal_size(fallback=(80, 24)).columns
            limit = max(1, columns - 1)
            percent = self.percent if self.received is None else (
                min(100, self.received * 100 // self.total) if self.total else None)
            label = 'Overall setup' if self.received is None else 'Downloading'
            suffix = f' {percent}%' if percent is not None else ' size unknown'
            bar_width = min(32, max(1, limit - len(label) - len(suffix) - 3))
            filled = percent * bar_width // 100 if percent is not None else self.tick % bar_width
            bar = '#' * filled + '-' * (bar_width - filled) if percent is not None else (
                '-' * filled + '#' + '-' * (bar_width - filled - 1))
            top = f'{label} [{bar}]{suffix}'
            detail = '' if self.received is None else (
                f'{self.received}/{self.total}B ' if self.total else f'{self.received}B received ')
            spinner = '|/-' + chr(92)
            bottom = f'{spinner[self.tick % 4]} devsift {self.operation}: {detail}{self.stage} ({elapsed:.1f}s)'
            self.tick += 1
            if not self.active:
                self.stream.write('\x1b[?25l\r\n')
                self.active = True
            # Cursor always rests on the second reserved row, at column one.
            self.stream.write('\r\x1b[1A\x1b[2K' + cells(top, limit) + '\r\n\x1b[2K' + cells(bottom, limit) + '\r')
            self.stream.flush()
        elif self.mode == 'console' and self.stage != self.last_stage and self.stage_events < 24:
            print(f'DevSift {self.operation}: {cells(self.stage, 160)}', file=self.stream, flush=True)
            self.last_stage = self.stage
            self.stage_events += 1

    def update(self, percent, stage):
        with self.lock:
            if stage != self.stage:
                self.started = time.monotonic()
            self.percent, self.stage = max(0, min(100, int(percent))), str(stage)
            self.received, self.total = None, None
            self._draw()

    def transfer(self, received, total, stage):
        with self.lock:
            self.stage, self.received, self.total = stage, max(0, received), total if total and total > 0 else None
            self._draw()

    def _clear(self):
        if self.active:
            self.stream.write('\r\x1b[2K\x1b[1A\r\x1b[2K\x1b[?25h')
            self.stream.flush()
            self.active = False

    @contextmanager
    def suspend(self):
        """Pause before a caller prompts; no prompt shares the live region."""
        with self.lock:
            self.paused = True
            self._clear()
        try:
            yield
        finally:
            with self.lock:
                self.paused = False
                self._draw()

    def close(self):
        self.stop.set()
        if self.worker is not None:
            self.worker.join()  # no draw may race the durable summary
        with self.lock:
            self._clear()
            self.closed = True
            if self.console_mode:
                import ctypes
                kernel, handle, mode = self.console_mode
                kernel.SetConsoleMode(ctypes.c_void_p(handle), mode)
                self.console_mode = None

    def finish(self, *, state=None, message=None):
        self.update(100, 'Ready')
        self.close()
        if self.mode == 'json':
            self._emit({'type': 'complete', 'state': state or {}})
        elif self.mode == 'console':
            if state:
                print(f'DevSift {state["version"]} ready.\nCLI: {state["launcher"]}\n'
                      f'Skills: {", ".join(state["hosts"])}\nNext: restart your terminal and agent, then run devsift --help.')
            elif message:
                print(message)

    def fail(self, error):
        self.close()
        if self.mode == 'json':
            self._emit({'type': 'error', 'stage': self.stage, 'message': str(error)})
        elif self.mode != 'none':
            print(f'Setup failed while {cells(self.stage, 160)}: {cells(error, 400)}', file=self.stream)

    def __exit__(self, *args):
        self.close()
