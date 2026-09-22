"""FastTouchController — low-latency touch via the uitest Gestures JSON socket.

Down/up: sent immediately. Move: throttled to max 20/sec, skip tiny deltas.
The socket channel's lifecycle is owned by the stream bridge (HosTouchChannel);
this controller only writes Gestures events through it.
"""

import time
from hos_scrcpy.interfaces import TouchProvider
from hos_scrcpy.utils.logger import logger

TAG = "FastTouch"


class FastTouchController(TouchProvider):
    """Low-latency touch over the persistent uitest socket channel."""

    def __init__(self, touch_channel):
        self._ch = touch_channel
        self._last_move_time = 0
        self._last_sent = (0, 0)
        if touch_channel is None:
            logger.warning(f"{TAG}: touch channel is None — touch commands will be skipped")

    def _send(self, api, x, y):
        if self._ch is None:
            return
        try:
            self._ch.send_touch(api, x, y)
        except Exception as ex:
            # send_touch already swallows OSError; anything else is a bug — log it
            logger.error(f"{TAG}: send {api} error: {ex}")

    def down(self, x, y, contact=0):
        self._send("touchDown", x, y)
        self._last_sent = (x, y)
        self._last_move_time = time.monotonic()

    def up(self, x, y, contact=0):
        self._send("touchUp", x, y)

    def move(self, x, y):
        now = time.monotonic()
        # Throttle: max 20 moves/sec, skip sub-10px deltas
        if now - self._last_move_time < 0.05:
            return
        lx, ly = self._last_sent
        if abs(x - lx) < 10 and abs(y - ly) < 10:
            return
        self._send("touchMove", x, y)
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
        """Detach from the channel. Channel teardown is owned by the bridge."""
        self._ch = None
