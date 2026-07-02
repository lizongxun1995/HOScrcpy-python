# HOScrcpy Python API 参考

> **资源管理**：使用 `with dev:` 上下文管理器或显式调用 `dev.stop()` 确保 Java 进程
> 和屏幕流正确释放。`HOSDevice.__del__` 和 `ScreenCapture.__del__` 提供兜底清理，
> 但不应依赖 GC。



## 目录

- [HOSDevice（统一入口）](#hosdevice)
- [Device（设备实体）](#device)
- [TouchController（触摸控制）](#touchcontroller)
- [FastTouchController（低延迟触摸）](#fasttouchcontroller)
- [AsyncTouchController（异步触摸）](#asynctouchcontroller)
- [MouseController（鼠标控制）](#mousecontroller)
- [KeyboardController（键盘控制）](#keyboardcontroller)
- [KeyCode（键码表）](#keycode)
- [ScreenCapture（屏幕捕获）](#screencapture)
- [UIHierarchy + UiSelector（UI 层级）](#uihierarchy--uiselector)
- [JsonStructure（UI 树节点）](#jsonstructure)
- [XPath 查找](#xpath-查找)
- [WebSocket 服务器](#websocket-服务器)
- [Settings（配置）](#settings)
- [AsyncTouchController（异步触摸）](#asynctouchcontroller)
- [UIFinder（uiautomator2 风格查找器）](#uifinder)
- [坐标工具](#坐标工具)

---

## HOSDevice

统一入口，聚合所有控制器。提供上下文管理器协议。

```python
from hos_scrcpy import HOSDevice

# 设备发现
devices = HOSDevice.list_devices()           # → list[Device]（含远程）
HOSDevice.list_remote(["192.168.1.100"])     # → list[Device]

# 连接
dev = HOSDevice.connect("SN123456")
dev = HOSDevice.connect("SN123456", ip="127.0.0.1", port="8710")

# 快捷操作
jpeg = dev.screenshot()            # → bytes | None
json_str = dev.dump_layout()       # → str | None
result = dev.execute_shell("cmd")  # → str

# 设备控制
dev.reboot()                       # 重启设备
dev.reboot_bootloader()            # 重启到 bootloader
dev.enable_tcp_mode("8710")        # 开启 WiFi 调试模式
dev.enable_usb_mode()              # 切回 USB 模式

# 状态
dev.is_online()                    # → bool

# 属性
dev.sn                             # 序列号
dev.ip                             # IP 地址
dev.device                         # 底层 Device 对象
dev.touch                          # TouchController
dev.keyboard                       # KeyboardController
dev.mouse                          # MouseController
dev.screen                         # ScreenCapture
dev.ui                             # UIHierarchy

# 上下文管理器（自动清理流资源）
with dev:
    dev.screen.start_screenshot_stream(on_frame)

# ---- uiautomator2 风格操作 ----
dev.dump_ui()                          # 刷新 UI 树

dev.click_by_text("Settings")          # 按文本点击
dev.click_by_id("submit_btn")          # 按 ID 点击
dev.click_by_xpath("//Button[0]")      # 按 XPath 点击
dev.click_by_description("返回")       # 按描述点击

dev.exists_text("OK")                  # → bool
dev.exists_id("cancel_btn")            # → bool
dev.exists_xpath("//*[@clickable=true]")  # → bool

dev.wait_text("加载完成", timeout=10)   # → JsonStructure | None
dev.wait_id("result_view", timeout=5)
dev.wait_xpath("//Text[0]")

dev.get_text_by_id("title")            # → str | None
dev.get_info_by_text("OK")             # → dict
dev.get_info_by_id("btn")              # → dict | None
dev.get_info_by_xpath("//Button[0]")   # → dict | None

# 高级查找
results = dev.finder.find(type="Button", clickable=True)
count = dev.finder.count(text="OK")
```

---

## Device

低级设备实体。

```python
from hos_scrcpy import Device

d = Device(sn="SN123456")                        # USB 设备
d = Device(sn="SN123456", ip="192.168.1.5")     # 远程设备

d.is_online()                    # → bool
d.screenshot()                   # → bytes | None
d.screenshot("path.jpg")         # 保存到文件
d.dump_layout()                  # → str (JSON) | None
d.execute_shell("cmd", timeout=10)  # 执行 shell 命令
d.execute("hdc_cmd", timeout=10)    # 执行 hdc 命令

# 按键
d.press_key(KeyCode.POWER)       # 按系统键

# 网络模式
d.enable_tcp_mode("8710")        # 开启 WiFi 调试
d.enable_usb_mode()              # 切回 USB
d.connect_remote("192.168.1.5")  # 连接远程设备
d.disconnect_remote("key")       # 断开远程设备

# 重启
d.reboot()
d.reboot_bootloader()

# 静态方法
Device.list_all()                # → list[Device]（本地+配置的远程）
Device.list_local()              # → list[Device]（仅本地）
Device.list_remote(["ip1","ip2"]) # → list[Device]
```

---

## TouchController

基于 `uinput -M` shell 命令的触摸注入。

```python
touch = dev.touch

touch.down(x, y)                        # 按下
touch.down(x, y, contact=0)            # 指定触点（0-9，多指）
touch.move(x, y)                        # 移动
touch.up(x, y)                          # 抬起
touch.click(500, 300)                   # 点击（默认 50ms 按住）
touch.click(500, 300, duration=0.1)    # 快速点击
touch.long_press(500, 300)             # 长按（默认 1s）
touch.long_press(500, 300, duration=2) # 2 秒长按
touch.swipe(100, 800, 100, 200)        # 滑动（默认 0.3s, 10 步）
touch.swipe(100, 800, 100, 200, duration=0.5, steps=20)
```

注意：该控制器每条命令启动一次 `hdc shell` 子进程，延迟较高（~50-100ms/命令）。

---

## FastTouchController

通过 Java StreamBridge stdin 的低延迟触摸（< 1ms）。

```python
from hos_scrcpy.bridge.native_stream import start_native_bridge
from hos_scrcpy.input.fast_touch import FastTouchController

output_proc, java_proc = start_native_bridge(sn)
touch = FastTouchController(java_proc)

touch.down(x, y)          # 发送 D:x:y
touch.move(x, y)          # 发送 M:x:y（最大 20/s，<10px 跳过）
touch.up(x, y)            # 发送 U:x:y
touch.click(x, y)
touch.swipe(x1,y1, x2,y2, duration=0.3, steps=10)

touch.stop()              # 释放资源
```

协议格式：`<op>:<x>:<y>\n`（通过 Java stdin）

---

## AsyncTouchController

非阻塞触摸队列，适用于截图轮询模式的 GUI。

```python
from hos_scrcpy.input.async_touch import AsyncTouchController

async_touch = AsyncTouchController(touch_controller)
async_touch.down(x, y)     # 立即返回
async_touch.move(x, y)
async_touch.up(x, y)
async_touch.click(x, y)
async_touch.swipe(x1,y1, x2,y2)
async_touch.stop()         # 清空队列，等待线程结束
```

---

## MouseController

鼠标事件注入。

```python
mouse = dev.mouse

mouse.down(MouseController.MOUSE_LEFT, x, y)
mouse.up(MouseController.MOUSE_LEFT, x, y)
mouse.move(x, y)
mouse.click(MouseController.MOUSE_RIGHT, 500, 300)

mouse.wheel_up(x, y)       # 上滚
mouse.wheel_down(x, y)     # 下滚
mouse.wheel_stop(x, y)     # 停止滚动

# 按钮常量
MouseController.MOUSE_LEFT    # "LEFT"
MouseController.MOUSE_MIDDLE  # "MIDDLE"
MouseController.MOUSE_RIGHT   # "RIGHT"
```

注意：中键和右键在 shell 模式下共用 code 1，功能受限。

---

## KeyboardController

按键和文本输入。

```python
keyboard = dev.keyboard

# 按键
keyboard.press(KeyCode.ENTER)       # 按下并释放
keyboard.key_down(KeyCode.SHIFT)    # 按住不放
keyboard.key_up(KeyCode.SHIFT)      # 释放
keyboard.press_shifted(KeyCode.A)   # Shift+按键

# 文本输入
keyboard.input_text("Hello 世界")   # 通过 uitest uiInput（支持 CJK）
keyboard.type("abcABC123")         # 逐字符输入（ASCII 用按键，CJK 用 input_text）
keyboard.type_char('A')            # 单字符

# 系统键
keyboard.home()                    # Home 键
keyboard.back()                    # 返回键
keyboard.power()                   # 电源键
keyboard.volume_up()               # 音量+
keyboard.volume_down()             # 音量-

# 功能键
keyboard.enter()                   # 回车
keyboard.backspace()              # 退格
keyboard.space()                   # 空格
keyboard.paste()                   # 模拟 Ctrl+V
keyboard.paste_from_clipboard()    # 读系统剪贴板 → 发到设备
```

---

## KeyCode

完整 HarmonyOS 键码常量。

```python
from hos_scrcpy import KeyCode, keycode_for_char

# 导航键
KeyCode.UP = 2012        KeyCode.DOWN = 2013
KeyCode.LEFT = 2014      KeyCode.RIGHT = 2015
KeyCode.ENTER = 2119     KeyCode.TAB = 2049
KeyCode.BACKSPACE = 2055 KeyCode.SPACE = 2050
KeyCode.ESCAPE = 2070

# 修饰键
KeyCode.SHIFT = 2047     KeyCode.CTRL = 2072

# 系统键
KeyCode.BACK = 2         KeyCode.HOME = 3
KeyCode.POWER = 18       KeyCode.VOLUME_UP = 16
KeyCode.VOLUME_DOWN = 17

# 字母 A-Z: 2017 +
KeyCode.A = 2017  ...  KeyCode.Z = 2042

# 数字 0-9: 2000 +
KeyCode.DIGIT_0 = 2000  ...  KeyCode.DIGIT_9 = 2009

# 符号
KeyCode.EQUALS = 2058    KeyCode.MINUS = 2057
KeyCode.SEMICOLON = 2062 KeyCode.QUOTE = 2063
KeyCode.BACK_SLASH = 2061 KeyCode.BACK_QUOTE = 2056
KeyCode.DIVIDE = 2064    KeyCode.MULTIPLY = 2010

# 字符映射
keycode_for_char('A')  # → 2017
keycode_for_char('5')  # → 2005
keycode_for_char('!')  # → -1（无映射，需用 input_text）
```

---

## ScreenCapture

统一屏幕流管理。3 种模式按性能降序排列。

```python
capture = dev.screen

# 模式 1：Java StreamBridge IMAGE 流（推荐，~30-60fps）
touch = capture.start_java_stream(on_frame)
# → 返回 FastTouchController 或 None（Java 不可用）

# 模式 2：H.264 screenrecord（~30fps，需 PyAV）
capture.start_native_stream(on_frame)

# 模式 3：截图轮询（~2fps，纯 Python）
capture.start_screenshot_stream(on_frame, interval=0.5)

# 回调签名
def on_frame(jpeg_bytes: bytes):
    with open("frame.jpg", "wb") as f:
        f.write(jpeg_bytes)

# 停止
capture.stop()

# 状态
capture.is_streaming  # → bool
```

模式选择建议：
1. Java 可用时用 `start_java_stream`（低延迟视频 + 低延迟触摸）
2. Java 不可用但有 PyAV 时用 `start_native_stream`
3. 都没有时用 `start_screenshot_stream`

---

## UIHierarchy + UiSelector

UI 树导出和查找。

```python
ui = dev.ui
root = ui.dump()                           # → JsonStructure | None

# 直接查找
ui.find_by_type("Button")                  # → list[JsonStructure]
ui.find_by_text("OK")                      # → list[JsonStructure]
ui.find_by_id("submit_btn")                # → list[JsonStructure]
ui.find_by_path("/Root/ScrollView/Button") # → JsonStructure | None
ui.find_at_point(500, 300)                 # → 最小包围元素 | None

# 链式选择器
from hos_scrcpy import UiSelector

result = (UiSelector(root)
    .type("Button")
    .text_contains("OK")
    .clickable(True)
    .first())                              # → JsonStructure | None

(UiSelector(root)
    .xpath("//*[@clickable=true]")         # XPath 过滤
    .text_contains("设置")
    .all())                                # → list[JsonStructure]
```

UiSelector 链式方法：

| 方法 | 说明 |
|------|------|
| `.type(name)` | 精确类型匹配 |
| `.type_contains(s)` | 类型包含子串（忽略大小写） |
| `.text(s)` | 精确文本匹配 |
| `.text_contains(s)` | 文本包含子串 |
| `.id(s)` | 精确 ID 匹配 |
| `.id_contains(s)` | ID 包含子串 |
| `.description(s)` | 精确描述匹配 |
| `.description_contains(s)` | 描述包含子串 |
| `.clickable(bool)` | 可点击过滤 |
| `.scrollable(bool)` | 可滚动过滤 |
| `.enabled(bool)` | 启用状态过滤 |
| `.focused(bool)` | 焦点过滤 |
| `.path(s)` / `.path_contains(s)` | XPath 路径过滤 |
| `.at_point(x, y)` | 坐标包含过滤 |
| `.xpath(expr)` | 完整 XPath 表达式过滤 |
| `.where(predicate_fn)` | 自定义过滤函数 |

结果方法：`.first()` / `.all()` / `.count()` / `.exists()`

---

## JsonStructure

UI 树节点。

```python
node.type               # → str    组件类型："Button", "Text", "ScrollView"
node.text               # → str    文本内容
node.id                 # → str    组件 ID（resource-id 等价物）
node.key                # → str    与 id 相同或相近
node.description        # → str    无障碍描述
node.hint               # → str    输入提示文本
node.raw_bounds         # → str    原始 bounds："[10,20][110,70]"
node.rectangle          # → (x, y, w, h)
node.center             # → (cx, cy) 中心点
node.is_clickable       # → bool
node.is_scrollable      # → bool
node.is_focused         # → bool
node.is_enabled         # → bool
node.is_visible         # → bool
node.is_selected        # → bool
node.is_long_clickable  # → bool
node.bundle_name        # → str    所属应用包名
node.ability_name       # → str    Ability 名称
node.hierarchy_path     # → str    数字层级路径："ROOT10,0,1,2"
node.z_index            # → str    Z 序
node.hashcode           # → str    内部哈希
node.child_count        # → int    子节点数量
node.children           # → list[JsonStructure]

# 树遍历
list(node.iter_all())          # 深度优先（含自身）
list(node.iter_children())     # 仅直接子节点
list(node.iter_descendants())  # 所有后代（不含自身）

# 查找
node.find_first(predicate)     # → JsonStructure | None
node.find_all(predicate)       # → list[JsonStructure]

# 序列化
node.to_dict()                 # → dict
```

---

## UIFinder（uiautomator2 风格查找器）

便捷的元素查找、点击、等待接口，自动管理 UI dump 缓存。

```python
from hos_scrcpy import UIFinder

finder = dev.finder  # 通过 HOSDevice 访问

# 通用查找
finder.find(type="Button", text="OK", clickable=True)     # -> list[JsonStructure]
finder.find(xpath="//Button[@clickable=true]")            # XPath 查找
finder.find_first(text="OK")                              # -> JsonStructure | None

# 点击（操作前自动 dump）
finder.click_by_text("OK")         # -> bool
finder.click_by_id("submit_btn")   # -> bool
finder.click_by_xpath("//Button[0]") # -> bool
finder.click_by_description("返回")  # -> bool

# 存在判断（操作前自动 dump）
finder.exists_text("OK")           # -> bool
finder.exists_id("submit_btn")     # -> bool
finder.exists_xpath("//Button")    # -> bool
finder.exists_description("返回")  # -> bool

# 等待出现（每 500ms 重新 dump + 查找）
finder.wait_text("OK", timeout=5)     # -> JsonStructure | None
finder.wait_id("submit_btn", timeout=3)
finder.wait_xpath("//Button", timeout=5)

# 获取属性
finder.get_text_by_id("title")       # -> str | None
finder.get_text_by_xpath("//Text[0]") # -> str | None
finder.get_bounds_by_id("btn")       # -> (x, y, w, h) | None
finder.get_center_by_id("btn")       # -> (cx, cy) | None
finder.get_bounds_by_text("OK")      # -> (x, y, w, h) | None
finder.get_center_by_text("OK")      # -> (cx, cy) | None

# 获取完整信息
finder.get_info_by_id("btn")         # -> dict | None
finder.get_info_by_text("OK")        # -> dict | None
finder.get_info_by_xpath("//Button") # -> dict | None

# 计数
finder.count(text="OK")              # -> int
finder.count_id("btn")               # -> int

# 手动刷新 UI 树
finder.dump()                        # -> JsonStructure | None
```

返回的 info dict 结构：
```python
{
    "type": "Button",
    "text": "OK",
    "id": "ok_button",
    "key": "ok_button",
    "description": "确认按钮",
    "bounds": (10, 20, 100, 50),
    "center": (60, 45),
    "clickable": True,
    "scrollable": False,
    "enabled": True,
    "focused": False,
    "visible": True,
    "long_clickable": False,
    "selected": False,
    "bundle": "com.example.app",
    "hierarchy": "ROOT10,0,1",
    "z_index": "0",
}
```

---

## XPath 查找

uiautomator2 风格的 XPath 表达式查找。

```python
from hos_scrcpy.ui.xpath import find_by_xpath, xpath_for, xpath_filter

# 查找
results = find_by_xpath(root, "//Button")                     # 所有 Button
results = find_by_xpath(root, "//*[@clickable=true]")         # 所有可点击元素
results = find_by_xpath(root, "//Button[@text='OK']")         # 文本精确匹配
results = find_by_xpath(root, "//*[@id='submit_btn']")        # 按 ID
results = find_by_xpath(root, "//Button[@clickable=true][@enabled=true]")  # 多条件
results = find_by_xpath(root, "//Button[0]")                  # 取第一个匹配
results = find_by_xpath(root, "//WindowScene/Button")         # 父子链

# 生成每个节点的 xpath
xpath_for(node, root)
# → "//WindowScene[@id='session10']/Button[@text='OK']"

# 属性字典过滤
xpath_filter(root, {"text": "OK", "clickable": "true"})
```

---

## WebSocket 服务器

远程投屏 + 触控。

```python
from hos_scrcpy.server.ws_server import ScreenServer

server = ScreenServer(port=8765)
server.attach_device("SN123456")  # 连接设备
server.start()                    # 阻塞运行

# 或命令行
# python -m hos_scrcpy.server.ws_server --sn SN123456 --port 8765
```

浏览器打开 `http://localhost:8765` 即可使用。
支持 Power / Home / Back 按钮、触摸操作、滚轮。

---

## Settings

持久化配置（`~/.hos-scrcpy/config.json`）。

```python
from hos_scrcpy.utils.settings import *

# 远程 IP 管理
add_remote_ip("192.168.1.100:8710")
remove_remote_ip("192.168.1.100:8710")
ips = get_remote_ips()             # → list[str]

# 通用设置
set_setting("my_key", "my_value")
value = get_setting("my_key", default=None)

# 视频流偏好
set_use_video_stream(True)
use_video = get_use_video_stream()  # → bool

# 默认端口
port = get_default_port()           # → "8710"
```

---

## UIFinder（uiautomator2 风格）

便捷的元素查找、点击、等待接口，自动管理 UI dump 缓存。

```python
finder = dev.finder

# 通用查找
finder.find(type="Button", text="OK", clickable=True)     # → list[JsonStructure]
finder.find(xpath="//Button[@clickable=true]")            # XPath 查找
finder.find_first(text="OK")                              # → JsonStructure | None

# 点击（操作前自动 dump）
finder.click_by_text("OK")         # → bool
finder.click_by_id("submit_btn")   # → bool
finder.click_by_xpath("//Button[0]") # → bool
finder.click_by_description("返回")  # → bool

# 存在判断（操作前自动 dump）
finder.exists_text("OK")           # → bool
finder.exists_id("submit_btn")     # → bool
finder.exists_xpath("//Button")    # → bool
finder.exists_description("返回")  # → bool

# 等待出现（每 500ms 重新 dump + 查找）
finder.wait_text("OK", timeout=5)     # → JsonStructure | None
finder.wait_id("submit_btn", timeout=3)
finder.wait_xpath("//Button", timeout=5)

# 获取属性
finder.get_text_by_id("title")       # → str | None
finder.get_text_by_xpath("//Text[0]") # → str | None
finder.get_bounds_by_id("btn")       # → (x, y, w, h) | None
finder.get_center_by_id("btn")       # → (cx, cy) | None
finder.get_bounds_by_text("OK")      # → (x, y, w, h) | None
finder.get_center_by_text("OK")      # → (cx, cy) | None

# 获取完整信息
finder.get_info_by_id("btn")         # → dict | None
finder.get_info_by_text("OK")        # → dict | None
finder.get_info_by_xpath("//Button") # → dict | None

# 计数
finder.count(text="OK")              # → int
finder.count_id("btn")               # → int

# 手动刷新 UI 树
finder.dump()                        # → JsonStructure | None
```

返回的 info dict 结构：
```python
{
    "type": "Button",
    "text": "OK",
    "id": "ok_button",
    "key": "ok_button",
    "description": "确认按钮",
    "hint": "",
    "bounds": (10, 20, 100, 50),
    "center": (60, 45),
    "clickable": True,
    "scrollable": False,
    "enabled": True,
    "focused": False,
    "visible": True,
    "long_clickable": False,
    "selected": False,
    "bundle": "com.example.app",
    "hierarchy": "ROOT10,0,1",
    "z_index": "0",
}
```

---

## 坐标工具

```python
from hos_scrcpy.utils.bounds import parse_bounds, bounds_to_rectangle

parse_bounds("[10,20][110,70]")    # → (10, 20, 100, 50)
parse_bounds("")                   # → (0, 0, 0, 0)
bounds_to_rectangle("[10,20][110,70]")  # → {"x":10,"y":20,"width":100,"height":50}
```
