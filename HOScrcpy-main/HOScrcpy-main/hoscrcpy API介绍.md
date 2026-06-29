# Hosscrcpy SDK API说明文档

## 版本说明

| 版本号               | 版本说明                                                     | 发布时间   |
| -------------------- | ------------------------------------------------------------ | ---------- |
| hosscrcpy-1.0.0-beta | 老系统版本上使用<br>如：3.0.0.25(SP36DEVC00E25R4P2log)、3.0.0.22(SP81DEVC00E22R4P1log)等之前的版本 | 2024-6-25  |
| hosscrcpy-1.0.1-beta | 新系统版本上使用，即上述1.0.0中版本之后的版本都可以使用      | 2024-6-25  |
| hosscrcpy-1.0.2-beta | 一、新增内容<br>1、HosRemoteDevice新增HosRemoteConfig变量初始化，支持设备分辨率<br>2、HosRemoteDevice新增获取当前页面layout的接口<br>二、修复问题<br>无 | 2024-9-5   |
| hosscrcpy-1.0.3-beta | 一、新增内容<br/>1、优化启动速度<br/>二、修复问题<br/>无     | 2024-9-23  |
| hosscrcpy-1.0.4-beta | 一、新增内容<br/>无<br/>二、修复问题<br/>1.修复5.0.0.71(SP6C00E71R4P17)版本无法投屏的问题 | 2024-10-12 |
| hosscrcpy-1.0.5-beta | 一、新增内容<br/>1、HosRemoteConfig 对象中支持设置投屏帧率、码率、端口号<br/>二、修复问题<br/>无 | 2024-12-31 |
| hosscrcpy-1.0.6-beta | 一、新增内容<br/>1、HosRemoteConfig 对象中支持设置HDC路径<br/>二、修复问题<br/>无 | 2025-2-28  |
| hosscrcpy-1.0.7-beta | 一、新增内容<br/>1、HosRemoteConfig 对象中支持设置视频流I帧的间隔<br/>二、修复问题<br/>无 |            |
| hosscrcpy-1.0.8-beta | 一、新增内容<br/>1、HosRemoteDevice 对象中添加获取图片流和停止图片流的方法<br/>二、修复问题<br/>无 |            |
| hosscrcpy-1.0.9-beta | 一、新增内容<br/>1、HosRemoteDevice 对象中添加鼠标注入事件<br/>二、修复问题<br/>无 |            |

## API说明

java版本需要在8及以上

sdk提供给开发者使用的类路径在com.huawei.hosscrcpy.api下，有以下3个类

1.HosRemoteDevice

| 方法                                                         | 参数              | 解释                                                         |
| ------------------------------------------------------------ | ----------------- | ------------------------------------------------------------ |
| HosRemoteDevice(String sn)                                   | sn                | 构造函数，通过传入sn号创建Scrcpy对象                         |
| HosRemoteDevice(HosRemoteConfig config)                      | config            | 构造函数，通过创建HosRemoteConfig对象，可以设置获取视频流分辨率的缩放倍率 |
| startCaptureScreen(ScreenCapCallback screenCapCallback)      | screenCapCallback | 通过传入视频流回调函数来开始获取视频流以及开启实时反控服务   |
| stopCaptureScreen()                                          |                   | 停止获取视频流                                               |
| getSn()                                                      |                   | 获取当前Scrcpy对象的sn                                       |
| executeShellCommand(String command, int timeOut)             | command, timeOut  | 让设备执行hdc shell命令。command：要执行的shell命令，timeOut：超时时间，单位秒 |
| getScreenSize(boolean needUpDate)                            | needUpDate        | 获取当前设备分辨率。传入true会重新获取分辨率信息，传入false会使用之前缓存的分辨率信息 |
| onTouchDown(int x, int y)                                    | x, y              | 注入手指按下事件，xy为手指按下的坐标                         |
| onTouchUp(int x, int y)                                      | x, y              | 注入手指抬起事件，xy为手指抬起的坐标                         |
| onTouchMove(int x, int y)                                    | x, y              | 注入手指移动事件，xy为手指移动的坐标                         |
| onMouseDown(String mouseType, int x, int y)                  | mouseType, x, y   | 注入鼠标按下事件，xy为鼠标按下的坐标。mouseType 可选 HosRemoteDevice.MOUSE_LEFT, HosRemoteDevice.MOUSE_MIDDLE, HosRemoteDevice.MOUSE_RIGHT；对应的类型分别是鼠标左键、中间、右键 |
| onMouseUp(String mouseType, int x, int y)                    | mouseType, x, y   | 注入鼠标抬起事件，xy为鼠标抬起的坐标。mouseType 可选 HosRemoteDevice.MOUSE_LEFT, HosRemoteDevice.MOUSE_MIDDLE, HosRemoteDevice.MOUSE_RIGHT；对应的类型分别是鼠标左键、中间、右键 |
| onMouseMove(String mouseType, int x, int y)                  | mouseType, x, y   | 注入鼠标移动事件，xy为鼠标移动的坐标。mouseType 可选 null ，HosRemoteDevice.MOUSE_LEFT, HosRemoteDevice.MOUSE_MIDDLE, HosRemoteDevice.MOUSE_RIGHT；当传入null时，表示注入的是普通的鼠标移动事件，典型场景是像Windows电脑将鼠标悬d浮移动到某个地方. |
| onMouseWheelUp(int x, int y)                                 | x, y              | 注入鼠标滚轮向上滑动事件, xy为鼠标当前的坐标。               |
| onMouseWheelDown(int x, int y)                               | x, y              | 注入鼠标滚轮向下滑动事件, xy为鼠标当前的坐标。               |
| onMouseWheelStop(int x, int y)                               | x, y              | 注入鼠标滚轮停止滑动事件, xy为鼠标当前的坐标。onMouseWheelStop需要跟在onMouseWheelUp或onMouseWheelDown事件后使用 |
| setRotationHorizontal()                                      |                   | 设置设备屏幕为横屏状态（需要应用支持）                       |
| setRotationVertical()                                        |                   | 设置设备屏幕为竖屏状态（需要应用支持）                       |
| getLayout()                                                  |                   | 获取当前页面结构json字符串(需要startCaptureScreen后才能调用) |
| startImageCaptureScreen(ScreenCapCallback screenCapCallback) | screenCapCallback | 通过传入图片流回调函数来开始获取图片流以及开启实时反控服务   |
| stopImageScreenCapture()                                     |                   | 停止获取图片流                                               |

2.ScreenCapCallback

| 方法                               | 参数         | 解释                                                                                                                     |
| -------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------- |
| onData(ByteBuffer byteBuffer)    | byteBuffer | 当sdk获取到视频流数据后，会回调此方法，并传入视频流的ByteBuffer，开发者可以用此进行画面显示                                                                   |
| onException(Throwable throwable) | throwable  | 当获取视频流出错后，会回调此方法，传入报错信息                                                                                                |
| onReady()                        |            | 因为需要设备画面变动才能获取视频流，所以如果设备以及处于一个亮屏且画面没有变动的状态时，onData方法是不会被调用。onReady方法是为了通知开发者当前已处于视频流获取就绪状态，开发者可以在此进行一些使画面变动的动作，比如按下电源键 |

3.HosRemoteConfig

| 方法                                  | 参数           | 解释                                                         |
| ------------------------------------- | -------------- | ------------------------------------------------------------ |
| HosRemoteConfig(String sn)            | sn             | 设备的sn                                                     |
| setScale(int scale)                   | scale          | 视频流分辨率的缩放倍率(输入2代表获取的视频流分辨率为原来的二分之一，3代表为原来的三分之一；最大设置为5) |
| setBitRate(int bitRate)               | bitRate        | 视频流码率，默认码率为30M                                    |
| setPort(int port)                     | port           | 设备侧视频流转发端口，默认为5000                             |
| setFrameRate(int frameRate)           | frameRate      | 视频流的帧率，默认为120FPS                                   |
| setHdcPath(String hdcPath)            | hdcPath        | hdc可执行文件的完整路径                                      |
| setIFrameInterval(int iFrameInterval) | iFrameInterval | 视频流I帧的间隔，默认为2000ms                                |

4.Size

| 属性     | 解释       |     |
| ------ | -------- | --- |
| width  | 设备分辨率的宽度 |     |
| height | 设备分辨率的长度 |     |

## Demo示例说明

以下为一个以maven构建的demo工程实例

demo原理：通过在本地创建一个WebSocket服务端启动投屏服务，然后在网页端进行投屏的查看以及控制

使用方法：

1.执行MyWebSocket下的main方法，以此启动WebScoket服务

2.修改resources/html下的h264.html的第31行，填写自己本地设备的sn号

3.用浏览器打开h264.html，稍等片刻即可看到投屏画面
PS：静止画面下不会自动刷新，可以滑动下手机看看
