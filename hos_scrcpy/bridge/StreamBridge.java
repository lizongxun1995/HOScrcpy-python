// StreamBridge.java — H.264 视频流转发到 stdout
// 两种模式：
//   默认模式：FFmpeg 解码 H.264 → JPEG → stdout（兼容无 PyAV 的场景）
//   --raw 模式：原始 H.264 NAL 单元 → stdout（高性能，需 PyAV 解码）
// Compile: javac -cp "libs/*" StreamBridge.java
// Run:     java -cp ".;libs/*" StreamBridge <sn> [ip] [port] [hdcPath] [--raw]

import com.huawei.hosscrcpy.api.HosRemoteConfig;
import com.huawei.hosscrcpy.api.HosRemoteDevice;
import com.huawei.hosscrcpy.api.ScreenCapCallback;
import java.io.*;
import java.nio.ByteBuffer;
import java.util.concurrent.*;

public class StreamBridge {

    private static HosRemoteDevice device;
    private static volatile boolean running = true;
    private static OutputStream out;
    private static volatile long frameCount = 0;
    private static long t0;
    private static boolean rawMode = false;

    private static void logTiming(String label) {
        long now = System.currentTimeMillis();
        long elapsed = now - t0;
        System.err.println("TIMING " + label + " +" + elapsed + "ms");
    }

    public static void main(String[] args) throws Exception {
        t0 = System.currentTimeMillis();
        if (args.length < 1) {
            System.err.println("Usage: StreamBridge <sn> [ip] [port] [hdcPath] [--raw]");
            System.exit(1);
        }

        String sn = args[0];

        // 扫描 --raw 标志，然后按位置解析剩余参数
        int argIdx = 1;
        if (argIdx < args.length && args[argIdx].equals("--raw")) {
            rawMode = true;
            argIdx++;
        }
        String ip = argIdx < args.length ? args[argIdx++] : "127.0.0.1";
        int hdcPort = argIdx < args.length ? Integer.parseInt(args[argIdx++]) : 8710;
        String hdcPath = argIdx < args.length ? args[argIdx] : "hdc";

        HosRemoteConfig config = new HosRemoteConfig(sn);
        config.setIp(ip);
        config.setHdcPath(hdcPath);
        config.setImageScaleSize(720);
        config.setFrameRate(30);
        config.setBitRate(4000000);

        System.err.println("STREAM_MODE sn=" + sn + (rawMode ? " raw" : " jpeg"));

        device = new HosRemoteDevice(config);
        out = System.out;

        startCaptureLoop();
    }

    private static void startCaptureLoop() throws Exception {
        boolean touchStarted = false;
        int retryCount = 0;

        while (running) {
            retryCount++;
            CountDownLatch readyLatch = new CountDownLatch(1);

            logTiming("init_done");

            if (!rawMode) {
                // JPEG 模式：需要 FFmpeg 解码
                initDecoder();
                logTiming("decoder_init_done");
            }

            System.err.println("TRY_CAPTURE_SCREEN attempt=" + retryCount + (rawMode ? " raw" : " jpeg"));
            logTiming("before_start_capture");

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
                            if (frameCount == 1) {
                                logTiming("first_onData");
                            }

                            if (rawMode) {
                                // ── Raw H.264 模式：直接转发原始数据 ──
                                // 发送到 stdout: [4字节大端长度][原始H.264数据]
                                out.write((dataLen >> 24) & 0xFF);
                                out.write((dataLen >> 16) & 0xFF);
                                out.write((dataLen >> 8) & 0xFF);
                                out.write(dataLen & 0xFF);
                                out.write(data, 0, dataLen);
                                out.flush();
                            } else {
                                // ── JPEG 模式：FFmpeg 解码 → JPEG 编码 ──
                                java.awt.image.BufferedImage img = decodeH264Frame(data, dataLen);
                                if (img != null) {
                                    ByteArrayOutputStream baos = new ByteArrayOutputStream();
                                    javax.imageio.ImageIO.write(img, "JPEG", baos);
                                    byte[] jpeg = baos.toByteArray();

                                    out.write((jpeg.length >> 24) & 0xFF);
                                    out.write((jpeg.length >> 16) & 0xFF);
                                    out.write((jpeg.length >> 8) & 0xFF);
                                    out.write(jpeg.length & 0xFF);
                                    out.write(jpeg);
                                    out.flush();
                                }
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
                        logTiming("onReady_called");
                        System.err.println("H264_READY");
                        readyLatch.countDown();
                    }
                });

                readyLatch.await(30, TimeUnit.SECONDS);
                logTiming("after_ready_latch");
                System.err.println("STREAM_READY");

                // 只在第一次成功时启动触摸
                if (!touchStarted) {
                    startTouchReader();
                    touchStarted = true;
                }

                // 监视流状态
                long lastFrameCount = -1;
                int staleSeconds = 0;
                while (running) {
                    Thread.sleep(3000);
                    long fCount = frameCount;
                    System.err.println("STATUS frames=" + fCount + " retry=" + retryCount + (rawMode ? " raw" : " jpeg"));

                    if (fCount == lastFrameCount && lastFrameCount >= 0) {
                        staleSeconds += 3;
                        int timeout = (lastFrameCount == 0) ? 30 : 12;
                        if (staleSeconds >= timeout) {
                            System.err.println("STREAM_STALE no progress for " + staleSeconds + "s, restarting...");
                            break;
                        }
                    } else {
                        staleSeconds = 0;
                    }
                    lastFrameCount = fCount;
                }

            } catch (Exception e) {
                System.err.println("CAPTURE_LOOP_ERR:" + e.getMessage());
            } finally {
                try {
                    if (!rawMode) releaseDecoder();
                    device.stopCaptureScreen();
                } catch (Exception ex) {}
                try { Thread.sleep(2000); } catch (Exception ex) {}
                System.err.println("STREAM_RESTART retry=" + retryCount);
            }
        }
    }


    private static org.bytedeco.javacpp.PointerPointer dummyPtr;
    private static org.bytedeco.ffmpeg.avcodec.AVCodecParserContext parser;
    private static org.bytedeco.ffmpeg.avcodec.AVCodecContext codecCtx;
    private static org.bytedeco.ffmpeg.avutil.AVFrame frame;
    private static org.bytedeco.ffmpeg.avutil.AVFrame frameRGB;
    private static org.bytedeco.ffmpeg.swscale.SwsContext swsCtx;
    private static boolean decoderReady = false;
    private static byte[] h264Buf = new byte[0];

    private static void initDecoder() {
        try {
            org.bytedeco.ffmpeg.global.avutil.av_log_set_level(
                org.bytedeco.ffmpeg.global.avutil.AV_LOG_QUIET);

            org.bytedeco.ffmpeg.avcodec.AVCodec codec =
                org.bytedeco.ffmpeg.global.avcodec.avcodec_find_decoder(
                    org.bytedeco.ffmpeg.global.avcodec.AV_CODEC_ID_H264);
            if (codec == null) {
                System.err.println("NO_H264_DECODER");
                return;
            }

            parser = org.bytedeco.ffmpeg.global.avcodec.av_parser_init(
                org.bytedeco.ffmpeg.global.avcodec.AV_CODEC_ID_H264);
            codecCtx = org.bytedeco.ffmpeg.global.avcodec.avcodec_alloc_context3(codec);
            if (org.bytedeco.ffmpeg.global.avcodec.avcodec_open2(
                    codecCtx, codec, dummyPtr) < 0) {
                System.err.println("CODEC_OPEN_FAIL");
                return;
            }

            frame = org.bytedeco.ffmpeg.global.avutil.av_frame_alloc();
            frameRGB = org.bytedeco.ffmpeg.global.avutil.av_frame_alloc();
            decoderReady = true;
            System.err.println("DECODER_INIT_OK");
        } catch (Exception e) {
            System.err.println("DECODER_INIT_ERR:" + e.getMessage());
        }
    }

    private static java.awt.image.BufferedImage decodeH264Frame(byte[] data, int len) {
        if (!decoderReady) return null;
        // (existing decode logic - omitted for brevity, same as before)
        byte[] newBuf = new byte[h264Buf.length + len];
        System.arraycopy(h264Buf, 0, newBuf, 0, h264Buf.length);
        System.arraycopy(data, 0, newBuf, h264Buf.length, len);
        h264Buf = newBuf;

        try {
            org.bytedeco.ffmpeg.avcodec.AVPacket pkt = new org.bytedeco.ffmpeg.avcodec.AVPacket();
            int offset = 0;

            while (offset < h264Buf.length) {
                org.bytedeco.javacpp.IntPointer pktSize = new org.bytedeco.javacpp.IntPointer(0);
                org.bytedeco.javacpp.BytePointer pktData = new org.bytedeco.javacpp.BytePointer();
                int remaining = h264Buf.length - offset;

                byte[] chunk = new byte[remaining];
                System.arraycopy(h264Buf, offset, chunk, 0, remaining);
                int consumed = org.bytedeco.ffmpeg.global.avcodec.av_parser_parse2(
                    parser, codecCtx, pktData, pktSize,
                    new org.bytedeco.javacpp.BytePointer(chunk), remaining,
                    org.bytedeco.ffmpeg.global.avutil.AV_NOPTS_VALUE,
                    org.bytedeco.ffmpeg.global.avutil.AV_NOPTS_VALUE,
                    org.bytedeco.ffmpeg.global.avutil.AV_NOPTS_VALUE);

                if (consumed < 0) break;
                offset += Math.max(consumed, 0);
                if (pktSize.get() <= 0) continue;

                pkt.data(pktData);
                pkt.size(pktSize.get());

                int ret = org.bytedeco.ffmpeg.global.avcodec.avcodec_send_packet(codecCtx, pkt);
                org.bytedeco.ffmpeg.global.avcodec.av_packet_unref(pkt);
                if (ret < 0) continue;

                ret = org.bytedeco.ffmpeg.global.avcodec.avcodec_receive_frame(codecCtx, frame);
                if (ret < 0) continue;

                int w = frame.width();
                int h = frame.height();
                if (w <= 0 || h <= 0) continue;

                if (frameRGB.width() != w || frameRGB.height() != h) {
                    org.bytedeco.ffmpeg.global.avutil.av_frame_unref(frameRGB);
                    frameRGB = org.bytedeco.ffmpeg.global.avutil.av_frame_alloc();
                    frameRGB.format(org.bytedeco.ffmpeg.global.avutil.AV_PIX_FMT_BGR24);
                    frameRGB.width(w);
                    frameRGB.height(h);
                    org.bytedeco.ffmpeg.global.avutil.av_frame_get_buffer(frameRGB, 32);

                    swsCtx = org.bytedeco.ffmpeg.global.swscale.sws_getContext(
                        w, h, frame.format(),
                        w, h, org.bytedeco.ffmpeg.global.avutil.AV_PIX_FMT_BGR24,
                        org.bytedeco.ffmpeg.global.swscale.SWS_BILINEAR,
                        (org.bytedeco.ffmpeg.swscale.SwsFilter)null,
                        (org.bytedeco.ffmpeg.swscale.SwsFilter)null,
                        (org.bytedeco.javacpp.DoublePointer)null);
                }

                org.bytedeco.ffmpeg.global.swscale.sws_scale(
                    swsCtx, frame.data(), frame.linesize(), 0, h,
                    frameRGB.data(), frameRGB.linesize());

                org.bytedeco.javacpp.BytePointer rgbPtr = frameRGB.data(0);
                byte[] rgbBytes = new byte[w * h * 3];
                rgbPtr.get(rgbBytes);

                for (int i = 0; i < rgbBytes.length; i += 3) {
                    byte tmp = rgbBytes[i];
                    rgbBytes[i] = rgbBytes[i + 2];
                    rgbBytes[i + 2] = tmp;
                }

                java.awt.image.BufferedImage img =
                    new java.awt.image.BufferedImage(w, h, java.awt.image.BufferedImage.TYPE_3BYTE_BGR);
                img.getRaster().setDataElements(0, 0, w, h, rgbBytes);

                if (offset > 0) {
                    byte[] rest = new byte[h264Buf.length - offset];
                    System.arraycopy(h264Buf, offset, rest, 0, rest.length);
                    h264Buf = rest;
                }
                return img;
            }

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
        if (frame != null) org.bytedeco.ffmpeg.global.avutil.av_frame_free(frame);
        if (frameRGB != null) org.bytedeco.ffmpeg.global.avutil.av_frame_free(frameRGB);
        if (codecCtx != null) org.bytedeco.ffmpeg.global.avcodec.avcodec_free_context(codecCtx);
        if (parser != null) org.bytedeco.ffmpeg.global.avcodec.av_parser_close(parser);
        if (swsCtx != null) org.bytedeco.ffmpeg.global.swscale.sws_freeContext(swsCtx);
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
