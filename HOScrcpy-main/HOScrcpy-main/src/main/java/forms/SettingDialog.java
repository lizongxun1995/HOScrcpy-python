package forms;

import utils.SettingUtil;

import javax.swing.*;
import java.awt.event.ActionListener;

public class SettingDialog extends JDialog {
    private JPanel contentPanel;
    private JRadioButton rbUseVideoStream;
    private JButton btnOK;
    private JButton btnCancel;
    private MainForm mainForm;

    public SettingDialog(MainForm mainForm) {
        super(mainForm, "设置", true);
        setTitle("设置");
        this.mainForm = mainForm;
        setContentPane(contentPanel);
        btnOK.addActionListener(btnOKListener);
        btnCancel.addActionListener(btnCancelListener);
        boolean useVideoStream = SettingUtil.useVideoStream();
        rbUseVideoStream.setSelected(useVideoStream);
    }


    private final ActionListener btnOKListener = e -> {
        SettingUtil.setUseVideoStream(rbUseVideoStream.isSelected());
        SettingUtil.saveConfig();
        SettingDialog.this.setVisible(false);
    };

    private final ActionListener btnCancelListener = e -> {
        SettingDialog.this.setVisible(false);
    };

    private boolean checkSettingChange(){
        boolean useVideoStream = SettingUtil.useVideoStream();
        if(useVideoStream != rbUseVideoStream.isSelected()){
            return true;
        }
        return false;
    }
}
