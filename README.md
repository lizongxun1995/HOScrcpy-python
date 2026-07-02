# HOScrcpy Python API 技术文档

## 1. 项目概述

HOScrcpy Python API 是对鸿蒙 6.0 设备投屏控制 Java 库（`hosscrcpy-*.jar`）的 Python 封装。目标是将 Java 接口完整转化为 Python API，并提供 GUI demo 用于设备投屏和交互式控制。

### 核心能力

| 模块 | 功能 | 底层实现 |
|------|------|---------|
| 设备管理 | 发现、连接、状态检查 | `hdc list targets` |
| 触摸控制 | 按下/抬起/移动/点击/滑动 | `uinput -M` shell 命令 或 Java 协议 |
| 键盘输入 | 按键、文本（含中文）、系统键 | `uinput -K` / `uitest uiInput` |
| 截图 | 截取设备屏幕 JPEG | `snapshot_display` + `file recv` |
| UI 层级 | 导出 UI 树并解析为 JSON | `uitest dumpLayout` + `file recv` |
| 视频流 | 实时投屏到 PC（H.264/PyAV 或 JPEG 双模式） | Java StreamBridge 子进程 或截图轮询 |
| UI 自动化 | uiautomator2 风格查找/点击/等待 | UIFinder + UiSelector + XPath |

---

## 2. 架构设计

### 2.1 总体架构

```
┌──────────────────────────────────────────────────────┐
│                    应用层                              │
│  GUI Demo (tkinter)  │  WS Server  │  Automation      │
└────────────┬──────────────────────┬───────────────────┘
             │  Python API (hos_scrcpy)                 │
             ├──────────────────────────────────────────┤
             │  HOSDevice 统一入口                       │
             │  ├─ TouchController / FastTouch          │
             │  ├─ KeyboardController                   │
             │  ├─ ScreenCapture (3 种流模式)            │
             │  └─ UIHierarchy / UIFinder               │
             ├──────────────┬───────────────────────────┤
             │              │                           │
        hdc 子进程    Java StreamBridge 子进程    PyHmDriver
        (shell cmd)   (H.264/JPEG 视频流)      (纯 Python)
             │              │                           │
             └──────────────┴───────────────────────────┘
                      鸿蒙设备
```

### 2.2 视频流三种模式

| 模式 | 路径 | 延迟 | 依赖 | 适用场景 |
|---|---|---|---|---|
| H.264 raw | Java → PyAV 软解码 → Python | 低 (~30ms) | PyAV | Python 消费 (GUI/自动化/CV) |
| JPEG | Java → FFmpeg 解码 → JPEG → Python | 中 (~50ms) | 无 | 浏览器消费 |
| 截图轮询 | hdc shell snapshot_display | 高 (~500ms) | 无 | 无 JRE 环境/兜底 |

```
┌─────────────────────────────────────────────┐
│  HOSDevice (统一入口)                        │
│  dev.touch / dev.keyboard / dev.screen /    │
│  dev.ui / dev.screenshot()                  │
├─────────────────────────────────────────────┤
│  第二层：Java 子进程 (StreamBridge)           │
│  低延迟 JPEG 流 + 协议级触摸                  │
├─────────────────────────────────────────────┤
│  第一层：hdc 子进程 (subprocess)             │
│  uinput 触摸 / snapshot_display 截图 /       │
│  uitest dumpLayout UI 树                    │
└─────────────────────────────────────────────┘
```

**第一层（hdc 子进程）** 无额外依赖，所有操作通过 `hdc shell` 完成。适合自动化测试和低频操作。

**第二层（Java StreamBridge）** 需要 Java 运行时和 JAR 文件，提供低延迟视频流和协议级触摸传输。适合实时投屏和交互式控制。

### 2.2 包结构

```
hos_scrcpy/
├── __init__.py          # HOSDevice 统一入口 + 公共 API 导出
├── core/                # 底层
│   ├── device.py        # Device 实体 — 截图、UI dump、shell、设备发现
│   ├── hdc_client.py    # hdc 命令行封装（list targets、shell、execute）
│   └── process.py       # 带超时 + stream 读取的子进程执行器
├── input/               # 输入控制
│   ├── touch.py         # TouchController — uinput -M 触摸注入
│   ├── async_touch.py   # AsyncTouchController — 线程安全异步队列
│   ├── fast_touch.py    # FastTouchController — Java stdin 协议级触摸
│   ├── mouse.py         # MouseController — 鼠标事件
│   ├── keyboard.py      # KeyboardController — 按键/文本输入
│   └── keycode.py       # KeyCode 完整键码表 + 字符映射
├── screen/
│   └── capture.py       # ScreenCapture — 统一流管理
│                         #   · start_screenshot_stream()  截图轮询
│                         #   · start_native_stream()      H.264 screenrecord
│                         #   · start_java_stream()        Java StreamBridge
├── ui/
│   ├── hierarchy.py     # JsonStructure — UI 树节点
│   └── selector.py      # UIHierarchy + UiSelector — 链式查找
├── bridge/
│   ├── __init__.py      # start_native_bridge, read_jpeg_frames
│   ├── native_stream.py # Java 子进程管理 + 帧读取
│   ├── StreamBridge.java# Java 端：JPEG 流 + stdin 触摸中继
│   └── extract_servers.py # scrcpy ELF 二进制提取工具
├── gui/
│   └── app.py           # tkinter 投屏 GUI（Demo 模式 + Live 模式）
└── utils/
    ├── bounds.py        # Bounds 坐标解析
    └── logger.py        # 日志（NullHandler 模式，由应用层配置）
```

### 2.3 数据流

```
触摸输入流 (Live 模式):

  tkinter Canvas                        Java StreamBridge
  mouse event                           subprocess
      │                                      │
      ▼                                      │
  DeviceMirror._on_press()                   │
      │                                      │
      ▼                                      │
  canvas→device 坐标转换                      │
      │                                      │
      ▼                                      │
  FastTouchController.down(x,y) ──stdin──▶ StreamBridge.java
                                            │
                                      HosRemoteDevice
                                      .onTouchDown(x,y)
                                            │
                                            ▼
                                        鸿蒙设备


视频帧流 (Live 模式, IMAGE):

  StreamBridge.java ──stdout──▶ read_jpeg_frames()
   (4字节长度前缀                  │
    + JPEG数据)                   ▼
                            _on_frame(jpeg)
                                  │
                                  ▼
                            _latest_frame (共享变量)
                                  │
                    threading.Event.set()
                                  │
                                  ▼
                            _render_tick() [主线程]
                                  │
                                  ▼
                            DeviceMirror.set_jpeg()
                                  │
                                  ▼
                            tkinter Canvas
```

---

## 3. 视频流模式

### 3.1 Java StreamBridge IMAGE 模式（主模式）

**流程**：
1. Python 启动 `java -cp ... StreamBridge <sn> <ip> <port> <hdc>`
2. Java 调用 `HosRemoteDevice.startImageScreenCapture(callback)`
3. 每帧回调通过 stdout 输出：`[4字节大端长度][JPEG数据]`
4. Python `read_jpeg_frames()` 解析长度前缀，yield JPEG 字节
5. 主线程 `_render_tick()` 定时（~30fps）渲染最新帧到 Canvas

**触摸中继**：
- Python 通过 Java stdin 发送 `D:544:1953\n` / `M:548:1973\n` / `U:823:1146\n`
- Java `startTouchReader()` 线程读取 stdin，调用 `HosRemoteDevice.onTouchDown/Move/Up()`

**协议格式**：

| 命令 | 格式 | 含义 |
|------|------|------|
| D | `D:x:y` | Touch down |
| M | `M:x:y` | Touch move |
| U | `U:x:y` | Touch up |

**JPEG 帧格式**（stdout 二进制）：
```
[0x00 0x00 0xNN 0xNN] [FF D8 ... JPEG data ... FF D9]
   4字节 Big-Endian 长度
```

### 3.2 截图轮询模式（回退模式）

当 Java 不可用时自动启用。循环调用 `snapshot_display -f /data/local/tmp/screen.jpeg` → `file recv` → 读取文件。

- 帧率：~2 fps（500ms 间隔）
- 触摸：使用 `AsyncTouchController`（异步队列，不阻塞 UI 线程）
- 优点：纯 Python，无 Java 依赖

### 3.3 H.264 screenrecord 模式（可选，需 PyAV）

使用 `hdc shell screenrecord --output-format=h264 -` 直接输出 H.264 裸流，PyAV 解码为 JPEG。

- 需要 `pip install av`
- 比截图轮询帧率高，但不如 Java 流稳定
- NAL unit 边界分割 + PyAV 解码

---

## 4. 触摸系统

### 4.1 三种 TouchController

| 控制器 | 协议 | 延迟 | 阻塞 | 使用场景 |
|--------|------|------|------|---------|
| `TouchController` | `uinput -M` shell | 高（每命令一次 hdc） | 阻塞 | 自动化脚本 |
| `AsyncTouchController` | `uinput -M` shell | 高 | 非阻塞（队列） | 截图轮询模式 GUI |
| `FastTouchController` | Java stdin 协议 | 低（<1ms） | 非阻塞 | Java 流模式 GUI |

### 4.2 uinput 命令参考

```bash
# 触摸
uinput -M -m {x} {y} -c {contact}    # 按下/抬起（-c 指定触点）
uinput -M -m {x} {y}                  # 移动

# 鼠标
uinput -M -m {x} {y} -c 0            # 左键点击
uinput -M -m {x} {y} -c 1            # 右键点击
uinput -M -m {x} {y} -s -500         # 滚轮上滚
uinput -M -m {x} {y} -s 500          # 滚轮下滚

# 键盘
uinput -K -d {keycode} -u {keycode}  # 按下并释放
uinput -K -d 2047 -d {kc} -u {kc} -u 2047  # Shift 组合键

# 系统键
uinput -K -d 2 -u 2    # 返回
uinput -K -d 18 -u 18  # 电源
uinput -K -d 17 -u 17  # 音量减
uinput -K -d 16 -u 16  # 音量加
```

### 4.3 坐标变换

GUI 中鼠标坐标经过两次变换：

```
Canvas 坐标 (tkinter event.x, event.y)
    │
    ▼ _canvas_to_device()
图片坐标 (缩放到显示尺寸内的坐标)
    │
    ▼ 按比例缩放
设备坐标 (实际屏幕分辨率，如 1280×2832)
```

关键代码见 `DeviceMirror._canvas_to_device()`：
```python
# 1. 考虑缩放 + 居中偏移
scale = min(cw / iw, ch / ih)
dx = int((cx - ox) / scale)
dy = int((cy - oy) / scale)
# 2. 缩放至设备分辨率
sx = self._device_width / iw
sy = self._device_height / ih
dx = int(dx * sx)
dy = int(dy * sy)
```

---

## 5. UI 层级系统

### 5.1 数据获取

```python
# 设备端操作
hdc shell uitest dumpLayout
# → 输出: "DumpLayout saved to: /data/local/tmp/layout_xxx.json"

hdc file recv /data/local/tmp/layout_xxx.json local_path.json
```

### 5.2 JsonStructure 树

`uitest dumpLayout` 输出 JSON 格式：
```json
{
  "attributes": {"type": "Button", "text": "确定", "bounds": "[0,100][200,150]"},
  "children": [...],
  "index": 0
}
```

`JsonStructure` 提供 Pythonic 访问：
- `node.type` / `node.text` / `node.id` — 属性
- `node.rectangle` — `(x, y, width, height)`
- `node.center` — 中心点 `(x+w//2, y+h//2)`
- `node.is_clickable` / `node.is_scrollable` — 布尔属性
- `node.iter_all()` — 深度优先遍历
- `node.find_first(predicate)` / `node.find_all(predicate)` — 查找

### 5.3 UiSelector 链式查询

模拟 Android UiSelector API：

```python
root = dev.ui.dump()
sel = UiSelector(root)

# 链式过滤
result = (sel
    .type("Button")
    .text_contains("OK")
    .clickable()
    .first())

# 坐标查找（最小包围元素）
widget = UiSelector(root).at_point(500, 300).first()
```

`UIHierarchy._compute_paths()` 自动生成 XPath 风格的路径：
```
/Root/ScrollView[0]/ListItem[2]/Button[0]
```

---

## 6. GUI 架构

### 6.1 两种模式

**Demo 模式**（无需设备）：
- 生成仿 HarmonyOS 设置页面的假截图
- `_MockTouch` 输出日志到控制台
- 点击/拖拽/滚轮有视觉涟漪反馈

**Live 模式**（需真机）：
- 选择设备 → Start Cast → 实时投屏
- 优先使用 Java StreamBridge IMAGE 流
- Java 不可用时自动回退截图轮询
- 触摸操作实时映射到真机

### 6.2 线程模型

```
主线程 (tkinter)
  ├── _render_tick()    — 30fps 渲染循环（Event 驱动）
  ├── Canvas 事件处理   — _on_press/_on_drag/_on_release
  └── UI 更新           — 状态栏、按钮状态

后台线程
  ├── _stream_loop()    — 视频帧读取 + _on_frame() 回调
  ├── _connect()        — 设备连接检查
  ├── _scan()           — 设备扫描（_refresh_devices）
  ├── _log_java()       — Java stderr 日志监控
  └── AsyncTouchController._worker()  — 触摸命令队列

线程安全：
  - _latest_frame: 后台写，主线程读（GIL 保护简单赋值）
  - _frame_ready Event: 后台 set，主线程 wait
  - tkinter widget: 仅主线程通过 self.after() 操作
```

### 6.3 连接流程

```
_start_cast()
    │
    ▼
Device(sn_str) 创建 + is_online() 检查  [后台线程]
    │
    ▼
screenshot() 获取首帧                    [后台线程]
    │
    ▼
_on_connect_ok(jpeg)
    │
    ├── 显示首帧
    ├── 启动 _render_tick()             [主线程 30fps]
    └── 启动 _stream_loop()             [后台线程]
         │
         ├── ScreenCapture.start_java_stream()
         │   ├── 成功 → FastTouchController
         │   └── 失败 → start_screenshot_stream() + AsyncTouchController
         │
         └── 帧到达 → _on_frame()
              └── _latest_frame = jpeg; _frame_ready.set()
```

---

## 7. 配置与环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `HOS_SCRCPY_HOME` | HOScrcpy 安装根目录 | — |
| `HOS_SCRCPY_LIBS` | JAR 库目录（直接路径） | `$HOS_SCRCPY_HOME/HOScrcpy/libs` |
| `HOS_SCRCPY_FFMPEG` | ffmpeg 可执行文件路径 | `~/.hos-scrcpy/ffmpeg/ffmpeg.exe` |

### hdc 搜索顺序

1. `~/.hos-scrcpy/toolchains/hdc.exe`
2. `$PATH` 中的 `hdc`

### JAR 搜索顺序

1. `$HOS_SCRCPY_LIBS`
2. `$HOS_SCRCPY_HOME/HOScrcpy/libs`
3. 包内 `hos_scrcpy/bridge/libs/`
4. 当前目录 `./libs/`

---

## 8. API 参考

### 8.1 HOSDevice（统一入口）

```python
from hos_scrcpy import HOSDevice

# 设备发现
HOSDevice.list_devices() → list[Device]
HOSDevice.list_remote(ips) → list[Device]

# 连接
dev = HOSDevice.connect(sn, ip="127.0.0.1", port="8710")

# 属性
dev.sn          # 序列号
dev.ip          # IP 地址
dev.device      # 底层 Device 对象
dev.touch       # TouchController
dev.keyboard    # KeyboardController
dev.screen      # ScreenCapture（流管理）
dev.ui          # UIHierarchy（UI 树）

# 快捷方法
dev.screenshot(save_path=None) → bytes | None
dev.dump_layout(save_path=None) → str | None
dev.execute_shell(cmd, timeout=10) → str
dev.is_online() → bool

# 上下文管理器（自动停止流）
with dev:
    pass  # 自动调用 dev.screen.stop()
```

### 8.2 TouchController

```python
touch.down(x, y, contact=0)          # 按下
touch.move(x, y)                     # 移动
touch.up(x, y, contact=0)            # 抬起
touch.click(x, y, duration=0.05)     # 点击
touch.long_press(x, y, duration=1.0) # 长按
touch.swipe(x1, y1, x2, y2, duration=0.3, steps=10)  # 滑动
```

### 8.3 KeyboardController

```python
keyboard.press(keycode)              # 按键
keyboard.input_text("Hello 世界")    # 文本（含中文）
keyboard.type("abc123")             # 逐字输入
keyboard.type_char('A')             # 单字符
keyboard.home() / back() / power()  # 系统键
keyboard.volume_up() / volume_down()
keyboard.enter() / backspace() / space()
keyboard.paste()                    # Ctrl+V
```

### 8.4 ScreenCapture

```python
cap = ScreenCapture(device)

# Java 流（推荐，低延迟）
touch = cap.start_java_stream(on_frame=jpeg_callback)
# → 返回 FastTouchController 或 None

# 截图轮询（回退方案）
cap.start_screenshot_stream(on_frame, interval=0.5)

# H.264 低延迟模式（需 PyAV: pip install av）
touch = cap.start_java_stream(on_frame, raw_mode=True)  # <1ms 延迟，60fps
# JPEG 兼容模式（无需 PyAV）
touch = cap.start_java_stream(on_frame, raw_mode=False)  # Java 侧解码

# H.264 流（需 PyAV）
cap.start_native_stream(on_frame, on_error, on_ready)

cap.stop()
cap.is_streaming → bool
```

### 8.4a UIFinder（uiautomator2 风格）

```python
dev.click_by_text("Settings")          # 按文本点击
dev.exists_text("OK")                  # 判断元素是否存在
dev.wait_text("加载完成", timeout=10)   # 等待元素出现
info = dev.get_info_by_id("title")     # 获取元素完整属性

# 或直接访问 finder
dev.finder.find(type="Button", clickable=True)
```

### 8.5 UIHierarchy + UiSelector

```python
ui = UIHierarchy(device)
root = ui.dump()                     # → JsonStructure | None

# 直接查找
ui.find_by_type("Button")
ui.find_by_id("submit_btn")
ui.find_by_text("OK")
ui.find_at_point(500, 300)           # 最小包围元素

# 链式选择器
UiSelector(root)\
    .type("Button")\
    .text_contains("OK")\
    .clickable()\
    .first()

# 自定义过滤器
UiSelector(root).where(lambda n: n.rectangle[2] > 100).all()
```

### 8.6 KeyCode

```python
from hos_scrcpy import KeyCode, keycode_for_char

KeyCode.HOME = 17         KeyCode.BACK = 2
KeyCode.POWER = 18        KeyCode.ENTER = 2119
KeyCode.BACKSPACE = 2055  KeyCode.SPACE = 2050
KeyCode.SHIFT = 2047      KeyCode.CTRL = 2072
KeyCode.A = 2017          KeyCode.Z = 2042
KeyCode.DIGIT_0 = 2000    KeyCode.DIGIT_9 = 2009
KeyCode.VOLUME_UP = 16    KeyCode.VOLUME_DOWN = 17

keycode_for_char('A') → 2017
keycode_for_char('z') → 2042
keycode_for_char('!') → -1  # 不可映射
```

---

## 9. 开发指南

### 9.1 运行测试

```bash
python test_smoke.py          # 冒烟测试（无需设备）
```

### 9.2 启动 GUI

```bash
# Demo 模式（无需设备）
python -m hos_scrcpy.gui.app

# 安装后
pip install -e .
hos-scrcpy
```

### 9.3 添加新的设备命令

1. 在 `Device` 类中添加方法，通过 `self._client.shell()` 或 `self._client.execute()` 调用 hdc
2. 如需暴露给 `HOSDevice`，在 `__init__.py` 中添加代理方法

### 9.4 添加新的触摸控制器

1. 实现 `down(x,y)` / `up(x,y)` / `move(x,y)` / `swipe(...)` 接口
2. 在 `app.py` 的 `_stream_loop` 中根据条件选择控制器
3. 通过 `self._mirror.set_controllers(touch, keyboard)` 注入 GUI

---

## 10. 已知限制

- **hdc 必须在 PATH** 或 `~/.hos-scrcpy/toolchains/` 目录
- **Java StreamBridge** 需要 JRE 8+ 和 `hosscrcpy-*.jar` 在 classpath
- **截图/UI dump** 走设备端 `/data/local/tmp/` 临时目录
- **坐标映射** 假定设备竖屏（portrait），横屏需旋转坐标
- **H.264 流** 依赖 PyAV（`pip install av`），部分设备 screenrecord 不可用
- **资源管理** 推荐使用 `with dev:` 上下文管理器确保 Java 进程正确释放
