package utils;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import forms.MainForm;

import java.io.File;
import java.util.HashMap;
import java.util.HashSet;

public class SettingUtil {
    private static final String TAG = "SettingUtil";
    public static final String USE_VIDEO_STREAM = "useVideoStream"; // 是否使用视频流投屏模式
    private static final File configFile = new File(System.getProperty("user.dir"), "HOScrcpyConfig.json");
    private static MainForm mainForm;
    private static HashMap<String, String> SCREEN_CAPTURE_PARAM_MAPPER = new HashMap<>();
    private static ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final HashSet<String> REMOTE_IP_MAP = new HashSet<>();


    private static boolean useVideoStream = true;

    public static void saveConfig() {
        try {
            ObjectNode objectNode = OBJECT_MAPPER.createObjectNode();
            saveIp(objectNode);
            objectNode.put(USE_VIDEO_STREAM, useVideoStream);
            FileUtil.createFileByString(configFile, objectNode.toString());
        } catch (Exception ex) {
            Log.info(TAG, "save config file error: " + ex.getMessage());
        }
    }

    public static void setUseVideoStream(boolean useVideoStream) {
        SettingUtil.useVideoStream = useVideoStream;
    }

    public static boolean useVideoStream() {
        String value = getSaveSettingByKey(USE_VIDEO_STREAM);
        if (value == null) {
            return true;
        }
        return value.equals("true");
    }

    public static String getSaveSettingByKey(String key) {
        if (configFile.exists()) {
            try {
                JsonNode jsonNode = OBJECT_MAPPER.readTree(configFile);
                if (jsonNode.get(key) != null) {
                    return jsonNode.get(key).asText().trim();
                }
            } catch (Exception ex) {
                Log.info(TAG, "parse config file error:" + ex);
            }
        }
        return null;
    }

    public static HashSet<String> getRemoteIp() {
        if (configFile.exists()) {
            try {
                String s = FileUtil.readFileContent(configFile);
                JsonNode jsonNode = OBJECT_MAPPER.readTree(s);
                if (jsonNode.get("remoteIp") != null) {
                    JsonNode remoteIp = jsonNode.get("remoteIp");
                    for (int i = 0; i < remoteIp.size(); i++) {
                        String ip = remoteIp.get(i).asText();
                        REMOTE_IP_MAP.add(ip);
                    }
                }
            } catch (Exception ex) {
                Log.info(TAG, "parse config file error: " + ex.getMessage());
            }
        }
        return REMOTE_IP_MAP;
    }

    public static HashSet<String> getRemoteIpMap() {
        return REMOTE_IP_MAP;
    }

    private static void saveIp(ObjectNode objectNode) {
        ArrayNode arrayNode = OBJECT_MAPPER.createArrayNode();
        for (String s : REMOTE_IP_MAP) {
            arrayNode.add(s);
        }
        objectNode.putIfAbsent("remoteIp", arrayNode);
    }
}
