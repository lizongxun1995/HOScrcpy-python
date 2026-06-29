package utils;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Timer;
import java.util.TimerTask;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class ProcessExecutor {
    private static final String TAG = "ProcessExecutor";
    private static final long TIMEOUT = 4;
    private CompletableFuture<Void> future;

    public String callProcess(String cmd) {
        return callProcess(cmd, null, TIMEOUT);
    }

    public String callProcess(String cmd, int timeOut) {
        return callProcess(cmd, null, timeOut);
    }

    public String callProcess(String cmd, File file, long timeOut) {
        StringBuilder sb = new StringBuilder();
        Timer timer = new Timer();
        try {
            Process process;
            ProcessBuilder processBuilder = new ProcessBuilder(cmd.split(" "));
            processBuilder.redirectErrorStream(true);
            if (file != null) {
                processBuilder.directory(file);
            }
            process = processBuilder.start();
            try {
                future = CompletableFuture.runAsync(() -> {
                    try {
                        String line;
                        try (BufferedReader outputReader = new BufferedReader(
                                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                            while ((line = outputReader.readLine()) != null) {
                                sb.append(line).append(System.lineSeparator());
                            }
                        }
                        try (BufferedReader outputReader = new BufferedReader(
                                new InputStreamReader(process.getErrorStream(), StandardCharsets.UTF_8))) {
                            boolean isFirstTime = true;
                            while ((line = outputReader.readLine()) != null) {
                                if (isFirstTime) {
                                    isFirstTime = false;
                                    sb.append("ErrorMessage:").append(System.lineSeparator());
                                }
                                sb.append(line).append(System.lineSeparator());
                            }
                        }
                        process.waitFor(timeOut, TimeUnit.SECONDS);
                    } catch (Exception ex) {
                        Log.error(TAG, "process error", ex);
                    } finally {
                        process.destroyForcibly();
                    }
                });
                timer.schedule(new TimerTask() {
                    @Override
                    public void run() {
                        process.destroyForcibly();
                        future.cancel(true);
                    }
                }, timeOut * 1000);
                future.get(timeOut, TimeUnit.SECONDS);
            } catch (Exception ex) {
                return sb.toString();
            }
        } catch (Exception ex) {
            sb.append("ErrorMessage:").append(System.lineSeparator());
        } finally {
            timer.cancel();
        }
        return sb.toString();
    }
}
