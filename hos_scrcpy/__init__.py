"""hos_scrcpy — Python API for controlling HarmonyOS 6.0 devices.

Provides a complete Python wrapper around the HOScrcpy Java library,
exposing all original interfaces: touch, mouse, keyboard, screen capture,
UI hierarchy dump, and device management.

Quick start:
    from hos_scrcpy import HOSDevice

    devices = HOSDevice.list_devices()
    if not devices:
        print("No devices found")
        exit(1)

    dev = devices[0].connect()
    print(f"Connected: {dev}")

    # Touch
    dev.touch.click(500, 300)

    # Keyboard
    dev.keyboard.input_text("Hello")

    # Screenshot
    jpeg = dev.screenshot()
    with open("screen.jpg", "wb") as f:
        f.write(jpeg)

    # UI dump
    ui = dev.ui.dump()
    if ui:
        for btn in ui.find_by_type("Button"):
            print(btn.text, btn.center)

    # Screen capture (polling)
    def on_frame(data):
        with open("frame.jpg", "wb") as f:
            f.write(data)

    dev.screen.start_screenshot_stream(on_frame, interval=0.5)
"""

from hos_scrcpy.core.device import Device
from hos_scrcpy.core.hdc_client import HdcClient
from hos_scrcpy.input.keycode import KeyCode, keycode_for_char
from hos_scrcpy.input.touch import TouchController
from hos_scrcpy.input.mouse import MouseController
from hos_scrcpy.input.keyboard import KeyboardController
from hos_scrcpy.screen.capture import ScreenCapture
from hos_scrcpy.ui.hierarchy import JsonStructure
from hos_scrcpy.ui.selector import UIHierarchy, UiSelector


class HOSDevice:
    """Convenience wrapper that bundles all controllers for one device.

    Usage:
        dev = HOSDevice.connect("SN123456")
        dev.touch.click(500, 300)
        dev.keyboard.input_text("Hello")
        jpeg = dev.screenshot()
    """

    def __init__(self, device: Device):
        self._device = device
        self.touch = TouchController(device)
        self.mouse = MouseController(device)
        self.keyboard = KeyboardController(device)
        self.screen = ScreenCapture(device)
        self.ui = UIHierarchy(device)
        from hos_scrcpy.ui.finder import UIFinder
        self.finder = UIFinder(device, touch_controller=self.touch)

    @classmethod
    def connect(cls, sn: str, ip: str = "127.0.0.1", port: str = "8710") -> "HOSDevice":
        """Connect to a device by serial number."""
        device = Device(sn=sn, ip=ip, port=port)
        if not device.is_online():
            raise ConnectionError(f"Device {sn} is not online")
        return cls(device)

    @staticmethod
    def list_devices() -> list[Device]:
        """List all connected devices."""
        return Device.list_all()

    @staticmethod
    def list_remote(ips: list[str]) -> list[Device]:
        """List devices on remote IPs."""
        return Device.list_remote(ips)

    @property
    def sn(self) -> str:
        return self._device.sn

    @property
    def ip(self) -> str:
        return self._device.ip

    @property
    def device(self) -> Device:
        return self._device

    def is_online(self) -> bool:
        return self._device.is_online()

    def screenshot(self, save_path: str = None) -> bytes | None:
        return self._device.screenshot(save_path)

    def dump_layout(self, save_path: str = None) -> str | None:
        return self._device.dump_layout(save_path)

    def execute_shell(self, cmd: str, timeout: int = 10) -> str:
        return self._device.execute_shell(cmd, timeout)

    # ---- uiautomator2-style UI operations ----

    def dump_ui(self):
        """Refresh and return the current UI tree root node."""
        return self.finder.dump()

    def click_by_text(self, text: str) -> bool:
        """Click the element with the given text. Returns True if clicked."""
        return self.finder.click_by_text(text)

    def click_by_id(self, id: str) -> bool:
        """Click the element with the given ID. Returns True if clicked."""
        return self.finder.click_by_id(id)

    def click_by_xpath(self, xpath: str) -> bool:
        """Click the first element matching the xpath. Returns True if clicked."""
        return self.finder.click_by_xpath(xpath)

    def click_by_description(self, description: str) -> bool:
        """Click the element with the given description."""
        return self.finder.click_by_description(description)

    def exists_text(self, text: str) -> bool:
        """Check if any element has the given text."""
        return self.finder.exists_text(text)

    def exists_id(self, id: str) -> bool:
        """Check if any element has the given ID."""
        return self.finder.exists_id(id)

    def exists_xpath(self, xpath: str) -> bool:
        """Check if the xpath matches any elements."""
        return self.finder.exists_xpath(xpath)

    def wait_text(self, text: str, timeout: float = 5.0):
        """Wait for an element with the given text to appear. Returns node or None."""
        return self.finder.wait_text(text, timeout)

    def wait_id(self, id: str, timeout: float = 5.0):
        """Wait for an element with the given ID to appear. Returns node or None."""
        return self.finder.wait_id(id, timeout)

    def wait_xpath(self, xpath: str, timeout: float = 5.0):
        """Wait for an element matching the xpath to appear. Returns node or None."""
        return self.finder.wait_xpath(xpath, timeout)

    def get_text_by_id(self, id: str) -> str | None:
        """Get the text of an element by ID."""
        return self.finder.get_text_by_id(id)

    def get_info_by_text(self, text: str) -> dict | None:
        """Get full info dict for an element by text."""
        return self.finder.get_info_by_text(text)

    def get_info_by_id(self, id: str) -> dict | None:
        """Get full info dict for an element by ID."""
        return self.finder.get_info_by_id(id)

    def get_info_by_xpath(self, xpath: str) -> dict | None:
        """Get full info dict for an element by xpath."""
        return self.finder.get_info_by_xpath(xpath)

    # ---- device management ----

    def reboot(self) -> str:
        """Reboot the device."""
        return self._device.reboot()

    def reboot_bootloader(self) -> str:
        """Reboot into bootloader."""
        return self._device.reboot_bootloader()

    def enable_tcp_mode(self, port: str = "8710") -> str:
        """Enable WiFi debugging mode. Like 'adb tcpip'."""
        return self._device.enable_tcp_mode(port)

    def enable_usb_mode(self) -> str:
        """Switch back to USB debugging mode."""
        return self._device.enable_usb_mode()

    def __repr__(self) -> str:
        return f"HOSDevice({self._device})"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        try:
            if hasattr(self, 'touch') and hasattr(self.touch, 'stop'):
                self.touch.stop()
        except Exception:
            pass
        try:
            self.screen.stop()
        except Exception:
            pass


__all__ = [
    "HOSDevice",
    "Device",
    "HdcClient",
    "KeyCode",
    "keycode_for_char",
    "TouchController",
    "MouseController",
    "KeyboardController",
    "ScreenCapture",
    "UIHierarchy",
    "UiSelector",
    "JsonStructure",
]
