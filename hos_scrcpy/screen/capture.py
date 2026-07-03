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
        self._proc = None
        self._stop_event: threading.Event = threading.Event()
        self._stop_event: threading.Event = threading.Event()
        self._stream_gen: int = 0  # generation counter to prevent stale-thread cleanup races
    # ---- screenshot polling mode ----

    def start_screenshot_stream(self, on_frame, interval: float = 0.5) -> None:
        """Start capturing screenshots at a fixed interval.

        Args:
            on_frame: Callable(jpeg_bytes) called with each JPEG frame.
            interval: Seconds between captures (default 0.5 = 2 fps).
        """
        if self._running:
            self.stop()
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._screenshot_loop,
            args=(on_frame, interval),
            daemon=True,
        )
        self._thread.start()
        logger.info(f"{TAG}: screenshot stream started interval={interval:.2f}s")

    def _screenshot_loop(self, on_frame, interval: float):
        failures = 0
        backoff = 1.0
        while self._running and not self._stop_event.is_set():
            start = time.monotonic()
            try:
                data = self._device.screenshot()
                if data and self._running:
                    on_frame(data)
                    failures = 0
                    backoff = 1.0
            except Exception as ex:
                failures += 1
                backoff = min(backoff * 2, 30.0)  # exponential backoff cap at 30s
                logger.warning(f"{TAG}: screenshot error (#{failures}): {ex}")
                if failures >= 10:
                    logger.error(f"{TAG}: {failures} consecutive failures, stopping")
                    break
            elapsed = time.monotonic() - start
            sleep_time = max(backoff * 0.1, interval - elapsed)
            # Poll stop_event during sleep so we don't block shutdown
            for _ in range(int(sleep_time / 0.1)):
                if self._stop_event.is_set():
                    return
                time.sleep(0.1)

    # ---- native H.264 stream mode (screenrecord) ----

    def start_native_stream(self, on_frame, on_error=None, on_ready=None) -> None:
        """Start native H.264 video stream via hdc screenrecord.

        Requires: PyAV (`pip install av`) for H.264 decoding.
        Falls back to screenshot polling if screenrecord is unavailable.
        """
        if self._running:
            self.stop()

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._native_loop,
            args=(on_frame, on_error, on_ready),
            daemon=True,
        )
        self._thread.start()

    def _native_loop(self, on_frame, on_error, on_ready):
        import subprocess
        from hos_scrcpy.core.hdc_client import _find_hdc
        hdc = _find_hdc() or "hdc"
        args = [
            hdc, "-s", f"{self._device.ip}:{self._device.port}",
            "-t", self._device.sn,
            "shell", "screenrecord --output-format=h264 -",
        ]

        try:
            proc = subprocess.Popen(
                args,
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
        stderr_done = threading.Event()

        def _read_stderr():
            try:
                for line in proc.stderr:
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded:
                        err_lines.append(decoded)
            except Exception:
                pass
            finally:
                stderr_done.set()

        threading.Thread(target=_read_stderr, daemon=True).start()
        stderr_done.wait(timeout=3)

        if err_lines:
            # 有任何 stderr 输出都说明 screenrecord 有问题
            first_err = err_lines[0].lower()
            if "error" in first_err or "not found" in first_err or "failed" in first_err:
                logger.warning(f"{TAG}: screenrecord failed: {err_lines[0]}")
                _kill_proc_tree(proc)
                if on_error:
                    on_error(f"screenrecord: {err_lines[0]}")
                self._fallback_to_screenshots(on_frame, on_error, on_ready)
                return

        # 检查进程是否还活着（如果命令不存在，进程会立即退出）
        try:
            proc.wait(timeout=0.5)
            # 进程已退出 → screenrecord 不可用
            logger.warning(f"{TAG}: screenrecord exited immediately")
            if on_error:
                on_error("screenrecord unavailable")
            self._fallback_to_screenshots(on_frame, on_error, on_ready)
            return
        except subprocess.TimeoutExpired:
            pass  # 进程还在运行，正常

        # Store for cleanup in stop()
        self._proc = proc
        # Kill any old screenrecord process still running
        from hos_scrcpy.bridge.native_stream import _kill_proc_tree

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
            _kill_proc_tree(proc)

    def _decode_h264_stream(self, proc, on_frame):
        try:
            import av
        except ImportError:
            logger.warning(f"{TAG}: PyAV not installed, falling back to screenshots")
            _kill_proc_tree(proc)
            raise RuntimeError("PyAV required for native stream: pip install av")

        codec = av.CodecContext.create("h264", "r")
        buf = b""

        while self._running and not self._stop_event.is_set() and proc.poll() is None:
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


    def start_java_stream(self, on_frame, wait_ready: bool = False,
                          raw_mode: bool = True):
        """Start low-latency JPEG or raw H.264 stream via Java StreamBridge.

        Args:
            on_frame: Callback(frame_bytes) for each frame.
            wait_ready: If True, blocks until Java READY signal (up to 35s).
            raw_mode: If True, use --raw mode (raw H.264, requires PyAV).
                      If False, use JPEG mode (Java-side decode, no PyAV needed).

        Returns a FastTouchController for touch injection, or None on failure.
        """
        # Automatically fall back to JPEG mode if PyAV is not installed
        if raw_mode:
            try:
                import av  # noqa: F401
            except ImportError:
                logger.warning(f"{TAG}: PyAV not installed, falling back to JPEG mode")
                raw_mode = False
        from hos_scrcpy.bridge.native_stream import start_native_bridge, read_frames as read_jpeg_frames
        from hos_scrcpy.input.fast_touch import FastTouchController

        if self._running:
            self.stop()

        self._stop_event.clear()
        self._running = True
        self._stream_gen += 1  # bump generation to invalidate old threads
        my_gen = self._stream_gen

        t_start = time.monotonic()
        logger.info(f"{TAG}: start_java_stream begin sn={self._device.sn} raw_mode={raw_mode}")
        java_proc = start_native_bridge(
            self._device.sn, self._device.ip, self._device.port,
            wait_ready=wait_ready, raw_mode=raw_mode,
        )
        logger.info(f"{TAG}: start_java_stream bridge_ready took {(time.monotonic() - t_start)*1000:.0f}ms")

        if java_proc is None:
            self._running = False
            return None

        self._proc = java_proc
        touch = FastTouchController(java_proc)

        def _stream_loop():
            try:
                for jpeg in read_jpeg_frames(java_proc, stop_event=self._stop_event):
                    if not self._running or self._stop_event.is_set():
                        break
                    on_frame(jpeg)
            except Exception as ex:
                logger.error(f"{TAG}: java stream error: {ex}")
            finally:
                # Only cleanup if we are still the current generation
                if self._stream_gen == my_gen:
                    self._proc = None
                try:
                    _kill_proc_tree(java_proc)
                except Exception:
                    pass

        self._thread = threading.Thread(target=_stream_loop, daemon=True)
        self._thread.start()
        return touch

    # ---- lifecycle ----

    # ---- lifecycle ----

    def stop(self, join: bool = True) -> None:
        """Stop streaming and release resources.

        Safe to call multiple times.

        Args:
            join: If True (default), waits for the stream thread to finish.
                  Set False when called from __del__ to avoid GC deadlock.
        """
        self._running = False
        self._stop_event.set()

        # Unregister from global process list before killing
        p = self._proc
        if p:
            from hos_scrcpy.bridge.native_stream import _kill_proc_tree, _unregister_proc
            _unregister_proc(p)
            _kill_proc_tree(p)
            self._proc = None

        # Join daemon thread in normal path to ensure full cleanup
        if join and self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
            self._thread = None
        logger.info(f"{TAG}: capture stopped")
        logger.info(f"{TAG}: capture stopped")

    @property
    def is_streaming(self) -> bool:
        return self._running

    def __del__(self):
        """Finalizer - kills subprocess and cleans up resources.

        Uses stop(join=False) to avoid deadlock from GC thread.
        """
        try:
            self.stop(join=False)
        except Exception:
            pass

