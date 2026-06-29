package utils;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.text.DateFormat;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.logging.*;

public class Log {
    private static Logger LOGGER = null;


    private static void printLog(Level level, String tag, String message, Throwable exception) {
        if (tag == null || message == null) {
            return;
        }
        synchronized (Logger.class) {
            if (LOGGER == null) {
                try {
                    LOGGER = Logger.getLogger("com.huawei.desktopscrcpy");
                    ConsoleHandler handler = new ConsoleHandler();
                    handler.setEncoding("UTF-8");
                    handler.setFormatter(new LogFormatter());
                    handler.setLevel(Level.FINE);
                    LOGGER.addHandler(handler);
                    LOGGER.setLevel(Level.FINE);
                    LOGGER.setUseParentHandlers(false);
                } catch (Exception ex) {
                    throw new RuntimeException(ex);
                }
            }
        }
        LogRecord record = new LogRecord(level, message);
        record.setSourceClassName(tag);
        if (exception != null) {
            record.setThrown(exception);
        }
        LOGGER.log(record);

    }

    public static void debug(String tag, String message) {
        printLog(Level.FINE, tag, message, null);
    }

    public static void info(String tag, String message) {
        printLog(Level.INFO, tag, message, null);
    }

    public static void error(String tag, String message, Throwable exception) {
        printLog(Level.SEVERE, tag, message, exception);
    }


    private static class LogFormatter extends Formatter {
        private static final DateFormat DF = new SimpleDateFormat("yyyy.MM.dd/hh:mm:ss.SSS");

        @Override
        public String format(LogRecord record) {
            if (record == null) {
                return null;
            }
            String level = record.getLevel().getName();
            if (record.getLevel() == Level.FINE) {
                level = "DEBUG";
            } else if (record.getLevel() == Level.SEVERE) {
                level = "ERROR";
            }

            StringBuilder builder = new StringBuilder(1000);
            builder.append(DF.format(new Date(record.getMillis()))).append("/");
            builder.append(level).append(" [");
            builder.append(record.getSourceClassName()).append("] ");
            builder.append(record.getMessage());
            if (record.getThrown() != null) {
                StringWriter sw = new StringWriter();
                record.getThrown().printStackTrace(new PrintWriter(sw));
                builder.append(": ").append(sw);
            }
            builder.append("\n");
            return builder.toString();
        }


    }
}
