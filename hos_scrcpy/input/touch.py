"""TouchController — touch injection via uinput shell commands.

Mirrors the HosRemoteDevice touch methods and MainForm touch callbacks.
"""

import time
from hos_scrcpy.core.device import Device
from hos_scrcpy.utils.logger import logger

TAG = "Touch"


class TouchController:
    """Inject touch events on a HarmonyOS device.

    Uses 'uinput -M' (multi-touch) commands via hdc shell.
    Compatible with all HarmonyOS versions.

    Usage:
        touch = TouchController(device)
        touch.down(500, 300)
        touch.move(510, 310)
        touch.up(510, 310)
        # or convenience:
        touch.click(500, 300)
        touch.swipe(100, 500, 800, 500, duration=0.5)
    """

    def __init__(self, device: Device):
        self._device = device
        self._default_timeout = 5

    def down(self, x: int, y: int, contact: int = 0) -> str:
        """Touch down at (x, y).

        Args:
            x, y: Screen coordinates.
            contact: Touch contact index (0-9 for multi-touch).
        """
        cmd = f"uinput -M -m {x} {y} -c {contact}"
        logger.debug(f"{TAG}: down ({x}, {y}) contact={contact}")
        return self._device.execute_shell(cmd, self._default_timeout)

    def up(self, x: int, y: int, contact: int = 0) -> str:
        """Touch up at (x, y)."""
        cmd = f"uinput -M -m {x} {y} -c {contact}"
        logger.debug(f"{TAG}: up ({x}, {y}) contact={contact}")
        return self._device.execute_shell(cmd, self._default_timeout)

    def move(self, x: int, y: int) -> str:
        """Move touch point to (x, y)."""
        cmd = f"uinput -M -m {x} {y}"
        logger.debug(f"{TAG}: move ({x}, {y})")
        return self._device.execute_shell(cmd, self._default_timeout)

    def click(self, x: int, y: int, duration: float = 0.05) -> None:
        """Tap at (x, y) — down, wait duration, up.

        Args:
            x, y: Screen coordinates.
            duration: Hold time in seconds.
        """
        self.down(x, y)
        time.sleep(duration)
        self.up(x, y)

    def long_press(self, x: int, y: int, duration: float = 1.0) -> None:
        """Long press at (x, y)."""
        self.down(x, y)
        time.sleep(duration)
        self.up(x, y)

    def swipe(
        self,
        x1: int, y1: int,
        x2: int, y2: int,
        duration: float = 0.3,
        steps: int = 10,
    ) -> None:
        """Swipe from (x1, y1) to (x2, y2).

        Args:
            x1, y1: Start coordinates.
            x2, y2: End coordinates.
            duration: Total swipe time in seconds.
            steps: Number of intermediate move events.
        """
        self.down(x1, y1)
        step_delay = duration / steps
        for i in range(1, steps + 1):
            frac = i / steps
            ix = int(x1 + (x2 - x1) * frac)
            iy = int(y1 + (y2 - y1) * frac)
            time.sleep(step_delay)
            self.move(ix, iy)
        time.sleep(0.02)
        self.up(x2, y2)
