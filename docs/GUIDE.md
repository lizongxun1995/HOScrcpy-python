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

### 4.1 列出设备

```python
from hos_scrcpy import HOSDevice

devices = HOSDevice.list_devices()
for d in devices:
    print(d)  # Device(sn=62Q0225B12006304)
```

### 4.2 连接设备

```python
# USB 连接
dev = HOSDevice.connect("62Q0225B12006304")

# 检查状态
print(dev.is_online())  # True
```

### 4.3 基本操作

```python
# 截图
jpeg = dev.screenshot()
with open("screen.jpg", "wb") as f:
    f.write(jpeg)

# 触摸
dev.touch.click(500, 300)
dev.touch.swipe(100, 800, 100, 200, duration=0.5)

# 按键
dev.keyboard.input_text("Hello 世界")
dev.keyboard.home()
dev.keyboard.back()

# UI 层级树
root = dev.ui.dump()
for node in root.find_all(lambda n: n.is_clickable):
    print(f"{node.type}: {node.text} @ {node.center}")

# 清理
dev.screen.stop()
```

### 4.4 上下文管理器（推荐）

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

### 6.1 Java StreamBridge（推荐，低延迟）

```python
capture = dev.screen
touch = capture.start_java_stream(on_frame)
if touch:
    print("Java 流已启动，触摸延迟 <1ms")
else:
    print("Java 不可用，回退截图模式")
    capture.start_screenshot_stream(on_frame, interval=0.5)
```

### 6.2 H.264 screenrecord（需 PyAV）

```python
capture.start_native_stream(on_frame)
```

### 6.3 截图轮询（纯 Python，~2fps）

```python
capture.start_screenshot_stream(on_frame, interval=0.5)
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

```bash
python -m hos_scrcpy.gui.app
```

两种模式：
- **Demo 模式**（默认）：模拟手机屏幕，点击/拖拽有视觉反馈
- **Live 模式**：选设备 → Start Cast → 实时投屏，触摸映射到真机

功能：
- 右侧 UI 层级树：Dump UI → 选中节点高亮 → XPath 搜索
- 工具栏：Power / Home / Back 按钮

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
