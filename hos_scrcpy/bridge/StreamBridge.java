// StreamBridge.java — JPEG image stream + stdin touch commands
// Compile: javac -cp "libs/*" StreamBridge.java
// Run:     java -cp ".;libs/*" StreamBridge <sn> <ip> <port> <hdcPath>

import com.huawei.hosscrcpy.api.HosRemoteConfig;
import com.huawei.hosscrcpy.api.HosRemoteDevice;
import com.huawei.hosscrcpy.api.ScreenCapCallback;
import java.io.*;
import java.nio.ByteBuffer;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class StreamBridge {

    private static HosRemoteDevice device;
    private static volatile boolean running = true;

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("Usage: StreamBridge <sn> [ip] [port] [hdcPath]");
            System.exit(1);
        }

        String sn = args[0];
        String ip = args.length > 1 ? args[1] : "127.0.0.1";
        int hdcPort = args.length > 2 ? Integer.parseInt(args[2]) : 8710;
        String hdcPath = args.length > 3 ? args[3] : "hdc";

        HosRemoteConfig config = new HosRemoteConfig(sn);
        config.setIp(ip);
        config.setHdcPath(hdcPath);

        System.err.println("IMAGE_MODE sn=" + sn);

        device = new HosRemoteDevice(config);
        CountDownLatch readyLatch = new CountDownLatch(1);
        CountDownLatch errorLatch = new CountDownLatch(1);
        OutputStream out = System.out;

        device.stopImageScreenCapture();
        device.startImageScreenCapture(new ScreenCapCallback() {
            @Override
            public void onData(ByteBuffer byteBuffer) {
                try {
                    byte[] data = byteBuffer.array();
                    int len = data.length;
                    out.write((len >> 24) & 0xFF);
                    out.write((len >> 16) & 0xFF);
                    out.write((len >> 8) & 0xFF);
                    out.write(len & 0xFF);
                    out.write(data);
                    out.flush();
                } catch (IOException e) {
                    errorLatch.countDown();
                }
            }
            @Override
            public void onException(Throwable throwable) {
                System.err.println("ERROR:" + throwable.getMessage());
                errorLatch.countDown();
            }
            @Override
            public void onReady() {
                System.err.println("READY");
                readyLatch.countDown();
            }
        });

        if (!readyLatch.await(30, TimeUnit.SECONDS)) {
            System.err.println("TIMEOUT");
            System.exit(1);
        }

        // Give the reverse control service time to fully initialize
        Thread.sleep(2000);

        startTouchReader();
        errorLatch.await();
        running = false;
        device.stopImageScreenCapture();
        System.exit(0);
    }

    private static void startTouchReader() {
        new Thread(() -> {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(System.in))) {
                System.err.println("TOUCH_READER_STARTED");
                String line;
                while (running && (line = reader.readLine()) != null) {
                    line = line.trim();
                    if (line.isEmpty()) continue;
                    System.err.println("TOUCH_CMD:" + line);
                    try {
                        String[] parts = line.split(":");
                        if (parts.length != 3) continue;
                        int x = Integer.parseInt(parts[1]);
                        int y = Integer.parseInt(parts[2]);
                        switch (parts[0]) {
                            case "D": device.onTouchDown(x, y); break;
                            case "U": device.onTouchUp(x, y); break;
                            case "M": device.onTouchMove(x, y); break;
                        }
                        System.err.println("TOUCH_DONE:" + line);
                    } catch (Exception e) {
                        System.err.println("TOUCH_ERR:" + e.getMessage());
                    }
                }
            } catch (IOException e) {
                System.err.println("TOUCH_IOERR:" + e.getMessage());
            }
        }, "touch-reader").start();
    }
}
