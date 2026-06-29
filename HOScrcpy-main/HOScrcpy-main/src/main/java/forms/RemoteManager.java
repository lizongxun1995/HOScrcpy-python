package forms;

import org.apache.commons.lang3.StringUtils;
import utils.MessageUtil;
import utils.SettingUtil;
import utils.TreeUtil;

import javax.swing.*;
import javax.swing.tree.DefaultMutableTreeNode;
import javax.swing.tree.DefaultTreeModel;
import javax.swing.tree.TreePath;
import javax.swing.tree.TreeSelectionModel;
import java.awt.*;
import java.awt.event.ActionListener;
import java.util.HashSet;

public class RemoteManager extends JDialog {
    private JButton btnAddRemoteIp;
    private JButton btnRemoveIp;
    private JTree tree;
    private JButton btnSave;
    private JButton btnCancel;
    private JPanel contentPanel;
    private DefaultMutableTreeNode ROOT;
    private JDialog dialog;
    private Frame owner;

    public RemoteManager(Frame owner, String title) {
        super(owner, title, true);
        setContentPane(contentPanel);
        setModal(true);
        dialog = this;
        this.owner = owner;
        setTitle("管理远程IP");

        // 创建树节点
        for (String s : SettingUtil.getRemoteIp()) {
            if (StringUtils.isEmpty(s)) {
                continue;
            }
            DefaultMutableTreeNode node = new DefaultMutableTreeNode(s);
            ROOT.add(node);
        }


        tree.setRootVisible(false);
        tree.setDragEnabled(true);
        tree.getSelectionModel().setSelectionMode(TreeSelectionModel.SINGLE_TREE_SELECTION);
        TreeUtil.expandTree(tree, new TreePath(ROOT.getPath()));
        tree.updateUI();

        btnAddRemoteIp.addActionListener(btnAddIpListener);
        btnRemoveIp.addActionListener(btnRemoveIpListener);
        btnSave.addActionListener(btnSaveListener);
        btnCancel.addActionListener(btnCancelListener);
    }

    private final ActionListener btnCancelListener = e -> {
        dialog.setVisible(false);
    };

    private final ActionListener btnSaveListener = e -> {
        HashSet<String> hashSet = new HashSet<>();
        for (int i = 0; i < ROOT.getChildCount(); i++) {
            DefaultMutableTreeNode node = (DefaultMutableTreeNode) ROOT.getChildAt(i);
            if (node.getUserObject() instanceof String) {
                String ip = (String) node.getUserObject();
                hashSet.add(ip);
            }
        }
        SettingUtil.getRemoteIpMap().clear();
        SettingUtil.getRemoteIpMap().addAll(hashSet);
        SettingUtil.saveConfig();
        dialog.setVisible(false);
    };

    private final ActionListener btnAddIpListener = e -> {
        String userInput = getUserInput().trim();
        if (StringUtils.isBlank(userInput)) {
            return;
        }
        DefaultMutableTreeNode node = new DefaultMutableTreeNode(userInput);
        ROOT.add(node);
        TreeUtil.expandTree(tree, new TreePath(ROOT.getPath()));
        tree.updateUI();
    };

    private final ActionListener btnRemoveIpListener = e -> {
        // 获取当前选中的树节点
        DefaultMutableTreeNode treeNode = (DefaultMutableTreeNode) tree.getLastSelectedPathComponent();
        if (treeNode == null) {
            MessageUtil.showInfoMessage(owner, "请先选中需要删除的IP");
            return;
        }
        DefaultTreeModel model = (DefaultTreeModel) tree.getModel();
        if (treeNode.getParent() != null) {
            model.removeNodeFromParent(treeNode);
        }
        tree.updateUI();
    };

    private String getUserInput() {
        JDialog dialog = new JDialog(this, "输入远程ip", true);
        dialog.setLocationRelativeTo(this);
        JPanel panel = new JPanel();
        panel.setLayout(new FlowLayout());
        dialog.setContentPane(panel);

        JTextField jTextField = new JTextField(20);
        JButton jButton = new JButton("确定");
        panel.add(jTextField);
        panel.add(jButton);

        jButton.addActionListener(e -> {
            dialog.setVisible(false);
        });

        dialog.setSize(300, 120);
        dialog.setMinimumSize(new Dimension(300, 120));
        dialog.setVisible(true);
        return jTextField.getText();
    }

    private void createUIComponents() {
        ROOT = new DefaultMutableTreeNode();
        tree = new JTree(ROOT);
    }
}
