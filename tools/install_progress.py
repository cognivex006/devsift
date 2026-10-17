"""Single-line setup UI and a private progress protocol for shell bootstraps."""
import json
import sys
import threading
import time


class Progress:
    def __init__(self, mode='console', *, stream=None):
        self.mode = mode
        self.stream = stream if stream is not None else sys.stderr
        self.interactive = mode == 'console' and self.stream.isatty()
        self.percent = 0
        self.stage = 'Checking installation'
        self.started = time.monotonic()
        self.width = 0
        self.tick = 0
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.worker = None

    def __enter__(self):
        if self.mode == 'json' or self.interactive:
            self.worker = threading.Thread(target=self._heartbeat, daemon=True)
            self.worker.start()
        return self

    def _heartbeat(self):
        while not self.stop.wait(0.25):
            with self.lock:
                self._draw()

    def _emit(self, value):
        print(json.dumps(value, ensure_ascii=True), flush=True)

    def _draw(self):
        elapsed = round(time.monotonic() - self.started, 1)
        if self.mode == 'json':
            self._emit({'type': 'progress', 'percent': self.percent, 'stage': self.stage, 'elapsed': elapsed})
        elif self.interactive:
            self.tick += 1
            spinner = '|/-\\'[self.tick % 4]
            filled = self.percent * 24 // 100
            line = f'{spinner} [{"#" * filled}{"." * (24 - filled)}] {self.percent:3d}% setup | {self.stage} ({elapsed:.1f}s)'
            self.stream.write('\r' + line.ljust(self.width))
            self.stream.flush()
            self.width = len(line)

    def update(self, percent, stage):
        with self.lock:
            percent = max(0, min(100, int(percent)))
            if stage != self.stage:
                self.started = time.monotonic()
            self.percent, self.stage = percent, stage
            self._draw()

    def close(self):
        self.stop.set()
        if self.worker is not None:
            self.worker.join(timeout=2)

    def finish(self, *, state=None, message=None):
        self.close()
        self.update(100, 'Ready')
        if self.mode == 'json':
            self._emit({'type': 'complete', 'state': state or {}})
        elif self.mode == 'console':
            if self.interactive:
                self.stream.write('\n')
            if state:
                print(f'DevSift {state["version"]} ready.\nCLI: {state["launcher"]}\n'
                      f'Skills: {", ".join(state["hosts"])}\nNext: restart your terminal and agent, then run devsift --help.')
            elif message:
                print(message)

    def fail(self, error):
        self.close()
        if self.mode == 'json':
            self._emit({'type': 'error', 'stage': self.stage, 'message': str(error)})
        else:
            if self.interactive:
                self.stream.write('\n')
            print(f'Setup failed while {self.stage}: {error}', file=self.stream)

    def __exit__(self, *args):
        self.close()
