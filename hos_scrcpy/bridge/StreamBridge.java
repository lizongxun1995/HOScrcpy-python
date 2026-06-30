// StreamBridge.java — H.264 解码为 JPEG 再发送到 stdout
// 使用 javacv (FFmpeg) 解码 H.264 帧，编码为 JPEG 后发送
// Compile: javac -cp "libs/*" StreamBridge.java
// Run:     java -cp ".;libs/*" StreamBridge <sn> <ip> <port> <hdcPath>

import com.huawei.hosscrcpy.api.HosRemoteConfig;
import com.huawei.hosscrcpy.api.HosRemoteDevice;
import com.huawei.hosscrcpy.api.ScreenCapCallback;
import java.io.*;
import java.nio.ByteBuffer;
import java.util.concurrent.*;
import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;

// javacv + FFmpeg
import org.bytedeco.javacpp.*;
import org.bytedeco.ffmpeg.avcodec.*;
import org.bytedeco.ffmpeg.avutil.*;
import org.bytedeco.ffmpeg.swscale.*;
import static org.bytedeco.ffmpeg.global.avcodec.*;
import static org.bytedeco.ffmpeg.global.avutil.*;
import static org.bytedeco.ffmpeg.global.swscale.*;

public class StreamBridge {

    private static HosRemoteDevice device;
    private static volatile boolean running = true;
    private static OutputStream out;
    private static long frameCount = 0;
    private static long jpegCount = 0;

    private static AVCodecParserContext parser;
    private static AVCodecContext codecCtx;
    private static AVFrame frame;
    private static AVFrame frameRGB;
    private static SwsContext swsCtx;
    private static boolean decoderReady = false;

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
        config.setImageScaleSize(720);
        config.setFrameRate(30);
        config.setBitRate(4000000);

        System.err.println("STREAM_MODE sn=" + sn + " jpeg");

        device = new HosRemoteDevice(config);
        CountDownLatch readyLatch = new CountDownLatch(1);
        out = System.out;

        // 初始化 FFmpeg H.264 解码器
        initDecoder();

        System.err.println("TRY_CAPTURE_SCREEN");
        try {
            device.startCaptureScreen(new ScreenCapCallback() {
                @Override
                public void onData(ByteBuffer byteBuffer) {
                    try {
                        int pos = byteBuffer.position();
                        int lim = byteBuffer.limit();
                        int len = lim - pos;
                        if (len <= 0) return;

                        byte[] data = byteBuffer.array();
                        int dataLen = Math.min(len, data.length);
                        if (dataLen <= 0) return;

                        frameCount++;

                        // 用 javacv 解码 H.264 → BufferedImage → JPEG
                        BufferedImage img = decodeH264Frame(data, dataLen);
                        if (img != null) {
                            // 编码为 JPEG
                            ByteArrayOutputStream baos = new ByteArrayOutputStream();
                            ImageIO.write(img, "JPEG", baos);
                            byte[] jpeg = baos.toByteArray();

                            // 发送到 stdout
                            out.write((jpeg.length >> 24) & 0xFF);
                            out.write((jpeg.length >> 16) & 0xFF);
                            out.write((jpeg.length >> 8) & 0xFF);
                            out.write(jpeg.length & 0xFF);
                            out.write(jpeg);
                            out.flush();
                            jpegCount++;
                        }
                    } catch (Exception e) {
                        System.err.println("ON_DATA_ERR:" + e.getMessage());
                    }
                }

                @Override
                public void onException(Throwable throwable) {
                    System.err.println("H264_EXCEPTION:" + throwable.getMessage());
                }

                @Override
                public void onReady() {
                    System.err.println("H264_READY");
                    readyLatch.countDown();
                }
            });
        } catch (Exception e) {
            System.err.println("CAPTURE_ERR:" + e.getMessage());
        }

        readyLatch.await(30, TimeUnit.SECONDS);
        System.err.println("STREAM_READY");

        startTouchReader();

        // 定期报告状态
        while (running) {
            Thread.sleep(5000);
            System.err.println("STATUS frames=" + frameCount + " jpeg=" + jpegCount);
        }

        releaseDecoder();
        System.exit(0);
    }

    // ─── javacv H.264 解码 ─────────────────────────────────────────────

    private static void initDecoder() {
        try {
            av_log_set_level(AV_LOG_QUIET);

            // 查找 H.264 解码器
            AVCodec codec = avcodec_find_decoder(AV_CODEC_ID_H264);
            if (codec == null) {
                System.err.println("NO_H264_DECODER");
                return;
            }

            // 创建 parser + codec context
            parser = av_parser_init(AV_CODEC_ID_H264);
            codecCtx = avcodec_alloc_context3(codec);
            if (avcodec_open2(codecCtx, codec, (PointerPointer) null) < 0) {
                System.err.println("CODEC_OPEN_FAIL");
                return;
            }

            frame = av_frame_alloc();
            frameRGB = av_frame_alloc();
            decoderReady = true;
            System.err.println("DECODER_INIT_OK");
        } catch (Exception e) {
            System.err.println("DECODER_INIT_ERR:" + e.getMessage());
        }
    }

    // H.264 数据缓冲区（跨 onData 调用累积）
    private static byte[] h264Buf = new byte[0];

    private static BufferedImage decodeH264Frame(byte[] data, int len) {
        if (!decoderReady) return null;

        // 累积到缓冲区
        byte[] newBuf = new byte[h264Buf.length + len];
        System.arraycopy(h264Buf, 0, newBuf, 0, h264Buf.length);
        System.arraycopy(data, 0, newBuf, h264Buf.length, len);
        h264Buf = newBuf;

        try {
            AVPacket pkt = new AVPacket();
            int offset = 0;

            while (offset < h264Buf.length) {
                IntPointer pktSize = new IntPointer(0);
                BytePointer pktData = new BytePointer();
                int remaining = h264Buf.length - offset;

                // 拷贝剩余数据到新数组（BytePointer 不支持 offset 构造）
                byte[] chunk = new byte[remaining];
                System.arraycopy(h264Buf, offset, chunk, 0, remaining);
                int consumed = av_parser_parse2(parser, codecCtx,
                    pktData, pktSize,
                    new BytePointer(chunk), remaining,
                    AV_NOPTS_VALUE, AV_NOPTS_VALUE, AV_NOPTS_VALUE);

                if (consumed < 0) break;
                offset += Math.max(consumed, 0);

                if (pktSize.get() <= 0) continue;

                // 找到一个完整 packet → 解码
                pkt.data(pktData);
                pkt.size(pktSize.get());

                int ret = avcodec_send_packet(codecCtx, pkt);
                av_packet_unref(pkt);
                if (ret < 0) continue;

                ret = avcodec_receive_frame(codecCtx, frame);
                if (ret < 0) continue;

                // 解码成功 → 提取帧
                int w = frame.width();
                int h = frame.height();
                if (w <= 0 || h <= 0) continue;

                if (frameRGB.width() != w || frameRGB.height() != h) {
                    av_frame_unref(frameRGB);
                    frameRGB = av_frame_alloc();
                    frameRGB.format(AV_PIX_FMT_BGR24);
                    frameRGB.width(w);
                    frameRGB.height(h);
                    av_frame_get_buffer(frameRGB, 32);

                    swsCtx = sws_getContext(w, h, frame.format(),
                        w, h, AV_PIX_FMT_BGR24,
                        SWS_BILINEAR, (SwsFilter) null, (SwsFilter) null, (DoublePointer) null);
                }

                sws_scale(swsCtx,
                    frame.data(), frame.linesize(), 0, h,
                    frameRGB.data(), frameRGB.linesize());

                BytePointer rgbPtr = frameRGB.data(0);
                byte[] rgbBytes = new byte[w * h * 3];
                rgbPtr.get(rgbBytes);

                // BGR24 → RGB24：交换每像素的第1和第3字节
                for (int i = 0; i < rgbBytes.length; i += 3) {
                    byte tmp = rgbBytes[i];
                    rgbBytes[i] = rgbBytes[i + 2];
                    rgbBytes[i + 2] = tmp;
                }

                BufferedImage img = new BufferedImage(w, h, BufferedImage.TYPE_3BYTE_BGR);
                img.getRaster().setDataElements(0, 0, w, h, rgbBytes);

                // 移除已处理的数据
                if (offset > 0) {
                    byte[] rest = new byte[h264Buf.length - offset];
                    System.arraycopy(h264Buf, offset, rest, 0, rest.length);
                    h264Buf = rest;
                }
                return img;
            }

            // 没有完整帧，保留剩余数据
            if (offset > 0) {
                byte[] rest = new byte[h264Buf.length - offset];
                System.arraycopy(h264Buf, offset, rest, 0, rest.length);
                h264Buf = rest;
            }

        } catch (Exception e) {
            System.err.println("DECODE_LOOP_ERR:" + e.getMessage());
        }
        return null;
    }
    private static void releaseDecoder() {
        if (frame != null) av_frame_free(frame);
        if (frameRGB != null) av_frame_free(frameRGB);
        if (codecCtx != null) avcodec_free_context(codecCtx);
        if (parser != null) av_parser_close(parser);
    }

    // ─── 触摸读取 ──────────────────────────────────────────────────────

    private static void startTouchReader() {
        new Thread(() -> {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(System.in))) {
                System.err.println("TOUCH_READER_STARTED");
                String line;
                while (running && (line = reader.readLine()) != null) {
                    line = line.trim();
                    if (line.isEmpty()) continue;
                    String[] parts = line.split(":");
                    if (parts.length != 3) continue;
                    int x = Integer.parseInt(parts[1]);
                    int y = Integer.parseInt(parts[2]);
                    switch (parts[0]) {
                        case "D": device.onTouchDown(x, y); break;
                        case "U": device.onTouchUp(x, y); break;
                        case "M": device.onTouchMove(x, y); break;
                    }
                }
            } catch (IOException e) {
                System.err.println("TOUCH_IOERR:" + e.getMessage());
            }
        }, "touch-reader").start();
    }
}
