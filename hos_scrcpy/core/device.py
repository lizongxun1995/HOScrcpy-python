"""Device entity — wraps device connection, screenshots, layout dump, and shell commands."""

import os
import json
import tempfile
import uuid
from hos_scrcpy.core.hdc_client import HdcClient
from hos_scrcpy.interfaces import (
    HOScrcpyError,
    DeviceOfflineError,
    ScreenshotError,
    CommandNotSupportedError,
    UIHierarchyError,
)
from hos_scrcpy.utils.logger import logger

TAG = "Device"


class Device:
    """Represents a connected HarmonyOS device.

    Mirrors the Java Device.java entity.  Uses hdc commands for all operations.
    """

    def __init__(self, sn: str, ip: str = "127.0.0.1", port: str = "8710"):
        self.sn = sn
        self.ip = ip
        self.port = port
        self._client = HdcClient(ip, port)

    # ---- factory methods ----

    @staticmethod
    def list_local() -> list["Device"]:
        """List devices connected via USB (localhost hdc)."""
        if not HdcClient.is_available():
            return []
        client = HdcClient("127.0.0.1")
        result = client.list_targets()
        return Device._parse_targets(result)

    @staticmethod
    def list_remote(ips: list[str]) -> list["Device"]:
        """List remote devices reachable at the given IP addresses."""
        if not HdcClient.is_available():
            return []
        devices = []
        for ip in ips:
            client = HdcClient(ip)
            result = client.list_targets()
            for sn in Device._parse_sn_list(result):
                devices.append(Device(sn=sn, ip=ip))
        return devices

    @staticmethod
    def list_all() -> list["Device"]:
        """List all devices (local + any configured remote IPs from settings)."""
        devices = Device.list_local()
        try:
            from hos_scrcpy.utils.settings import get_remote_ips
            for entry in get_remote_ips():
                parts = entry.rsplit(":", 1)
                ip = parts[0]
                port = parts[1] if len(parts) == 2 else "8710"
                client = HdcClient(ip, port)
                result = client.list_targets()
                for sn in Device._parse_sn_list(result):
                    if not any(d.sn == sn for d in devices):
                        devices.append(Device(sn=sn, ip=ip, port=port))
        except ImportError:
            pass
        return devices

    @staticmethod
    def _parse_targets(raw: str) -> list["Device"]:
        """Parse 'hdc list targets' output into Device list."""
        devices = []
        if not raw or "Empty" in raw:
            return devices
        for line in raw.splitlines():
            sn = line.strip()
            if sn and not sn.startswith("ErrorMessage:") and len(sn) < 256:
                devices.append(Device(sn=sn))
        return devices

    @staticmethod
    def _parse_sn_list(raw: str) -> list[str]:
        """Parse SN strings from hdc output."""
        if not raw or "Empty" in raw or "failed" in raw.lower():
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]

    # ---- properties ----

    @property
    def is_remote(self) -> bool:
        return self.ip != "127.0.0.1"

    def is_online(self) -> bool:
        """Check if the device is still reachable."""
        result = self._client.list_targets()
        return bool(self.sn) and self.sn in result

    # ---- commands ----

    def execute_shell(self, command: str, timeout: int = 10) -> str:
        """Run a shell command on the device."""
        return self._client.shell(self.sn, command, timeout)

    def execute(self, command: str, timeout: int = 10) -> str:
        """Run a raw hdc command."""
        return self._client.execute(self.sn, command, timeout)

    # ---- screenshot ----

    def screenshot(self, save_path: str = None) -> bytes | None:
        """Capture a screenshot from the device.

        Each call uses a unique remote temp file to avoid races
        when multiple threads capture concurrently.

        Args:
            save_path: Optional local path to persist the JPEG. If None,
                       the image bytes are still returned but no file kept.

        Returns:
            JPEG bytes, or None on failure.

        Raises:
            ScreenshotError: All screenshot commands failed.
        """
        remote_path = "/data/local/tmp/" + uuid.uuid4().hex + ".jpeg"
        local_path = save_path or os.path.join(
            tempfile.gettempdir(),
            f"hdc-{self.sn}-{uuid.uuid4().hex}.jpeg",
        )
        try:
            for cmd in [
                f"snapshot_display -f {remote_path}",
                f"screenshot -f {remote_path}",
                f"uitest screenshot -f {remote_path}",
            ]:
                # Remove any stale file from a previous failed call
                self.execute_shell(f"rm -f {remote_path}", timeout=5)
                result = self.execute_shell(cmd, timeout=7)
                logger.debug(f"{TAG}: {cmd} -> {result[:120] if result else '(empty)'}")

                if result and ("error" not in result.lower() and "fail" not in result.lower() and "not found" not in result.lower()):
                    break
            else:
                raise ScreenshotError("all screenshot commands failed")

            pull_result = self.execute(
                f'file recv {remote_path} "{local_path}"',
                timeout=5,
            )
            logger.debug(f"{TAG}: file recv -> {pull_result[:120] if pull_result else '(empty)'}")

            if not os.path.exists(local_path):
                raise ScreenshotError(f"screenshot file not found at {local_path}")

            with open(local_path, "rb") as f:
                return f.read()
        except HOScrcpyError:
            raise
        except Exception as ex:
            raise ScreenshotError(f"screenshot exception: {ex}") from ex
        finally:
            # Clean up remote file (best-effort)
            try:
                self.execute_shell(f"rm -f {remote_path}", timeout=3)
            except Exception:
                pass
            # Clean up local temp file unless caller asked to keep it
            if not save_path and local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception:
                    pass

    # ---- layout dump ----

    def dump_layout(self, save_path: str = None) -> str | None:
        """Dump the UI layout hierarchy from the device.

        Uses 'uitest dumpLayout' to capture the current UI tree as JSON.

        Args:
            save_path: Optional local file path to persist the JSON.
                       If None, saves to a temp file.

        Returns:
            JSON string of the layout hierarchy, or None on failure.
        """
        try:
            result = self.execute_shell("uitest dumpLayout", timeout=10)
            logger.debug(f"{TAG}: dump layout result: {result}")

            if not result or "DumpLayout saved to:" not in result:
                logger.debug(f"{TAG}: dump layout failed: {result}")
                return None

            first = result.rfind("to:")
            last = result.find(".json")
            if first < 0 or last < 0 or last <= first:
                logger.error(f"{TAG}: cannot parse dump path from: {result}")
                return None
            remote_path = result[first + 3:last + 5].strip()

            if save_path is None:
                tmpdir = tempfile.gettempdir()
                save_path = os.path.join(tmpdir, "dumpLayout.json")

            pull_result = self.execute(
                f'file recv "{remote_path}" "{save_path}"',
                timeout=5,
            )

            if "finish" not in pull_result or not os.path.exists(save_path):
                logger.info(f"{TAG}: pull dumpLayout.json failed")
                return None

            with open(save_path, "r", encoding="utf-8") as f:
                content = f.read()

            return content
        except Exception as ex:
            logger.error(f"{TAG}: get layout failed: {ex}")
            return None

    # ---- key event helpers ----

    def press_key(self, keycode: int) -> str:
        """Press and release a key (for power, back, volume, etc.)."""
        return self.execute_shell(f"uinput -K -d {keycode} -u {keycode}", timeout=3)

    def reboot(self) -> str:
        """Reboot the device."""
        return self._client.execute(self.sn, "target boot", timeout=10)

    def reboot_bootloader(self) -> str:
        """Reboot into bootloader."""
        return self._client.execute(self.sn, "target boot -bootloader", timeout=10)

    # ---- network mode ----

    def enable_tcp_mode(self, port: str = "8710") -> str:
        """Enable TCP/IP mode on device (makes it discoverable over WiFi).

        Like 'adb tcpip 5555'. Device will reboot and listen on the given port.
        """
        return self._client.execute(self.sn, f"tmode port {port}", timeout=10)

    def enable_usb_mode(self) -> str:
        """Switch device back to USB mode."""
        return self._client.execute(self.sn, "tmode usb", timeout=10)

    def connect_remote(self, remote_ip: str, remote_port: str = "8710") -> str:
        """Connect to a remote device over TCP/IP.

        Like 'adb connect IP:PORT'.
        """
        return self._client.connect_remote(remote_ip, remote_port)

    def disconnect_remote(self, remote_key: str) -> str:
        """Disconnect a remote device."""
        return self._client.disconnect_remote(remote_key)

    def __repr__(self) -> str:
        if self.is_remote:
            return f"Device(ip={self.ip}, sn={self.sn})"
        return f"Device(sn={self.sn})"

    def __str__(self) -> str:
        if self.is_remote:
            return f"{self.ip}-{self.sn}"
        return self.sn

    def __eq__(self, other) -> bool:
        if not isinstance(other, Device):
            return False
        return self.sn == other.sn and self.ip == other.ip

    def __hash__(self) -> int:
        return hash((self.sn, self.ip))
