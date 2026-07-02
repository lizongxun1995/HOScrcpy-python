"""Native scrcpy stream via Java subprocess bridge.

Launches StreamBridge.java as a subprocess for JPEG image streaming
and touch command relay via stdin.
"""

import os
import subprocess
import struct
import time
import threading
import atexit
import signal
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


def _kill_proc_tree(proc):
    """Kill a process and its children. Cross-platform.

    On Windows uses taskkill /T to kill the process tree.
    On POSIX uses proc.kill() (SIGTERM).
    """
    import os
    try:
        if os.name == "nt" and proc.pid:
            import subprocess as _sp
            _sp.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True, timeout=5)
        else:
            proc.kill()
            proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass


_CLEANUP_DONE = False

def _cleanup_procs():
    """Kill all active Java subprocesses on exit. Idempotent."""
    global _CLEANUP_DONE
    if _CLEANUP_DONE:
        return
    _CLEANUP_DONE = True
    with _ACTIVE_PROCS_LOCK:
        procs = list(_ACTIVE_PROCS)
        _ACTIVE_PROCS.clear()
    for p in procs:
        _kill_proc_tree(p)

atexit.register(_cleanup_procs)

# ---- signal handlers for robust cleanup ----

def _signal_handler(signum, frame):
    """Signal handler — clean up Java processes on SIGTERM/SIGINT."""
    _cleanup_procs()
    # Re-raise the signal to restore default behavior
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)

try:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
except (ValueError, AttributeError):
    # Not all platforms support signal handlers (e.g., Windows threads)
    pass
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


def _cleanup_stale_procs(sn: str = None):
    """Kill orphaned StreamBridge processes for the given device SN.

    If sn is None, cleans up ALL stale StreamBridge processes (used at exit).
    If sn is provided, only kills processes associated with that device.
    """
    import subprocess as _sp
    target = sn if sn else "StreamBridge"

    if os.name == "nt":
        try:
            result = _sp.run(
                ["wmic", "process", "where", "name='java.exe'",
                 "get", "ProcessId,CommandLine", "/format:csv"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "StreamBridge" in line and target in line:
                    parts = line.split(",")
                    if len(parts) >= 2:
                        pid = parts[-1].strip()
                        if pid.isdigit():
                            logger.info(f"{TAG}: killing stale java[StreamBridge] pid={pid}")
                            _sp.run(["taskkill", "/F", "/T", "/PID", pid],
                                    capture_output=True, timeout=5)
        except Exception:
            pass
    else:
        try:
            result = _sp.run(
                ["pgrep", "-f", f"StreamBridge.*{target}"],
                capture_output=True, text=True, timeout=5,
            )
            for pid in result.stdout.strip().splitlines():
                if pid.isdigit():
                    logger.info(f"{TAG}: killing stale java[StreamBridge] pid={pid}")
                    _sp.run(["kill", "-9", pid], capture_output=True, timeout=5)
        except Exception:
            pass




def _restart_hdc(hdc_path: str, sn: str = None, ip: str = "127.0.0.1", port: str = "8710"):
    """Clean stale forwarding rules and device-side scrcpy processes.

    Only removes port forwarding rules and device-side stale processes.
    Does NOT kill the HDC server itself (preserves other device connections).
    """
    import subprocess as _sp
    # 构建连接参数：远程设备需要 -s ip:port 和 -t sn
    conn_args = [hdc_path]
    if ip not in ("127.0.0.1", "localhost", "::1"):
        conn_args += ["-s", f"{ip}:{port}"]
    if sn:
        conn_args += ["-t", sn]

    # 1. Remove stale forwarding rules (fport rm) instead of killing HDC
    if sn:
        try:
            t_fport = time.monotonic()
            _sp.run(conn_args + ["fport", "rm", "tcp:20000", "tcp:8012"],
                    capture_output=True, timeout=3)
            logger.info(f"{TAG}: _restart_hdc fport_rm took {(time.monotonic() - t_fport)*1000:.0f}ms")
        except Exception:
            pass

    # 2. Kill stale scrcpy processes on the device AND remove stale library
    if sn:
        try:
            t_shell = time.monotonic()
            _sp.run(conn_args + ["shell",
                "for pid in $(pgrep -f 'screen_casting' 2>/dev/null); do "
                "kill -9 $pid 2>/dev/null; done; "
                "rm -f /data/local/tmp/libscreen_casting.z.so"],
                capture_output=True, timeout=5)
            logger.info(f"{TAG}: _restart_hdc shell_cleanup took {(time.monotonic() - t_shell)*1000:.0f}ms")
        except Exception:
            pass


def _push_scrcpy_library(sn: str, ip: str, port: str, hdc_path: str):
    """Push the correct scrcpy server library to device before starting Java.

    Pre-pushes the alternative scrcpy library so the SDK doesn't need
    to fail-and-retry. Just overwrites in case the device copy is stale.
    """
    import subprocess as _sp

    # 构建 hdc 基础参数
    base_args = [hdc_path]
    if ip not in ("127.0.0.1", "localhost", "::1"):
        base_args += ["-s", f"{ip}:{port}", "-t", sn]

    # 推送备用库（覆盖设备上已有的，确保是最新版本）
    lib_filename = "libscrcpy_server_unix_6.5-20260313.z.so"
    lib_path = os.path.join(_BRIDGE_DIR, "scrcpy_server", lib_filename)
    if not os.path.isfile(lib_path):
        logger.warning(f"{TAG}: scrcpy library not found at {lib_path}, skipping push")
        return False

    remote_path = "/data/local/tmp/libscreen_casting.z.so"
    cmd_push = base_args + ["file", "send", lib_path, remote_path]

    logger.info(f"{TAG}: pushing scrcpy library to {sn}...")
    t0 = time.monotonic()
    result = _sp.run(cmd_push, capture_output=True, timeout=15)
    elapsed = (time.monotonic() - t0) * 1000

    if result.returncode == 0:
        logger.info(f"{TAG}: pre-pushed scrcpy library ({elapsed:.0f}ms)")
        return True
    else:
        err = result.stderr.decode("utf-8", errors="replace").strip()
        logger.warning(f"{TAG}: failed to push scrcpy library: {err}")
        return False


def start_native_bridge(sn: str, ip: str = "127.0.0.1", port: str = "8710",
                        wait_ready: bool = True, ready_timeout: float = 35.0,
                        raw_mode: bool = False):
    """Launch Java StreamBridge for JPEG or raw H.264 streaming.

    Args:
        raw_mode: If True, StreamBridge sends raw H.264 + extradata (--raw flag).
    """
    t_total = time.monotonic()
    from hos_scrcpy.core.hdc_client import _find_hdc
    t_find = time.monotonic()
    hdc_path = _find_hdc() or "hdc"
    logger.info(f"{TAG}: _find_hdc took {(time.monotonic() - t_find)*1000:.0f}ms -> {hdc_path}")
    t_find_java = time.monotonic()
    java_path = _find_java_cached()
    logger.info(f"{TAG}: _find_java_cached took {(time.monotonic() - t_find_java)*1000:.0f}ms -> {java_path}")
    classpath = os.path.join(_LIBS_DIR, "*") + os.pathsep + _BRIDGE_DIR

    java_cmd = [
        java_path, "-cp", classpath, "StreamBridge", sn,
    ]
    if raw_mode:
        java_cmd.append("--raw")
    java_cmd += [ip, str(port), hdc_path]

    # 重启 HDC 服务，清除残留的端口转发规则和设备端 scrcpy 进程
    t_restart = time.monotonic()
    _restart_hdc(hdc_path, sn, ip, port)
    logger.info(f"{TAG}: _restart_hdc took {(time.monotonic() - t_restart)*1000:.0f}ms")

    # 启动前清理同设备的残留 Java 进程
    t0 = time.monotonic()
    _cleanup_stale_procs(sn)
    logger.info(f"{TAG}: cleanup_stale_procs took {(time.monotonic() - t0)*1000:.0f}ms")

    # 预推备用 scrcpy 库到设备，避免 SDK 首次启动时推送耗时
    _push_scrcpy_library(sn, ip, port, hdc_path)

    try:
        t1 = time.monotonic()
        java_proc = subprocess.Popen(
            java_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=_BRIDGE_DIR,
        )
        _register_proc(java_proc)
        logger.info(f"{TAG}: subprocess.Popen took {(time.monotonic() - t1)*1000:.0f}ms")
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
            except Exception:
                pass

        threading.Thread(target=_wait_ready, daemon=True).start()
        wait_t0 = time.monotonic()
        if not ready_event.wait(timeout=ready_timeout):
            logger.error(f"{TAG}: Java StreamBridge READY timeout after {ready_timeout}s")
            try:
                java_proc.kill()
                java_proc.wait(timeout=5)
            except Exception:
                pass
            _unregister_proc(java_proc)
            return None

        logger.info(f"{TAG}: wait_ready took {(time.monotonic() - wait_t0)*1000:.0f}ms")

        logger.info(f"{TAG}: start_native_bridge total {(time.monotonic() - t_total)*1000:.0f}ms")

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


def read_frames(proc: subprocess.Popen, stop_event: threading.Event = None):
    """Read length-prefixed frames from proc stdout.

    Args:
        proc: The Java subprocess.
        stop_event: Optional threading.Event; when set, the generator
                    exits on the next read cycle (instead of blocking forever).

    Yields:
        Raw bytes for each frame (H.264 NAL units or JPEG).
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
            if len(data) == length:
                yield data
        except Exception:
            break
