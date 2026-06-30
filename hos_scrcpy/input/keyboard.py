"""KeyboardController — key injection and text input.

Mirrors the KeyBoardCallBack interface and uses uinput -K commands.
Also supports Chinese text input via 'uitest uiInput'.
"""

from hos_scrcpy.core.device import Device
from hos_scrcpy.input.keycode import KeyCode, keycode_for_char
from hos_scrcpy.interfaces import KeyboardProvider
from hos_scrcpy.utils.logger import logger

TAG = "Keyboard"


class KeyboardController(KeyboardProvider):
    """Inject key events and text on a HarmonyOS device."""

    def __init__(self, device: Device):
        self._device = device
        self._timeout = 5

    def key_down(self, keycode: int) -> str:
        """Press a key down (hold)."""
        cmd = f"uinput -K -d {keycode}"
        logger.debug(f"{TAG}: key_down {keycode}")
        return self._device.execute_shell(cmd, self._timeout)

    def key_up(self, keycode: int) -> str:
        """Release a key."""
        cmd = f"uinput -K -u {keycode}"
        logger.debug(f"{TAG}: key_up {keycode}")
        return self._device.execute_shell(cmd, self._timeout)

    def press(self, keycode: int) -> str:
        """Press and release a key."""
        cmd = f"uinput -K -d {keycode} -u {keycode}"
        logger.debug(f"{TAG}: press {keycode}")
        return self._device.execute_shell(cmd, self._timeout)

    def press_shifted(self, keycode: int) -> str:
        """Press a key with shift held."""
        cmd = f"uinput -K -d {KeyCode.SHIFT} -d {keycode} -u {keycode} -u {KeyCode.SHIFT}"
        return self._device.execute_shell(cmd, self._timeout)

    def input_text(self, text: str) -> str:
        """Input text (supports Chinese and special characters).

        Uses 'uitest uiInput text' command which handles IME input.
        """
        if not text:
            return ""
        # Escape single quotes in text for shell safety
        safe_text = text.replace("'", "'\\''")
        cmd = f"uitest uiInput text '{safe_text}'"
        logger.debug(f"{TAG}: input_text len={len(text)}")
        return self._device.execute_shell(cmd, max(self._timeout, 10))

    def paste(self) -> None:
        """Paste clipboard content (Ctrl+V)."""
        self.key_down(KeyCode.CTRL)
        self.press(KeyCode.V)
        self.key_up(KeyCode.CTRL)

    def paste_from_clipboard(self) -> str | None:
        """Read system clipboard and send text to device.

        This reads the actual system clipboard (not just simulating Ctrl+V).
        Uses 'uitest uiInput text' for Chinese/Unicode support.
        """
        text = _read_clipboard()
        if text:
            return self.input_text(text)
        return None

    # ---- convenience shortcuts ----

    def home(self) -> str:
        """Press Home key."""
        return self._device.press_key(KeyCode.HOME)

    def back(self) -> str:
        """Press Back key."""
        return self._device.press_key(KeyCode.BACK)

    def power(self) -> str:
        """Press Power key."""
        return self._device.press_key(KeyCode.POWER)

    def volume_up(self) -> str:
        """Press Volume Up key."""
        return self._device.press_key(KeyCode.VOLUME_UP)

    def volume_down(self) -> str:
        """Press Volume Down key."""
        return self._device.press_key(KeyCode.VOLUME_DOWN)

    def enter(self) -> str:
        """Press Enter key."""
        return self.press(KeyCode.ENTER)

    def backspace(self) -> str:
        """Press Backspace key."""
        return self.press(KeyCode.BACKSPACE)

    def space(self) -> str:
        """Press Space key."""
        return self.press(KeyCode.SPACE)

    def type_char(self, char: str) -> str:
        """Type a single character."""
        code = keycode_for_char(char)
        if code < 0:
            return self.input_text(char)
        if char.isupper():
            return self.press_shifted(code)
        return self.press(code)

    def type(self, text: str) -> None:
        """Type a string, character by character.

        Non-printable / CJK characters fall back to input_text.
        """
        if not text:
            return
        for ch in text:
            if ch.isascii() and ch.isprintable():
                self.type_char(ch)
            else:
                self.input_text(ch)


def _read_clipboard() -> str | None:
    """Read text from the system clipboard. Cross-platform.

    Tries platform-native tools first, falls back to tkinter as last resort
    (since tk.Tk() may fail in headless/SSH environments).
    """
    import subprocess
    import os
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["powershell", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                return result.stdout.strip()
        else:
            for cmd in [["xclip", "-o", "-selection", "clipboard"], ["pbpaste"]]:
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0 and result.stdout.strip():
                        return result.stdout.strip()
                except Exception:
                    continue
    except Exception:
        pass

    # Last resort: try tkinter (may fail in headless environments)
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        return text
    except Exception:
        pass

    return None
