#!/usr/bin/env python3
"""HOScrcpy Demo — 投屏 + 控制 + UI 层级查看。

一键体验鸿蒙设备投屏控制的全功能 GUI 演示。
无需设备时自动进入 Demo 模式（模拟手机屏幕）。

用法:
    python -m demo.app
    python -m demo.app --sn DEVICE_SN    # 直接连接指定设备
"""

import argparse
import io
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

from hos_scrcpy import HOSDevice, Device
from hos_scrcpy.screen.capture import ScreenCapture
from hos_scrcpy.input.fast_touch import FastTouchController
from hos_scrcpy.input.keyboard import KeyboardController
from hos_scrcpy.ui.selector import UIHierarchy
from hos_scrcpy.utils.logger import setup_logging

TAG = "Demo"

# ── 颜色主题 ──────────────────────────────────────────────────────────────
BG_DARK = "#1e1e1e"
BG_PANEL = "#252526"
BG_TOOLBAR = "#333333"
FG_TEXT = "#cccccc"
ACCENT = "#007acc"
ACCENT_GREEN = "#4ec9b0"
BORDER = "#444444"

# ── 假屏幕（无设备时演示用） ──────────────────────────────────────────────

def _make_demo_screen(width=420, height=780):
    """生成一张模拟的鸿蒙设置页截图供演示."""
    from PIL import ImageDraw, ImageFont
    img = Image.new("RGB", (width, height), "#f0f0f5")
    draw = ImageDraw.Draw(img)
    try:
        font_sm = ImageFont.truetype("segoeui.ttf", 14)
        font_md = ImageFont.truetype("segoeui.ttf", 18)
    except Exception:
        font_sm = font_md = ImageFont.load_default()
    # 状态栏
    draw.rectangle([0, 0, width, 48], fill="#e8e8ed")
    draw.text((12, 14), "9:41", fill="#333", font=font_sm)
    draw.text((width - 60, 14), "100%", fill="#333", font=font_sm)
    # 标题
    draw.rectangle([0, 48, width, 96], fill="#fff")
    draw.text((16, 60), "设置", fill="#000", font=font_md)
    y = 112
    for section in [
        ("网络和互联网", ["WLAN", "蓝牙", "移动网络"]),
        ("设备", ["显示与亮度", "声音", "通知", "电池"]),
        ("应用", ["应用管理", "权限管理"]),
    ]:
        draw.text((16, y), section[0], fill="#888", font=font_sm)
        y += 28
        for item in section[1]:
            draw.rectangle([0, y, width, y + 48], fill="#fff")
            draw.text((20, y + 12), item, fill="#222", font=font_sm)
            draw.line([20, y + 48, width, y + 48], fill="#eee")
            y += 48
        y += 8
    return img


# ── 投屏画布 ──────────────────────────────────────────────────────────────

class MirrorCanvas(tk.Canvas):
    """显示设备屏幕，处理鼠标→触摸坐标映射。

    优化要点:
    - JPEG draft mode: 降采样解码，避免全分辨率解码再缩小
    - NEAREST 缩放：实时视频用最近邻足够，比 LANCZOS 快 10x
    - 缓存 PhotoImage：尺寸不变时复用，减少 tk 对象创建
    """

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG_DARK, highlightthickness=0, **kw)
        self._photo: ImageTk.PhotoImage | None = None
        self._img_id: int | None = None
        self._img: Image.Image | None = None
        self._dev_w = 1080
        self._dev_h = 2340
        self._touch = None
        self._pressing = False
        self._swipe_start = None
        self._render_busy = False

        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", lambda e: self._redraw())

    def set_touch(self, touch):
        self._touch = touch

    def set_device_size(self, w, h):
        self._dev_w, self._dev_h = w, h

    def show_frame(self, img: Image.Image):
        """直接设置 PIL Image（演示模式用）。"""
        self._img = img
        self._dev_w, self._dev_h = img.width, img.height
        self._redraw()

    def show_jpeg(self, jpeg_bytes: bytes):
        """帧数据 → 显示。

        支持两种格式：
        1. JPEG（由 startImageScreenCapture 产生）
        2. H.264 NAL 单元（由 startCaptureScreen 产生，需 PyAV 解码）
        """
        if self._render_busy:
            return
        self._render_busy = True
        try:
            cw, ch = self.winfo_width(), self.winfo_height()
            if cw < 10 or ch < 10:
                return

            # 尝试 JPEG 解码（快速路径）
            try:
                img = Image.open(io.BytesIO(jpeg_bytes))
            except Exception:
                # JPEG 失败 → H.264 NAL 累积解码
                img = self._feed_h264(jpeg_bytes)
                if img is None:
                    return

            iw, ih = img.width, img.height
            scale = min(cw / iw, ch / ih)
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))

            # 直接用当前帧数据，缩放后创建新 PhotoImage
            if (img.width, img.height) != (nw, nh):
                resized = img.resize((nw, nh), Image.NEAREST)
            else:
                resized = img

            self._photo = ImageTk.PhotoImage(resized)
            self._img = resized
            self._dev_w, self._dev_h = iw, ih

            if self._img_id is None:
                self._img_id = self.create_image(
                    cw // 2, ch // 2, image=self._photo, anchor=tk.CENTER,
                )
            else:
                self.itemconfig(self._img_id, image=self._photo)
        except Exception as ex:
            print(f"[Demo] show_jpeg error: {ex}")
        finally:
            self._render_busy = False

    def _feed_h264(self, nal_data: bytes) -> Image.Image | None:
        """持久的 H.264 解码器，逐帧喂数据，无需缓冲。"""
        try:
            import av
        except ImportError:
            return None

        # 检测 extradata 标记
        if len(nal_data) >= 8 and nal_data[:4] == b'\xff\xff\xff\xfe':
            ext_len = int.from_bytes(nal_data[4:8], 'big')
            ext = nal_data[8:8+ext_len]
            if len(ext) == ext_len:
                self._h264_ctx = av.CodecContext.create("h264", "r")
                self._h264_ctx.extradata = ext
                self._h264_ctx.open()
                print(f"[Demo] H264 extradata set ({ext_len} bytes)")
            return None

        # 首次调用创建解码器（手动设分辨率避免缺 extradata）
        if not hasattr(self, '_h264_ctx'):
            self._h264_ctx = av.CodecContext.create("h264", "r")
            self._h264_ctx.width = 1280
            self._h264_ctx.height = 2832
            self._h264_ctx.pix_fmt = "yuv420p"
            self._h264_ctx.open()

        # 每帧直接喂给解析器（不缓冲）
        try:
            packets = self._h264_ctx.parse(nal_data)
            for packet in packets:
                try:
                    frames = self._h264_ctx.decode(packet)
                    for frame in frames:
                        self._h264_decoded = getattr(self, '_h264_decoded', 0) + 1
                        return frame.to_image()
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _redraw(self):
        if self._img is None:
            return
        cw, ch = self.winfo_width(), self.winfo_height()
        if cw < 10 or ch < 10:
            return
        self._photo = ImageTk.PhotoImage(self._img)
        if self._img_id is None:
            self._img_id = self.create_image(
                cw // 2, ch // 2, image=self._photo, anchor=tk.CENTER,
            )
        else:
            self.itemconfig(self._img_id, image=self._photo)

    # ── 坐标转换 ──────────────────────────────────────────────────────

    def _canvas_to_device(self, cx, cy):
        """画布坐标 → 设备坐标."""
        if self._img is None:
            return None
        cw, ch = self.winfo_width(), self.winfo_height()
        iw, ih = self._img.width, self._img.height
        scale = min(cw / iw, ch / ih)
        dw = int(iw * scale)
        dh = int(ih * scale)
        ox = (cw - dw) // 2
        oy = (ch - dh) // 2
        dx = int((cx - ox) / scale)
        dy = int((cy - oy) / scale)
        dx = int(dx * self._dev_w / iw)
        dy = int(dy * self._dev_h / ih)
        return max(0, min(self._dev_w - 1, dx)), max(0, min(self._dev_h - 1, dy))

    # ── 鼠标事件 ──────────────────────────────────────────────────────
    # ── 鼠标事件 ──────────────────────────────────────────────────────

    def _on_press(self, e):
        pt = self._canvas_to_device(e.x, e.y)
        if pt is None:
            return
        self._pressing = True
        self._swipe_start = pt
        if self._touch:
            self._touch.down(*pt)
            self._draw_indicator(pt)

    def _on_drag(self, e):
        if not self._pressing:
            return
        pt = self._canvas_to_device(e.x, e.y)
        if pt is None:
            return
        if self._touch:
            self._touch.move(*pt)

    def _on_release(self, e):
        if not self._pressing:
            return
        self._pressing = False
        pt = self._canvas_to_device(e.x, e.y)
        if pt is None:
            return
        if self._touch:
            self._touch.up(*pt)
        self._swipe_start = None
        self.after(200, lambda: self.delete("indicator"))

    def _draw_indicator(self, pt):
        """在点击位置画小圆点."""
        self.delete("indicator")
        if self._img is None:
            return
        iw, ih = self._img.width, self._img.height
        cw, ch = self.winfo_width(), self.winfo_height()
        scale = min(cw / iw, ch / ih)
        sx = iw / (self._dev_w or 1)
        sy = ih / (self._dev_h or 1)
        cx = (cw - int(iw * scale)) // 2 + int(pt[0] * sx * scale)
        cy = (ch - int(ih * scale)) // 2 + int(pt[1] * sy * scale)
        r = 10
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                          outline="#ff4444", width=3, tags="indicator")


# ── 主窗口 ──────────────────────────────────────────────────────────────

class DemoApp(tk.Tk):
    """HOScrcpy 演示主窗口。"""

    def __init__(self, sn: str | None = None):
        super().__init__()
        self.title("HOScrcpy Demo — 鸿蒙设备投屏控制")
        self.geometry("520x800")
        self.minsize(400, 600)

        # 状态
        self._device: Device | None = None
        self._capture: ScreenCapture | None = None
        self._touch = None
        self._keyboard: KeyboardController | None = None
        self._streaming = False
        self._demo_mode = True
        self._latest_frame: bytes | None = None
        self._last_rendered: bytes | None = None
        self._render_timer: str | None = None
        self._fps_counter = 0
        self._fps_t0 = 0.0

        self._build_ui()

        # 启动
        if sn:
            self.after(200, lambda: self._connect_device(sn))
        else:
            self.after(200, self._start_demo)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 界面构建 ──────────────────────────────────────────────────────

    def _build_ui(self):
        self.configure(bg=BG_DARK)

        # 工具栏
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=4, pady=4)

        ttk.Label(toolbar, text="设备:").pack(side=tk.LEFT, padx=(0, 4))
        self._cmb = ttk.Combobox(toolbar, state="readonly", width=22)
        self._cmb.pack(side=tk.LEFT, padx=(0, 4))

        self._btn_refresh = ttk.Button(
            toolbar, text="🔄", width=3, command=self._refresh
        )
        self._btn_refresh.pack(side=tk.LEFT, padx=(0, 4))

        self._btn_connect = ttk.Button(
            toolbar, text="连接", width=6, command=self._toggle_connect
        )
        self._btn_connect.pack(side=tk.LEFT, padx=(0, 4))

        self._btn_demo = ttk.Button(
            toolbar, text="演示", width=5, command=self._start_demo
        )
        self._btn_demo.pack(side=tk.LEFT, padx=(0, 4))

        # 控制按钮
        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.X, padx=4, pady=(0, 4))
        for text, cmd in [
            ("◀ 返回", self._press_back),
            ("🏠 主页", self._press_home),
            ("⏻ 电源", self._press_power),
            ("📋 Dump", self._dump_ui),
        ]:
            ttk.Button(ctrl, text=text, command=cmd).pack(side=tk.LEFT, padx=2)

        self._status = ttk.Label(ctrl, text="就绪 — 点击「连接」或「演示」")
        self._status.pack(side=tk.RIGHT, padx=4)

        # 主区域：镜像 + 树
        paned = tk.PanedWindow(
            self, orient=tk.HORIZONTAL, bg=BG_DARK,
            sashwidth=3, sashrelief=tk.RAISED,
        )
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        self._mirror = MirrorCanvas(paned)
        paned.add(self._mirror, stretch="always")

        # 右侧面板
        right = ttk.Frame(paned, width=280)
        right.pack_propagate(False)

        # XPath 搜索
        srch = ttk.Frame(right)
        srch.pack(fill=tk.X, padx=2, pady=2)
        self._xpath_entry = ttk.Entry(srch)
        self._xpath_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        self._xpath_entry.bind("<Return>", lambda e: self._search_xpath())
        ttk.Button(srch, text="查找", command=self._search_xpath).pack(side=tk.LEFT)

        # UI 树
        self._tree = ttk.Treeview(
            right, columns=("id", "text"),
            show="tree headings", selectmode="browse",
        )
        self._tree.heading("#0", text="类型")
        self._tree.heading("id", text="ID")
        self._tree.heading("text", text="文本")
        self._tree.column("#0", width=100)
        self._tree.column("id", width=70)
        self._tree.column("text", width=80)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # 节点详情
        self._info = tk.Text(
            right, height=8, bg=BG_PANEL, fg=FG_TEXT,
            relief=tk.FLAT, font=("Consolas", 9),
        )
        self._info.pack(fill=tk.X, padx=2, pady=2)

        paned.add(right)

        self._tree_nodes: dict[str, object] = {}
        self._ui_root = None

        # 初始扫描设备
        self.after(300, self._refresh)

    # ── 设备发现 ──────────────────────────────────────────────────────

    def _refresh(self):
        self._btn_refresh.configure(state="disabled")
        self._status.configure(text="扫描设备...")

        def _do():
            devices = HOSDevice.list_devices()
            names = [str(d) for d in devices]
            self.after(0, lambda: self._on_refresh(names))

        threading.Thread(target=_do, daemon=True).start()

    def _on_refresh(self, names):
        self._btn_refresh.configure(state="normal")
        if names:
            self._cmb["values"] = names
            self._cmb.current(0)
            self._status.configure(text=f"发现 {len(names)} 台设备")
        else:
            self._cmb["values"] = ["(无设备 — 点击演示)"]
            self._cmb.current(0)
            self._status.configure(text="未发现设备，可点「演示」体验")

    # ── 连接 / 断开 ──────────────────────────────────────────────────

    def _toggle_connect(self):
        if self._streaming and not self._demo_mode:
            self._disconnect()
        else:
            sn = self._cmb.get()
            if not sn or sn.startswith("(无"):
                messagebox.showinfo("提示", "未检测到设备，请点击「演示」")
                return
            self._connect_device(sn)

    def _connect_device(self, sn: str):
        self._stop_demo()
        self._btn_connect.configure(text="连接中...", state="disabled")
        self._status.configure(text=f"连接 {sn}...")

        def _do():
            try:
                dev = Device(sn)
                if not dev.is_online():
                    self.after(0, lambda: self._on_connect_fail(f"{sn} 离线"))
                    return
                jpeg = dev.screenshot()
                if jpeg is None:
                    self.after(0, lambda: self._on_connect_fail("截图失败"))
                    return
                self.after(0, lambda: self._on_connect_ok(dev, jpeg))
            except Exception as ex:
                self.after(0, lambda e=str(ex): self._on_connect_fail(e))

        threading.Thread(target=_do, daemon=True).start()

    def _on_connect_fail(self, msg: str):
        self._btn_connect.configure(text="连接", state="normal")
        self._status.configure(text=f"❌ {msg}")
        messagebox.showerror("连接失败", msg)

    def _on_connect_ok(self, dev: Device, jpeg: bytes):
        self._device = dev
        self._demo_mode = False
        self._streaming = True
        self._btn_connect.configure(text="断开", state="normal")
        self._status.configure(text=f"已连接 {dev.sn}")

        self._keyboard = KeyboardController(dev)
        self._mirror.set_device_size(1080, 2340)
        self._mirror.show_jpeg(jpeg)

        # 启动投屏流
        self._capture = ScreenCapture(dev)
        self._render_timer = self.after(16, self._render_tick)

        def _stream():
            touch = self._capture.start_java_stream(self._on_frame, wait_ready=True)
            if touch:
                self._mirror.set_touch(touch)
                self.after(
                    0,
                    lambda: self._status.configure(text=f"📡 投屏中 {dev.sn}"),
                )

        threading.Thread(target=_stream, daemon=True).start()

        # 后台状态更新
        def _status_loop():
            while self._streaming:
                import time
                time.sleep(2)
                recv = getattr(self, '_frames_recv', 0)
                dec = getattr(self._mirror, '_h264_decoded', 0)
                self.after(0, lambda r=recv, d=dec: self._status.configure(
                    text=f"📡 recv={r} dec={d}"))
        threading.Thread(target=_status_loop, daemon=True).start()

    def _disconnect(self):
        self._streaming = False
        if self._render_timer:
            self.after_cancel(self._render_timer)
            self._render_timer = None
        if self._capture:
            self._capture.stop()
            self._capture = None
        self._device = None
        self._touch = None
        self._mirror.set_touch(None)
        self._btn_connect.configure(text="连接", state="normal")
        self._status.configure(text="已断开")
        self._mirror.delete("all")
        self._mirror._photo = None
        self._mirror._img_id = None
        self._mirror._img = None

    # ── 演示模式 ──────────────────────────────────────────────────────

    def _start_demo(self):
        if self._streaming and not self._demo_mode:
            self._disconnect()
        self._demo_mode = True
        self._streaming = True
        self._btn_connect.configure(text="连接", state="normal")
        self._status.configure(text="🎮 演示模式（模拟触摸）")

        img = _make_demo_screen()
        self._mirror.set_device_size(img.width, img.height)
        self._mirror.show_frame(img)

        class _MockTouch:
            def down(self, x, y):
                print(f"[Demo] 触摸 DOWN ({x}, {y})")

            def move(self, x, y):
                pass

            def up(self, x, y):
                print(f"[Demo] 触摸 UP ({x}, {y})")

        self._mirror.set_touch(_MockTouch())
        self._keyboard = None

    def _stop_demo(self):
        self._demo_mode = False

    # ── 渲染循环 ──────────────────────────────────────────────────────

    def _on_frame(self, jpeg: bytes):
        self._latest_frame = jpeg
        self._frames_recv = getattr(self, '_frames_recv', 0) + 1

    def _render_tick(self):
        if not self._streaming:
            return
        jpeg = self._latest_frame
        if jpeg and jpeg is not self._last_rendered:
            self._last_rendered = jpeg
            self._mirror.show_jpeg(jpeg)
            self._fps_counter += 1
            now = time.monotonic()
            if self._fps_counter % 30 == 0:
                if self._fps_t0:
                    fps = 30 / (now - self._fps_t0)
                    recv = getattr(self, '_frames_recv', 0)
                    self._status.configure(text=f"📡 recv={recv} {fps:.0f}fps")
                self._fps_t0 = now
        self._render_timer = self.after(16, self._render_tick)

    # ── 按键控制 ──────────────────────────────────────────────────────

    def _press_back(self):
        if self._keyboard:
            self._keyboard.back()
            self._status.configure(text="◀ 返回")

    def _press_home(self):
        if self._keyboard:
            self._keyboard.home()
            self._status.configure(text="🏠 主页")

    def _press_power(self):
        if self._keyboard:
            self._keyboard.power()
            self._status.configure(text="⏻ 电源")

    # ── UI Dump ──────────────────────────────────────────────────────

    def _dump_ui(self):
        if not self._device:
            messagebox.showinfo("提示", "请先连接设备")
            return
        self._status.configure(text="📋 正在获取 UI 层级...")

        def _do():
            try:
                ui = UIHierarchy(self._device)
                root = ui.dump()
                self.after(0, lambda: self._on_dump_done(root))
            except Exception as ex:
                self.after(0, lambda: messagebox.showerror("Dump 失败", str(ex)))

        threading.Thread(target=_do, daemon=True).start()

    def _on_dump_done(self, root):
        if root is None:
            self._status.configure(text="Dump 失败")
            return
        self._ui_root = root
        self._tree_nodes.clear()
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._populate_tree("", root)
        total = len(self._tree_nodes)
        self._status.configure(text=f"📋 加载 {total} 个节点 — 点击高亮")

    def _populate_tree(self, parent, node):
        type_name = node.type or "(root)"
        iid = self._tree.insert(
            parent, "end",
            text=type_name,
            values=(node.id or "", (node.text or "")[:30]),
        )
        self._tree_nodes[iid] = node
        for child in node.children:
            self._populate_tree(iid, child)

    def _on_tree_select(self, _e=None):
        sel = self._tree.selection()
        if not sel:
            return
        node = self._tree_nodes.get(sel[0])
        if node is None or self._mirror._img is None:
            return
        x, y, w, h = node.rectangle
        if w <= 0 or h <= 0:
            return
        # 在镜像画布上画高亮框
        self._mirror.delete("hl")
        iw, ih = self._mirror._img.width, self._mirror._img.height
        cw, ch = self._mirror.winfo_width(), self._mirror.winfo_height()
        scale = min(cw / iw, ch / ih)
        dw, dh = int(iw * scale), int(ih * scale)
        ox, oy = (cw - dw) // 2, (ch - dh) // 2
        sx = iw / (self._mirror._dev_w or 1)
        sy = ih / (self._mirror._dev_h or 1)
        x1 = ox + int(x * sx * scale)
        y1 = oy + int(y * sy * scale)
        x2 = ox + int((x + w) * sx * scale)
        y2 = oy + int((y + h) * sy * scale)
        self._mirror.create_rectangle(
            x1, y1, x2, y2, outline="#00ff00", width=2, tags="hl",
        )
        # 显示节点信息
        self._info.delete("1.0", tk.END)
        self._info.insert(
            "1.0",
            f"类型: {node.type}\n"
            f"文本: {node.text or '(空)'}\n"
            f"ID: {node.id or '(空)'}\n"
            f"描述: {node.description or '(空)'}\n"
            f"范围: [{x},{y}] {w}x{h}\n"
            f"可点击: {'是' if node.is_clickable else '否'}\n"
            f"可见: {'是' if node.is_visible else '否'}",
        )

    def _search_xpath(self):
        expr = self._xpath_entry.get().strip()
        if not expr or self._ui_root is None:
            return
        from hos_scrcpy.ui.xpath import find_by_xpath
        try:
            results = find_by_xpath(self._ui_root, expr)
        except Exception as ex:
            self._status.configure(text=f"XPath 错误: {ex}")
            return
        self._mirror.delete("hl")
        colors = ["#00ff00", "#ff4444", "#4488ff", "#ffaa00"]
        for i, node in enumerate(results[:20]):
            x, y, w, h = node.rectangle
            if w <= 0 or h <= 0:
                continue
            iw, ih = self._mirror._img.width, self._mirror._img.height
            cw, ch = self._mirror.winfo_width(), self._mirror.winfo_height()
            scale = min(cw / iw, ch / ih)
            dw, dh = int(iw * scale), int(ih * scale)
            ox, oy = (cw - dw) // 2, (ch - dh) // 2
            sx = iw / (self._mirror._dev_w or 1)
            sy = ih / (self._mirror._dev_h or 1)
            x1 = ox + int(x * sx * scale)
            y1 = oy + int(y * sy * scale)
            x2 = ox + int((x + w) * sx * scale)
            y2 = oy + int((y + h) * sy * scale)
            self._mirror.create_rectangle(
                x1, y1, x2, y2,
                outline=colors[i % len(colors)],
                width=2, tags="hl",
            )
        self._status.configure(text=f"XPath 找到 {len(results)} 个结果")

    # ── 关闭 ──────────────────────────────────────────────────────────

    def _on_close(self):
        self._streaming = False
        if self._render_timer:
            self.after_cancel(self._render_timer)
        if self._capture:
            self._capture.stop()
        self.destroy()


def main():
    setup_logging()
    ap = argparse.ArgumentParser(description="HOScrcpy 投屏演示")
    ap.add_argument("--sn", help="设备序列号，直接连接")
    args = ap.parse_args()
    app = DemoApp(sn=args.sn)
    app.mainloop()


if __name__ == "__main__":
    main()
