package forms;

import org.apache.commons.lang3.StringUtils;
import utils.MessageUtil;

import javax.swing.*;
import javax.swing.filechooser.FileFilter;
import java.awt.event.ActionListener;
import java.io.File;

public class LayoutInputForm extends JFrame {
    private JPanel contentPanel;
    private JButton btnOK;
    private JButton btnCancel;
    private JTextField txtPicPath;
    private JButton btnPicSearch;
    private JTextField txtJsonPath;
    private JButton btnJsonSearch;
    private JPanel testPanel;
    private String picPath = "";
    private String jsonPath = "";
    private boolean isCancel = false;


    public LayoutInputForm() {
        btnJsonSearch.addActionListener(btnJsonSearchListener);
        btnOK.addActionListener(btnOKListener);
        btnCancel.addActionListener(btnCancelListener);
        btnPicSearch.addActionListener(btnPicSearchListener);
        testPanel.setVisible(false);
        setSize(200, 300);
        setResizable(false);
    }


    public JComponent getContentPanel() {
        return contentPanel;
    }


    private ActionListener btnJsonSearchListener = e -> {
        JFileChooser fileChooser = new JFileChooser();
        fileChooser.setFileSelectionMode(JFileChooser.FILES_ONLY);
        fileChooser.addChoosableFileFilter(new FileFilter() {
            @Override
            public boolean accept(File f) {
                return f.getName().endsWith(".json");
            }

            @Override
            public String getDescription() {
                return "选择json文件";
            }
        });
        int dialog = fileChooser.showOpenDialog(contentPanel);
        if (dialog == JFileChooser.APPROVE_OPTION) {
            try {
                txtJsonPath.setText(fileChooser.getSelectedFile().getCanonicalPath());
            } catch (Exception ex) {
                MessageUtil.showInfoMessage(contentPanel,"获取json文件路径失败");
            }
        }
    };

    private ActionListener btnPicSearchListener = e -> {
        JFileChooser fileChooser = new JFileChooser();
        fileChooser.setFileSelectionMode(JFileChooser.FILES_ONLY);
        fileChooser.addChoosableFileFilter(new FileFilter() {
            @Override
            public boolean accept(File f) {
                return f.getName().endsWith(".png") || f.getName().endsWith(".jpeg") || f.getName().endsWith(".jpg");
            }

            @Override
            public String getDescription() {
                return "选择图片文件";
            }
        });
        int dialog = fileChooser.showOpenDialog(contentPanel);
        if (dialog == JFileChooser.APPROVE_OPTION) {
            try {
                txtPicPath.setText(fileChooser.getSelectedFile().getCanonicalPath());
            } catch (Exception ex) {
                MessageUtil.showInfoMessage(contentPanel, "获取图片文件路径失败");
            }
        }
    };


    public boolean checkPicPath() {
        picPath = txtPicPath.getText().trim();
        File f = new File(picPath);
        if (StringUtils.isEmpty(picPath) || !f.exists()) {
            MessageUtil.showInfoMessage(contentPanel,"图片路径不存在");
            return false;
        }
        if (!picPath.endsWith(".png") && !picPath.endsWith(".jpeg") && !picPath.endsWith(".jpg")) {
            MessageUtil.showInfoMessage(contentPanel,"请选择png,jpeg或jpg格式的图片");
            return false;
        }
        return true;
    }

    public boolean checkJsonPath() {
        jsonPath = txtJsonPath.getText().trim();
        File f = new File(jsonPath);
        if (StringUtils.isEmpty(jsonPath) || !f.exists()) {
            MessageUtil.showInfoMessage(contentPanel,"json文件路径不存在");
            return false;
        }
        if (!jsonPath.endsWith(".json")) {
            MessageUtil.showInfoMessage(contentPanel,"请选择正确的json文件");
            return false;
        }
        return true;
    }


    private final ActionListener btnOKListener = e -> {


    };

    private final ActionListener btnCancelListener = e -> {
        picPath = "";
        jsonPath = "";
        isCancel = true;
    };

    public File getJson() {
        return new File(txtJsonPath.getText().trim());
    }

    public File getPic() {
        return new File(txtPicPath.getText().trim());
    }
}
