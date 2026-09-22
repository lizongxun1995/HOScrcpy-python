"""Pure-Python scrcpy stream bridge — no Java, no JAR.

Replaces the former Java StreamBridge subprocess. Two channels, both relayed
through local ``hdc fport`` forwards, talking to the device-side components
that ship with HarmonyOS itself (the same components the closed-source
hosScrcpy SDK used):

Video (H.264 server stream):
  1. md5-check and push ``libscreen_casting.z.so`` to /data/local/tmp/;
  2. restart the extension daemon: ``uitest start-daemon singleness
     --extension-name libscreen_casting.z.so -scale N -frameRate N
     -bitRate N(bytes) -p 5000 -iFrameInterval N -repeatInterval N &``;
  3. ``hdc fport`` — uitest > 6.0.2.1 targets ``localabstract:scrcpy_grpc_socket``,
     older systems ``tcp:5000``;
  4. plaintext gRPC to the local forward port, ``ScrcpyService/onStart``
     server stream; each message's ``payload["data"].val_bytes`` is one raw
     H.264 chunk (no length prefix — concatenate and split on NAL start codes).

Touch (uitest daemon JSON socket, persistent connection):
  1. pick the agent .so for the device's uitest version (5-entry mapping);
  2. version-check and push ``/data/local/tmp/agent.so``;
  3. make sure the system uitest daemon is running (no --extension-name);
  4. ``hdc fport`` — agent >= 1.2.0 targets ``localabstract:uitest_socket``,
     older ``tcp:8012``; then send Gestures JSON events directly.

Discipline: every hdc call carries an explicit timeout; failures raise
RuntimeError with a Chinese message; no automatic retry loops (the SDK's
5s flush-and-repush timer was what kept breaking the device-side service).
"""

import hashlib
import json
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path
from queue import Queue, Full

import grpc

from hos_scrcpy.bridge import scrcpy_pb2, scrcpy_pb2_grpc
from hos_scrcpy.core.hdc_client import _find_hdc, _ERROR_MARKERS
from hos_scrcpy.core.process import run
from hos_scrcpy.utils.logger import logger

TAG = "NativeStream"

# ---- static assets and constants ----

_SO_DIR = Path(__file__).parent / "scrcpy_server"

# 投屏扩展库用 6.5-20260313：参考项目真机实证能出帧（6.6-20260418 在部分
# 设备 createChannel 循环失败）；推到设备端固定名 libscreen_casting.z.so，
# 守护进程按名加载
_VIDEO_SO_FILE = "libscrcpy_server_unix_6.5-20260313.z.so"
_VIDEO_SO_REMOTE = "/data/local/tmp/libscreen_casting.z.so"
_EXTENSION_NAME = "libscreen_casting.z.so"

# 设备端 gRPC 监听口（老版本走 tcp 转发目标；新版本 localabstract 与口无关，
# 但 -p 参数仍带上，保持与 SDK 行为一致）
_VIDEO_DAEMON_PORT = 5000

# agent so 固定落点与版本标记（agent.so 内嵌 UITEST_AGENT_LIBRARY 字符串 +
# '#版本号'，用 grep -a 提取）
_AGENT_SO_REMOTE = "/data/local/tmp/agent.so"
_AGENT_VERSION_TAG = "UITEST_AGENT_LIBRARY"

# 流参数：WiFi 下 2Mbps/20fps；-bitRate 单位是字节/秒（SDK 的 getParams() 对
# MB 数做 <<10<<10，历史版本误传 2_000_000 进 MB 通道会 int 溢出成垃圾值）
STREAM_SCALE = 1
STREAM_FRAME_RATE = 20
STREAM_BIT_RATE = 2_000_000
STREAM_IFRAME_INTERVAL_MS = 2000
STREAM_REPEAT_INTERVAL = 33

_CONNECT_TIMEOUT = 5.0
_RPC_TIMEOUT = 3.0

FIRST_CHUNK_TIMEOUT = 15.0   # 首块等待（唤屏 + IDR 催帧）
STALL_PROBE_INTERVAL = 5.0   # 无块多久后做一次 IDR 探活 + 唤屏
_STALL_DEATH_TIMEOUT = 60.0  # 持续无块多久判死、退出流


# ---- process-tree killer (kept for the screenrecord path in capture.py) ----

def _kill_proc_tree(proc):
    """Kill a process and its children. Cross-platform.

    On Windows uses taskkill /T to kill the process tree.
    On POSIX uses proc.kill() (SIGTERM).
    """
    try:
        if os.name == "nt" and proc.pid:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
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


# ---- hdc adapter (module-level, explicit failures) ----

def _hdc_run(sn: str, ip: str, port: str, args: list[str], timeout: float = 8.0) -> str:
    """Run an hdc command for the device. Returns stdout; raises on failure."""
    hdc = _find_hdc() or "hdc"
    cmd = [hdc, "-s", f"{ip}:{port}"]
    if sn:
        cmd += ["-t", sn]
    cmd += args
    out, rc = run(cmd, timeout=timeout)
    text = out or ""
    if rc != 0 or any(m in text for m in _ERROR_MARKERS):
        raise RuntimeError(f"hdc {' '.join(args)} 失败 (rc={rc}): {text.strip()[:200]}")
    return text


def _shell(sn: str, ip: str, port: str, command: str, timeout: float = 8.0) -> str:
    """Run a shell command on the device via hdc."""
    return _hdc_run(sn, ip, port, ["shell", command], timeout=timeout)


def _exec(sn: str, ip: str, port: str, args: list[str], timeout: float = 8.0) -> str:
    """Run a raw hdc subcommand (file send / fport ...)."""
    return _hdc_run(sn, ip, port, args, timeout=timeout)


# ---- version helpers ----

def parse_version(text: str) -> tuple[int, ...]:
    """'6.0.2.1' → (6, 0, 2, 1)；解析失败返回空元组（调用方按不可用处理）。"""
    parts: list[int] = []
    for seg in text.strip().split("."):
        if not seg.isdigit():
            return ()
        parts.append(int(seg))
    return tuple(parts)


def version_cmp(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """元组版本比较：a>b 返回 1、a<b 返回 -1、相等返回 0（空元组视为最小）。"""
    if not a:
        return -1 if b else 0
    if not b:
        return 1
    for x, y in zip(a, b):
        if x != y:
            return 1 if x > y else -1
    if len(a) == len(b):
        return 0
    return 1 if len(a) > len(b) else -1


def _uitest_version(sn: str, ip: str, port: str) -> tuple[int, ...]:
    """/system/bin/uitest --version → 版本元组（失败/解析不出返回空元组）。"""
    try:
        out = _shell(sn, ip, port, "/system/bin/uitest --version", timeout=5.0)
    except Exception:
        return ()
    # 输出可能混入换行/提示语，取最后一个 x.y.z(.n) 形态段
    for line in reversed(out.strip().splitlines()):
        m = re.search(r"(\d+(?:\.\d+){1,3})", line)
        if m:
            return parse_version(m.group(1))
    return ()


# ---- shared small utilities ----

def _alloc_local_port() -> int:
    """取一个空闲本机 TCP 口（bind(0) 即取即还，紧接的 fport 会立刻占用）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _local_md5(path: Path) -> str:
    """本地文件 md5（推送前与设备端 md5sum 对比，不一致才推）。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _device_md5(sn: str, ip: str, port: str, remote_path: str, name: str) -> str:
    """设备端文件 md5（md5sum 输出首段）；文件不存在/命令失败返回空串。"""
    try:
        out = _shell(sn, ip, port, f"md5sum {remote_path}", timeout=8.0)
    except Exception as e:
        logger.debug(f"{TAG}: [{name}] 设备端 md5sum {remote_path} 失败（按未部署处理）: {e}")
        return ""
    first = out.strip().split()
    return first[0] if first else ""


def _ps_singleness(sn: str, ip: str, port: str) -> list[str]:
    """设备端 singleness 守护进程行列表（ps + grep；失败返回空）。"""
    try:
        out = _shell(sn, ip, port, "ps -ef | grep singleness", timeout=8.0)
    except Exception:
        return []
    return [ln for ln in out.splitlines() if "singleness" in ln and "grep" not in ln]


def _kill_daemon_pids(sn: str, ip: str, port: str, extension: bool, name: str) -> None:
    """杀设备端残留 uitest singleness 守护进程。

    extension=True 杀带 --extension-name 的（投屏扩展），False 杀不带的
    （系统守护进程，agent 版本变更需重载时用）。清理是启动正门步骤，
    失败留痕不阻塞。
    """
    for line in _ps_singleness(sn, ip, port):
        if ("extension-name" in line) != extension:
            continue
        if extension and _EXTENSION_NAME not in line:
            continue  # 扩展进程限定是我们的扩展库（多扩展互不误杀）
        if not extension and "uitest" not in line:
            continue
        fields = line.split()
        if len(fields) < 2 or not fields[1].isdigit():
            continue
        try:
            _shell(sn, ip, port, f"kill -9 {fields[1]}", timeout=3.0)
            logger.info(f"{TAG}: [{name}] 已清理残留守护进程 pid={fields[1]} extension={extension}")
        except Exception as e:
            logger.debug(f"{TAG}: [{name}] 清理 pid={fields[1]} 失败: {e}")


def _daemon_running(sn: str, ip: str, port: str, extension: bool) -> bool:
    """对应守护进程是否已在跑（与 _kill_daemon_pids 同款过滤口径）。"""
    for line in _ps_singleness(sn, ip, port):
        if ("extension-name" in line) != extension:
            continue
        if extension and _EXTENSION_NAME not in line:
            continue
        if not extension and "uitest" not in line:
            continue
        return True
    return False


def _wakeup_screen(sn: str, ip: str, port: str, name: str = "hdc") -> None:
    """power-shell wakeup 唤屏催帧（亮屏但画面静止时编码器不出帧）。尽力而为。"""
    try:
        _shell(sn, ip, port, "power-shell wakeup", timeout=5.0)
    except Exception as e:
        logger.debug(f"{TAG}: [{name}] 唤屏失败（不阻塞起流）: {e}")


def _so_path(name: str) -> Path:
    """本地 so 资产路径；缺失时给出补齐指引。"""
    path = _SO_DIR / name
    if not path.is_file():
        raise RuntimeError(
            f"缺少 so 资产 {path}——请运行 "
            "python -m hos_scrcpy.bridge.extract_servers 从 hosScrcpy jar 重新提取"
        )
    return path


# ---- video channel ----

class HosVideoStream:
    """H.264 视频流客户端：守护进程起停 + fport + gRPC onStart 收流。

    生命周期：start()（阻塞，失败抛错）→ read_chunk() 循环取流 →
    request_idr() 探活/催帧 → stop() 收口（cancel 流 + fport rm + 杀扩展
    守护进程）。线程模型：gRPC 迭代在独立接收线程，块经有界队列交付
    （队满丢最旧，防解码端卡顿反压 gRPC 线程）。
    """

    _QUEUE_SIZE = 240  # 约 12s@20fps 的缓冲上限

    def __init__(self, sn: str, ip: str = "127.0.0.1", port: str = "8710", name: str = "hdc"):
        self._sn = sn
        self._ip = ip
        self._port = port
        self._name = name
        self._local_port = 0
        self._channel = None
        self._stub = None
        self._call = None  # onStart 服务端流调用（可 cancel）
        self._queue: Queue[bytes] = Queue(maxsize=self._QUEUE_SIZE)
        self._recv_thread: threading.Thread | None = None
        self._stopped = threading.Event()
        self._recv_error = ""  # 接收线程的死亡原因（看门狗诊断用）
        self._new_ui = False  # uitest > 6.0.2.1：fport 目标走 localabstract
        # 首块就绪信号（接收线程置位；起流等待用，不动队列本身）
        self.first_chunk_event = threading.Event()

    # ── 启动（阻塞；错误路径显式抛错）──

    def start(self) -> None:
        uitest = _uitest_version(self._sn, self._ip, self._port)
        if not uitest:
            raise RuntimeError(
                f"无法获取设备 uitest 版本（sn={self._sn}）——"
                "请确认设备已连接、开发者选项已开启"
            )
        self._new_ui = version_cmp(uitest, (6, 0, 2, 1)) > 0
        self._stopped.clear()
        self._local_port = _alloc_local_port()

        # 1. 扩展库 md5 核对推送（不一致才推；推送失败=起流必败，显式抛错）。
        #    守护进程固定重起（带当前流参数）：md5 一致也重起，保证参数确定性
        so_path = _so_path(_VIDEO_SO_FILE)
        need_push = _device_md5(
            self._sn, self._ip, self._port, _VIDEO_SO_REMOTE, self._name
        ) != _local_md5(so_path)
        _kill_daemon_pids(self._sn, self._ip, self._port, extension=True, name=self._name)
        if need_push:
            try:
                _exec(self._sn, self._ip, self._port,
                      ["file", "send", str(so_path), _VIDEO_SO_REMOTE], timeout=20.0)
                logger.info(f"{TAG}: [{self._name}] 已推送投屏扩展库 {so_path.name} → {_VIDEO_SO_REMOTE}")
            except Exception as e:
                raise RuntimeError(f"推送投屏扩展库失败: {e}") from e

        # 2. 起扩展守护进程
        params = (
            f"-scale {STREAM_SCALE} -frameRate {STREAM_FRAME_RATE} "
            f"-bitRate {STREAM_BIT_RATE} -p {_VIDEO_DAEMON_PORT} "
            f"-iFrameInterval {STREAM_IFRAME_INTERVAL_MS} "
            f"-repeatInterval {STREAM_REPEAT_INTERVAL}"
        )
        start_cmd = (
            "/system/bin/uitest start-daemon singleness "
            f"--extension-name {_EXTENSION_NAME} {params} &"
        )
        try:
            _shell(self._sn, self._ip, self._port, start_cmd, timeout=5.0)
        except Exception as e:
            raise RuntimeError(f"启动设备端投屏守护进程失败: {e}") from e
        time.sleep(1.0)  # 守护进程就绪窗口（SDK 同款 1s 等待）

        # 3. fport 转发（新系统 localabstract / 老系统 tcp:5000）
        fwd_target = ("localabstract:scrcpy_grpc_socket" if self._new_ui
                      else f"tcp:{_VIDEO_DAEMON_PORT}")
        try:
            _exec(self._sn, self._ip, self._port,
                  ["fport", f"tcp:{self._local_port}", fwd_target], timeout=5.0)
        except Exception as e:
            raise RuntimeError(f"hdc fport 建立视频转发失败 ({fwd_target}): {e}") from e

        # 4. gRPC 连接（连接失败显式报错，不静默重试）
        try:
            self._channel = grpc.insecure_channel(
                f"127.0.0.1:{self._local_port}",
                options=[("grpc.max_receive_message_length", 104_857_600)],
            )
            grpc.channel_ready_future(self._channel).result(timeout=_CONNECT_TIMEOUT)
            self._stub = scrcpy_pb2_grpc.ScrcpyServiceStub(self._channel)
            self._call = self._stub.onStart(scrcpy_pb2.Empty())
        except Exception as e:
            self._cleanup_forward()
            raise RuntimeError(
                f"视频流通道建立失败（grpc → 127.0.0.1:{self._local_port}）: {e}"
            ) from e

        # 5. 接收线程起流
        self._recv_thread = threading.Thread(
            target=self._recv_loop, daemon=True, name=f"{self._name}-grpc-recv"
        )
        self._recv_thread.start()

    def _recv_loop(self) -> None:
        """gRPC 服务端流迭代：payload["data"].val_bytes → 队列。

        流断开/异常：记录死因退出线程（read_chunk 超时后由上层看门狗接管，
        本层不自动重连）。
        """
        call = self._call
        try:
            for msg in call:
                if self._stopped.is_set():
                    return
                pv = msg.payload.get("data")
                if pv is None or not pv.val_bytes:
                    continue
                self.first_chunk_event.set()
                try:
                    self._queue.put_nowait(pv.val_bytes)
                except Full:
                    # 解码端积压：丢最旧一块腾位（实时流保新弃旧）
                    try:
                        self._queue.get_nowait()
                        self._queue.put_nowait(pv.val_bytes)
                    except Exception:
                        pass
        except Exception as e:
            if not self._stopped.is_set():
                self._recv_error = str(e)
                logger.error(f"{TAG}: [{self._name}] 视频流接收线程退出: {e}")

    # ── 取流 / 探活 ──

    def read_chunk(self, timeout: float = 0.5) -> bytes | None:
        """取一段 H.264 数据（无数据/超时返回 None；stop 后恒 None）。"""
        if self._stopped.is_set():
            return None
        try:
            return self._queue.get(timeout=timeout)
        except Exception:
            return None

    def request_idr(self, timeout: float = _RPC_TIMEOUT) -> None:
        """强制编码器立即出 IDR 帧（催首帧/停滞探活；失败抛错=链路死证据）。"""
        if self._stub is None:
            raise RuntimeError("视频通道未启动")
        self._stub.onRequestIDRFrame(scrcpy_pb2.Empty(), timeout=timeout)

    @property
    def alive(self) -> bool:
        """接收线程活着且无死亡记录（看门狗的 alive 口径）。"""
        t = self._recv_thread
        return (not self._stopped.is_set() and self._recv_error == ""
                and t is not None and t.is_alive())

    # ── 停止 ──

    def stop(self) -> None:
        """收口：cancel 流 → 关 channel → fport rm → 杀扩展守护进程。"""
        self._stopped.set()
        call, self._call = self._call, None
        if call is not None:
            try:
                call.cancel()
            except Exception:
                pass
        channel, self._channel = self._channel, None
        self._stub = None
        if channel is not None:
            try:
                channel.close()
            except Exception:
                pass
        t, self._recv_thread = self._recv_thread, None
        if t is not None and t.is_alive():
            t.join(timeout=2.0)
        self._cleanup_forward()
        _kill_daemon_pids(self._sn, self._ip, self._port, extension=True, name=self._name)

    def _cleanup_forward(self) -> None:
        """fport 规则清理（停止正门步骤，失败留痕不阻塞）。"""
        if not self._local_port:
            return
        fwd_target = ("localabstract:scrcpy_grpc_socket" if self._new_ui
                      else f"tcp:{_VIDEO_DAEMON_PORT}")
        try:
            _exec(self._sn, self._ip, self._port,
                  ["fport", "rm", f"tcp:{self._local_port}", fwd_target], timeout=3.0)
        except Exception as e:
            logger.debug(f"{TAG}: [{self._name}] fport rm 视频转发（正常收尾）: {e}")


# ---- touch channel ----

class HosTouchChannel:
    """触控注入客户端：agent so 管理 + 系统 uitest 守护进程 + JSON 持久 socket。

    消息格式（compact JSON 无换行）：
      {"module":"com.ohos.devicetest.hypiumApiHelper","method":"Gestures",
       "params":{"api":"touchDown","args":{"x":100,"y":200}}}
    写后守护进程会回 JSON（异常时带 "exception" 键）——由后台排空线程持续
    读掉（不读会积压撑爆缓冲），异常键留痕。
    """

    _MODULE = "com.ohos.devicetest.hypiumApiHelper"

    def __init__(self, sn: str, ip: str = "127.0.0.1", port: str = "8710", name: str = "hdc"):
        self._sn = sn
        self._ip = ip
        self._port = port
        self._name = name
        self._local_port = 0
        self._sock: socket.socket | None = None
        self._drain_thread: threading.Thread | None = None
        self._stopped = threading.Event()
        self._send_lock = threading.Lock()
        self._new_ui = False  # agent >= 1.2.0：fport 走 localabstract
        self._healthy = False

    # ── agent so 版本映射 ─────────────────────────────────────────

    def _select_agent_so(self, uitest: tuple[int, ...]) -> str:
        """uitest 版本 → agent so 资源名。越新的系统用越新的通道：
        >6.0.2.1 配 1.2.3（走 abstract socket），5.1.1.3~6.0.2.1 配
        1.1.12（tcp:8012），≤5.1.1.2 配老 1.1.3/1.1.5。

        注意与视频通道的 _new_ui 判据同源但独立：视频按 uitest>6.0.2.1 走
        localabstract，触控按 agent≥1.2.0（即 1.2.3 那条线）走 localabstract。
        """
        try:
            file_out = _shell(self._sn, self._ip, self._port,
                              "file /system/bin/uitest", timeout=5.0)
        except Exception:
            file_out = ""
        if "x86_64" in file_out:
            return "uitest_agent_x86_1.1.12.so"
        if version_cmp((5, 1, 1, 2), uitest) >= 0:      # uitest ≤ 5.1.1.2
            return "uitest_agent_1.1.3.so"
        if uitest == (5, 1, 1, 3):
            return "uitest_agent_1.1.5.so"
        if version_cmp((6, 0, 2, 1), uitest) >= 0:      # 5.1.1.3 < uitest ≤ 6.0.2.1
            return "uitest_agent_1.1.12.so"
        return "uitest_agent_1.2.3.so"                  # uitest > 6.0.2.1

    def _device_agent_version(self) -> tuple[int, ...]:
        """设备端 agent.so 内嵌版本标记（'#' 后面的 x.y.z）。

        实测格式 UITEST_AGENT_LIBRARY@v0.0.0#1.2.3——标记与 '#' 之间还有一段
        @v0.0.0 基线串，若取整行第一个 x.y.z 会把基线 0.0.0 误当版本，
        导致 fport 转错目标（tcp:8012）触控连上即断。
        """
        try:
            out = _shell(
                self._sn, self._ip, self._port,
                f"cat {_AGENT_SO_REMOTE} | grep -a {_AGENT_VERSION_TAG}",
                timeout=5.0,
            )
        except Exception:
            return ()
        # 版本在 '#' 之后；量词段用拼接而非 f-string——f-string 会把 {1,3}
        # 当替换字段吃掉
        m = re.search(_AGENT_VERSION_TAG + r"[^#]*#(\d+(?:\.\d+){1,3})", out)
        return parse_version(m.group(1)) if m else ()

    def _ensure_agent(self, so_name: str) -> None:
        """agent so 版本核对推送：本地更新 / 次版本不同 → 重推。

        次版本不同时守护进程已加载旧库，先杀再推（守护进程占着旧库，
        rm 会失败）。
        """
        local_path = _so_path(so_name)
        # 文件名内嵌版本（uitest_agent_1.1.12.so → (1,1,12)）
        stem = so_name[: so_name.rfind(".")]
        local_ver = parse_version(stem[stem.rfind("_") + 1:])
        if not local_ver:
            raise RuntimeError(f"agent so 文件名无版本段: {so_name}")
        device_ver = self._device_agent_version()
        minor_differs = bool(device_ver) and local_ver[:2] != device_ver[:2]
        need_push = (not device_ver
                     or version_cmp(local_ver, device_ver) > 0
                     or minor_differs)
        if not need_push:
            return
        logger.info(f"{TAG}: [{self._name}] agent 需更新: 本地 {local_ver} vs 设备 {device_ver or '无'}")
        if minor_differs:
            _kill_daemon_pids(self._sn, self._ip, self._port, extension=False, name=self._name)
        try:
            _shell(self._sn, self._ip, self._port, f"rm -f {_AGENT_SO_REMOTE}", timeout=3.0)
        except Exception as e:
            raise RuntimeError(f"清理旧 agent.so 失败: {e}") from e
        try:
            _exec(self._sn, self._ip, self._port,
                  ["file", "send", str(local_path), _AGENT_SO_REMOTE], timeout=15.0)
        except Exception as e:
            raise RuntimeError(f"推送 agent so 失败: {e}") from e
        logger.info(f"{TAG}: [{self._name}] agent so 已更新 → {so_name}")

    # ── 启动（阻塞；错误路径显式抛错）──

    def start(self) -> None:
        uitest = _uitest_version(self._sn, self._ip, self._port)
        if not uitest:
            raise RuntimeError(
                f"无法获取设备 uitest 版本（sn={self._sn}）——"
                "请确认设备已连接、开发者选项已开启"
            )
        self._stopped.clear()
        self._ensure_agent(self._select_agent_so(uitest))
        # 确保系统守护进程在跑（不带 extension 的 singleness；已在跑则复用）
        if not _daemon_running(self._sn, self._ip, self._port, extension=False):
            try:
                _shell(self._sn, self._ip, self._port,
                       "/system/bin/uitest start-daemon singleness &", timeout=5.0)
                time.sleep(1.0)  # 守护进程就绪窗口
            except Exception as e:
                raise RuntimeError(f"启动系统 uitest 守护进程失败: {e}") from e

        # fport：agent >= 1.2.0 → localabstract:uitest_socket；老版 tcp:8012
        agent_ver = self._device_agent_version()
        if not agent_ver:
            raise RuntimeError("无法读取设备端 agent.so 版本标记（推送后应存在）")
        self._new_ui = version_cmp(agent_ver, (1, 2, 0)) >= 0
        self._local_port = _alloc_local_port()
        fwd_target = "localabstract:uitest_socket" if self._new_ui else "tcp:8012"
        try:
            _exec(self._sn, self._ip, self._port,
                  ["fport", f"tcp:{self._local_port}", fwd_target], timeout=5.0)
        except Exception as e:
            raise RuntimeError(f"hdc fport 建立触控转发失败 ({fwd_target}): {e}") from e
        try:
            self._sock = socket.create_connection(("127.0.0.1", self._local_port), timeout=5)
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception as e:
            self._cleanup_forward()
            raise RuntimeError(
                f"触控通道连接失败（127.0.0.1:{self._local_port} → {fwd_target}）: {e}"
            ) from e

        self._healthy = True
        self._drain_thread = threading.Thread(
            target=self._drain_loop, daemon=True, name=f"{self._name}-touch-drain"
        )
        self._drain_thread.start()

    def _drain_loop(self) -> None:
        """持续排空守护进程回复（带 exception 键的留痕）。"""
        while not self._stopped.is_set():
            sock = self._sock
            if sock is None:
                return
            try:
                sock.settimeout(2.0)
                data = sock.recv(65536)
                if not data:
                    # 对端关闭 = 守护进程死了（随流重启恢复）
                    self._healthy = False
                    logger.warning(f"{TAG}: [{self._name}] 触控通道对端关闭")
                    return
                text = data.decode("utf-8", errors="replace")
                if "exception" in text:
                    logger.warning(f"{TAG}: [{self._name}] 触控通道回复异常: {text[:300]}")
            except socket.timeout:
                continue  # 2s 无回复是常态（只在有事件时回）
            except OSError:
                if not self._stopped.is_set():
                    self._healthy = False
                return

    # ── 发送 ──

    def send_touch(self, api: str, x: int, y: int) -> None:
        """发一条 Gestures 事件（api: touchDown/touchMove/touchUp）。

        写失败留痕并标记不健康（上层看门狗接管重启，本层不重连）。
        """
        msg = json.dumps({
            "module": self._MODULE,
            "method": "Gestures",
            "params": {"api": api, "args": {"x": int(x), "y": int(y)}},
        }, separators=(",", ":"))
        with self._send_lock:
            sock = self._sock
            if sock is None:
                return
            try:
                sock.sendall(msg.encode("utf-8"))
            except OSError as e:
                self._healthy = False
                logger.error(f"{TAG}: [{self._name}] 触控发送失败（通道已断）: {e}")

    @property
    def healthy(self) -> bool:
        return self._healthy

    # ── 停止 ──

    def stop(self) -> None:
        """收口：关 socket → fport rm。系统守护进程留着（dumpLayout 同源共用）。"""
        self._stopped.set()
        self._healthy = False
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        t, self._drain_thread = self._drain_thread, None
        if t is not None and t.is_alive():
            t.join(timeout=2.0)
        self._cleanup_forward()

    def _cleanup_forward(self) -> None:
        if not self._local_port:
            return
        fwd_target = "localabstract:uitest_socket" if self._new_ui else "tcp:8012"
        try:
            _exec(self._sn, self._ip, self._port,
                  ["fport", "rm", f"tcp:{self._local_port}", fwd_target], timeout=3.0)
        except Exception as e:
            logger.debug(f"{TAG}: [{self._name}] fport rm 触控转发（正常收尾）: {e}")


# ---- bridge facade (StreamBridge-compatible contract) ----

class HosStreamBridge:
    """视频 + 触控双通道门面：一次 start/stop 管理两条通道的生命周期。"""

    def __init__(self, sn: str, ip: str = "127.0.0.1", port: str = "8710"):
        self.video = HosVideoStream(sn, ip, port, name=f"hdc-{sn}")
        self.touch = HosTouchChannel(sn, ip, port, name=f"hdc-{sn}")

    def start(self, wait_first_chunk: bool = True) -> None:
        """阻塞启动。失败抛 RuntimeError（内部已收口，无需调用方清理）。"""
        self.touch.start()
        try:
            self.video.start()
            if wait_first_chunk:
                self._wait_first_chunk()
        except Exception:
            self.stop()
            raise

    def _wait_first_chunk(self, timeout: float = FIRST_CHUNK_TIMEOUT) -> None:
        """唤屏 + IDR 催帧，等首块数据（锁屏/静止画面编码器不出帧）。"""
        _wakeup_screen(self.video._sn, self.video._ip, self.video._port, self.video._name)
        deadline = time.monotonic() + timeout
        while not self.video.first_chunk_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"{timeout:.0f}s 内未收到视频首块（唤屏/IDR 催帧无效）——"
                    "设备可能锁屏或投屏扩展不可用"
                )
            try:
                self.video.request_idr(timeout=2.0)
            except Exception as e:
                logger.debug(f"{TAG}: 首块等待期 IDR 催帧失败: {e}")
            self.video.first_chunk_event.wait(timeout=3.0)

    def probe_stall(self) -> None:
        """停滞探活：IDR 催帧 + 唤屏（read_frames 看门狗调用）。"""
        try:
            self.video.request_idr(timeout=2.0)
        except Exception as e:
            logger.debug(f"{TAG}: IDR 探活失败: {e}")
        _wakeup_screen(self.video._sn, self.video._ip, self.video._port, self.video._name)

    def stop(self) -> None:
        """收口两条通道（幂等，未启动的通道安全跳过）。"""
        self.video.stop()
        self.touch.stop()


# ---- legacy-compatible module API (used by ScreenCapture) ----

def start_native_bridge(sn: str, ip: str = "127.0.0.1", port: str = "8710",
                        wait_ready: bool = True, ready_timeout: float = 35.0,
                        raw_mode: bool = True):
    """Start the pure-Python stream bridge. Returns HosStreamBridge or None.

    Legacy signature kept from the Java era. ``raw_mode`` no longer changes
    the wire protocol — the gRPC channel always delivers raw H.264 chunks;
    JPEG transcoding (when needed) is the caller's job. ``wait_ready`` keeps
    its meaning: block until the first video chunk arrives (capped at
    FIRST_CHUNK_TIMEOUT); pass False to return right after channel setup.
    """
    t_total = time.monotonic()
    bridge = HosStreamBridge(sn, ip, port)
    try:
        bridge.start(wait_first_chunk=wait_ready)
    except Exception as ex:
        logger.error(f"{TAG}: bridge start failed for {sn}: {ex}")
        try:
            bridge.stop()
        except Exception:
            pass
        return None
    logger.info(f"{TAG}: stream bridge ready for {sn} "
                f"({(time.monotonic() - t_total) * 1000:.0f}ms)")
    return bridge


def read_frames(bridge: HosStreamBridge, stop_event: threading.Event = None):
    """Yield raw H.264 chunks from the bridge's video channel.

    Watchdog built in: after 5s without a chunk, probe with an IDR request
    plus a screen wakeup (keeps the device awake too); after 60s of total
    silence the generator exits (consumers handle stream end as before).
    """
    video = bridge.video
    last_chunk = time.monotonic()
    last_probe = last_chunk
    while video.alive:
        if stop_event is not None and stop_event.is_set():
            return
        chunk = video.read_chunk(timeout=0.5)
        if chunk:
            last_chunk = time.monotonic()
            yield chunk
            continue
        now = time.monotonic()
        if now - last_chunk >= STALL_PROBE_INTERVAL and now - last_probe >= STALL_PROBE_INTERVAL:
            last_probe = now
            logger.info(f"{TAG}: video stalled {now - last_chunk:.0f}s, probing (IDR + wakeup)")
            bridge.probe_stall()
        if now - last_chunk >= _STALL_DEATH_TIMEOUT:
            logger.error(f"{TAG}: video stalled {_STALL_DEATH_TIMEOUT:.0f}s, ending stream")
            return
