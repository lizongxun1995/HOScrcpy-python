package utils;

import javax.swing.*;
import java.awt.*;

public class MessageUtil {
    public static void showInfoMessage(Component parent, String message){
        JOptionPane.showMessageDialog(parent, message, "提示", JOptionPane.INFORMATION_MESSAGE);
    }
}
