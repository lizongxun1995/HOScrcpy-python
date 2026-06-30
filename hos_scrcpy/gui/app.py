"""HOScrcpy GUI �?screen mirroring with mouse-to-touch mapping.

Two modes:
1. Demo mode �?fake phone screen, visual feedback for clicks/swipes (no device needed)
2. Live mode �?real device screen via screenshot polling

Run:
    python -m hos_scrcpy.gui.app
"""

import math
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageTk

from hos_scrcpy.core.device import Device
from hos_scrcpy.input.touch import TouchController
from hos_scrcpy.input.async_touch import AsyncTouchController
from hos_scrcpy.input.fast_touch import FastTouchController
from hos_scrcpy.input.keyboard import KeyboardController
from hos_scrcpy.screen.capture import ScreenCapture
from hos_scrcpy.ui.selector import UIHierarchy
from hos_scrcpy.ui.xpath import find_by_xpath, xpath_for
from hos_scrcpy.utils.logger import logger, setup_logging

TAG = "GUI"

# ─── Mock controllers for demo mode ──────────────────────────────────────────

class _MockTouch:
    """Pretend touch controller that logs coordinates."""
    def down(self, x, y):
        logger.debug(f"[Demo] Touch DOWN at ({x}, {y})")

    def up(self, x, y):
        logger.debug(f"[Demo] Touch UP at ({x}, {y})")

    def move(self, x, y):
        logger.debug(f"[Demo] Touch MOVE to ({x}, {y})")

    def swipe(self, x1, y1, x2, y2, duration=0.3, steps=10):
        logger.debug(f"[Demo] SWIPE ({x1},{y1})→({x2},{y2}) dur={duration}")

    def click(self, x, y, duration=0.05):
        logger.debug(f"[Demo] CLICK at ({x}, {y})")


class _MockKeyboard:
    """Pretend keyboard that just prints actions."""
    def back(self): pass
    def home(self): pass

# ─── Fake phone screen generator ─────────────────────────────────────────────

def _make_fake_screen(width: int = 540, height: int = 1170) -> Image.Image:
    """Generate a realistic HarmonyOS phone screen image."""
    img = Image.new("RGB", (width, height), "#F0F0F5")
    draw = ImageDraw.Draw(img)

    # Status bar background
    draw.rectangle([0, 0, width, 64], fill="#E8E8ED")
    try:
        font_sm = ImageFont.truetype("segoeui.ttf", 18)
        font_md = ImageFont.truetype("segoeui.ttf", 22)
        font_lg = ImageFont.truetype("segoeui.ttf", 28)
    except Exception:
        font_sm = ImageFont.load_default()
        font_md = font_sm
        font_lg = font_sm

    draw.text((16, 18), "9:41", fill="#1A1A1A", font=font_sm)
    draw.text((width - 80, 18), "100%", fill="#1A1A1A", font=font_sm)
    # Battery icon
    bx = width - 62
    draw.rectangle([bx, 22, bx + 42, 42], outline="#1A1A1A", width=2)
    draw.rectangle([bx + 42, 28, bx + 46, 36], fill="#1A1A1A")
    draw.rectangle([bx + 5, 27, bx + 32, 37], fill="#4CAF50")

    # Settings title
    draw.rectangle([0, 64, width, 120], fill="#FFFFFF")
    draw.text((24, 80), "Settings", fill="#1A1A1A", font=font_lg)

    # Section: Network
    y = 136
    draw.text((24, y), "NETWORK & INTERNET", fill="#888888", font=font_sm)
    y += 36

    items = [
        ("Wi-Fi", "HUAWEI-5G"),
        ("Bluetooth", "On"),
        ("Mobile network", "China Mobile"),
        ("Data usage", ""),
    ]
    for title, subtitle in items:
        draw.rectangle([0, y, width, y + 64], fill="#FFFFFF")
        draw.text((24, y + 8), title, fill="#1A1A1A", font=font_md)
        if subtitle:
            draw.text((24, y + 34), subtitle, fill="#888888", font=font_sm)
        if y > 136:
            draw.line([24, y, width, y], fill="#E8E8ED")
        # Right chevron
        cx, cy = width - 36, y + 32
        draw.line([cx - 6, cy - 10, cx + 6, cy, cx - 6, cy + 10], fill="#CCCCCC", width=2)
        y += 64

    # Section: Display
    y += 12
    draw.text((24, y), "DEVICE", fill="#888888", font=font_sm)
    y += 36

    dev_items = [
        ("Display & brightness", ""),
        ("Sound & vibration", ""),
        ("Notifications", "3 apps allowed"),
        ("Battery", "85%"),
    ]
    for title, subtitle in dev_items:
        draw.rectangle([0, y, width, y + 64], fill="#FFFFFF")
        draw.text((24, y + 8), title, fill="#1A1A1A", font=font_md)
        if subtitle:
            draw.text((24, y + 34), subtitle, fill="#888888", font=font_sm)
        if subtitle:
            draw.line([24, y, width, y], fill="#E8E8ED")
        cx, cy = width - 36, y + 32
        draw.line([cx - 6, cy - 10, cx + 6, cy, cx - 6, cy + 10], fill="#CCCCCC", width=2)
        y += 64

    # Bottom buttons
    y = height - 160
    btn_w, btn_h = width - 48, 52
    bx = 24

    # A "Test Button"
    draw.rounded_rectangle([bx, y, bx + btn_w, y + btn_h], radius=26, fill="#007AFF")
    draw.text((bx + btn_w // 2 - 54, y + 14), "Tap Here", fill="#FFFFFF", font=font_lg)
    y += btn_h + 16

    # Another button
    draw.rounded_rectangle([bx, y, bx + btn_w, y + btn_h], radius=26, fill="#34C759")
    draw.text((bx + btn_w // 2 - 60, y + 14), "Long Press", fill="#FFFFFF", font=font_lg)
    y += btn_h + 16

    # A slider-like element
    draw.rounded_rectangle([bx, y, bx + btn_w, y + btn_h], radius=26, fill="#FFFFFF", outline="#E0E0E0", width=2)
    draw.rounded_rectangle([bx + 4, y + 4, bx + btn_w // 2, y + btn_h - 4], radius=22, fill="#007AFF")
    draw.text((bx + 16, y + 14), "Swipe Me >>>", fill="#FFFFFF", font=font_lg)

    return img


# ─── Device mirror canvas ────────────────────────────────────────────────────

class DeviceMirror(tk.Frame):
    """Canvas that displays device screen and maps mouse events to touch."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._canvas = tk.Canvas(self, bg="#1a1a1a", highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._photo: ImageTk.PhotoImage | None = None
        self._tk_photo: tk.PhotoImage | None = None  # Native tk PhotoImage from JPEG
        self._image_id: int | None = None
        self._device_width = 1080
        self._device_height = 2340
        self._current_image: Image.Image | None = None
        self._base_image: Image.Image | None = None  # pristine copy for redraw

        # Controller references
        self._touch = None
        self._keyboard = None
        self._demo_mode = False

        # Touch state
        self._pressing = False
        self._swipe_points: list[tuple[int, int]] = []
        self._last_touch_point: tuple[int, int] | None = None

        # Visual feedback overlays (canvas ids, cleared each redraw)
        self._overlay_ids: list[int] = []

        # Bind mouse events
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<MouseWheel>", self._on_scroll)
        self._canvas.bind("<Configure>", self._on_resize)

        # Status callback for demo mode
        self._on_action_log: callable | None = None

    # ---- public API ----

    def set_controllers(self, touch, keyboard):
        self._touch = touch
        self._keyboard = keyboard

    def set_device_size(self, width: int, height: int):
        self._device_width = width
        self._device_height = height

    def update_frame(self, img: Image.Image):
        """Called from streaming thread with a new PIL Image."""
        self._current_image = img.copy()
        self._base_image = img.copy()
        self._device_width = img.width
        self._device_height = img.height
        self._clear_overlays()
        self._redraw()

    def enable_demo_mode(self):
        """Load a fake phone screen and mock controllers for testing."""
        self._demo_mode = True
        img = _make_fake_screen()
        self._current_image = img.copy()
        self._base_image = img.copy()
        self._device_width = img.width
        self._device_height = img.height
        self._touch = _MockTouch()
        self._keyboard = _MockKeyboard()
        self._clear_overlays()
        self._redraw()

    # ---- drawing ----

    def set_jpeg(self, jpeg_bytes: bytes):
        """Render JPEG on canvas: scale to fit, update PhotoImage."""
        try:
            img = Image.open(BytesIO(jpeg_bytes))
            img.load()
            self._current_image = img
            self._device_width = img.width
            self._device_height = img.height

            cw = self._canvas.winfo_width()
            ch = self._canvas.winfo_height()
            if cw < 10 or ch < 10:
                return
            scale = min(cw / img.width, ch / img.height)
            new_w, new_h = int(img.width * scale), int(img.height * scale)
            resized = img.resize((new_w, new_h), Image.NEAREST)

            self._photo = ImageTk.PhotoImage(resized)
            if self._image_id is None:
                self._image_id = self._canvas.create_image(
                    cw // 2, ch // 2, image=self._photo, anchor=tk.CENTER,
                )
            else:
                self._canvas.itemconfig(self._image_id, image=self._photo)
        except Exception as ex:
            logger.debug(f"{TAG}: set_jpeg error: {ex}")

    def _redraw(self):
        if self._current_image is None:
            return

        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        dw, dh = self._current_image.width, self._current_image.height
        scale = min(cw / dw, ch / dh)
        new_w, new_h = int(dw * scale), int(dh * scale)

        # Skip resize if image already at target size
        if dw == new_w and dh == new_h:
            resized = self._current_image
        else:
            resized = self._current_image.resize((new_w, new_h), Image.NEAREST)

        self._photo = ImageTk.PhotoImage(resized)

        if self._image_id is not None:
            self._canvas.delete(self._image_id)
        self._image_id = self._canvas.create_image(
            cw // 2, ch // 2, image=self._photo, anchor=tk.CENTER
        )

    def _draw_touch_indicator(self, dev_x: int, dev_y: int, color: str = "#FF4444"):
        """Draw a ripple circle at device coordinates."""
        if self._current_image is None:
            return
        cx, cy = self._device_to_canvas(dev_x, dev_y)
        if cx is None:
            return
        r = 12
        oval = self._canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=color, width=3, tags="overlay"
        )
        self._overlay_ids.append(oval)

    def _draw_swipe_trail(self):
        """Draw a line showing the swipe path."""
        if len(self._swipe_points) < 2:
            return
        pts = []
        for dx, dy in self._swipe_points:
            c = self._device_to_canvas(dx, dy)
            if c:
                pts.extend(c)
        if len(pts) >= 4:
            line = self._canvas.create_line(
                pts, fill="#FF4444", width=4, tags="overlay", smooth=True
            )
            self._overlay_ids.append(line)

    def _clear_overlays(self):
        for oid in self._overlay_ids:
            self._canvas.delete(oid)
        self._overlay_ids.clear()

    # ---- coordinate conversion ----

    def _canvas_to_device(self, cx: int, cy: int) -> tuple[int, int] | None:
        """Convert canvas coordinates to device coordinates."""
        if self._current_image is None:
            return None
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        iw, ih = self._current_image.width, self._current_image.height
        scale = min(cw / iw, ch / ih)
        new_w, new_h = int(iw * scale), int(ih * scale)
        ox = (cw - new_w) // 2
        oy = (ch - new_h) // 2
        dx = int((cx - ox) / scale)
        dy = int((cy - oy) / scale)
        dx = max(0, min(iw - 1, dx))
        dy = max(0, min(ih - 1, dy))
        # Scale from stream resolution to device resolution
        sx = self._device_width / iw
        sy = self._device_height / ih
        dx = int(dx * sx)
        dy = int(dy * sy)
        return dx, dy

    def _device_to_canvas(self, dx: int, dy: int) -> tuple[int, int] | None:
        """Convert device coordinates to canvas coordinates."""
        if self._current_image is None:
            return None
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        iw, ih = self._current_image.width, self._current_image.height
        sx = self._device_width / iw
        sy = self._device_height / ih
        ix = dx / sx
        iy = dy / sy
        scale = min(cw / iw, ch / ih)
        new_w, new_h = int(iw * scale), int(ih * scale)
        ox = (cw - new_w) // 2
        oy = (ch - new_h) // 2
        cx = int(ox + ix * scale)
        cy = int(oy + iy * scale)
        return cx, cy

    # ---- mouse events ----

    def _on_press(self, event):
        pt = self._canvas_to_device(event.x, event.y)
        if pt is None:
            logger.debug("{0}: press, no coord (img={1})".format(TAG, self._current_image is not None))
            return
        logger.debug("{0}: press canvas=({1},{2}) device=({3},{4}) touch={5}".format(
            TAG, event.x, event.y, pt[0], pt[1], self._touch is not None))
        self._pressing = True
        self._swipe_points = [pt]
        self._last_touch_point = pt
        if self._touch:
            self._touch.down(pt[0], pt[1])

        self._clear_overlays()
        self._draw_touch_indicator(pt[0], pt[1])
        if self._on_action_log:
            self._on_action_log(f"Touch DOWN at ({pt[0]}, {pt[1]})")

    def _on_release(self, event):
        if not self._pressing:
            return
        self._pressing = False
        pt = self._canvas_to_device(event.x, event.y)
        if pt is None:
            return

        if self._touch:
            dist = ((pt[0] - self._swipe_points[0][0])**2 + (pt[1] - self._swipe_points[0][1])**2)**0.5
            is_swipe = len(self._swipe_points) > 2 and dist > 15
            logger.debug("{0}: release pts={1} dist={2:.0f} swipe={3}".format(TAG, len(self._swipe_points), dist, is_swipe))
            if is_swipe:
                # Down already sent by _on_press, moves by _on_drag — just send up
                self._touch.up(pt[0], pt[1])
            else:
                x, y = pt[0], pt[1]
                self.after(50, lambda xx=x, yy=y: self._touch.up(xx, yy) if self._touch else None)

        if self._on_action_log:
            action = "Swipe" if len(self._swipe_points) > 1 else "Click"
            self._on_action_log(f"{action} at ({pt[0]}, {pt[1]})")

        self.after(300, self._clear_overlays)
        self._swipe_points = []
        self._last_touch_point = None

    def _on_drag(self, event):
        if not self._pressing:
            return
        pt = self._canvas_to_device(event.x, event.y)
        if pt is None:
            return
        self._swipe_points.append(pt)
        if self._touch:
            self._touch.move(pt[0], pt[1])

        # Throttle visual updates: only redraw trail every 80ms
        now = time.monotonic()
        if not hasattr(self, '_last_trail_draw') or now - self._last_trail_draw > 0.08:
            self._last_trail_draw = now
            self._clear_overlays()
            self._draw_swipe_trail()
        if self._on_action_log:
            self._on_action_log(f"Move ({pt[0]}, {pt[1]})")

    def _on_scroll(self, event):
        pt = self._canvas_to_device(event.x, event.y)
        if pt is None:
            return
        delta = -80 if event.delta > 0 else 80
        sy = max(0, pt[1] - delta)
        ey = min(self._device_height - 1, pt[1] + delta)
        if self._touch:
            self._touch.swipe(pt[0], sy, pt[0], ey, duration=0.15)
        if self._on_action_log:
            direction = "UP" if event.delta > 0 else "DOWN"
            self._on_action_log(f"Scroll {direction} at ({pt[0]}, {pt[1]})")

    def _on_resize(self, _event):
        self._redraw()


# ─── Main window ─────────────────────────────────────────────────────────────

class MainWindow(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title("HOScrcpy �?Device Mirror")
        self.geometry("480x900")
        self.minsize(320, 480)

        self._device: Device | None = None
        self._capture: ScreenCapture | None = None
        self._stream_running = False
        self._stream_thread: threading.Thread | None = None
        self._touch = None
        self._keyboard = None
        self._demo_mode = False
        self._frame_ready = threading.Event()
        self._last_rendered = None
        self._tree_nodes: dict[str, object] = {}  # Treeview iid -> JsonStructure

        self._build_ui()

        # Go straight to demo mode on startup
        self.after(100, self._start_demo)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # ---- toolbar ----
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=4, pady=4)

        ttk.Label(toolbar, text="Device:").pack(side=tk.LEFT, padx=(0, 4))
        self._cmb_device = ttk.Combobox(toolbar, state="readonly", width=20)
        self._cmb_device.pack(side=tk.LEFT, padx=(0, 4))

        self._btn_refresh = ttk.Button(
            toolbar, text="Refresh", width=7, command=self._refresh_devices
        )
        self._btn_refresh.pack(side=tk.LEFT, padx=(0, 4))

        self._btn_cast = ttk.Button(toolbar, text="Start Cast", command=self._toggle_cast)
        self._btn_cast.pack(side=tk.LEFT, padx=(0, 4))

        self._btn_demo = ttk.Button(toolbar, text="Demo", width=6, command=self._start_demo)
        self._btn_demo.pack(side=tk.LEFT, padx=(0, 4))

        self._btn_back = ttk.Button(toolbar, text="Back", width=5, command=self._press_back)
        self._btn_back.pack(side=tk.LEFT, padx=(0, 2))
        self._btn_home = ttk.Button(toolbar, text="Home", width=5, command=self._press_home)
        self._btn_home.pack(side=tk.LEFT, padx=(0, 2))
        self._btn_power = ttk.Button(toolbar, text="Power", width=6, command=self._press_power)
        self._btn_power.pack(side=tk.LEFT, padx=(0, 2))
        self._btn_dump = ttk.Button(toolbar, text="Dump UI", width=7, command=self._dump_ui)
        self._btn_dump.pack(side=tk.LEFT)

        # ---- main area: mirror | tree panel ----
        pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=3, sashrelief=tk.RAISED)
        pane.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        # Left: device mirror
        self._mirror = DeviceMirror(pane)
        self._mirror._on_action_log = self._log_action
        pane.add(self._mirror, stretch="always")

        # Right: UI tree panel
        right_frame = ttk.Frame(pane, width=300)
        right_frame.pack_propagate(False)

        # XPath search bar
        search_frame = ttk.Frame(right_frame)
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=2, pady=(2, 0))
        self._xpath_entry = ttk.Entry(search_frame)
        self._xpath_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        self._xpath_entry.bind("<Return>", self._search_xpath)
        self._btn_search = ttk.Button(
            search_frame, text="Find", width=5, command=self._search_xpath
        )
        self._btn_search.pack(side=tk.LEFT)

        self._tree = ttk.Treeview(
            right_frame,
            columns=("id", "text", "xpath", "bundle", "desc"),
            show="tree headings",
            selectmode="browse",
        )
        self._tree.heading("#0", text="Type")
        self._tree.heading("id", text="ID")
        self._tree.heading("text", text="Text")
        self._tree.heading("xpath", text="XPath")
        self._tree.heading("bundle", text="Bundle")
        self._tree.heading("desc", text="Desc")
        self._tree.column("#0", width=110, minwidth=60)
        self._tree.column("id", width=80, minwidth=60)
        self._tree.column("text", width=60, minwidth=40)
        self._tree.column("xpath", width=140, minwidth=80)
        self._tree.column("bundle", width=70, minwidth=50)
        self._tree.column("desc", width=60, minwidth=40)
        self._tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Scrollbar for tree
        tree_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Node info label at bottom of right panel
        self._tree_info = ttk.Label(right_frame, text="Select a node to see details", anchor=tk.W, wraplength=280)
        self._tree_info.pack(side=tk.BOTTOM, fill=tk.X, pady=2, padx=2)

        pane.add(right_frame, stretch="never")

        # Bind tree selection
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._status = ttk.Label(
            self, text="Demo mode loaded �?click/drag/scroll on the phone screen",
            relief=tk.SUNKEN, anchor=tk.W,
        )
        self._status.pack(fill=tk.X, side=tk.BOTTOM)

        # Also refresh real devices in background
        self._refresh_devices()

    # ---- demo mode ----

    def _start_demo(self):
        """Enter demo mode with a fake phone screen."""
        self._stop_cast()
        self._demo_mode = True
        self._mirror.enable_demo_mode()
        self._btn_cast.configure(state="disabled")
        self._status.configure(
            text="[DEMO] Click = tap, Drag = swipe, Scroll = scroll �?"
            "coordinates shown on each action"
        )

    # ---- device management ----

    def _refresh_devices(self):
        self._btn_refresh.configure(state="disabled")

        def _scan():
            try:
                from hos_scrcpy.core.hdc_client import HdcClient
                if not HdcClient.is_available():
                    self.after(0, lambda: self._on_hdc_missing())
                    return
                devices = Device.list_all()
            except Exception:
                devices = []

            def _update():
                items = [str(d) for d in devices]
                self._cmb_device["values"] = items
                if items:
                    self._cmb_device.current(0)
                    self._btn_cast.configure(state="normal")
                self._btn_refresh.configure(state="normal")
                if not self._demo_mode and not devices:
                    self._status.configure(
                        text="No devices found �?connect USB/WiFi and click Refresh"
                    )
            self.after(0, _update)

        threading.Thread(target=_scan, daemon=True).start()

    def _on_hdc_missing(self):
        """Handle case where hdc is not installed."""
        self._cmb_device["values"] = ["(hdc not found - install HarmonyOS SDK)"]
        self._cmb_device.current(0)
        self._btn_refresh.configure(state="normal")
        self._btn_cast.configure(state="disabled")
        self._status.configure(
            text="hdc not found �?install HarmonyOS SDK or use Demo mode"
        )

    # ---- casting (live device) ----

    def _toggle_cast(self):
        if self._demo_mode:
            self._demo_mode = False
        if self._stream_running:
            self._stop_cast()
        else:
            self._start_cast()

    def _start_cast(self):
        sn_str = self._cmb_device.get()
        if not sn_str:
            messagebox.showwarning("No Device", "Select a device first.")
            return

        self._demo_mode = False
        self._touch = None  # Will be set after native stream starts

        try:
            self._device = Device(sn_str)
        except Exception as ex:
            messagebox.showerror("Error", f"Failed to create device: {ex}")
            return

        self._btn_cast.configure(text="Connecting...", state="disabled")
        self._status.configure(text=f"Checking {sn_str}...")

        # Safety timeout: auto-reset if connection hangs > 25s
        self._conn_timeout = self.after(25000, self._on_connect_timeout)

        def _connect():
            if not self._device.is_online():
                self.after(0, lambda: self._on_connect_fail("Device is offline"))
                return
            self.after(0, lambda: self._status.configure(text=f"Taking screenshot..."))
            try:
                jpeg = self._device.screenshot()
                if jpeg is None:
                    self.after(0, lambda e="Screenshot failed": self._on_connect_fail(e))
                    return
                img = Image.open(BytesIO(jpeg))
                self._keyboard = KeyboardController(self._device)
                self.after(0, lambda j=jpeg: self._on_connect_ok(j))
            except Exception as ex:
                self.after(0, lambda e=str(ex): self._on_connect_fail(e))

        threading.Thread(target=_connect, daemon=True).start()

    def _on_connect_timeout(self):
        if not self._stream_running:
            self._btn_cast.configure(text="Start Cast", state="normal")
            self._status.configure(
                text="Connection timed out (25s) - check device and hdc"
            )

    def _on_connect_fail(self, msg: str):
        if hasattr(self, "_conn_timeout"):
            self.after_cancel(self._conn_timeout)
        self._btn_cast.configure(text="Start Cast", state="normal")
        self._status.configure(text="Connection failed: " + msg)
        messagebox.showerror("Connection Error", msg)

    def _on_connect_ok(self, jpeg: bytes):
        if hasattr(self, "_conn_timeout"):
            self.after_cancel(self._conn_timeout)
        self._mirror.set_controllers(None, self._keyboard)
        self._mirror.set_jpeg(jpeg)
        self._stream_running = True
        self._frame_count = 0
        self._latest_frame = None
        self._last_rendered = None
        self._btn_cast.configure(text="Stop Cast", state="normal")
        self._status.configure(text=f"LIVE {self._device} - native stream starting...")

        # Start event-driven render loop on main thread
        self._render_timer_id = self.after(16, self._render_tick)

        # Start native stream via ScreenCapture in background
        self._capture = ScreenCapture(self._device)
        self._stream_thread = threading.Thread(
            target=self._stream_loop, daemon=True
        )
        self._stream_thread.start()

    def _stream_loop(self):
        """Background: read frames from Java bridge or screenshot fallback."""
        self._touch = self._capture.start_java_stream(self._on_frame, wait_ready=False)
        if self._touch is not None:
            # Java stream active — FastTouch for low-latency touch
            self._mirror.set_controllers(self._touch, self._keyboard)
            # Update finder's touch controller so click_by_* uses fast path
            if hasattr(self, '_finder') and self._finder:
                self._finder._touch = self._touch
            self.after(0, lambda: self._status.configure(
                text="LIVE {0} - native stream active".format(self._device)
            ))
        else:
            self._touch = AsyncTouchController(TouchController(self._device))
            self._mirror.set_controllers(self._touch, self._keyboard)

            # Try H.264 screenrecord (30-60fps, needs PyAV)
            try:
                import av  # noqa: F401
                self.after(0, lambda: self._status.configure(
                    text="LIVE {0} - H.264 screenrecord stream".format(self._device)
                ))
                self._capture.start_native_stream(self._on_frame)
                return
            except ImportError:
                pass

            # Final fallback: screenshot polling (~2fps)
            self.after(0, lambda: self._status.configure(
                text="LIVE {0} - screenshot mode (2fps)".format(self._device)
            ))
            self._capture.start_screenshot_stream(self._on_frame, interval=0.5)

    def _on_frame(self, jpeg: bytes):
        """Called from background thread when a new frame is ready."""
        self._latest_frame = jpeg

    def _render_tick(self):
        """Main thread: render latest frame at ~60fps."""
        if not self._stream_running:
            return
        jpeg = self._latest_frame
        if jpeg is not None and jpeg is not self._last_rendered:
            self._last_rendered = jpeg
            self._mirror.set_jpeg(jpeg)
            self._frame_count += 1
            self._status.configure(
                text="LIVE {0} - frame #{1}".format(self._device, self._frame_count)
            )
        self._render_timer_id = self.after(16, self._render_tick)

    def _stop_cast(self):
        self._stream_running = False
        self._frame_ready.set()  # wake up render loop to exit
        if hasattr(self, "_render_timer_id"):
            self.after_cancel(self._render_timer_id)
        if hasattr(self, "_conn_timeout"):
            self.after_cancel(self._conn_timeout)
        if self._capture:
            self._capture.stop()
            self._capture = None
        if self._stream_thread:
            self._stream_thread.join(timeout=2)
            self._stream_thread = None
        self._touch = None
        self._keyboard = None
        self._mirror.set_controllers(None, None)
        self._device = None
        self._btn_cast.configure(text="Start Cast", state="normal")

    # ---- key shortcuts ----

    def _press_back(self):
        if self._keyboard:
            self._keyboard.back()
        self._log_action("Back key pressed")

    def _press_home(self):
        if self._keyboard:
            self._keyboard.home()
        self._log_action("Home key pressed")

    def _press_power(self):
        if self._keyboard:
            self._keyboard.power()
        self._log_action("Power key pressed")

    # ---- helpers ----

    def _log_action(self, msg: str):
        """Show action in status bar. Thread-safe."""
        self.after(0, lambda: self._status.configure(text=f"[Action] {msg}"))

    def _dump_ui(self):
        """Dump UI hierarchy from device and populate the tree view."""
        if not self._device or not self._device.is_online():
            self._status.configure(text="No device connected - connect first")
            return

        self._btn_dump.configure(text="Loading...", state="disabled")
        self._status.configure(text="Dumping UI hierarchy...")

        def _do_dump():
            try:
                ui = UIHierarchy(self._device)
                root = ui.dump()
            except Exception as ex:
                logger.error(f"Dump UI failed: {ex}")
                root = None

            self.after(0, lambda r=root: self._on_dump_done(r))

        threading.Thread(target=_do_dump, daemon=True).start()

    def _on_dump_done(self, root):
        """Populate tree view with UI hierarchy (called on main thread)."""
        self._btn_dump.configure(text="Dump UI", state="normal")
        self._tree_nodes.clear()

        # Clear existing tree items
        for item in self._tree.get_children():
            self._tree.delete(item)

        if root is None:
            self._status.configure(text="UI dump failed - check device")
            return

        self._ui_root = root
        self._populate_tree("", root, root)
        total = len(self._tree_nodes)
        self._status.configure(text=f"UI tree loaded: {total} nodes - click a node to highlight")

    def _populate_tree(self, parent_iid: str, node, root):
        """Recursively insert JsonStructure nodes into the Treeview."""
        type_name = node.type or "(root)"
        node_id = node.id or ""
        text_value = (node.text or "")[:40]
        xp = xpath_for(node, root) if root else ""
        bundle = node.bundle_name or ""
        desc = (node.description or "")[:30]

        iid = self._tree.insert(
            parent_iid, "end",
            text=type_name,
            values=(node_id, text_value, xp, bundle, desc),
        )
        self._tree_nodes[iid] = node

        for child in node.children:
            self._populate_tree(iid, child, root)

    def _on_tree_select(self, event):
        """Highlight the selected UI element on the mirror canvas."""
        selection = self._tree.selection()
        if not selection:
            return

        node = self._tree_nodes.get(selection[0])
        if node is None:
            return

        # Clear previous highlight
        self._mirror._clear_overlays()

        # Draw highlight rectangle
        x, y, w, h = node.rectangle
        if w <= 0 or h <= 0:
            self._tree_info.configure(text=f"{node.type}: {node.text or ''} (zero-size)")
            return

        tl = self._mirror._device_to_canvas(x, y)
        br = self._mirror._device_to_canvas(x + w, y + h)
        if tl is None or br is None:
            return

        rect_id = self._mirror._canvas.create_rectangle(
            tl[0], tl[1], br[0], br[1],
            outline="#00FF00", width=2, tags="overlay"
        )
        self._mirror._overlay_ids.append(rect_id)

        # Show node info
        xp = xpath_for(node, self._ui_root) if hasattr(self, '_ui_root') and self._ui_root else ""
        info_parts = [
            f"XPath: {xp}",
            f"",
            f"Type: {node.type}",
            f"Text: {node.text or '(none)'}",
            f"ID: {node.id or '(none)'}",
            f"Desc: {node.description or '(none)'}",
            f"Bundle: {node.bundle_name or '(none)'}",
            f"Bounds: [{x},{y}][{x+w},{y+h}] ({w}x{h})",
            f"zIndex: {node.z_index}",
        ]
        flags = []
        if node.is_clickable: flags.append("clickable")
        if node.is_long_clickable: flags.append("long-click")
        if node.is_scrollable: flags.append("scrollable")
        if node.is_focused: flags.append("focused")
        if node.is_selected: flags.append("selected")
        if node.is_enabled: flags.append("enabled")
        if node.is_visible: flags.append("visible")
        info_parts.append(f"Flags: {', '.join(flags) if flags else '(none)'}")
        info = "\n".join(info_parts)
        self._tree_info.configure(text=info)

    def _search_xpath(self, event=None):
        """Search UI tree by xpath expression, highlight all matches."""
        expr = self._xpath_entry.get().strip()
        if not expr:
            return

        # Find the root from the tree dump
        if not self._tree_nodes:
            self._status.configure(text="Dump UI first before searching")
            return

        # Get root from first tree item (iid = first child of "")
        roots = self._tree.get_children()
        if not roots:
            return

        # Find root node (the one with empty type or "Root")
        from hos_scrcpy.ui.xpath import find_by_xpath
        from hos_scrcpy.ui.hierarchy import JsonStructure

        # Rebuild root from stored nodes
        root_nodes = [self._tree_nodes[iid] for iid in roots]
        # The tree root is the first root-level node
        root = root_nodes[0]

        try:
            results = find_by_xpath(root, expr)
        except Exception as ex:
            self._status.configure(text=f"XPath error: {ex}")
            return

        # Clear previous highlights
        self._mirror._clear_overlays()

        n = len(results)
        if n == 0:
            self._status.configure(text=f"No matches for: {expr}")
            return

        # Highlight all matches
        colors = ["#00FF00", "#FF4444", "#4488FF", "#FFAA00", "#AA44FF"]
        for i, node in enumerate(results):
            x, y, w, h = node.rectangle
            if w <= 0 or h <= 0:
                continue
            tl = self._mirror._device_to_canvas(x, y)
            br = self._mirror._device_to_canvas(x + w, y + h)
            if tl is None or br is None:
                continue
            color = colors[i % len(colors)]
            rect_id = self._mirror._canvas.create_rectangle(
                tl[0], tl[1], br[0], br[1],
                outline=color, width=2, tags="overlay"
            )
            self._mirror._overlay_ids.append(rect_id)

        # Show xpath for first match
        first_xpath = xpath_for(results[0], root)
        self._tree_info.configure(text=f"XPath: {expr}\nMatches: {n}\nFirst: {first_xpath}")
        self._status.configure(text=f"XPath found {n} matches for: {expr}")

    def _on_close(self):
        self._stop_cast()
        self.destroy()


def main():
    """Entry point: python -m hos_scrcpy.gui.app  or  hos-scrcpy"""
    setup_logging()

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("ERROR: Pillow is required. Install with: pip install Pillow", file=sys.stderr)
        raise SystemExit(1)

    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
