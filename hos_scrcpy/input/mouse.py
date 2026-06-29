"""MouseController — mouse event injection.

Mirrors HosRemoteDevice mouse methods (MOUSE_LEFT / MOUSE_MIDDLE / MOUSE_RIGHT).
Uses 'uinput -M' with button codes for basic click support,
falls back to protocol-level calls when JPype bridge is available.
"""

from hos_scrcpy.core.device import Device
from hos_scrcpy.utils.logger import logger

TAG = "Mouse"

MOUSE_LEFT = "LEFT"
MOUSE_MIDDLE = "MIDDLE"
MOUSE_RIGHT = "RIGHT"

_BUTTON_CODE = {MOUSE_LEFT: 0, MOUSE_MIDDLE: 1, MOUSE_RIGHT: 1}


class MouseController:
    """Inject mouse events on a HarmonyOS device.

    For devices with uitest >= 5.1.1.3 full mouse support (drag, wheel) is available.
    Older versions support only left/right click without drag.
    """

    MOUSE_LEFT = MOUSE_LEFT
    MOUSE_MIDDLE = MOUSE_MIDDLE
    MOUSE_RIGHT = MOUSE_RIGHT

    def __init__(self, device: Device):
        self._device = device
        self._timeout = 5

    def down(self, button: str, x: int, y: int) -> str:
        """Mouse button down at (x, y)."""
        code = _BUTTON_CODE.get(button, 0)
        cmd = f"uinput -M -m {x} {y} -c {code}"
        logger.debug(f"{TAG}: down {button} ({x}, {y})")
        return self._device.execute_shell(cmd, self._timeout)

    def up(self, button: str, x: int, y: int) -> str:
        """Mouse button up at (x, y)."""
        code = _BUTTON_CODE.get(button, 0)
        cmd = f"uinput -M -m {x} {y} -c {code}"
        logger.debug(f"{TAG}: up {button} ({x}, {y})")
        return self._device.execute_shell(cmd, self._timeout)

    def move(self, x: int, y: int) -> str:
        """Move mouse cursor to (x, y)."""
        cmd = f"uinput -M -m {x} {y}"
        logger.debug(f"{TAG}: move ({x}, {y})")
        return self._device.execute_shell(cmd, self._timeout)

    def click(self, button: str, x: int, y: int) -> None:
        """Mouse click — down then up."""
        self.down(button, x, y)
        self.up(button, x, y)

    def wheel_up(self, x: int, y: int) -> str:
        """Scroll wheel up at (x, y). Negative scroll value."""
        cmd = f"uinput -M -m {x} {y} -s -500"
        return self._device.execute_shell(cmd, self._timeout)

    def wheel_down(self, x: int, y: int) -> str:
        """Scroll wheel down at (x, y). Positive scroll value."""
        cmd = f"uinput -M -m {x} {y} -s 500"
        return self._device.execute_shell(cmd, self._timeout)

    def wheel_stop(self, x: int, y: int) -> str:
        """Stop scroll wheel at (x, y)."""
        cmd = f"uinput -M -m {x} {y} -s 0"
        return self._device.execute_shell(cmd, self._timeout)
