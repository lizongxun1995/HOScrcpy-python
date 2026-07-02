"""FastTouchController — protocol-level touch via Java StreamBridge stdin.

Down/up: sent immediately. Move: throttled to max 20/sec, skip tiny deltas.
"""

import time
from hos_scrcpy.interfaces import TouchProvider
from hos_scrcpy.utils.logger import logger

TAG = "FastTouch"


class FastTouchController(TouchProvider):
    """Low-latency touch using StreamBridge stdin. Runs writes in daemon thread."""

    def __init__(self, java_proc):
        self._stdin = java_proc.stdin if java_proc else None
        self._dead = False
        self._last_move_time = 0
        self._last_sent = (0, 0)
        if self._stdin is None:
            logger.warning(f"{TAG}: stdin is None — touch commands will be skipped")
            self._dead = True
        else:
            logger.info(f"{TAG}: initialized, stdin={self._stdin}")

    def _write(self, line):
        if self._dead:
            return
        try:
            self._stdin.write((line + "\n").encode())
            self._stdin.flush()
            logger.debug(f"{TAG}: sent {line}")
        except Exception as ex:
            logger.error(f"{TAG}: write error, marking dead: {ex}")
            self._dead = True

    def down(self, x, y, contact=0):
        self._write(f"D:{x}:{y}")
        self._last_sent = (x, y)
        self._last_move_time = time.monotonic()

    def up(self, x, y, contact=0):
        self._write(f"U:{x}:{y}")

    def move(self, x, y):
        now = time.monotonic()
        # Throttle: max 20 moves/sec, skip sub-10px deltas
        if now - self._last_move_time < 0.05:
            return
        lx, ly = self._last_sent
        if abs(x - lx) < 10 and abs(y - ly) < 10:
            return
        self._write(f"M:{x}:{y}")
        self._last_sent = (x, y)
        self._last_move_time = now

    def click(self, x, y, duration=0.05):
        self.down(x, y)
        time.sleep(duration)
        self.up(x, y)

    def swipe(self, x1, y1, x2, y2, duration=0.3, steps=10):
        """Complete swipe: down at (x1,y1), interpolated moves, up at (x2,y2).

        For standalone use only. GUI should use down()+move()+up() separately
        since _on_press already sends the initial down.
        """
        steps = max(1, steps)
        duration = max(0.01, duration)
        self.down(x1, y1)
        for i in range(1, steps + 1):
            frac = i / steps
            ix = int(x1 + (x2 - x1) * frac)
            iy = int(y1 + (y2 - y1) * frac)
            time.sleep(duration / steps)
            self.move(ix, iy)
        time.sleep(0.02)
        self.up(x2, y2)

    def stop(self):
        """Close stdin pipe and mark as dead."""
        try:
            self._dead = True
            if self._stdin:
                try:
                    self._stdin.flush()
                except Exception:
                    pass
                self._stdin.close()
        except Exception:
            pass

    def __del__(self):
        """Finalizer — ensure stdin is closed."""
        self.stop()
