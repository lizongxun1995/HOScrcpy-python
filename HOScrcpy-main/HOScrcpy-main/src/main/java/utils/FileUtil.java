package utils;

import java.io.*;
import java.nio.charset.StandardCharsets;

public class FileUtil {
    private static final String TAG = "FileUtil";

    public static String getTempDirectory() {
        String path = System.getProperty("user.dir");
        return path == null ? "temp" : path + "/temp";
    }


    public static String readFileContent(File file) {
        return readFileContent(file, false);
    }

    public static String readFileContent(File file, boolean needAddWarp) {
        try (FileInputStream fis = new FileInputStream(file);
             InputStreamReader isr = new InputStreamReader(fis, StandardCharsets.UTF_8);
             BufferedReader br = new BufferedReader(isr)) {
            String line;
            StringBuilder sb = new StringBuilder();
            while ((line = br.readLine()) != null) {
                sb.append(line).append(needAddWarp ? "\n" : "");
            }
            return sb.toString();
        } catch (Exception ex) {
            Log.info(TAG, "read file content fail: " + ex);
            return "";
        }
    }

    public static void createFileByString(File file, String content) {
        try (FileWriter fileWriter = new FileWriter(file)) {
            fileWriter.write(content);
        } catch (IOException ex) {
            Log.info(TAG, "createFileByString fail: " + ex);
        }
    }

    public static byte[] readResourceFileByteArray(String fileName) {
        byte[] res = null;
        try (InputStream inputStream = FileUtil.class.getClassLoader().getResourceAsStream(fileName)) {
            ByteArrayOutputStream result = new ByteArrayOutputStream();
            byte[] bytes = new byte[1024];
            int length;
            while (true) {
                try {
                    assert inputStream != null;
                    if ((length = inputStream.read(bytes)) == -1) {
                        break;
                    }
                } catch (IOException e) {
                    Log.info(TAG, String.format("read resource file error: %s", e.getMessage()));
                    break;
                }
                result.write(bytes, 0, length);
            }
            res = result.toByteArray();
        } catch (IOException ex) {
            Log.info(TAG, String.format("read resource file error: %s", ex.getMessage()));
        }
        return res;
    }
}
