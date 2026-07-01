"""纯 Python 鸿蒙投屏驱动 — 通过 socket 直连 uitest 服务。

原理：
1. hdc 端口转发 → 本地 socket 连接到设备 uitest 服务
2. JSON 协议通信（非 gRPC，无 4s 超时问题）
3. 启动前强制重启设备端 uitest 服务
4. 从 socket 读取 JPEG 流
"""

import os, time, socket, json, typing, struct, hashlib
from hos_scrcpy.utils.logger import logger
from hos_scrcpy.core.hdc_client import HdcClient

TAG = "PyDriver"
UITEST_PORT = 8012
SOCKET_TIMEOUT = 30


class PyHmDriver:
    """纯 Python 鸿蒙驱动 — 通过 socket 直连 uitest。"""

    def __init__(self, sn: str, ip: str = "127.0.0.1", hdc_port: str = "8710"):
        self._sn = sn
        self._ip = ip
        self._hdc = HdcClient(ip, hdc_port)
        self._sock: socket.socket | None = None
        self._local_port: int | None = None
        self._driver_created = False

    # ── 端口转发 ────────────────────────────────────────────────────

    def _setup_forward(self) -> int:
        """建立 hdc 端口转发，返回本地端口号。"""
        # 查找空闲端口
        import random
        port = random.randint(20000, 30000)
        result = self._hdc.server_execute(
            f"tmode port {self._hdc.port}", timeout=5)
        if result:
            logger.debug(f"{TAG}: tmode port ok")

        # 建立转发
        result = self._hdc.execute(
            self._sn,
            f"fport tcp:{port} tcp:{UITEST_PORT}",
            timeout=5,
        )
        if result:
            logger.debug(f"{TAG}: fport {port} -> {UITEST_PORT}")
        else:
            # 可能已存在，尝试已有端口
            logger.warning(f"{TAG}: fport might already exist")
        self._local_port = port
        return port

    def _remove_forward(self):
        """删除端口转发。"""
        if self._local_port:
            try:
                self._hdc.execute(
                    self._sn,
                    f"fport rm tcp:{self._local_port} tcp:{UITEST_PORT}",
                    timeout=3,
                )
            except Exception as e:
                logger.debug(f"{TAG}: rm fport: {e}")

    # ── Socket 通信 ─────────────────────────────────────────────────

    def _connect_socket(self):
        """连接本地转发端口到设备 uitest 服务。"""
        if self._local_port is None:
            self._setup_forward()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(SOCKET_TIMEOUT)
        self._sock.connect(("127.0.0.1", self._local_port))
        logger.info(f"{TAG}: socket connected to port {self._local_port}")

    def _send_json(self, msg: dict):
        """发送 JSON 消息到设备。"""
        data = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
        logger.debug(f"{TAG} >> {data[:200]}")
        self._sock.sendall(data.encode("utf-8") + b"\n")

    def _recv_json(self) -> dict:
        """从设备接收 JSON 响应。"""
        buf = bytearray()
        while True:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                logger.warning(f"{TAG}: socket recv timeout")
                return {}
            if not chunk:
                break
            buf.extend(chunk)
            try:
                return json.loads(buf.decode("utf-8"))
            except json.JSONDecodeError:
                continue  # 数据不完整，继续接收
        return {}

    # ── 调用设备 API ─────────────────────────────────────────────────

    def _invoke(self, api: str, this: str = "Driver#0", args: list = None) -> dict:
        """调用 Hypium API。"""
        from datetime import datetime
        args = args or []
        msg = {
            "module": "com.ohos.devicetest.hypiumApiHelper",
            "method": "callHypiumApi",
            "params": {
                "api": api,
                "this": this,
                "args": args,
                "message_type": "hypium",
            },
            "request_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        }
        self._send_json(msg)
        resp = self._recv_json()
        if resp.get("exception"):
            raise Exception(f"Hypium error: {resp['exception']}")
        return resp

    def _invoke_captures(self, api: str, args: list = None) -> dict:
        """调用屏幕捕获 API（返回 JPEG 帧）。"""
        from datetime import datetime
        args = args or []
        msg = {
            "module": "com.ohos.devicetest.hypiumApiHelper",
            "method": "Captures",
            "params": {"api": api, "args": args},
            "request_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        }
        self._send_json(msg)
        resp = self._recv_json()
        if resp.get("exception"):
            raise Exception(f"Capture error: {resp['exception']}")
        return resp

    # ── 生命周期 ─────────────────────────────────────────────────────

    def start(self):
        """启动驱动：重启 uitest → 端口转发 → socket 连接 → 创建 driver。"""
        logger.info(f"{TAG}: starting for {self._sn}")
        self._restart_uitest()
        self._setup_forward()
        self._connect_socket()
        self._create_driver()

    def stop(self):
        """停止驱动，清理资源。"""
        logger.info(f"{TAG}: stopping")
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._remove_forward()

    def _create_driver(self):
        """创建设备驱动实例。"""
        resp = self._invoke("Driver.create")
        logger.info(f"{TAG}: driver created: {resp.get('result')}")
        self._driver_created = True

    # ── 截屏 ─────────────────────────────────────────────────────────

    def start_capture(self):
        """启动屏幕截取，返回 JPEG 帧生成器。"""
        # 启动截取
        self._invoke_captures("startCaptureScreen", [])
        logger.info(f"{TAG}: capture started, reading frames...")

        # 读取 JPEG 帧
        JPEG_START = b"\xff\xd8"
        JPEG_END = b"\xff\xd9"
        buf = bytearray()

        while self._sock and self._driver_created:
            try:
                chunk = self._sock.recv(65536)
            except socket.timeout:
                logger.warning(f"{TAG}: capture read timeout")
                continue
            except Exception:
                break
            if not chunk:
                break

            buf.extend(chunk)
            # 从缓冲区提取 JPEG 帧
            start = buf.find(JPEG_START)
            end = buf.find(JPEG_END)
            while start != -1 and end != -1 and end > start:
                jpeg = bytes(buf[start : end + 2])
                buf = buf[end + 2 :]
                yield jpeg
                start = buf.find(JPEG_START)
                end = buf.find(JPEG_END)

    # ── 触摸 ─────────────────────────────────────────────────────────

    def touch_down(self, x: int, y: int):
        """触摸按下。"""
        self._invoke("Touch.down", args=[x, y])

    def touch_up(self, x: int, y: int):
        """触摸抬起。"""
        self._invoke("Touch.up", args=[x, y])

    def touch_move(self, x: int, y: int):
        """触摸移动。"""
        self._invoke("Touch.move", args=[x, y])

    # ── uitest 重启 ──────────────────────────────────────────────────

    def _restart_uitest(self):
        """强制重启设备端 uitest 服务。"""
        logger.info(f"{TAG}: restarting uitest on device")
        try:
            # 获取所有 uitest 进程
            output = self._hdc.shell(self._sn, "ps -ef", timeout=5)
            if not output:
                # 没有输出也可能是没有进程
                pass
            for line in output.splitlines():
                if "uitest" in line and "singleness" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        pid = parts[1]
                        self._hdc.shell(self._sn, f"kill -9 {pid}", timeout=3)
                        logger.debug(f"{TAG}: killed uitest pid {pid}")

            # 启动新的 uitest
            self._hdc.shell(self._sn, "uitest start-daemon singleness", timeout=5)
            time.sleep(1)
            logger.info(f"{TAG}: uitest restarted")
        except Exception as e:
            logger.error(f"{TAG}: restart uitest error: {e}")
