"""HdcClient — wraps the hdc command-line tool for device communication."""

import os
import shutil
from hos_scrcpy.core.process import run
from hos_scrcpy.utils.logger import logger


def _shell_escape(text: str) -> str:
    """Escape a string for safe use as a shell command argument.

    On Windows, uses double-quote wrapping with internal double-quote escaping.
    On POSIX, uses single-quote wrapping (POSIX standard).
    """
    if os.name == "nt":
        # Windows cmd.exe: wrap in double quotes, escape internal double quotes
        escaped = text.replace('"', '""')
        # Remove characters that always break cmd.exe parsing
        for ch in '&|<>':
            escaped = escaped.replace(ch, '')
        return f'"{escaped}"'
    else:
        import shlex
        return shlex.quote(text)

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


def _find_hdc() -> str | None:
    """Find hdc executable. Caches the result."""
    global _HDC_PATH
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
    """

    HDC_PORT = "8710"

    def __init__(self, ip: str = "127.0.0.1", port: str = None):
        self.ip = ip
        self.port = port or self.HDC_PORT

    @staticmethod
    def is_available() -> bool:
        """Check if hdc is installed and accessible."""
        return _find_hdc() is not None

    @staticmethod
    def _is_error_output(output: str) -> bool:
        """Heuristic: does this output look like an error rather than valid data?"""
        if not output.strip():
            return False
        lower = output.lower()
        for marker in _ERROR_MARKERS:
            if marker.lower() in lower:
                return True
        return False

    @staticmethod
    def _clean_arg(val: str) -> str:
        """Sanitize a value for safe use as a shell argument (no shell metacharacters)."""
        # Remove characters that have special meaning to cmd.exe or sh
        forbidden = set(';&|`$(){}!<>')
        return ''.join(c for c in str(val) if c not in forbidden)

    def _base_cmd(self, sn: str = None) -> str:
        """Build the base hdc command prefix."""
        hdc = _find_hdc() or "hdc"
        base = f'"{hdc}" -s {self._clean_arg(self.ip)}:{self._clean_arg(str(self.port))}'
        if sn:
            base += f" -t {self._clean_arg(sn)}"
        return base

    def _run(self, cmd: str, timeout: int = 10) -> str:
        """Execute a command and return output, or empty string on error."""
        output, rc = run(cmd, timeout=timeout)
        if rc != 0:
            logger.debug(f"hdc command failed (rc={rc}): {cmd[:80]}")
            return ""
        return output

    def list_targets(self) -> str:
        """List all connected device targets."""
        if not self.is_available():
            return ""
        cmd = f"{self._base_cmd()} list targets"
        return self._run(cmd, timeout=10)

    def shell(self, sn: str, command: str, timeout: int = 10) -> str:
        """Execute a shell command on the device."""
        safe_command = _shell_escape(command)
        cmd = f"{self._base_cmd(sn)} shell {safe_command}"
        logger.debug(f"Shell [{sn}]: {command}")
        return self._run(cmd, timeout=timeout)

    def execute(self, sn: str, command: str, timeout: int = 10) -> str:
        """Execute a raw hdc command (not shell).

        Note: raw hdc commands go directly to hdc, not through device shell.
        We only clean dangerous metacharacters, not quote-wrap.
        """
        safe_command = self._clean_arg(command)
        cmd = f"{self._base_cmd(sn)} {safe_command}"
        logger.debug(f"Execute [{sn}]: {command}")
        return self._run(cmd, timeout=timeout)

    def server_execute(self, command: str, timeout: int = 10) -> str:
        """Execute a server-level hdc command (no device target required).

        Used for tconn (connect/disconnect remote) and other server operations.
        """
        hdc = _find_hdc() or "hdc"
        cmd = f'"{hdc}" -s {self.ip}:{self.port} {command}'
        logger.debug(f"Server: {command}")
        return self._run(cmd, timeout=timeout)

    def connect_remote(self, remote_ip: str, remote_port: str = "8710") -> str:
        """Connect to a remote device over TCP/IP. Like 'adb connect'."""
        key = f"{self._clean_arg(remote_ip)}:{self._clean_arg(str(remote_port))}"
        return self.server_execute(f"tconn {key}", timeout=10)

    def disconnect_remote(self, remote_key: str) -> str:
        """Disconnect a remote device."""
        return self.server_execute(f"tconn {self._clean_arg(remote_key)} -remove", timeout=10)
