# HOScrcpy Python API

用 Python 控制鸿蒙设备。投屏、点按、滑动、输入文字、dump UI 树，都能干。

网上没有鸿蒙设备的 Python 投屏+控制库，所以我写了一个。底层是对 `hdc` 命令行和设备端 uitest/scrcpy 组件（gRPC 视频流 + JSON 触控 socket）的纯 Python 封装，上面提供了跟 Android uiautomator2 差不多的 API 体验。不依赖 Java，不依赖闭源 JAR SDK。

## 能干什么

投屏到 PC，三种模式自动切换：gRPC 直收 H.264（~20fps，延迟低）→ screenrecord H.264 → 截图轮询兜底（~2fps，纯 Python）。

操控设备：点击、滑动、长按、多点触控、鼠标左右键、滚轮。键盘输入包括中文，走 `uitest uiInput`。

dump UI 层级树，然后链式查找：`UiSelector(root).type("Button").text_contains("OK").clickable().first()`。XPath 也能用。找到元素后直接点：`dev.click_by_text("设置")`。

设备管理：USB 发现、WiFi 远程连接、应用启停、文件推拉、重启、屏幕开关。

## 快速看一眼

```python
from hos_scrcpy import HOSDevice

# 列出设备
devices = HOSDevice.list_devices()

# 连上
dev = HOSDevice.connect("SN123456")

# 截个图
jpeg = dev.screenshot()
with open("screen.jpg", "wb") as f:
    f.write(jpeg)

# 点点点
dev.touch.click(500, 300)
dev.touch.swipe(100, 800, 100, 200, duration=0.5)

# 输入中文
dev.keyboard.input_text("Hello 世界")

# dump UI 树，找按钮，点它
dev.click_by_text("设置")
dev.wait_text("加载完成", timeout=10)

# 用完了，自动清理资源
with dev:
    dev.screen.start_grpc_stream(on_frame)
```

## 安装

```bash
pip install hos-scrcpy

# 或者开发模式
pip install -e .

# H.264 解码需要 PyAV
pip install av
```

前置条件：hdc 在 PATH 里（或者放到 `~/.hos-scrcpy/toolchains/`）。视频流依赖 `grpcio`（随包自动安装）。视频/触摸需要的设备端 so 组件已随包内置（`bridge/scrcpy_server/`），首次连接时自动核对并推送到设备。

## 架构

两层设计：

**第一层：hdc 子进程。** 纯 Python。触摸走 `uinput -M`，截图走 `snapshot_display`，UI 树走 `uitest dumpLayout`。每次操作一条 `hdc shell` 命令，简单可靠。

**第二层：gRPC 流桥（纯 Python，无 Java）。** 视频：向设备推送 `libscreen_casting.z.so` 扩展库，起 `uitest start-daemon` 扩展守护进程（H.264 编码 gRPC 服务端），`hdc fport` 转发到本机，gRPC `ScrcpyService/onStart` 服务端流收裸 H.264 数据块。触控：向设备推送 `agent.so`，连系统 uitest 守护进程的持久 socket，直发 Gestures JSON（touchDown/touchMove/touchUp）。带首块等待（唤屏 + IDR 催帧）和停滞看门狗（5s 探活 / 60s 判死）。

```
Python 应用层 (GUI / 自动化脚本 / WebSocket Server)
        │
        ▼
  HOSDevice 统一入口
  ├─ TouchController / FastTouch / AsyncTouch
  ├─ KeyboardController
  ├─ ScreenCapture (3 种流模式)
  └─ UIHierarchy / UIFinder / UiSelector / XPath
        │
   ┌────┴─────────┐
   ▼              ▼
hdc 子进程     gRPC 视频流 + uitest JSON 触控 socket
(shell cmd)    (hdc fport 本机转发)
   │              │
   └──────┬───────┘
          ▼
      鸿蒙设备
```

## 视频流：三种模式

系统会按这个顺序尝试，失败了自动降级：

1. **gRPC H.264（首选）**——设备端 scrcpy 扩展直出 H.264 数据块，Python 端 PyAV 软解码→PIL Image。低延迟，帧率 ~20fps。需要 `pip install av`（gRPC 通道本身随包安装）。

2. **screenrecord H.264**——`hdc shell screenrecord --output-format=h264 -` 管道流 + PyAV 解码。部分设备不可用。

3. **截图轮询（保底）**——循环 `snapshot_display` → `file recv` → 读文件。~2fps，纯 Python，零依赖。

## 触摸：三种控制器

| 控制器 | 怎么工作 | 延迟 | 什么时候用 |
|--------|---------|------|-----------|
| `TouchController` | 每次操作一条 `hdc shell uinput -M` | ~100ms | 自动化脚本 |
| `AsyncTouchController` | 命令入队，后台线程逐个消费 | ~100ms | 截图轮询 GUI |
| `FastTouchController` | uitest 持久 socket 直发 Gestures JSON | <1ms | 投屏流 GUI |

FastTouchController 自带限流：move 事件最多 20 次/秒，位移<10px 直接跳过，防止拖拽时 socket 拥塞。

## UI 自动化

五层递进，从原始数据到一行代码搞定：

```python
# 底层：dump 原始 JSON
root = dev.ui.dump()           # → JsonStructure 对象树

# 链式选择器
from hos_scrcpy import UiSelector
btn = (UiSelector(root)
       .type("Button")
       .text_contains("OK")
       .clickable()
       .first())               # → 找到的第一个可点击 OK 按钮

# XPath
from hos_scrcpy.ui.xpath import find_by_xpath
btns = find_by_xpath(root, "//*[@clickable=true][@enabled=true]")

# 最方便：uiautomator2 风格
dev.click_by_text("设置")       # 按文字点
dev.exists_text("OK")          # 检查是否存在
dev.wait_text("加载完成", 10)   # 等到出现再继续
info = dev.get_info_by_id("title")  # 拿到完整属性字典
```

JsonStructure 节点能拿到的信息：type、text、id、description、bounds（x,y,w,h）、center、clickable、scrollable、enabled、focused、visible、selected、bundle_name、z_index、hierarchy_path。

## GUI

```bash
# Demo 模式——不需要设备，生成一个假手机画面练手
python -m hos_scrcpy.gui.app

# 或者用 demo/app.py（单文件实现，适合读代码学习）
python -m demo.app
```

左边投屏画面，鼠标操作映射到设备（Demo 模式有涟漪反馈）。右边 UI 树面板，点节点高亮，XPath 搜索多彩标注。

## 其他能力

WiFi 无线调试：`dev.enable_tcp_mode("8710")` 开启 WiFi 模式，`dev.connect_remote("192.168.1.5")` 远程连接。

WebSocket 服务器：`python -m hos_scrcpy.server.ws_server --port 8765`，浏览器打开就能投屏+操控。

应用管理：`dev.app_start("com.example.app")`、`dev.app_stop("com.example.app")`、`dev.app_list()`。

文件传输：`dev.push("local.txt", "/data/local/tmp/remote.txt")`、`dev.pull("...", "...")`。

## 限制

- hdc 必须在 PATH 或 `~/.hos-scrcpy/toolchains/` 目录
- 坐标映射假定竖屏，横屏得自己旋转
- 部分设备 screenrecord 命令不可用
- 记得用 `with dev:` 或调 `dev.stop()` 释放流通道（fport 转发、设备端守护进程），虽然 `__del__` 兜底，但别依赖 GC

## 包结构

```
hos_scrcpy/
├── __init__.py           # HOSDevice 统一入口
├── interfaces.py         # 抽象接口（TouchProvider 等 ABC）
├── core/
│   ├── device.py         # Device 实体——截图、UI dump、shell、设备发现
│   ├── hdc_client.py     # hdc 命令封装（参数列表，shell=False 防注入）
│   └── process.py        # 带超时子进程执行器
├── input/
│   ├── touch.py          # TouchController（uinput shell）
│   ├── async_touch.py    # AsyncTouchController（异步队列）
│   ├── fast_touch.py     # FastTouchController（uitest socket，<1ms）
│   ├── mouse.py          # MouseController
│   ├── keyboard.py       # KeyboardController（按键+中文输入+剪贴板）
│   └── keycode.py        # 完整 HarmonyOS 键码表
├── screen/
│   └── capture.py        # ScreenCapture——三种流统一管理
├── ui/
│   ├── hierarchy.py      # JsonStructure——UI 树节点
│   ├── selector.py       # UIHierarchy + UiSelector——链式查找
│   ├── finder.py         # UIFinder——uiautomator2 风格 API
│   └── xpath.py          # XPath 解析引擎
├── bridge/
│   ├── native_stream.py  # 纯 Python 双通道客户端（gRPC 视频 + uitest JSON 触控）
│   ├── scrcpy.proto      # 设备端 gRPC 协议（ScrcpyService）
│   ├── scrcpy_pb2*.py    # protoc 生成代码
│   ├── extract_servers.py# so 资产维护工具（从上游 jar 重新提取）
│   └── scrcpy_server/    # 设备端 so 资产（视频扩展库 + uitest agent）
├── gui/
│   └── app.py            # tkinter 投屏 GUI（Demo + Live 双模式）
├── server/
│   └── ws_server.py      # WebSocket 投屏服务器
├── utils/
│   ├── bounds.py         # 坐标边界解析
│   ├── apps.py           # 应用管理、屏幕控制、设备信息、文件传输
│   ├── settings.py       # 持久化配置
│   └── logger.py         # 日志（NullHandler 模式）
└── toolchains/
    └── hdc.exe           # 内置 hdc
```


