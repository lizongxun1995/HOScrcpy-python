# HOScrcpy Python API 使用指南

## 1. 简介

HOScrcpy 是鸿蒙设备投屏控制 Python API，封装了 `hdc` 命令行和 `hosscrcpy-*.jar` SDK，提供触摸、键盘、屏幕捕获、UI 层级树等完整控制能力。

### 核心特性

- 触摸/鼠标/键盘注入
- 实时设备截图
- 视频流投屏（Java StreamBridge / H.264 screenrecord / 截图轮询）
- UI 层级树 dump 与 XPath 查找
- GUI demo（tkinter 投屏窗口）
- WebSocket 服务器（Web 端远程投屏）
- WiFi 无线调试

---

## 2. 环境要求

| 组件 | 说明 |
|------|------|
| Python | >= 3.10 |
| Pillow | >= 10.0（核心依赖，内置） |
| hdc | HarmonyOS Device Connector（**已内置**于 `hos_scrcpy/toolchains/`） |
| Java | JRE 8+（可选，视频流低延迟需要） |
| PyAV | `pip install av`（可选，H.264 screenrecord 模式） |

---

## 3. 安装

```bash
# 基础安装
pip install hos-scrcpy

# 开发模式安装
pip install -e .

# 全功能安装
pip install hos-scrcpy[all]

# 仅 WebSocket 服务器
pip install hos-scrcpy[server]
```

### hdc 搜索顺序

1. 包内 `hos_scrcpy/toolchains/hdc.exe`（优先）
2. `~/.hos-scrcpy/toolchains/hdc.exe`
3. 系统 PATH 中的 `hdc`

---

## 4. 快速开始

### 4.1 启动 Demo（最简单的方式）

```bash
# 图形化投屏 Demo
python -m demo.app

# 指定设备直接连接
python -m demo.app --sn DEVICE_SN
```

Demo 启动后界面包含：
- **设备列表下拉框**：自动扫描并列出可用设备
- **连接/断开按钮**：一键连接或断开设备
- **投屏画布**：实时显示设备画面，支持鼠标触控
- **设备刷新按钮**：重新扫描设备列表
- **状态栏**：显示连接状态和帧率

### 4.2 Demo 连接流程

```
点击「连接」
    │
    ▼
扫描设备（HOSDevice.list_devices()）
    │
    ▼
用户选择设备 → _connect_device(sn)
    │
    ├── Device(sn) 创建
    ├── dev.is_online() 在线检查
    ├── self._mirror.reset_h264_state() 重置解码器
    ├── ScreenCapture(dev) 创建捕获器
    └── cap.start_java_stream(on_frame, wait_ready=True)
         │
         ├── _restart_hdc() 清理残留转发规则 + 设备端旧文件
         ├── _cleanup_stale_procs() 杀僵尸 Java 进程
         ├── _push_scrcpy_library() 预推 scrcpy 库到设备
         ├── subprocess.Popen(java StreamBridge) 启动 Java 子进程
         └── 等待 Java READY 信号（最多 35s）
              │
              ▼
         FastTouchController(java_proc) 创建触摸控制器
              │
              ▼
         _stream_loop() 后台线程读取视频帧
              │
              ▼
         _render_tick() 主线程渲染（每 16ms）
```

### 4.3 流模式选择

Demo 默认使用 **JPEG 模式**（`raw_mode=False`），无需 PyAV。两种模式对比：

| 模式 | `raw_mode` | 解码位置 | 延迟 | Python 依赖 | 适用 |
|------|-----------|---------|------|------------|------|
| JPEG | `False`（默认） | Java 端 FFmpeg → JPEG | ~50ms | 无 | 通用、浏览器 |
| Raw H.264 | `True` | Python 端 PyAV | ~30ms | `pip install av` | 低延迟 GUI/CV |

```python
# JPEG 模式（默认，推荐）
touch = cap.start_java_stream(on_frame, raw_mode=False)

# Raw H.264 模式（需 PyAV）
touch = cap.start_java_stream(on_frame, raw_mode=True)
```

> **注意**：Raw H.264 模式下，SDK 的 SPS/PPS 通过 out-of-band 方式传递，可能不可靠。
> JPEG 模式由 Java 端 FFmpeg 完整处理 H.264 解码，兼容性更好，推荐作为默认。

### 4.4 视频帧渲染管线

```
StreamBridge.java (Java 子进程)
    │
    │  HosRemoteDevice.startImageScreenCapture(callback)
    │  每帧回调：FFmpeg 解码 H.264 → JPEG 编码 → stdout
    │
    ▼
read_frames(proc)  (Python 后台线程)
    │
    │  读取 [4字节大端长度][JPEG数据]
    │  yield JPEG bytes
    │
    ▼
_on_frame(jpeg_bytes)  (回调)
    │
    ├── self._latest_frame = jpeg_bytes  (更新最新帧)
    └── self._frame_ready.set()          (通知渲染线程)
         │
         ▼
_render_tick()  (主线程，每 16ms)
    │
    ├── 读取 self._latest_frame
    ├── self._mirror.show_jpeg(jpeg)
    │   ├── Image.open() 解码 JPEG
    │   └── canvas.create_image() 渲染
    └── self.after(16, self._render_tick)  (调度下一帧)
```

### 4.5 触控管线

```
Canvas 鼠标事件 (tkinter)
    │
    ▼
_on_press / _on_drag / _on_release
    │
    ▼
_canvas_to_device(cx, cy)  坐标变换
    │  Canvas 坐标 → 设备坐标（考虑缩放+居中偏移）
    ▼
FastTouchController
    │
    ├── down(x, y)  →  stdin:  "D:544:1953\n"
    ├── move(x, y)  →  stdin:  "M:548:1973\n"  (限速20/s, <10px跳过)
    └── up(x, y)    →  stdin:  "U:823:1146\n"
         │
         ▼
StreamBridge.java (touch-reader 线程)
    │
    │  BufferedReader.readLine()
    │  解析 D:/M:/U: 前缀
    │
    ▼
HosRemoteDevice.onTouchDown/Move/Up(x, y)
    │
    ▼
鸿蒙设备
```

触控协议格式：

| 命令 | 格式 | 含义 |
|------|------|------|
| D | `D:x:y` | Touch down |
| M | `M:x:y` | Touch move |
| U | `U:x:y` | Touch up |

### 4.6 坐标变换

```
Canvas 坐标 (event.x, event.y)
    │
    ▼ _canvas_to_device()
图片坐标（去掉缩放+居中偏移）
    │
    ▼ 按比例映射
设备坐标（实际屏幕分辨率，如 1280×2832）
```

```python
def _canvas_to_device(self, cx, cy):
    cw, ch = self._mirror.winfo_width(), self._mirror.winfo_height()
    iw, ih = self._mirror._img.width, self._mirror._img.height
    
    # 1. 计算缩放和居中偏移
    scale = min(cw / iw, ch / ih)
    ox = (cw - iw * scale) / 2
    oy = (ch - ih * scale) / 2
    
    # 2. Canvas 坐标 → 图片坐标
    dx = int((cx - ox) / scale)
    dy = int((cy - oy) / scale)
    
    # 3. 图片坐标 → 设备坐标
    dx = int(dx * self._mirror._dev_w / iw)
    dy = int(dy * self._mirror._dev_h / ih)
    
    return max(0, min(dx, self._mirror._dev_w)), max(0, min(dy, self._mirror._dev_h))
```

### 4.7 Demo 和 GUI 两种入口

项目提供两个 GUI 入口，用途不同：

| 入口 | 命令 | 特点 |
|------|------|------|
| Demo App | `python -m demo.app` | 单文件，自包含，适合学习和二次开发 |
| GUI App | `python -m hos_scrcpy.gui.app` | 模块化，带 UI 层级树，适合日常使用 |

Demo App (`demo/app.py`) 是单文件实现，所有逻辑内聚，方便理解整个投屏流程。
GUI App (`hos_scrcpy/gui/app.py`) 使用项目模块化结构，额外提供 UI 层级树查看、XPath 搜索功能。

```python
with HOSDevice.connect("SN123456") as dev:
    dev.touch.click(100, 200)
    jpeg = dev.screenshot()
# 自动停止视频流、清理资源
```

---

## 5. WiFi 无线调试

类似 ADB 的 `adb tcpip` + `adb connect`。

```python
# Step 1: USB 模式下开启 WiFi 调试（设备会重启）
dev = HOSDevice.connect("SN123456")
dev.enable_tcp_mode("8710")

# Step 2: 设备重启后，通过 WiFi 连接
dev.connect_remote("192.168.1.100", "8710")

# Step 3: 保存 IP 以便下次自动发现
from hos_scrcpy.utils.settings import add_remote_ip
add_remote_ip("192.168.1.100:8710")

# 切回 USB 模式
dev.enable_usb_mode()
```

或者直接用 hdc 命令行：

```bash
# 开启 WiFi 模式
hdc tmode port 8710

# 连接
hdc tconn 192.168.1.100:8710

# 断开
hdc tconn 192.168.1.100:8710 -remove
```

---

## 6. 视频流

### 6.1 Java StreamBridge JPEG 模式（推荐，默认）

Java 端 FFmpeg 完成 H.264 解码 + JPEG 编码，Python 端直接显示 JPEG。
无需 PyAV，兼容性最好。

```python
capture = dev.screen

# JPEG 模式（默认），返回 FastTouchController（低延迟触控）
touch = capture.start_java_stream(on_frame)
# 等价于
touch = capture.start_java_stream(on_frame, raw_mode=False)

def on_frame(jpeg_bytes: bytes):
    """每帧回调，jpeg_bytes 是完整 JPEG 数据"""
    with open("frame.jpg", "wb") as f:
        f.write(jpeg_bytes)
```

**启动流程**：
1. `_restart_hdc(hdc_path, sn, ip, port)` — 清理端口转发 + 设备端残留进程和库文件
2. `_cleanup_stale_procs(sn)` — 杀同设备残留 Java 进程
3. `_push_scrcpy_library(sn, ip, port, hdc_path)` — 预推 scrcpy 库到 `/data/local/tmp/`
4. `subprocess.Popen(java StreamBridge)` — 启动 Java 子进程
5. 等待 Java `READY` 信号（最多 35s 超时）
6. 返回 `FastTouchController(java_proc)` 用于低延迟触控

**Java 端处理**：
- `HosRemoteDevice.startImageScreenCapture(callback)` 启动截图
- FFmpeg 解码 H.264 → `javax.imageio.ImageIO` 编码 JPEG
- stdout 输出 `[4字节大端长度][JPEG数据]`，每帧 `flush()`
- stdin 接收触控命令 `D:x:y` / `M:x:y` / `U:x:y`

### 6.2 Java StreamBridge Raw H.264 模式（需 PyAV）

Java 端直通原始 H.264 NAL 单元，Python 端 PyAV 软解码。
延迟更低但 SPS/PPS 传递依赖 SDK 内部行为。

```python
# Raw H.264 模式（需 pip install av）
touch = capture.start_java_stream(on_frame, raw_mode=True)
```

> **已知限制**：SDK 通过 out-of-band 方式传递 SPS/PPS，不一定出现在 `onData` 回调中。
> 如需使用 Raw 模式，建议搭配 `requestIDRFrame()` 强制编码器输出 SPS+PPS+IDR。

### 6.3 H.264 screenrecord（需 PyAV）

```python
capture.start_native_stream(on_frame)
```

通过 `hdc shell screenrecord --output-format=h264 -` 管道输出 H.264 裸流。
比截图轮询帧率高，但部分设备 `screenrecord` 不可用。

### 6.4 截图轮询（纯 Python，~2fps）

```python
capture.start_screenshot_stream(on_frame, interval=0.5)
```

循环调用 `snapshot_display -f /tmp/screen.jpeg` → `file recv`。
纯 Python，无 Java 依赖，适用于无 JRE 环境或兜底方案。

### 6.5 流模式选择建议

```
Java 可用？
 ├── 是 → start_java_stream(raw_mode=False)  ← 推荐
 │        ├── 需要低延迟 + 有 PyAV → raw_mode=True
 │        └── 通用/浏览器 → raw_mode=False
 └── 否 → PyAV 可用？
           ├── 是 → start_native_stream()
           └── 否 → start_screenshot_stream()
```

---

## 7. UI 自动化

### 7.1 uiautomator2 风格操作（推荐）

```python
# 一键点击
dev.click_by_text("Settings")          # 按文本
dev.click_by_id("submit_btn")          # 按 ID
dev.click_by_xpath("//Button[0]")      # 按 XPath
dev.click_by_description("返回")       # 按描述

# 存在判断
if dev.exists_text("OK"):
    print("OK 按钮存在")

# 等待元素出现
node = dev.wait_text("加载完成", timeout=10)
if node:
    dev.click_by_text("加载完成")

# 获取信息
text = dev.get_text_by_id("title")
info = dev.get_info_by_text("OK")      # 返回完整属性字典
```

### 7.2 Dump UI 树

```python
root = dev.dump_ui()  # 或 dev.ui.dump()
```

### 7.3 高级查找

```python
# 通过 dev.finder 进行多条件查找
results = dev.finder.find(type="Button", clickable=True, enabled=True)
count = dev.finder.count(text="OK")
```

### 7.4 链式选择器（原 API，更精确）

```python
# 直接查找
buttons = ui.find_by_type("Button")
ok_buttons = ui.find_by_text("OK")

# 链式选择器
from hos_scrcpy import UiSelector

result = (UiSelector(root)
    .type("Button")
    .text_contains("OK")
    .clickable(True)
    .first())

if result:
    dev.touch.click(*result.center)

# XPath 查找
from hos_scrcpy.ui.xpath import find_by_xpath
matches = find_by_xpath(root, "//*[@clickable=true]")
```

---

## 8. GUI Demo

两个 GUI 入口：

```bash
# Demo App（单文件，适合学习）
python -m demo.app
python -m demo.app --sn DEVICE_SN    # 直接连接指定设备

# GUI App（模块化，带 UI 层级树）
python -m hos_scrcpy.gui.app
```

### 8.1 Demo App 界面功能

| 组件 | 功能 |
|------|------|
| 设备下拉框 | 自动扫描，选择目标设备 |
| 连接/断开按钮 | 一键连接或断开设备 |
| 刷新按钮 | 重新扫描设备列表 |
| 投屏画布 | 实时显示设备画面，鼠标触控 |
| 状态栏 | 连接状态、帧率统计 |

### 8.2 Demo App 关键类

| 类 | 文件 | 职责 |
|----|------|------|
| `DemoApp(tk.Tk)` | `demo/app.py` | 主窗口，设备管理，线程调度 |
| `MirrorCanvas(tk.Canvas)` | `demo/app.py` | 投屏画布，帧渲染，触控事件 |
| `ScreenCapture` | `hos_scrcpy/screen/capture.py` | 统一流管理（3 种模式） |
| `FastTouchController` | `hos_scrcpy/input/fast_touch.py` | Java stdin 协议触控 |
| `Device` | `hos_scrcpy/core/device.py` | 设备实体（SN、IP、截图等） |

### 8.3 线程模型

```
主线程 (tkinter)
  ├── _render_tick()    — 30fps 渲染循环
  ├── Canvas 事件处理   — 鼠标按下/拖拽/释放
  └── UI 更新           — 状态栏、按钮状态

后台线程
  ├── _stream_loop()    — read_frames() → _on_frame() 回调
  ├── _connect()        — 设备连接 + 在线检查
  ├── _scan()           — 设备扫描 (_refresh_devices)
  └── touch-reader      — Java 端 stdin 触控读取

线程安全：
  - _latest_frame: 后台写，主线程读
  - _render_busy: 简单的帧跳跃锁
  - tkinter widget: 仅主线程通过 self.after() 操作
```

### 8.4 GUI App 额外功能

| 功能 | 说明 |
|------|------|
| UI 层级树 | Dump UI → 树形展示 → 选中节点高亮 |
| XPath 搜索 | 输入 XPath 表达式查找元素 |
| 工具栏按钮 | Power / Home / Back 快捷操作 |
| Demo 模式 | 无需设备，生成模拟手机画面 |

---

## 9. WebSocket 服务器

```bash
python -m hos_scrcpy.server.ws_server --sn SN123456 --port 8765
```

浏览器打开 `http://localhost:8765`：
- 实时投屏
- 触控操作映射到设备
- Power / Home / Back 按钮

---

## 10. 配置

### 10.1 持久化配置

配置文件位置：`~/.hos-scrcpy/config.json`

```json
{
    "remote_ips": ["192.168.1.100:8710"],
    "use_video_stream": false,
    "default_port": "8710"
}
```

API 操作：
```python
from hos_scrcpy.utils.settings import *

add_remote_ip("192.168.1.101:8710")
set_use_video_stream(True)
```

### 10.2 Java StreamBridge 配置

| 环境变量 | 用途 | 默认值 |
|----------|------|--------|
| `JAVA_HOME` | JDK/JRE 安装目录 | — |
| `HOS_SCRCPY_JAVA` | Java 可执行文件路径 | — |
| `HOS_SCRCPY_HOME` | HOScrcpy 安装根目录 | — |
| `HOS_SCRCPY_LIBS` | JAR 库目录（直接路径） | `$HOS_SCRCPY_HOME/HOScrcpy/libs` |

**Java 搜索顺序**：
1. `$JAVA_HOME/bin/java`（或 `.exe`）
2. `$HOS_SCRCPY_JAVA`
3. 系统 `PATH` 中的 `java`
4. Windows 常见 JDK 安装目录（`C:\Program Files\Microsoft\`, `Eclipse Adoptium`, `Java`, `Android\openjdk`）

**JAR 库搜索顺序**：
1. `$HOS_SCRCPY_LIBS`
2. `$HOS_SCRCPY_HOME/HOScrcpy/libs`
3. 包内 `hos_scrcpy/bridge/libs/`
4. 开发模式回退：`HOScrcpy-main/HOScrcpy/libs/`
5. 当前目录 `./libs/`

**StreamBridge 启动命令**（自动构建）：
```bash
java -cp "libs/*;bridge_dir" StreamBridge <sn> <ip> <hdc_port> <hdc_path>
```

**HosRemoteConfig 参数**（`StreamBridge.java` 内设置）：

| 参数 | 值 | 说明 |
|------|-----|------|
| `setImageScaleSize` | 720 | 短边缩放到 720px |
| `setFrameRate` | 30 | 目标帧率 |
| `setBitRate` | 4000000 | 4 Mbps 码率 |

### 10.3 进程生命周期

```
启动时:
  _restart_hdc()        清理 hdc 端口转发 + 设备端 screen_casting 进程 + 残留 so 文件
  _cleanup_stale_procs() 杀同设备的残留 Java StreamBridge 进程
  _push_scrcpy_library() 预推备用 scrcpy 库到设备（可选，跳过则 SDK 自动处理）
  subprocess.Popen()    启动 Java 子进程
  注册 atexit 清理      确保进程退出时 Java 子进程被终止

断开时:
  ScreenCapture.stop()
    ├── _kill_proc_tree(java_proc)  递归杀 Java 进程树
    ├── _unregister_proc()          从全局追踪列表移除
    └── 线程 join(3s)               等待流线程退出

复连时:
  _connect_device()
    ├── 已有连接 → _disconnect() 断开旧连接
    ├── self._mirror.reset_h264_state() 清除解码器状态
    └── 创建新连接...
```

---

## 11. 项目结构

```
hos_scrcpy/
├── __init__.py          # HOSDevice 统一入口
├── core/                # 底层
│   ├── device.py        # Device 实体
│   ├── hdc_client.py    # hdc 命令封装
│   └── process.py       # 子进程执行器
├── input/               # 输入控制
│   ├── touch.py         # TouchController (uinput shell)
│   ├── async_touch.py   # AsyncTouchController (非阻塞队列)
│   ├── fast_touch.py    # FastTouchController (Java stdin 协议)
│   ├── mouse.py         # MouseController
│   ├── keyboard.py      # KeyboardController
│   └── keycode.py       # KeyCode 键码表
├── screen/
│   └── capture.py       # ScreenCapture (3 种流模式)
├── ui/
│   ├── hierarchy.py     # JsonStructure UI 树节点
│   ├── selector.py      # UIHierarchy + UiSelector
│   └── xpath.py         # XPath 引擎
├── bridge/
│   ├── native_stream.py # Java 子进程管理
│   └── StreamBridge.java
├── server/
│   └── ws_server.py     # WebSocket 服务器
├── gui/
│   └── app.py           # tkinter 投屏 GUI
├── utils/
│   ├── bounds.py        # 坐标解析
│   ├── logger.py        # 日志
│   └── settings.py      # 持久化配置
└── toolchains/
    └── hdc.exe          # 内置 hdc
```

---

## 12. 常见问题

### 截图/触摸不工作？

检查 hdc 是否可用：
```python
from hos_scrcpy.core.hdc_client import HdcClient
print(HdcClient.is_available())
```

### Java 流启动失败？

1. 检查 Java 是否安装：`java -version`
2. 检查 JAR 文件是否存在（需在 `HOScrcpy-main/HOScrcpy/libs/` 目录）
3. 如 Java 不可用，自动回退截图模式

### 画面延迟高？

- 优先使用 Java StreamBridge（低延迟）
- WiFi 连接比 USB 延迟高 50-100ms
- 截图轮询模式下延迟约 500ms

## 投屏架构对比

项目提供了三种投屏 Demo，架构不同适用场景不同：

### 1. GUI Demo（Python tkinter）
```
python -m hos_scrcpy.gui.app
```
- **架构**: Java H.264 raw → PyAV 软解码 → PIL Image → tkinter Canvas
- **特点**: 纯 Python UI，适合桌面控制、自动化测试集成
- **依赖**: PyAV (`pip install av`)
- **帧率**: ~50fps

### 2. Python WebSocket 服务器
```
python -m hos_scrcpy.server.ws_server --port 8765
```
- **架构**: Java JPEG → stdout → Python → WebSocket → 浏览器 `<img>`
- **特点**: 远程访问，设备控制和投屏在浏览器中完成
- **依赖**: 无需 PyAV（JPEG 模式）
- **帧率**: ~40fps

### 3. Java WebSocket Demo（官方）
位于 `HOScrcpy-main/HOScrcpy-main/web_demo/`
- **架构**: Java SDK → ByteBuffer → WebSocket → 浏览器 JMuxer.js + `<video>` GPU 硬解
- **特点**: 零中间环节，最低延迟/最高帧率
- **帧率**: 60fps

### 多设备切换 Java 进程残留？

v0.2.0+ 已修复进程生命周期管理：
- 切换设备时只清理当前设备的残留进程，不影响其他设备
- `hdc kill` 已移除，改为精确清理转发规则
- 线程使用 generation ID 防止竞态

```python
# 安全的多设备切换
dev1 = HOSDevice.connect("SN_DEVICE_1")
with dev1:
    dev1.touch.click(100, 200)
# dev1 自动清理

dev2 = HOSDevice.connect("SN_DEVICE_2")
with dev2:
    dev2.screen.start_java_stream(on_frame)
# dev2 自动清理，不会影响 dev1
```

### 布尔属性误判？

`JsonStructure` 正确解析 `"true"/"false"/"True"/"False"/"TRUE"/"FALSE"/"1"/"0"`。
