package utils;

import org.apache.commons.lang3.StringUtils;
import utils.entity.JsonStructure;

import javax.swing.*;
import javax.swing.tree.DefaultMutableTreeNode;
import javax.swing.tree.TreeNode;
import javax.swing.tree.TreePath;
import java.awt.*;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;

public class TreeUtil {
    public static String getTreeNodePath(DefaultMutableTreeNode treeNode) {
        TreeNode[] paths = treeNode.getPath();
        StringBuilder sb = new StringBuilder();
        for (int i = paths.length - 1; i > 1; i--) {
            DefaultMutableTreeNode self = (DefaultMutableTreeNode) paths[i];
            JsonStructure jsonStructure = (JsonStructure) self.getUserObject();
            if (paths[i - 1].getChildCount() == 1) {
                sb.insert(0, "/" + jsonStructure.getType());
            } else {
                DefaultMutableTreeNode parent = (DefaultMutableTreeNode) paths[i - 1];
                int index = 0;
                boolean hasSameType = false;
                boolean canIncrement = true;
                for (int j = 0; j < parent.getChildCount(); j++) {
                    DefaultMutableTreeNode c = (DefaultMutableTreeNode) parent.getChildAt(j);
                    JsonStructure cj = (JsonStructure) c.getUserObject();
                    if (cj.getType().equals(jsonStructure.getType()) && c.equals(self)) {
                        canIncrement = false;
                    } else if (cj.getType().equals(jsonStructure.getType())) {
                        hasSameType = true;
                        if (canIncrement) {
                            index++;
                        }
                    }
                }
                if (hasSameType) {
                    sb.insert(0, String.format("/%s[%s]", jsonStructure.getType(), index));
                } else {
                    sb.insert(0, "/" + jsonStructure.getType());
                }
            }
        }
        return sb.toString();
    }

    public static DefaultMutableTreeNode convertJsonStructureToJTreeNode(JsonStructure root) {
        String bounds = root.getBounds();
        if (StringUtils.isNotBlank(bounds)) {
            root.setRectangle(convertBoundsToRectangle(bounds));
        }
        DefaultMutableTreeNode node = new DefaultMutableTreeNode(root);
        root.setTreeNode(node);
        for (int i = 0; i < root.getChildren().size(); i++) {
            root.getChildren().get(i).setIndex(i);
            node.add(convertJsonStructureToJTreeNode(root.getChildren().get(i)));
        }
        return node;
    }

    public static Rectangle convertBoundsToRectangle(String bounds) {
        bounds = bounds.replace("][", " ").replace("[", "").replace("]", "");
        String[] strBounds = bounds.split(" ");
        int startX = Integer.parseInt(strBounds[0].split(",")[0]);
        int startY = Integer.parseInt(strBounds[0].split(",")[1]);
        int endX = Integer.parseInt(strBounds[1].split(",")[0]);
        int endY = Integer.parseInt(strBounds[1].split(",")[1]);
        return new Rectangle(startX, startY, endX - startX, endY - startY);
    }

    public static DefaultMutableTreeNode findMinRangeTreeNode(DefaultMutableTreeNode jTreeNode, Point target) {
        List<DefaultMutableTreeNode> tempList = new ArrayList<>();
        findCommonDataMinRangeTreeNode(tempList, jTreeNode, null, target);
        tempList.sort((o1, o2) -> {
            JsonStructure data1 = (JsonStructure) o1.getUserObject();
            JsonStructure data2 = (JsonStructure) o2.getUserObject();
            int size1 = data1.getRectangle().height * data1.getRectangle().width;
            int size2 = data2.getRectangle().height * data2.getRectangle().width;
            return size1 - size2;
        });
        if (!tempList.isEmpty()) {
            return tempList.get(0);
        }
        return null;
    }

    private static void findCommonDataMinRangeTreeNode(List<DefaultMutableTreeNode> treeSearchResult, DefaultMutableTreeNode jTreeNode, DefaultMutableTreeNode parentTreeNode, Point target) {
        if (!(jTreeNode.getUserObject() instanceof JsonStructure)) {
            return;
        }
        JsonStructure jsonStructure = (JsonStructure) jTreeNode.getUserObject();
        if (jsonStructure.getRectangle().contains(target)) {
            if (parentTreeNode != null) {
                JsonStructure partentJsonStructure = (JsonStructure) parentTreeNode.getUserObject();
                if (partentJsonStructure.getRectangle().width == jsonStructure.getRectangle().width &&
                        partentJsonStructure.getRectangle().height == jsonStructure.getRectangle().height) {
                    treeSearchResult.remove(parentTreeNode);
                }
            }
            treeSearchResult.add(jTreeNode);
        }
        for (JsonStructure child : jsonStructure.getChildren()) {
            findCommonDataMinRangeTreeNode(treeSearchResult, child.getTreeNode(), jTreeNode, target);
        }
    }


    public static void expandTree(JTree tree, TreePath parent) {
        TreeNode node = (TreeNode) parent.getLastPathComponent();
        if (node.getChildCount() > 0) {
            for (Enumeration<? extends TreeNode> e = node.children(); e.hasMoreElements(); ) {
                TreeNode n = e.nextElement();
                TreePath path = parent.pathByAddingChild(n);
                expandTree(tree, path);
            }
        }
        tree.expandPath(parent);
    }

    public static void collapseTree(JTree tree) {
        int row = tree.getRowCount() - 1;
        while (row > 0) {
            tree.collapseRow(row--);
        }
    }

    public static void findTreeNodeByCondition(List<DefaultMutableTreeNode> result, DefaultMutableTreeNode root, String condition, boolean isFuzzyMatch) {
        if (!(root.getUserObject() instanceof JsonStructure)) {
            return;
        }
        JsonStructure jsonStructure = (JsonStructure) root.getUserObject();
        jsonStructure.setTreeNodePath(TreeUtil.getTreeNodePath(jsonStructure.getTreeNode()));
        String id = (String) jsonStructure.getAttributes().getOrDefault("id", "");
        String key = (String) jsonStructure.getAttributes().getOrDefault("key", "");
        String text = jsonStructure.getText();
        String type = jsonStructure.getType();
        String desc = jsonStructure.getDesc();
        String path = jsonStructure.getPath();
        // 判断是否选中了模糊匹配
        if (isFuzzyMatch) {
            if (id.contains(condition) || key.contains(condition) || text.contains(condition) ||
                    desc.contains(condition)) {
                result.add(root);
            }
        } else {
            if (id.equals(condition) || key.equals(condition) || text.equals(condition) ||
                    desc.equals(condition) || path.equals(condition)) {
                result.add(root);
            }
        }

        for (JsonStructure child : jsonStructure.getChildren()) {
            findTreeNodeByCondition(result, child.getTreeNode(), condition, isFuzzyMatch);
        }
    }
}
