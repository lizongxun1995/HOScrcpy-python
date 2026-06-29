package utils.swing;

import org.apache.commons.lang3.StringUtils;
import utils.KeyCodeUtil;
import utils.callbacks.ActualTimeControlCallBack;
import utils.callbacks.DumpLayoutCallBack;
import utils.callbacks.KeyBoardCallBack;
import utils.callbacks.MouseWheelCallBack;

import javax.swing.*;
import java.awt.*;
import java.awt.event.*;
import java.awt.image.BufferedImage;
import java.text.AttributedCharacterIterator;
import java.util.ArrayList;
import java.util.List;

public class MultiFunctionLabel extends JTextField {
    public static final String DEFAULT_TIP_MESSAGE = "可以将单个图片或控件树json文件拖动到此处";
    public static final String STREAM_INIT_TIP_MESSAGE = "画面初始化中,请等待...";
    public static final String STREAM_READY_TIP_MESSAGE = "视频流准备完成,如无画面请点击电源键按钮";
    private BufferedImage image;
    private ActualTimeControlCallBack actualTimeControlCallBack;
    private MouseWheelCallBack mouseWheelCallBack;
    private DumpLayoutCallBack dumpLayoutCallBack;
    private KeyBoardCallBack keyBoardCallBack;
    private boolean screenCapturingMode = false;
    private Dimension currentSize = new Dimension();
    private List<Rectangle> rectangles = new ArrayList<>();
    private Rectangle scaleRectangle;
    private String tipMessage = "";

    public void setTipMessage(String tipMessage) {
        this.tipMessage = tipMessage;
        repaint();
    }

    public void setMouseWheelCallBack(MouseWheelCallBack mouseWheelCallBack) {
        this.mouseWheelCallBack = mouseWheelCallBack;
    }

    public void setKeyBoardCallBack(KeyBoardCallBack keyBoardCallBack) {
        this.keyBoardCallBack = keyBoardCallBack;
    }

    public boolean isScreenCapturingMode() {
        return screenCapturingMode;
    }

    public void setScreenCapturingMode(boolean screenCapturingMode) {
        this.screenCapturingMode = screenCapturingMode;
    }

    public void setDumpLayoutCallBack(DumpLayoutCallBack dumpLayoutCallBack) {
        this.dumpLayoutCallBack = dumpLayoutCallBack;
    }

    public void setImage(BufferedImage image) {
        tipMessage = image == null ? DEFAULT_TIP_MESSAGE : "";
        this.image = image;
        repaint();
    }

    public BufferedImage getImage() {
        return image;
    }

    public void setRectangles(List<Rectangle> rectangles) {
        this.rectangles = rectangles;
        repaint();
    }

    public Dimension getCurrentSize() {
        if (image == null) {
            return null;
        }
        double aspectRatio = 1.0 * image.getWidth() / image.getHeight();
        int imgSizeWidth = (int) Math.min(getWidth(), aspectRatio * getHeight());
        int imgSizeHeight = (int) (imgSizeWidth / aspectRatio);
        currentSize.setSize(imgSizeWidth, imgSizeHeight);
        return currentSize;
    }

    public void setActualTimeControlCallBack(ActualTimeControlCallBack actualTimeControlCallBack) {
        this.actualTimeControlCallBack = actualTimeControlCallBack;
    }

    public MultiFunctionLabel() {
        setBorder(BorderFactory.createEmptyBorder());
        setCursor(Cursor.getPredefinedCursor(Cursor.DEFAULT_CURSOR));
        addMouseWheelListener(new MouseWheelListener() {
            @Override
            public void mouseWheelMoved(MouseWheelEvent e) {
                if (mouseWheelCallBack != null && isScreenCapturingMode()) {
                    mouseWheelCallBack.onMouseWheelChange(e.getPoint(), e.getWheelRotation() != 1);
                }
            }
        });
        addMouseListener(new MouseAdapter() {
            @Override
            public void mousePressed(MouseEvent e) {
                requestFocus();
                if (isScreenCapturingMode()) {
                    if (actualTimeControlCallBack != null) {
                        actualTimeControlCallBack.onMouseDown(e, MultiFunctionLabel.this);
                    }
                } else {
                    if (dumpLayoutCallBack != null) {
                        dumpLayoutCallBack.normalDumpLayoutMode(e.getPoint());
                    }
                }

            }

            @Override
            public void mouseReleased(MouseEvent e) {
                if (screenCapturingMode && actualTimeControlCallBack != null) {
                    actualTimeControlCallBack.onMouseUp(e, MultiFunctionLabel.this);
                }
            }
        });

        addMouseMotionListener(new MouseAdapter() {

            @Override
            public void mouseDragged(MouseEvent e) {
                if (screenCapturingMode && actualTimeControlCallBack != null) {
                    actualTimeControlCallBack.onMouseMove(e, MultiFunctionLabel.this, true);
                }
            }

            @Override
            public void mouseMoved(MouseEvent e) {
                if (getImage() == null) {
                    return;
                }
                if (screenCapturingMode && actualTimeControlCallBack != null) {
                    actualTimeControlCallBack.onMouseMove(e, MultiFunctionLabel.this, false);
                }
            }
        });

        addKeyListener(new KeyAdapter() {
            @Override
            public void keyPressed(KeyEvent e) {
                if (e.getKeyCode() == KeyEvent.VK_SHIFT || !screenCapturingMode
                        || !KeyCodeUtil.isSupport(e) || keyBoardCallBack == null) {
                    return;
                }
                if (KeyCodeUtil.isPasteAction(e)) {
                    keyBoardCallBack.onPressPaste();
                    return;
                }

                int keyCode = KeyCodeUtil.getKeyCode(e);
                if (keyCode == -1) {
                    return;
                }
                keyBoardCallBack.onKeyBoardDown(e, keyCode,
                        e.getModifiers() == Event.SHIFT_MASK);
            }
        });

        addInputMethodListener(new InputMethodListener() {
            @Override
            public void inputMethodTextChanged(InputMethodEvent event) {
                int committedCount = event.getCommittedCharacterCount();
                AttributedCharacterIterator text = event.getText();
                if (committedCount > 0 && text != null) {
                    StringBuilder committedText = new StringBuilder();
                    text.first();
                    for (int i = 0; i < committedCount; i++) {
                        committedText.append(text.current());
                        text.next();
                    }
                    String chineseInput = committedText.toString();
                    keyBoardCallBack.onChineseCharInput(chineseInput);
                }
            }

            @Override
            public void caretPositionChanged(InputMethodEvent event) {

            }
        });
    }


    @Override
    protected void paintComponent(Graphics g) {
        Graphics2D g2 = (Graphics2D) g;
        if (image != null) {
            double aspectRatio = 1.0 * image.getWidth() / image.getHeight();
            int imgSizeWidth = (int) Math.min(getWidth(), aspectRatio * getHeight());
            int imgSizeHeight = (int) (imgSizeWidth / aspectRatio);
            int startX = (int) (0.5 * (getWidth() - imgSizeWidth));
            int startY = (int) (0.5 * (getHeight() - imgSizeHeight));
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            g2.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
            g2.drawImage(image, startX, startY, imgSizeWidth, imgSizeHeight, null);

            if (!rectangles.isEmpty()) {
                for (Rectangle rectangle : rectangles) {
                    double scaleWidthRatio = 1.0 * imgSizeWidth / image.getWidth();
                    double scaleHeightRatio = 1.0 * imgSizeHeight / image.getHeight();
                    BasicStroke stroke = new BasicStroke(3.0f);
                    g2.setStroke(stroke);
                    g2.setColor(Color.RED);
                    scaleRectangle = new Rectangle((int) (rectangle.x * scaleWidthRatio * 1f) + startX,
                            (int) (rectangle.y * scaleHeightRatio * 1f) + startY,
                            (int) (rectangle.getWidth() * scaleWidthRatio * 1f),
                            (int) (rectangle.getHeight() * scaleHeightRatio * 1f));
                    g2.drawRoundRect(scaleRectangle.x, scaleRectangle.y, scaleRectangle.width, scaleRectangle.height, 5, 5);
                }
            }
        }
        if (StringUtils.isNotEmpty(tipMessage)) {
            FontMetrics metrics = g.getFontMetrics();
            int stringWidth = metrics.stringWidth(tipMessage);
            int height = metrics.getHeight();
            int x = (getWidth() - stringWidth) / 4;
            int y = (getHeight() - height) / 2 + metrics.getAscent();

            g.setFont(new Font(null, Font.PLAIN, 20));
            g.setColor(Color.BLACK);
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            g2.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
            g2.drawString(tipMessage, x, y);
        }
    }
}
