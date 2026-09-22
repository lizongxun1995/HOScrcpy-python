# 使用指南

HOScrcpy 是鸿蒙设备投屏控制 Python API。如果还不知道这是干什么的，先看 [README](../README.md)。

## 环境

| 组件 | 说明 |
|------|------|
| Python | >= 3.10 |
| Pillow | >= 10.0（核心依赖，内置） |
| grpcio | >= 1.60（核心依赖，内置，gRPC 视频通道） |
| hdc | HarmonyOS Device Connector（**已内置**于 `hos_scrcpy/toolchains/`） |
| PyAV | `pip install av`（可选，H.264 解码） |

---

## 安装

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

## 快速开始

启动 Demo（最简单）：

```bash
python -m demo.app                    # 自动扫描设备
python -m demo.app --sn DEVICE_SN     # 直接连指定设备
```

界面：设备下拉框、连接/断开按钮、投屏画布（鼠标直接操作设备）、状态栏帧率。

### Demo 连接内部流程

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
    └── cap.start_grpc_stream(on_frame, wait_ready=True)
         │
         ├── HosTouchChannel.start() 推 agent.so → 起/复用系统 uitest 守护进程
         │                        → fport 转发 → 连 JSON socket
         ├── HosVideoStream.start() md5 核对推 libscreen_casting.z.so
         │                       → 起扩展守护进程（H.264 gRPC 服务端）
         │                       → fport 转发 → gRPC onStart 服务端流
         └── 唤屏 + IDR 催帧等首块（最多 15s）
              │
              ▼
         FastTouchController(touch_channel) 创建触摸控制器
              │
              ▼
         _stream_loop() 后台线程读取视频块
              │
              ▼
         _render_tick() 主线程渲染（每 16ms）
```

### 流模式选择

默认走 gRPC Raw H.264（需 PyAV），约 20fps。两种模式对比：

| 模式 | `raw_mode` | 解码位置 | 帧率 | 依赖 |
|------|-----------|---------|------|------|
| Raw H.264 | `True`（默认） | 消费方 PyAV | ~20fps | `pip install av` |
| JPEG | `False` | 本库 PyAV | ~20fps | `pip install av` |

```python
# Raw H.264 模式（默认，高帧率）
touch = cap.start_grpc_stream(on_frame, raw_mode=True)

# JPEG 模式（on_frame 直接收 JPEG，方便落盘/转发）
touch = cap.start_grpc_stream(on_frame, raw_mode=False)
```

> Raw H.264 模式下 Demo 偶有闪屏，因为后台线程调了 tkinter 渲染。库本身的 `on_frame` 回调没问题。

### 视频帧渲染管线

```
设备端 uitest 扩展守护进程 (libscreen_casting.z.so)
    │
    │  H.264 编码，gRPC ScrcpyService/onStart 服务端流
    │  每条消息 payload["data"].val_bytes = 一段裸 H.264
    │  （经 hdc fport 转发到本机随机口）
    ▼
HosVideoStream._recv_loop()  (接收线程)
    │
    │  块入有界队列（满丢最旧，防反压）
    ▼
read_frames(bridge)  (Python 后台线程)
    │
    │  yield H.264 bytes（含停滞看门狗：5s IDR 探活 / 60s 判死）
    ▼
_on_frame(chunk)  (回调)
    │
    ├── self._latest_frame = chunk  (更新最新帧)
    └── self._frame_ready.set()     (通知渲染线程)
         │
         ▼
_render_tick()  (主线程，每 16ms)
    │
    ├── 读取 self._latest_frame
    ├── self._mirror.show_jpeg(data)
    │   ├── 数据以 00 00 00 01 开头 → _feed_h264() PyAV 持久解码器
    │   └── canvas.create_image() 渲染
    └── self.after(16, self._render_tick)  (调度下一帧)
```

### 触控管线

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
    ├── down(x, y)  →  {"api":"touchDown","args":{"x":544,"y":1953}}
    ├── move(x, y)  →  {"api":"touchMove","args":{"x":548,"y":1973"}}  (限速20/s, <10px跳过)
    └── up(x, y)    →  {"api":"touchUp","args":{"x":823,"y":1146}}
         │
         ▼
HosTouchChannel (持久 socket，经 hdc fport 转发)
    │
    │  compact JSON: module=com.ohos.devicetest.hypiumApiHelper, method=Gestures
    │  后台排空线程持续读掉守护进程回复
    ▼
鸿蒙设备 (系统 uitest 守护进程注入)
```

触控协议格式（Gestures JSON，按 api 字段区分）：

| api | 含义 |
|-----|------|
| `touchDown` | Touch down |
| `touchMove` | Touch move |
| `touchUp` | Touch up |

### 坐标变换

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

### Demo 和 GUI 两种入口

两个 GUI 入口，用途不同：

| 入口 | 命令 | 适合 |
|------|------|------|
| Demo App | `python -m demo.app` | 单文件，读代码学流程 |
| GUI App | `python -m hos_scrcpy.gui.app` | 模块化，带 UI 树面板和 XPath 搜索 |

Demo App (`demo/app.py`) 所有逻辑在一个文件里，方便理解。GUI App 多一个 UI 树浏览器。

```python
with HOSDevice.connect("SN123456") as dev:
    dev.touch.click(100, 200)
    jpeg = dev.screenshot()
# 自动停止视频流、清理资源
```

---

## WiFi 无线调试

类似 `adb tcpip` + `adb connect`。

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

## 视频流

### gRPC Raw H.264（默认推荐）

设备端 scrcpy 扩展直出 H.264 数据块（Annex B 流，无长度前缀），消费方 PyAV 软解码。~20fps，纯 Python 无 Java。

```python
capture = dev.screen

# Raw H.264 模式（默认），需 pip install av
touch = capture.start_grpc_stream(on_frame, raw_mode=True)

def on_frame(chunk: bytes):
    """每块回调，chunk 是原始 H.264 数据（连续拼接，按 NAL start code 切分）"""
    # 自行用 PyAV 解码
    import av
    ctx = av.CodecContext.create("h264", "r")
    ...
```

**启动流程**（`HosStreamBridge.start()`，全部纯 Python）：
1. `uitest --version` 读取设备 uitest 版本，判定 fport 转发目标（>6.0.2.1 → `localabstract:scrcpy_grpc_socket`，老版本 → `tcp:5000`）
2. 触控通道：按 uitest 版本选 agent so（五件映射），md5/版本核对推送 `/data/local/tmp/agent.so`，确保系统 uitest 守护进程在跑，fport 转发 + 连 JSON socket
3. 视频通道：md5 核对推送 `libscreen_casting.z.so`（不一致才推），杀残留扩展守护进程后带流参数重起（`-scale 1 -frameRate 20 -bitRate 2000000 -p 5000 ...`）
4. gRPC 明文连本机转发口，`ScrcpyService/onStart(Empty)` 服务端流；接收线程逐消息取 `payload["data"].val_bytes` 入有界队列（满丢最旧）
5. 唤屏（`power-shell wakeup`）+ `onRequestIDRFrame` 催帧，等首块（最多 15s）
6. 返回 `FastTouchController` 用于低延迟触控

**停滞看门狗**（`read_frames` 内置）：
- 5s 无数据 → IDR 探活 + 唤屏（兼防灭屏）
- 60s 持续无数据 → 判死退出流（消费方按流结束处理）

**SPS/PPS 处理**：
- 首块通常含 SPS+PPS（Annex B `00 00 00 01 67 / 68`）
- 库只透传原始字节，SPS/PPS 检测由调用方处理

**码率参数**：`-bitRate` 单位是字节/秒，直接传 `2_000_000`（闭源 SDK 曾因单位是 MB 导致 int 溢出的坑，自研后不存在）

### JPEG 模式（本库内解码）

`raw_mode=False` 时本库用 PyAV 把 H.264 块解码成 JPEG 再回调。方便落盘/网络转发。

```python
touch = capture.start_grpc_stream(on_frame, raw_mode=False)

def on_frame(jpeg_bytes: bytes):
    """每帧回调，jpeg_bytes 是完整 JPEG 数据"""
    with open("frame.jpg", "wb") as f:
        f.write(jpeg_bytes)
```

### H.264 screenrecord（需 PyAV）

```python
capture.start_native_stream(on_frame)
```

通过 `hdc shell screenrecord --output-format=h264 -` 管道输出 H.264 裸流。部分设备不可用。

### 截图轮询（纯 Python，~2fps）

```python
capture.start_screenshot_stream(on_frame, interval=0.5)
```

循环 `snapshot_display -f` → `file recv` → 读文件。零额外依赖。

### 流模式怎么选

```
gRPC 通道可用？（设备已连、so 推送成功）
 ├── 是 → start_grpc_stream(raw_mode=True)   ← 推荐（~20fps）
 │        └── 需 PyAV；JPEG 需求 → raw_mode=False
 └── 否（设备端扩展起不来）→ PyAV 可用？
           ├── 是 → start_native_stream()
           └── 否 → start_screenshot_stream()
```

---

## UI 自动化

### uiautomator2 风格（推荐）

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

### Dump UI 树

```python
root = dev.dump_ui()  # 或 dev.ui.dump()
```

### 高级查找

```python
# 通过 dev.finder 进行多条件查找
results = dev.finder.find(type="Button", clickable=True, enabled=True)
count = dev.finder.count(text="OK")
```

### 链式选择器（更精确）

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

## GUI Demo

两个入口：

```bash
# Demo App（单文件，适合学习）
python -m demo.app
python -m demo.app --sn DEVICE_SN    # 直接连接指定设备

# GUI App（模块化，带 UI 层级树）
python -m hos_scrcpy.gui.app
```

### Demo App 界面

| 组件 | 功能 |
|------|------|
| 设备下拉框 | 自动扫描，选择目标设备 |
| 连接/断开按钮 | 一键连接或断开设备 |
| 刷新按钮 | 重新扫描设备列表 |
| 投屏画布 | 实时显示设备画面，鼠标触控 |
| 状态栏 | 连接状态、帧率统计 |

### 关键类

| 类 | 文件 | 职责 |
|----|------|------|
| `DemoApp(tk.Tk)` | `demo/app.py` | 主窗口，设备管理，线程调度 |
| `MirrorCanvas(tk.Canvas)` | `demo/app.py` | 投屏画布，帧渲染，触控事件 |
| `ScreenCapture` | `hos_scrcpy/screen/capture.py` | 统一流管理（3 种模式） |
| `FastTouchController` | `hos_scrcpy/input/fast_touch.py` | uitest socket 触控 |
| `Device` | `hos_scrcpy/core/device.py` | 设备实体（SN、IP、截图等） |

### 线程模型

```
主线程 (tkinter)
  ├── _render_tick()    — 30fps 渲染循环
  ├── Canvas 事件处理   — 鼠标按下/拖拽/释放
  └── UI 更新           — 状态栏、按钮状态

后台线程
  ├── _stream_loop()    — read_frames() → _on_frame() 回调
  ├── _connect()        — 设备连接 + 在线检查
  ├── _scan()           — 设备扫描 (_refresh_devices)
  ├── grpc-recv         — gRPC 服务端流迭代 → 队列
  └── touch-drain       — 持续排空触控通道回复

线程安全：
  - _latest_frame: 后台写，主线程读
  - _render_busy: 简单的帧跳跃锁
  - tkinter widget: 仅主线程通过 self.after() 操作
```

### GUI App 额外功能

| 功能 | 说明 |
|------|------|
| UI 层级树 | Dump UI → 树形展示 → 选中节点高亮 |
| XPath 搜索 | 输入 XPath 表达式查找元素 |
| 工具栏按钮 | Power / Home / Back 快捷操作 |
| Demo 模式 | 无需设备，生成模拟手机画面 |

---

## WebSocket 服务器

```bash
python -m hos_scrcpy.server.ws_server --sn SN123456 --port 8765
```

浏览器打开 `http://localhost:8765`：
- 实时投屏
- 触控操作映射到设备
- Power / Home / Back 按钮

---

## 配置

### 持久化配置

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

### so 资产（设备端组件）

视频和触控需要的设备端 so 随包内置在 `hos_scrcpy/bridge/scrcpy_server/`，首次连接时自动核对（md5/版本标记）并推送到设备：

| 文件 | 用途 | 设备端落点 |
|------|------|-----------|
| `libscrcpy_server_unix_6.5-20260313.z.so` | 视频扩展库（H.264 gRPC 服务端） | `/data/local/tmp/libscreen_casting.z.so` |
| `uitest_agent_1.1.3.so` / `1.1.5.so` / `1.1.12.so` / `1.2.3.so` / `x86_1.1.12.so` | 触控 agent（按设备 uitest 版本五选一） | `/data/local/tmp/agent.so` |

需要刷新资产时（上游出了新 jar）：

```bash
python -m hos_scrcpy.bridge.extract_servers   # 从 hosScrcpy jar 重新提取
```

流参数（`native_stream.py` 顶部常量）：`STREAM_SCALE=1`、`STREAM_FRAME_RATE=20`、`STREAM_BIT_RATE=2_000_000`（字节/秒）、`STREAM_IFRAME_INTERVAL_MS=2000`、`STREAM_REPEAT_INTERVAL=33`。

### 通道生命周期

```
启动时:
  HosTouchChannel.start()  推 agent.so → 起/复用系统 uitest 守护进程 → fport → JSON socket
  HosVideoStream.start()   推 libscreen_casting.z.so → 起扩展守护进程 → fport → gRPC 收流
                           （首块等待：唤屏 + IDR 催帧，最多 15s）
  接收/排空线程           grpc-recv 迭代服务端流；touch-drain 排空回复

断开时:
  ScreenCapture.stop()
    ├── HosVideoStream.stop()  cancel 流 → 关 channel → fport rm → 杀扩展守护进程
    ├── HosTouchChannel.stop() 关 socket → fport rm（系统守护进程留着，dumpLayout 共用）
    └── 线程 join(3s)          等待流线程退出

复连时:
  _connect_device()
    ├── 已有连接 → _disconnect() 断开旧连接
    ├── self._mirror.reset_h264_state() 清除解码器状态
    └── 创建新连接...
```

---

## 项目结构

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
│   ├── fast_touch.py    # FastTouchController (uitest socket)
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
│   ├── native_stream.py # 纯 Python 双通道客户端（gRPC 视频 + uitest JSON 触控）
│   ├── scrcpy.proto     # 设备端 gRPC 协议
│   ├── scrcpy_pb2*.py   # protoc 生成代码
│   ├── extract_servers.py # so 资产维护工具
│   └── scrcpy_server/   # 设备端 so 资产
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

## 常见问题

### 截图或触摸不工作

检查 hdc 是否可用：
```python
from hos_scrcpy.core.hdc_client import HdcClient
print(HdcClient.is_available())
```

### gRPC 流启动失败

1. 检查设备是否在线：`hdc list targets`
2. 检查 so 资产是否齐全（`hos_scrcpy/bridge/scrcpy_server/`，缺了跑 `python -m hos_scrcpy.bridge.extract_servers`）
3. 看日志里哪一步抛错：推库 / 起守护进程 / fport / gRPC 连接，各有明确报错
4. 通道起不来时 ws_server 等消费方会自动回退截图模式

### 画面延迟高

- gRPC 模式延迟最低；WiFi 连接比 USB 延迟高 50-100ms
- 截图轮询模式下延迟约 500ms

### 多设备切换残留

线程用 generation ID 防竞态；fport 转发按随机本机口隔离，停止时逐条 `fport rm` 清理。

```python
# 安全的多设备切换
dev1 = HOSDevice.connect("SN_DEVICE_1")
with dev1:
    dev1.touch.click(100, 200)
# dev1 自动清理

dev2 = HOSDevice.connect("SN_DEVICE_2")
with dev2:
    dev2.screen.start_grpc_stream(on_frame)
# dev2 自动清理，不会影响 dev1
```

### 布尔属性误判？

`JsonStructure` 正确解析 `"true"/"false"/"True"/"False"/"TRUE"/"FALSE"/"1"/"0"`。
