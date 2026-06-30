"""ScreenCapture — device screen capture with polling and streaming modes.

Supports three modes:
1. Screenshot polling (pure Python): periodically calls snapshot_display + file recv.
2. Native H.264 stream (hdc screenrecord, needs PyAV): pipes raw H.264 via hdc shell.
3. Java StreamBridge (IMAGE mode): low-latency JPEG frames via Java subprocess + touch relay.

Usage:
    cap = ScreenCapture(device)
    cap.start_java_stream(on_frame=lambda jpeg_bytes: ...)
    cap.stop()
"""

import subprocess
import threading
import time
from hos_scrcpy.core.device import Device
from hos_scrcpy.utils.logger import logger

TAG = "ScreenCapture"


class ScreenCapture:
    """Control device screen capture."""

    def __init__(self, device: Device):
        self._device = device
        self._running = False
        self._thread: threading.Thread | None = None

    # ---- screenshot polling mode ----

    def start_screenshot_stream(self, on_frame, interval: float = 0.5) -> None:
        """Start capturing screenshots at a fixed interval.

        Args:
            on_frame: Callable(jpeg_bytes) called with each JPEG frame.
            interval: Seconds between captures (default 0.5 = 2 fps).
        """
        if self._running:
            self.stop()
        self._running = True
        self._thread = threading.Thread(
            target=self._screenshot_loop,
            args=(on_frame, interval),
            daemon=True,
        )
        self._thread.start()
        logger.info(f"{TAG}: screenshot stream started interval={interval:.2f}s")

    def _screenshot_loop(self, on_frame, interval: float):
        while self._running:
            start = time.monotonic()
            try:
                data = self._device.screenshot()
                if data and self._running:
                    on_frame(data)
            except Exception as ex:
                logger.error(f"{TAG}: screenshot error: {ex}")
            elapsed = time.monotonic() - start
            time.sleep(max(0.05, interval - elapsed))

    # ---- native H.264 stream mode (screenrecord) ----

    def start_native_stream(self, on_frame, on_error=None, on_ready=None) -> None:
        """Start native H.264 video stream via hdc screenrecord.

        Requires: PyAV (`pip install av`) for H.264 decoding.
        Falls back to screenshot polling if screenrecord is unavailable.
        """
        if self._running:
            self.stop()

        self._running = True
        self._thread = threading.Thread(
            target=self._native_loop,
            args=(on_frame, on_error, on_ready),
            daemon=True,
        )
        self._thread.start()

    def _native_loop(self, on_frame, on_error, on_ready):
        cmd = (
            f'hdc -s {self._device.ip}:{self._device.port} '
            f'-t {self._device.sn} '
            f'shell "screenrecord --output-format=h264 -"'
        )

        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as ex:
            logger.error(f"{TAG}: failed to start screenrecord: {ex}")
            if on_error:
                on_error(f"screenrecord failed: {ex}")
            self._fallback_to_screenshots(on_frame, on_error, on_ready)
            return

        # Check stderr for errors — use thread for cross-platform compatibility
        err_lines = []
        def _read_stderr():
            try:
                line = proc.stderr.readline()
                if line:
                    err_lines.append(line.decode("utf-8", errors="replace").strip())
            except Exception:
                pass
        stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        stderr_thread.start()
        stderr_thread.join(timeout=3)

        if err_lines and "error" in err_lines[0].lower():
            logger.warning(f"{TAG}: screenrecord stderr: {err_lines[0]}")
            proc.kill()
            if on_error:
                on_error(f"screenrecord: {err_lines[0]}")
            self._fallback_to_screenshots(on_frame, on_error, on_ready)
            return

        logger.info(f"{TAG}: native H.264 stream started")
        if on_ready:
            try:
                on_ready()
            except Exception:
                pass

        try:
            self._decode_h264_stream(proc, on_frame)
        except Exception as ex:
            logger.error(f"{TAG}: H.264 decode error: {ex}")
            if on_error:
                on_error(str(ex))
        finally:
            proc.kill()
            proc.wait()

    def _decode_h264_stream(self, proc, on_frame):
        try:
            import av
        except ImportError:
            logger.warning(f"{TAG}: PyAV not installed, falling back to screenshots")
            proc.kill()
            raise RuntimeError("PyAV required for native stream: pip install av")

        codec = av.CodecContext.create("h264", "r")
        buf = b""

        while self._running and proc.poll() is None:
            try:
                chunk = proc.stdout.read(8192)
                if not chunk:
                    time.sleep(0.01)
                    continue
            except Exception:
                break

            buf += chunk

            # Guard against runaway buffer
            if len(buf) > 10_000_000:
                buf = buf[-1_000_000:]

            while True:
                idx = buf.find(b"\x00\x00\x00\x01")
                if idx < 0:
                    idx = buf.find(b"\x00\x00\x01")
                if idx < 0:
                    break

                if idx > 0:
                    nal = buf[:idx]
                    buf = buf[idx:]
                    self._try_decode_nal(codec, nal, on_frame)

                next_idx = buf.find(b"\x00\x00\x00\x01", 4)
                if next_idx < 0:
                    next_idx = buf.find(b"\x00\x00\x01", 4)
                if next_idx < 0:
                    break

                nal = buf[:next_idx]
                buf = buf[next_idx:]
                self._try_decode_nal(codec, nal, on_frame)

    def _try_decode_nal(self, codec, nal_data, on_frame):
        try:
            packets = codec.parse(nal_data)
            for packet in packets:
                frames = codec.decode(packet)
                for frame in frames:
                    img = frame.to_image()
                    import io
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    jpeg = buf.getvalue()
                    if self._running:
                        on_frame(jpeg)
        except Exception:
            pass

    def _fallback_to_screenshots(self, on_frame, on_error, on_ready):
        if not self._running:
            return
        logger.info(f"{TAG}: falling back to screenshot polling mode")
        if on_error:
            on_error("screenrecord unavailable, using screenshot polling (~2 fps)")
        if on_ready:
            on_ready()
        self._screenshot_loop(on_frame, interval=0.5)

    # ---- Java StreamBridge mode ----

    def start_java_stream(self, on_frame, wait_ready: bool = False):
        """Start low-latency JPEG stream via Java StreamBridge subprocess.

        Launches StreamBridge.java which connects to the device via the
        hdc SDK, captures JPEG frames, and relays touch commands via stdin.

        Args:
            on_frame: Callback(jpeg_bytes) for each frame.
            wait_ready: If True, blocks until Java READY signal (up to 35s).
                        Set False for GUI (touch must work immediately).

        Returns a FastTouchController for touch injection, or None on failure.
        """
        from hos_scrcpy.bridge.native_stream import start_native_bridge, read_jpeg_frames
        from hos_scrcpy.input.fast_touch import FastTouchController

        if self._running:
            self.stop()

        self._running = True
        result = start_native_bridge(
            self._device.sn, self._device.ip, self._device.port,
            wait_ready=wait_ready,
        )

        if result is None:
            self._running = False
            return None

        output_proc, java_proc = result
        touch = FastTouchController(java_proc)

        def _stream_loop():
            try:
                for jpeg in read_jpeg_frames(output_proc):
                    if not self._running:
                        break
                    on_frame(jpeg)
            except Exception as ex:
                logger.error(f"{TAG}: java stream error: {ex}")
            finally:
                try:
                    java_proc.kill()
                except Exception:
                    pass

        self._thread = threading.Thread(target=_stream_loop, daemon=True)
        self._thread.start()
        return touch

    # ---- lifecycle ----

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
            self._thread = None
        logger.info(f"{TAG}: capture stopped")

    @property
    def is_streaming(self) -> bool:
        return self._running

    def __del__(self):
        try:
            self._running = False
        except Exception:
            pass
