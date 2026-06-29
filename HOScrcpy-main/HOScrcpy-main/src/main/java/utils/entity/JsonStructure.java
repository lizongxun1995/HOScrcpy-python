package utils.entity;

import com.google.gson.annotations.Expose;
import org.apache.commons.lang3.StringUtils;

import javax.swing.tree.DefaultMutableTreeNode;
import java.awt.*;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;

public class JsonStructure {

    @Expose
    private List<JsonStructure> children = new ArrayList<>();
    @Expose
    private HashMap<String, Object> attributes = new HashMap<>();
    private DefaultMutableTreeNode treeNode = new DefaultMutableTreeNode();
    private Rectangle rectangle = new Rectangle();
    private String treeNodePath = "";
    private int index = 0;
    private Point position;
    private String scale = "";

    @Override
    public String toString() {
        return (String) attributes.getOrDefault("type", "");
    }


    public String getText() {
        return (String) attributes.getOrDefault("text", "");
    }

    public String getType() {
        return (String) attributes.getOrDefault("type", "");
    }

    public String getBounds() {
        String origBounds = (String) attributes.getOrDefault("origBounds", "");
        if (StringUtils.isEmpty(origBounds)) {
            return (String) attributes.getOrDefault("bounds", "");
        }
        return origBounds;
    }

    public String getDesc() {
        return (String) attributes.getOrDefault("description", "");
    }


    public String getCenterPosition() {
        if (rectangle != null) {
            return String.format("%s, %s", (int) rectangle.getCenterX(), (int) rectangle.getCenterY());
        }
        return "";
    }


    public String getPath() {
        return getTreeNodePath();
    }

    public List<JsonStructure> getChildren() {
        return children;
    }

    public void setChildren(List<JsonStructure> children) {
        this.children = children;
    }

    public HashMap<String, Object> getAttributes() {
        return attributes;
    }

    public void setAttributes(HashMap<String, Object> attributes) {
        this.attributes = attributes;
    }

    public DefaultMutableTreeNode getTreeNode() {
        return treeNode;
    }

    public void setTreeNode(DefaultMutableTreeNode treeNode) {
        this.treeNode = treeNode;
    }

    public Rectangle getRectangle() {
        return rectangle;
    }

    public void setRectangle(Rectangle rectangle) {
        this.rectangle = rectangle;
    }

    public String getTreeNodePath() {
        return treeNodePath;
    }

    public void setTreeNodePath(String treeNodePath) {
        this.treeNodePath = treeNodePath;
    }

    public int getIndex() {
        return index;
    }

    public void setIndex(int index) {
        this.index = index;
    }

    public Point getPosition() {
        return position;
    }

    public void setPosition(Point position) {
        this.position = position;
    }

    public String getScale() {
        return scale;
    }

    public void setScale(String scale) {
        this.scale = scale;
    }
}
