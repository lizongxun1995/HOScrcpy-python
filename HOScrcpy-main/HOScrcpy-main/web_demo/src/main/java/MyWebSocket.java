import com.alibaba.fastjson.JSONObject;
import com.huawei.hosscrcpy.api.HosRemoteDevice;
import com.huawei.hosscrcpy.api.ScreenCapCallback;
import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;

import java.net.InetSocketAddress;
import java.nio.ByteBuffer;

public class MyWebSocket extends WebSocketServer {
    private HosRemoteDevice remoteDevice = null;

    public MyWebSocket(int port) {
        super(new InetSocketAddress(port));
    }


    @Override
    public void onOpen(WebSocket webSocket, ClientHandshake clientHandshake) {
        System.out.println("Open");
        String ip = clientHandshake.getResourceDescriptor().split("/")[1];
        String sn = clientHandshake.getResourceDescriptor().split("/")[2];
        remoteDevice = new HosRemoteDevice(ip, sn);
    }

    @Override
    public void onClose(WebSocket webSocket, int i, String s, boolean b) {

    }

    @Override
    public void onMessage(WebSocket webSocket, String message) {
        System.out.println(message);
        JSONObject jsonObject = JSONObject.parseObject(message);
        String type = (String) jsonObject.get("type");
        if ("screen".equals(type)) {
            remoteDevice.stopCaptureScreen();
            remoteDevice.startCaptureScreen(new ScreenCapCallback() {
                @Override
                public void onData(ByteBuffer byteBuffer) {
                    broadcast(byteBuffer);
                }

                @Override
                public void onException(Throwable throwable) {
                    System.out.println("获取视频流失败");
                }

                @Override
                public void onReady() {
                    System.out.println("视频流准备完成");
                }
            });
        } else if ("image".equals(type)) {
            remoteDevice.stopImageScreenCapture();
            remoteDevice.startImageScreenCapture(new ScreenCapCallback() {
                @Override
                public void onData(ByteBuffer byteBuffer) {
                    broadcast(byteBuffer);
                }

                @Override
                public void onException(Throwable throwable) {
                    System.out.println("获取图片流失败");
                }

                @Override
                public void onReady() {
                    System.out.println("图片流准备完成");
                }
            });
        } else if ("touchEvent".equals(type)) {
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
