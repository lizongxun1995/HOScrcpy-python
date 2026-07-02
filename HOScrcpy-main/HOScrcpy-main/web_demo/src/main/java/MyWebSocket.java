import com.alibaba.fastjson.JSONObject;
import com.huawei.hosscrcpy.api.HosRemoteConfig;
import com.huawei.hosscrcpy.api.HosRemoteDevice;
import com.huawei.hosscrcpy.api.ScreenCapCallback;
import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;

import java.net.InetSocketAddress;
import java.nio.ByteBuffer;

public class MyWebSocket extends WebSocketServer {
    private HosRemoteDevice remoteDevice = null;
    private volatile boolean streaming = false;
    private volatile long lastDataTime = 0;
    private volatile long lastTouchTime = 0;
    private volatile long frameCount = 0;
    private volatile long streamStartTime = 0;
    private volatile long t0;

    public MyWebSocket(int port) {
        super(new InetSocketAddress(port));
    }

    private void startScreenCapture() {
        t0 = System.currentTimeMillis();
        frameCount = 0;
        streamStartTime = 0;
        remoteDevice.stopCaptureScreen();
        remoteDevice.startCaptureScreen(new ScreenCapCallback() {
            @Override
            public void onData(ByteBuffer byteBuffer) {
                long now = System.currentTimeMillis();
                if (frameCount == 0) {
                    streamStartTime = now;
                    System.out.println("TIMING first_frame +" + (now - t0) + "ms");
                }
                frameCount++;
                lastDataTime = now;
                if (frameCount % 100 == 0) {
                    System.out.println("TIMING frames=" + frameCount + " elapsed=" + (now - streamStartTime) + "ms");
                }
                broadcast(byteBuffer);
            }
            @Override
            public void onException(Throwable throwable) {
                long age = streamStartTime > 0 ? (System.currentTimeMillis() - streamStartTime) : 0;
                System.out.println("TIMING EXCEPTION frames=" + frameCount + " stream_age=" + age + "ms msg=" + throwable.getMessage());
            }
            @Override
            public void onReady() {
                long now = System.currentTimeMillis();
                System.out.println("TIMING onReady +" + (now - t0) + "ms");
                remoteDevice.executeShellCommand("input tap 1 1", 2);
            }
        });
    }

    private void startWatchdog() {
        try { Thread.sleep(5000); } catch (Exception e) {}
        Thread t = new Thread(() -> {
            while (streaming) {
                try { Thread.sleep(1000); } catch (Exception e) { break; }
                long now = System.currentTimeMillis();
                long dataAge = now - lastDataTime;
                long touchAge = now - lastTouchTime;

                // 如果超过5秒没有帧，记录
                if (frameCount > 0 && dataAge > 5000) {
                    long streamAge = now - streamStartTime;
                    System.out.println("TIMING DEAD frames=" + frameCount + " data_age=" + dataAge + "ms touch_age=" + touchAge + "ms stream_age=" + streamAge + "ms");
                }

                // 用户有操作但超过3秒没收到帧 → 重启
                long dataStaleMs = now - lastDataTime;
                boolean userSinceLastData = lastTouchTime > lastDataTime;
                if (streaming && frameCount > 0 && dataStaleMs > 3000 && userSinceLastData) {
                    long streamAge = now - streamStartTime;
                    System.out.println("TIMING RESTART frames=" + frameCount + " stream_age=" + streamAge + "ms no_data=" + dataStaleMs + "ms");
                    System.out.println("TIMING checking device...");
                    try {
                        String result = remoteDevice.executeShellCommand("echo alive", 2);
                        System.out.println("TIMING device_status: " + (result != null ? result.trim() : "null"));
                    } catch (Exception e) {
                        System.out.println("TIMING device_error: " + e.getMessage());
                    }
                    startScreenCapture();
                }
            }
        }, "watchdog");
        t.setDaemon(true);
        t.start();
    }

    @Override
    public void onOpen(WebSocket webSocket, ClientHandshake clientHandshake) {
        System.out.println("Open");
        String ip = clientHandshake.getResourceDescriptor().split("/")[1];
        String sn = clientHandshake.getResourceDescriptor().split("/")[2];
        HosRemoteConfig config = new HosRemoteConfig(sn);
        config.setIp(ip);
        config.setHdcPath("C:/Users/14057/Documents/AutoTestFramework/HOScrcpy-python-api/hos_scrcpy/toolchains/hdc.exe");
        remoteDevice = new HosRemoteDevice(config);
        // 删掉设备内置 scrcpy 库，迫使 SDK 推备用库走直连 socket（不走 HDC 转发）
        remoteDevice.executeShellCommand("rm -f /data/local/tmp/libscreen_casting.z.so", 3);
        streaming = true;
    }

    @Override
    public void onClose(WebSocket webSocket, int i, String s, boolean b) {
        streaming = false;
    }

    @Override
    public void onMessage(WebSocket webSocket, String message) {
        JSONObject jsonObject = JSONObject.parseObject(message);
        String type = (String) jsonObject.get("type");
        if ("screen".equals(type)) {
            startScreenCapture();
            startWatchdog();
        } else if ("touchEvent".equals(type)) {
            lastTouchTime = System.currentTimeMillis();
            JSONObject msg = (JSONObject) jsonObject.get("message");
            String event = (String) msg.get("event");
            Integer x = (Integer) msg.get("x");
            Integer y = (Integer) msg.get("y");
            if ("down".equals(event)) {
                remoteDevice.onTouchDown(x, y);
            } else if ("up".equals(event)) {
                remoteDevice.onTouchUp(x, y);
            } else {
                remoteDevice.onTouchMove(x, y);
            }
        }
    }

    @Override
    public void onError(WebSocket webSocket, Exception e) {
        System.out.println("error");
    }

    @Override
    public void onStart() {
        System.out.println("Server start!");
        setTcpNoDelay(true);
        setConnectionLostTimeout(0);
    }

    public static void main(String[] args) throws InterruptedException {
        int port = 8899;
        MyWebSocket myWebSocket = new MyWebSocket(port);
        myWebSocket.start();
    }
}
