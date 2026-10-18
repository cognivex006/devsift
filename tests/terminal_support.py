"""Native PTY capture and visual screen assertions (test dependencies only)."""
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import unittest

try:
    import pyte
except ImportError:
    pyte = None


def capture(argv, *, cwd, env, width=80, resize=False, cancel=False, timeout=120,
            resize_trigger='Overall setup', cancel_trigger='Installing verified wheels'):
    """Run a real ConPTY on Windows, native PTY elsewhere; retain raw terminal bytes."""
    if os.name == 'nt':
        try:
            from winpty import PtyProcess, Backend
        except ImportError:
            raise unittest.SkipTest('pywinpty test dependency required for ConPTY evidence') from None
        child = PtyProcess.spawn(argv, cwd=str(cwd), env=env,
                                 dimensions=(24, width), backend=Backend.ConPTY)
        read = lambda: child.read(8192)
        running = child.isalive
        change = lambda: child.setwinsize(24, 40)
        interrupt = lambda: child.write('\x03')
        def close():
            child.close(force=True)
            # pywinpty isalive() marks closed before close() frees its sockets.
            child.fileobj.close()
            child._server.close()
            child._thread.join(timeout=5)
        status = lambda: child.exitstatus
    else:
        import pty
        import termios
        import errno
        master, slave = pty.openpty()
        termios.tcsetwinsize(slave, (24, width))
        child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=slave, stderr=slave,
                                 start_new_session=True)
        os.close(slave)
        def read():
            try:
                return os.read(master, 8192).decode('utf-8', errors='replace')
            except OSError as error:
                if error.errno == errno.EIO:
                    return ''
                raise
        running = lambda: child.poll() is None
        change = lambda: termios.tcsetwinsize(master, (24, 40))
        def interrupt():
            import signal
            os.killpg(child.pid, signal.SIGINT)
        def close():
            if running():
                child.kill()
            child.wait()
            os.close(master)
        status = lambda: child.returncode
    messages = queue.Queue()
    def reader():
        try:
            while True:
                chunk = read()
                if not chunk:
                    break
                messages.put(chunk)
        except EOFError:
            pass
        except Exception as error:
            messages.put(error)
        finally:
            messages.put(None)
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    parts, changed, cancelled = [], False, False
    deadline = time.monotonic() + timeout
    try:
        while True:
            if time.monotonic() > deadline:
                raise AssertionError('Native terminal test exceeded deadline')
            try:
                chunk = messages.get(timeout=0.2)
            except queue.Empty:
                continue
            if chunk is None:
                break
            if isinstance(chunk, Exception):
                raise chunk
            parts.append(chunk)
            if os.name == 'nt' and '\x1b[c' in chunk:
                child.write('\x1b[?1;2c')  # ConPTY terminal capability negotiation
            if resize and not changed and resize_trigger in ''.join(parts):
                change()
                # Test-only capture metadata: never written into the child terminal.
                parts.append('\x1b]777;devsift-test-resize=40\x07')
                changed = True
            if cancel and not cancelled and cancel_trigger in ''.join(parts):
                interrupt()
                cancelled = True
        # pywinpty refreshes exitstatus on isalive().
        for _ in range(100):
            if not running():
                break
            time.sleep(.02)
        return ''.join(parts), status()
    finally:
        close()
        thread.join(timeout=5)


def screens(raw, width=80):
    """Decode every completed repaint with an independent VT emulator."""
    if pyte is None:
        raise unittest.SkipTest('pyte test dependency required for visual assertions')
    screen = pyte.HistoryScreen(width, 24, history=1000)
    stream = pyte.Stream(screen)
    # Each renderer frame ends on the second row at column one.
    pattern = re.compile(r'\r\x1b\[1A\x1b\[2K[^\r]*\r+\n\x1b\[2K[^\r]*\r')
    offset, frames = 0, []
    def feed(text):
        position = 0
        for marker in re.finditer(r'\x1b\]777;devsift-test-resize=(\d+)\x07', text):
            stream.feed(text[position:marker.start()])
            screen.resize(columns=int(marker[1]))
            position = marker.end()
        stream.feed(text[position:])
    for match in pattern.finditer(raw):
        feed(raw[offset:match.end()])
        offset = match.end()
        lines = [line.rstrip() for line in screen.display]
        active = [(i, line) for i, line in enumerate(lines) if line.strip()]
        # ConPTY may optimize equivalent cursor/erase commands; native evidence
        # also gets full-stream snapshots in the bootstrap test.
        if active:
            frames.append({'lines': [line for _, line in active], 'rows': [i for i, _ in active],
                           'cursor': (screen.cursor.x, screen.cursor.y),
                           'columns': screen.columns,
                           'history': len(screen.history.top)})
    feed(raw[offset:])
    return frames, screen


def assert_two_rows(test, raw, width=80):
    frames, screen = screens(raw, width)
    test.assertGreater(len(frames), 2, repr(raw[-2000:]))
    for frame in frames:
        test.assertEqual(len(frame['lines']), 2, frame)
        test.assertEqual(frame['rows'], [0, 1], frame)
        test.assertEqual(frame['cursor'], (0, 1), frame)
        test.assertEqual(frame['history'], 0, frame)
        test.assertTrue(frame['lines'][0].startswith(('Overall setup', 'Downloading')), frame)
        test.assertRegex(frame['lines'][1], r'^[|/\\-] devsift ')
    test.assertIn('\x1b[?25l', raw)
    test.assertIn('\x1b[?25h', raw)
    test.assertFalse(screen.cursor.hidden)
    return frames


def save_evidence(name, raw, frames):
    folder = os.environ.get('DEVSIFT_TEST_TERMINAL_ARTIFACTS')
    if folder:
        import json
        root = Path(folder)
        root.mkdir(parents=True, exist_ok=True)
        (root / (name + '.ansi')).write_text(raw, encoding='utf-8')
        (root / (name + '.frames.json')).write_text(json.dumps(frames, ensure_ascii=False, indent=2), encoding='utf-8')
