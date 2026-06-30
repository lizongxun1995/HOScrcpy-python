"""Native scrcpy stream via Java subprocess bridge.

Launches StreamBridge.java as a subprocess for JPEG image streaming
and touch command relay via stdin.
"""

import os
import subprocess
import struct
import time
import threading
from hos_scrcpy.utils.logger import logger

TAG = "NativeStream"

# ---- global process tracking (thread-safe) ----

_ACTIVE_PROCS: list = []
_ACTIVE_PROCS_LOCK = threading.Lock()


def _register_proc(p):
    """Register a Java subprocess for atexit cleanup."""
    with _ACTIVE_PROCS_LOCK:
        _ACTIVE_PROCS.append(p)


def _unregister_proc(p):
    """Remove a Java subprocess from the tracking list."""
    with _ACTIVE_PROCS_LOCK:
        try:
            _ACTIVE_PROCS.remove(p)
        except ValueError:
            pass


def _cleanup_procs():
    """Kill all active Java subprocesses on exit."""
    with _ACTIVE_PROCS_LOCK:
        procs = list(_ACTIVE_PROCS)
        _ACTIVE_PROCS.clear()
    for p in procs:
        try:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=3)
        except Exception:
            pass

import atexit
atexit.register(_cleanup_procs)
_JAVA_EXE = "java.exe" if os.name == "nt" else "java"

_BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_libs_dir():
    """Find the HOScrcpy libs directory containing the JAR files.

    Resolution order:
    1. HOS_SCRCPY_HOME env var -> $HOS_SCRCPY_HOME/HOScrcpy/libs
    2. HOS_SCRCPY_LIBS env var -> direct path to libs directory
    3. Package-relative: hos_scrcpy/bridge/libs/
    4. Current working directory fallback
    """
    home = os.environ.get("HOS_SCRCPY_HOME")
    if home:
        return os.path.join(home, "HOScrcpy", "libs")

    libs = os.environ.get("HOS_SCRCPY_LIBS")
    if libs:
        return libs

    pkg_libs = os.path.join(_BRIDGE_DIR, "libs")
    if os.path.isdir(pkg_libs):
        return pkg_libs

    # Dev-mode relative path
    dev_libs = os.path.abspath(os.path.join(
        _BRIDGE_DIR, "..", "..", "HOScrcpy-main", "HOScrcpy", "libs"
    ))
    if os.path.isdir(dev_libs):
        return dev_libs

    return os.path.join(os.getcwd(), "libs")


def _find_java():
    """Find java executable. Searches common install locations."""
    # 1. Explicit env var
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = os.path.join(java_home, "bin", _JAVA_EXE)
        if os.path.isfile(candidate):
            return candidate

    # 2. HOS_SCRCPY_JAVA env var
    java_path = os.environ.get("HOS_SCRCPY_JAVA")
    if java_path and os.path.isfile(java_path):
        return java_path

    # 3. PATH
    import shutil
    from_path = shutil.which("java")
    if from_path:
        return from_path

    # 4. Windows common install dirs
    if os.name == "nt":
        import glob as _glob
        search_roots = [
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Microsoft"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Eclipse Adoptium"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Java"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Android\\openjdk"),
        ]
        for root in search_roots:
            if os.path.isdir(root):
                for pattern in ["jdk-*", "jre-*"]:
                    for d in sorted(_glob.glob(os.path.join(root, pattern)), reverse=True):
                        candidate = os.path.join(d, "bin", _JAVA_EXE)
                        if os.path.isfile(candidate):
                            return candidate

    return "java"


_LIBS_DIR = _find_libs_dir()
_JAVA_PATH: str | None = None


def _find_java_cached() -> str:
    """Cached wrapper around _find_java(). Only searches disk once."""
    global _JAVA_PATH
    if _JAVA_PATH is None:
        _JAVA_PATH = _find_java()
    return _JAVA_PATH


def start_native_bridge(sn: str, ip: str = "127.0.0.1", port: str = "8710", wait_ready: bool = True, ready_timeout: float = 35.0):
    """Launch Java StreamBridge for JPEG image streaming.

    Returns (java_proc) on success, None if Java unavailable.
    If wait_ready=True, waits for the Java "READY" signal (image channel active).
    Returns None if READY doesn't arrive within ready_timeout seconds.
    """
    from hos_scrcpy.core.hdc_client import _find_hdc
    hdc_path = _find_hdc() or "hdc"
    java_path = _find_java_cached()
    classpath = os.path.join(_LIBS_DIR, "*") + os.pathsep + _BRIDGE_DIR

    java_cmd = [
        java_path, "-cp", classpath, "StreamBridge", sn, ip, str(port), hdc_path,
    ]

    try:
        java_proc = subprocess.Popen(
            java_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=_BRIDGE_DIR,
        )
        _register_proc(java_proc)
    except Exception as ex:
        logger.error(f"{TAG}: failed to start java: {ex}")
        return None

    if wait_ready:
        # Read stderr line-by-line until READY or timeout
        ready_event = threading.Event()

        def _wait_ready():
            try:
                for line in java_proc.stderr:
                    msg = line.decode("utf-8", errors="replace").strip()
                    if msg:
                        logger.info(f"{TAG}: JAVA {msg}")
                        if "READY" in msg:
                            ready_event.set()
                            break
            except Exception:
                pass
            # Continue logging remaining stderr (touch commands, warnings)
            for line in java_proc.stderr:
                msg = line.decode("utf-8", errors="replace").strip()
                if msg:
                    logger.info(f"{TAG}: JAVA {msg}")

        threading.Thread(target=_wait_ready, daemon=True).start()

        if not ready_event.wait(timeout=ready_timeout):
            logger.error(f"{TAG}: Java StreamBridge READY timeout after {ready_timeout}s")
            try:
                java_proc.kill()
                java_proc.wait(timeout=5)
            except Exception:
                pass
            _unregister_proc(java_proc)
            return None

        logger.info(f"{TAG}: Java image stream ready for {sn}")
    else:
        # Just monitor stderr
        def _log_java():
            for line in java_proc.stderr:
                msg = line.decode("utf-8", errors="replace").strip()
                if msg:
                    logger.info(f"{TAG}: JAVA {msg}")
        threading.Thread(target=_log_java, daemon=True).start()

        logger.info(f"{TAG}: Java image stream started for {sn}")

    return java_proc


def _read_exactly(stream, n: int, stop_event: threading.Event = None, timeout: float = 1.0) -> bytes:
    """Read exactly n bytes from a binary stream, with timeout.

    Returns the bytes if successful, or b'' if stop_event is set or timeout.
    Uses a polling loop so it can be interrupted via stop_event.
    """
    buf = b""
    deadline = time.monotonic() + timeout
    while len(buf) < n:
        if stop_event and stop_event.is_set():
            return b""
        if time.monotonic() > deadline:
            # Partial read -> return what we have (caller checks length)
            return buf
        try:
            chunk = stream.read(min(4096, n - len(buf)))
            if not chunk:
                return buf  # EOF
            buf += chunk
        except Exception:
            return buf
    return buf


def read_jpeg_frames(proc: subprocess.Popen, stop_event: threading.Event = None):
    """Read length-prefixed JPEG frames from proc stdout.

    Args:
        proc: The Java subprocess.
        stop_event: Optional threading.Event; when set, the generator
                    exits on the next read cycle (instead of blocking forever).

    Yields:
        JPEG bytes for each frame.
    """
    while proc.poll() is None:
        try:
            # Use timed read so stop_event can unblock us
            header = _read_exactly(proc.stdout, 4, stop_event, timeout=0.5)
            if stop_event and stop_event.is_set():
                break
            if len(header) < 4:
                time.sleep(0.001)
                continue
            length = struct.unpack(">I", header)[0]
            if length > 10_000_000 or length <= 0:
                continue
            data = _read_exactly(proc.stdout, length, stop_event, timeout=2.0)
            if stop_event and stop_event.is_set():
                break
            if len(data) == length and len(data) > 1000:
                yield data
        except Exception:
            break
