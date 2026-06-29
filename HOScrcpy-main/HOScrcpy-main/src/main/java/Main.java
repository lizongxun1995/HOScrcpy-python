import com.formdev.flatlaf.FlatIntelliJLaf;
import forms.MainForm;

import javax.swing.*;
import java.awt.*;

public class Main {
    public static void main(String[] args) {
        FlatIntelliJLaf.install();
        Dimension screenSize = Toolkit.getDefaultToolkit().getScreenSize();
        int x = (screenSize.width - 550) / 2;
        int y = (screenSize.height - 500) / 2;
        MainForm mainForm = new MainForm();
        mainForm.setLocation(x, y);
        mainForm.setSize(new Dimension(550, 500));
        mainForm.setMinimumSize(new Dimension(550, 500));
        mainForm.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        mainForm.getContentPane().setFocusCycleRoot(true);
        mainForm.setVisible(true);
    }
}
