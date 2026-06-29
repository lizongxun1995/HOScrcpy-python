package utils.entity;

import org.apache.commons.lang3.StringUtils;
import utils.FileUtil;
import utils.Log;
import utils.ProcessExecutor;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.File;

public class Device {
    private static final String TAG = "Device";
    private String ip = "127.0.0.1";
    private String sn = "";
    private String port = "8710";

    public Device(String sn) {
        this.sn = sn;
    }

    public Device(String ip, String sn) {
        this.ip = ip;
        this.sn = sn;
    }

    private boolean isRemoteDevice() {
        return !"127.0.0.1".equals(ip);
    }


    public String getSn() {
        return sn;
    }

    @Override
    public String toString() {
        if (isRemoteDevice()) {
            return ip + "-" + sn;
        }
        return sn;
    }

    public String getIp() {
        return ip;
    }

    public boolean isOnline() {
        ProcessExecutor processExecutor = new ProcessExecutor();
        String result = processExecutor.callProcess(String.format("hdc -s %s:8710 list targets", ip));
        return !"".equals(sn) && result.contains(sn);
    }


    public BufferedImage getScreenshot(File saveFile) {
        try {
            ProcessExecutor processExecutor = new ProcessExecutor();
            executeShellCommand("rm /data/local/tmp/screen.jpeg", 7);
            executeShellCommand("snapshot_display -f /data/local/tmp/screen.jpeg", 7);
            if (saveFile == null) {
                File tempDirectory = new File(FileUtil.getTempDirectory());
                if (!tempDirectory.exists()) {
                    tempDirectory.mkdirs();
                }
                String jpegName = String.format("%s-screen.jpeg", sn);
                saveFile = new File(FileUtil.getTempDirectory(), jpegName);
            }
            String pullCmd = String.format("file recv /data/local/tmp/screen.jpeg \"%s\"", saveFile.getCanonicalPath());
            String pullResult = executeCommand(pullCmd, 5);
            Log.debug(TAG, "pull screenshot result: " + pullResult);
            if (!saveFile.exists()) {
                Log.info(TAG, "screenshot file not exist");
                return null;
            }
            return ImageIO.read(saveFile);
        } catch (Exception ex) {
            Log.error(TAG, "get screenshot fail", ex);
        }
        return null;
    }

    public String getLayout(File saveFile) {
        try {
            String result = executeShellCommand("uitest dumpLayout", 10);
            Log.debug(TAG, "dump layout result: " + result);
            if (StringUtils.isBlank(result) || !result.contains("DumpLayout saved to:")) {
                Log.debug(TAG, "dump layout failed: " + result);
                return null;
            }
            int first = result.lastIndexOf("to:") + 3;
            int last = result.indexOf(".json") + 6;
            String savePath = result.substring(first, last).trim();
            if (saveFile == null) {
                File tempDirectory = new File(FileUtil.getTempDirectory());
                if (!tempDirectory.exists()) {
                    tempDirectory.mkdirs();
                }
                saveFile = new File(FileUtil.getTempDirectory(), "dumpLayout.json");
            }

            result = executeCommand(String.format("file recv \"%s\" \"%s\"", savePath, saveFile.getCanonicalPath()), 5);
            if (!result.contains("finish") || !saveFile.exists()) {
                Log.info(TAG, "pull dumpLayout.json fail");
                return null;
            }
            return FileUtil.readFileContent(saveFile);
        } catch (Exception ex) {
            Log.error(TAG, "get layout fail", ex);
            return null;
        }
    }

    public String executeShellCommand(String command, int timeOut) {
        return executeCommand("shell " + command, timeOut);
    }

    public String executeCommand(String command, int timeOut) {
        ProcessExecutor processExecutor = new ProcessExecutor();
        String cmd = String.format("hdc -s %s:%s -t %s %s", ip, port, sn, command);
        return processExecutor.callProcess(cmd, timeOut);
    }
}
