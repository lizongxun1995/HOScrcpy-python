"""HdcClient — wraps the hdc command-line tool for device communication.

All commands are built as argument lists and launched with shell=False,
eliminating shell-injection attack vectors.
"""

import os
import shlex
import shutil
import threading
from hos_scrcpy.core.process import run
from hos_scrcpy.utils.logger import logger


_ERROR_MARKERS = [
    "ErrorMessage:",
    "not recognized",
    "not found",
    "No such file",
    "[Fail]",
]

# Search for hdc in these directories (in order)
_HDC_SEARCH_DIRS = [
    # 1. Bundled with package (highest priority)
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "toolchains"),
    # 2. User toolchain directory
    os.path.join(os.path.expanduser("~"), ".hos-scrcpy", "toolchains"),
]

_HDC_PATH = None
_HDC_LOCK = threading.Lock()


def _find_hdc() -> str | None:
    """Find hdc executable. Caches the result (thread-safe)."""
    global _HDC_PATH
    if _HDC_PATH is not None:
        return _HDC_PATH if _HDC_PATH else None

    with _HDC_LOCK:
        # Double-check inside lock
        if _HDC_PATH is not None:
            return _HDC_PATH if _HDC_PATH else None

        # 1. Check local toolchains directory
        for d in _HDC_SEARCH_DIRS:
            candidate = os.path.join(d, "hdc.exe" if os.name == "nt" else "hdc")
            if os.path.isfile(candidate):
                _HDC_PATH = candidate
                logger.debug(f"Found hdc at: {candidate}")
                return _HDC_PATH

        # 2. Fall back to PATH
        from_path = shutil.which("hdc")
        if from_path:
            _HDC_PATH = from_path
            logger.debug(f"Found hdc on PATH: {from_path}")
            return _HDC_PATH

        _HDC_PATH = ""
        return None


class HdcClient:
    """Low-level hdc command wrapper.

    All commands go through the hdc CLI tool installed with HarmonyOS SDK.
    Default hdc port is 8710.

    Builds argument lists internally so no shell injection vector exists.
    """

    HDC_PORT = "8710"

    def __init__(self, ip: str = "127.0.0.1", port: str = None):
        self.ip = ip
        self.port = port or self.HDC_PORT

    @staticmethod
    def is_available() -> bool:
        """Check if hdc is installed and accessible."""
        return _find_hdc() is not None

    # ---- argument list builders ----

    def _hdc_cmd(self) -> str:
        """Resolved hdc executable path."""
        return _find_hdc() or "hdc"

    def _connect_args(self, sn: str = None) -> list[str]:
        """Return the leading args that select device: ["-s", "ip:port", "-t", "sn"]."""
        hdc = self._hdc_cmd()
        args = [hdc, "-s", f"{self.ip}:{self.port}"]
        if sn:
            args.extend(["-t", sn])
        return args

    def _run(self, args: list[str], timeout: int = 10) -> str:
        """Execute an arg list and return output, or empty string on error."""
        output, rc = run(args, timeout=timeout)
        if rc != 0:
            logger.debug(f"hdc command failed (rc={rc}): {' '.join(args[:4])}...")
            return ""
        return output

    # ---- commands ----

    def list_targets(self) -> str:
        """List all connected device targets."""
        if not self.is_available():
            return ""
        hdc = self._hdc_cmd()
        # For localhost, skip -s (auto-discover is instant)
        if self.ip in ("127.0.0.1", "localhost", "::1"):
            args = [hdc, "list", "targets"]
        else:
            args = [hdc, "-s", f"{self.ip}:{self.port}", "list", "targets"]
        return self._run(args, timeout=10)

    def shell(self, sn: str, command: str, timeout: int = 10) -> str:
        """Execute a shell command on the device.

        The entire command string is passed as a single argument to hdc,
        which forwards it verbatim to the device shell. No local shell
        interpretation occurs.
        """
        args = self._connect_args(sn)
        args.extend(["shell", command])
        logger.debug(f"Shell [{sn}]: {command}")
        return self._run(args, timeout=timeout)

    def execute(self, sn: str, command: str, timeout: int = 10) -> str:
        """Execute a raw hdc command (not shell).

        The command string is split into arguments via shlex.split() so
        things like ``file recv "remote path" "local path"`` work correctly.
        """
        args = self._connect_args(sn)
        args.extend(shlex.split(command))
        logger.debug(f"Execute [{sn}]: {command}")
        return self._run(args, timeout=timeout)

    def server_execute(self, command: str, timeout: int = 10) -> str:
        """Execute a server-level hdc command (no device target required).

        Used for tconn (connect/disconnect remote) and other server operations.
        """
        hdc = self._hdc_cmd()
        args = [hdc, "-s", f"{self.ip}:{self.port}"] + shlex.split(command)
        logger.debug(f"Server: {command}")
        return self._run(args, timeout=timeout)

    def connect_remote(self, remote_ip: str, remote_port: str = "8710") -> str:
        """Connect to a remote device over TCP/IP. Like 'adb connect'."""
        key = f"{remote_ip}:{remote_port}"
        return self.server_execute(f"tconn {key}", timeout=10)

    def disconnect_remote(self, remote_key: str) -> str:
        """Disconnect a remote device."""
        return self.server_execute(f"tconn {remote_key} -remove", timeout=10)
