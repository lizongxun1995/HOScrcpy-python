package utils;

import org.apache.commons.lang3.StringUtils;
import utils.entity.Device;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;

public class HdcUtil {
    public static List<Device> getRemoteDevice() {
        List<Device> list = new ArrayList<>();
        HashSet<String> remoteIp = SettingUtil.getRemoteIp();
        for (String ip : remoteIp) {
            String cmd = String.format("hdc -s %s:8710 list targets", ip);
            ProcessExecutor processExecutor = new ProcessExecutor();
            String result = processExecutor.callProcess(cmd, 10);
            if (StringUtils.isNotEmpty(result) && !result.contains("Empty")) {
                if (result.contains("failed")) {
                    continue;
                }
                for (String sn : result.split(System.lineSeparator())) {
                    if (StringUtils.isEmpty(sn)) {
                        continue;
                    }
                    Device device = new Device(ip, sn.trim());
                    list.add(device);
                }
            }

        }
        return list;
    }

    public static List<Device> getLocalDevices() {
        List<Device> list = new ArrayList<>();
        String cmd = "hdc -s 127.0.0.1:8710 list targets";
        ProcessExecutor processExecutor = new ProcessExecutor();
        String result = processExecutor.callProcess(cmd, 10);
        if (StringUtils.isNotEmpty(result) && !result.contains("Empty")) {
            if (result.contains("failed")) {
                return list;
            }
            for (String sn : result.split(System.lineSeparator())) {
                if (StringUtils.isEmpty(sn)) {
                    continue;
                }
                Device device = new Device(sn.trim());
                list.add(device);
            }
        }
        return list;
    }
}
