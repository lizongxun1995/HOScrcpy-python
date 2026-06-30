"""AsyncTouchController — non-blocking touch injection.

Wraps TouchController with a command queue processed in a background thread.
Mouse event handlers return immediately without waiting for hdc subprocess.
"""

import queue
import threading
from hos_scrcpy.input.touch import TouchController
from hos_scrcpy.interfaces import TouchProvider
from hos_scrcpy.utils.logger import logger

TAG = "AsyncTouch"


class AsyncTouchController(TouchProvider):
    """Non-blocking touch controller for GUI use.

    Queues touch commands and executes them in a background thread
    so the tkinter main thread never blocks on hdc subprocess calls.
    """

    def __init__(self, touch: TouchController):
        self._touch = touch
        self._queue = queue.Queue()
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        while self._running:
            try:
                cmd, args = self._queue.get(timeout=0.5)
                try:
                    cmd(*args)
                except Exception as ex:
                    logger.debug(f"{TAG}: cmd error: {ex}")
            except queue.Empty:
                continue

    def _enqueue(self, cmd, *args):
        if self._running:
            self._queue.put((cmd, args))

    def down(self, x, y, contact=0):
        self._enqueue(self._touch.down, x, y, contact)

    def up(self, x, y, contact=0):
        self._enqueue(self._touch.up, x, y, contact)

    def move(self, x, y):
        self._enqueue(self._touch.move, x, y)

    def click(self, x, y, duration=0.05):
        self._enqueue(self._touch.click, x, y, duration)

    def swipe(self, x1, y1, x2, y2, duration=0.3, steps=10):
        self._enqueue(self._touch.swipe, x1, y1, x2, y2, duration, steps)

    def stop(self):
        """Stop the worker and send up for any pending down."""
        self._running = False
        # Drain remaining commands in queue
        try:
            while True:
                cmd, args = self._queue.get_nowait()
                try:
                    cmd(*args)
                except Exception:
                    pass
        except queue.Empty:
            pass
        # Wait for worker to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
