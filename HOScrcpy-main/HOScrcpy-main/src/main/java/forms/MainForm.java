package forms;

import com.google.gson.GsonBuilder;
import com.huawei.hosscrcpy.api.HosRemoteConfig;
import com.huawei.hosscrcpy.api.HosRemoteDevice;
import com.huawei.hosscrcpy.api.ScreenCapCallback;
import org.apache.commons.lang3.StringUtils;
import org.bytedeco.ffmpeg.avcodec.AVCodec;
import org.bytedeco.ffmpeg.avcodec.AVCodecContext;
import org.bytedeco.ffmpeg.avcodec.AVCodecParserContext;
import org.bytedeco.ffmpeg.avcodec.AVPacket;
import org.bytedeco.ffmpeg.avutil.AVFrame;
import org.bytedeco.ffmpeg.swscale.SwsContext;
import org.bytedeco.javacpp.*;
import utils.*;
import utils.callbacks.ActualTimeControlCallBack;
import utils.callbacks.DumpLayoutCallBack;
import utils.callbacks.KeyBoardCallBack;
import utils.callbacks.MouseWheelCallBack;
import utils.entity.AutoDiscardQueue;
import utils.entity.Device;
import utils.entity.JsonStructure;
import utils.swing.MultiFunctionLabel;

import javax.imageio.ImageIO;
import javax.swing.*;
import javax.swing.tree.DefaultMutableTreeNode;
import javax.swing.tree.DefaultTreeModel;
import javax.swing.tree.TreePath;
import java.awt.*;
import java.awt.datatransfer.Clipboard;
import java.awt.datatransfer.DataFlavor;
import java.awt.datatransfer.Transferable;
import java.awt.dnd.DnDConstants;
import java.awt.dnd.DropTarget;
import java.awt.dnd.DropTargetAdapter;
import java.awt.dnd.DropTargetDropEvent;
import java.awt.event.*;
import java.awt.image.BufferedImage;
import java.awt.image.DataBufferByte;
import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.bytedeco.ffmpeg.global.avcodec.*;
import static org.bytedeco.ffmpeg.global.avutil.*;
import static org.bytedeco.ffmpeg.global.swscale.*;

public class MainForm extends JFrame {
    private static final String TAG = "MainForm";
    private static final int RIGHT_BAR_SIZE = 500;
    private MultiFunctionLabel multiFunctionLabel;
    private static final ProcessExecutor PROCESS_EXECUTOR = new ProcessExecutor();
    private static final LinkedHashMap<String, String> FIX_ATTRIBUTE_MAP = new LinkedHashMap<>(); // 存放固定展示属性的map
    private DefaultMutableTreeNode structureTreeRoot;
    private AutoDiscardQueue<BufferedImage> imageQueue = new AutoDiscardQueue<>(2);
    private boolean isFirstTimeEnterScreenCapture = true; // 是否第一次进入投屏模式,若是则将当前窗口大小进行自适应
    private final List<DefaultMutableTreeNode> treeSearchResult = new ArrayList<>(); // 存放搜索树符合条件的结果列表
    private int currentSelectedTreeSearchIndex = 0; // 当前选中的搜索树索引
    private String lastTreeSearchConent = null;
    private AVCodecContext codecCtx = null;
    private AVFrame frame;
    private AVFrame frameRGB;
    private AVCodecParserContext codecParserContext;
    private static SwsContext swsContext;
    private AVPacket packet = null;
    private BufferedImage img;
    private boolean hadSetSwsContext = false;
    private boolean hadBuffer = false;
    private volatile boolean hadScreenSizeChange = false; // 检测当前屏幕分辨率是否变化
    private final HashMap<String, BufferedImage> imgMap = new HashMap<>();
    private String layoutJson = null;
    private Point lastPressPoint = null; // 鼠标在屏幕上的最后一次点击位置
    private boolean isFirstTimeShowMouseTip = true; // 判断是否是第一次展示鼠标事件提示
    private boolean canUseCompleteMouse = false; // 判断当前设备能否使用完整鼠标事件
    private boolean injectMouseEvent = false;

    private HosRemoteDevice hosRemoteDevice = null;
    private JPanel contentPanel;
    private JComboBox<Device> cmbSn;
    private JButton btnEnterScreenCapture;
    private JButton btnRefreshDevice;
    private JButton btnPower;
    private JButton btnVolumeDown;
    private JButton btnVolumeUp;
    private JButton btnBack;
    private JPanel controlPanel;
    private JToggleButton btnSeeWidget;
    private JPanel rightBarPanel;
    private JTree structureTree;
    private JTextField txtTreeSearch;
    private JButton btnExpandAll;
    private JCheckBox cmbFuzzyMatch;
    private JButton btnPrevious;
    private JButton btnNext;
    private JLabel lblCount;
    private JScrollPane widgetContentScrollPanel;
    private JPanel attributePanel;
    private JButton btnRefreshLayout;
    private JSplitPane splitPanel;
    private JSplitPane layoutSplitPanel;
    private JMenuBar menuBar;
    private JPanel layoutToolBar;
    private JToggleButton btnMouseEvent;
    private JButton btnReboot;
    private JLabel lblTip;
    private final JMenu menu = new JMenu("菜单");
    private JMenuItem menuItemSetting = new JMenuItem("设置");
    private JMenuItem menuItemRemoteIpManager = new JMenuItem("管理远程IP");
    private JMenuItem menuItemInputLayout = new JMenuItem("导入Layout");
    private JMenuItem menuItemExportLayout = new JMenuItem("导出Layout");
    private final ExecutorService inputTextThreadPool = Executors.newFixedThreadPool(10);


    static {
        FIX_ATTRIBUTE_MAP.put("xpath", "控件路径: ");
        FIX_ATTRIBUTE_MAP.put("text", "text: ");
        FIX_ATTRIBUTE_MAP.put("key", "key: ");
        FIX_ATTRIBUTE_MAP.put("type", "type: ");
        FIX_ATTRIBUTE_MAP.put("position", "点击位置: ");
        FIX_ATTRIBUTE_MAP.put("range", "控件范围: ");
        FIX_ATTRIBUTE_MAP.put("centerPosition", "控件中心位置: ");
        FIX_ATTRIBUTE_MAP.put("relativePath", "相对位置: ");
        FIX_ATTRIBUTE_MAP.put("refRange", "点击相对位置: ");

    }

    public MainForm() {
        add(contentPanel);
        setTitle("HOScrcpy");
        initH265Decoder();
        addDragFileListener();
        initButtons();
        lblTip.setVisible(false);
        multiFunctionLabel.setTipMessage(MultiFunctionLabel.DEFAULT_TIP_MESSAGE);
        controlPanel.setVisible(false);
        rightBarPanel.setVisible(false);
        btnRefreshLayout.setEnabled(false);
        widgetContentScrollPanel.getVerticalScrollBar().setUnitIncrement(30);
        multiFunctionLabel.setActualTimeControlCallBack(actualTimeControlCallBack);
        multiFunctionLabel.setDumpLayoutCallBack(dumpLayoutCallBack);
        multiFunctionLabel.setKeyBoardCallBack(keyBoardCallBack);
        structureTree.addMouseListener(structureTreeMouseListener);
        btnRefreshDevice.addActionListener(btnRefreshDeviceListener);
        btnEnterScreenCapture.addActionListener(btnScreenCaptureListener);
        btnSeeWidget.addActionListener(btnSeeWidgetListener);
        btnRefreshLayout.addActionListener(btnRefreshLayoutListener);
        btnExpandAll.addActionListener(btnExpandAllListener);
        btnMouseEvent.addActionListener(btnMouseEventListener);
        btnReboot.addActionListener(btnRebootListener);
        btnNext.addActionListener(btnNextListener);
        btnPrevious.addActionListener(btnPreviousListener);
        menuItemInputLayout.addActionListener(menuItemInputLayoutListener);
        menuItemExportLayout.addActionListener(menuItemExportLayoutListener);
        menuItemSetting.addActionListener(menuItemSettingListener);
        menuItemRemoteIpManager.addActionListener(btnRemoteIpManagerListener);
        menu.add(menuItemSetting);
        menu.add(menuItemRemoteIpManager);
        menu.add(menuItemInputLayout);
        menu.add(menuItemExportLayout);
        menuBar.add(menu);
        txtTreeSearch.addKeyListener(new KeyAdapter() {
            @Override
            public void keyPressed(KeyEvent e) {
                if (e.getKeyChar() == KeyEvent.VK_ENTER) {
                    treeSearchAction();
                }
            }
        });

        btnPower.addActionListener(e -> {
            if (hosRemoteDevice != null) {
                hosRemoteDevice.executeShellCommand("uinput -K -d 18 -u 18", 3);
            }
        });
        btnBack.addActionListener(e -> {
            if (hosRemoteDevice != null) {
                hosRemoteDevice.executeShellCommand("uinput -K -d 2 -u 2", 3);
            }
        });
        btnVolumeDown.addActionListener(e -> {
            if (hosRemoteDevice != null) {
                hosRemoteDevice.executeShellCommand("uinput -K -d 17 -u 17", 3);
            }
        });
        btnVolumeUp.addActionListener(e -> {
            if (hosRemoteDevice != null) {
                hosRemoteDevice.executeShellCommand("uinput -K -d 16 -u 16", 3);
            }
        });
        // 进入后就自动刷新一次设备
        btnRefreshDevice.doClick();
    }

    private void startScreenCapture(Device device) {
        isFirstTimeShowMouseTip = true;
        canUseCompleteMouse = false;
        btnMouseEvent.setSelected(false);
        HosRemoteConfig config = new HosRemoteConfig(device.getSn());
        config.setIp(device.getIp());
        hosRemoteDevice = new HosRemoteDevice(config);
        hosRemoteDevice.stopCaptureScreen();
        isFirstTimeEnterScreenCapture = true;
        multiFunctionLabel.setMouseWheelCallBack(mouseWheelCallBack);
        multiFunctionLabel.setRectangles(Collections.emptyList());
        multiFunctionLabel.setScreenCapturingMode(true);
        multiFunctionLabel.setTipMessage(MultiFunctionLabel.STREAM_INIT_TIP_MESSAGE);
        Executors.newSingleThreadExecutor().submit(() -> {
            if (SettingUtil.useVideoStream()) {
                lblTip.setVisible(false);
                hosRemoteDevice.startCaptureScreen(newSoScreenCallBack);
            } else {
                startScreenCaptureByImageMode();
            }
        });
    }


    private void initH265Decoder() {
        Log.info(TAG, "start init decoder");
        int codec_id = AV_CODEC_ID_H264;
        AVCodec codec = avcodec_find_decoder(codec_id);
        if (codec == null) {
            Log.info(TAG, "codec not found");
        }
        codecCtx = avcodec_alloc_context3(codec);
        if (codecCtx == null) {
            Log.info(TAG, "could not allow codec context");
        }
        codecParserContext = av_parser_init(codec_id);
        avcodec_open2(codecCtx, codec, (PointerPointer<Pointer>) null);
        frame = av_frame_alloc();
        frameRGB = av_frame_alloc();
        packet = av_packet_alloc();
        av_new_packet(packet, 3000);
        Log.info(TAG, "finish init decoder");
    }


    private void decodeH264(byte[] h264) {
        ByteBuffer data = ByteBuffer.allocate(h264.length);
        data.put(h264);
        int curSize = h264.length;
        IntPointer pktSize = new IntPointer(packet.size());
        BytePointer tempBp = new BytePointer();
        while (curSize > 0) {
            data.flip();
            BytePointer dataPointer = new BytePointer(data);
            int len = av_parser_parse2(codecParserContext, codecCtx, tempBp, pktSize, dataPointer, curSize, AV_NOPTS_VALUE, AV_NOPTS_VALUE, AV_NOPTS_VALUE);
            packet = packet.size(pktSize.get());
            data.position(len);
            data = data.compact();
            curSize -= len;
            if (pktSize.get() == 0) {
                continue;
            }
            packet = packet.data(tempBp);
            avcodec_send_packet(codecCtx, packet);
            if (avcodec_receive_frame(codecCtx, frame) == 0) {
                if (!hadBuffer) {
                    frameRGB.format(AV_PIX_FMT_BGR24);
                    frameRGB.width(codecCtx.width());
                    frameRGB.height(codecCtx.height());
                    av_image_alloc(frameRGB.data(), frameRGB.linesize(), frameRGB.width(), frameRGB.height(), frameRGB.format(), 1);
                    hadBuffer = true;
                }
            }

            if (frameRGB.width() != codecCtx.width() || frameRGB.height() != codecCtx.height()) {
                hadScreenSizeChange = true;
            }

            if (hadScreenSizeChange) {
                av_freep(frameRGB.data());
                av_freep(frameRGB.getPointer());
                av_frame_free(frameRGB.data());
                av_frame_free(frameRGB);
                av_free(frameRGB);
                frameRGB = av_frame_alloc();
                frameRGB.format(AV_PIX_FMT_BGR24);
                frameRGB.width(codecCtx.width());
                frameRGB.height(codecCtx.height());
                av_image_alloc(frameRGB.data(), frameRGB.linesize(), frameRGB.width(), frameRGB.height(), frameRGB.format(), 1);
            }
            setSwf();
            sws_scale(swsContext, frame.data(), frame.linesize(), 0, frame.height(), frameRGB.data(), frameRGB.linesize());
            try {
                setImg();
                DataBufferByte buffer = (DataBufferByte) img.getRaster().getDataBuffer();
                frameRGB.data(0).get(buffer.getData());
                imageQueue.offer(img);
                if (hadScreenSizeChange || isFirstTimeEnterScreenCapture) {
                    changeFrameByImgSize(img.getWidth(), img.getHeight());
                    isFirstTimeEnterScreenCapture = false;
                    // 将当前窗口重新居中显示
                    try {
                        Dimension screenSize = Toolkit.getDefaultToolkit().getScreenSize();
                        int x = (screenSize.width - getWidth()) / 2;
                        int y = (screenSize.height - getHeight()) / 2;
                        setLocation(x, y);
                    } catch (Exception ex) {
                        Log.info(TAG, "change location failed: " + ex);
                    }
                }
                if (multiFunctionLabel.isScreenCapturingMode()) {
                    multiFunctionLabel.setImage(img);
                }
            } catch (Exception ex) {
                Log.info(TAG, "change location fail:" + ex);
            }

        }
    }

    private void changeFrameByImgSize(int width, int height) {
        // 默认设置为设备分辨率的三分之一大小
        double aspectRatio = (double) width / height;
        int imgSizeWidth = (int) (width * 0.35);
        int imgSizeHeight = (int) (imgSizeWidth / aspectRatio);
        setSize(imgSizeWidth + controlPanel.getWidth(), imgSizeHeight + layoutToolBar.getHeight());
    }

    private void setSwf() {
        if (hadSetSwsContext && !hadScreenSizeChange) {
            return;
        }
        if (hadScreenSizeChange) {
            sws_freeContext(swsContext);
        }
        swsContext = sws_getCachedContext(null, codecCtx.width(), codecCtx.height(), codecCtx.pix_fmt(), frameRGB.width(), frameRGB.height(), frameRGB.format(), SWS_FAST_BILINEAR, null, null, (DoublePointer) null);
        hadSetSwsContext = true;
    }


    private void setImg() {
        if (img == null || hadScreenSizeChange) {
            String screenSize = String.format("%s;%s", frameRGB.width(), frameRGB.height());
            if (!imgMap.containsKey(screenSize)) {
                imgMap.put(screenSize, new BufferedImage(frameRGB.width(), frameRGB.height(), BufferedImage.TYPE_3BYTE_BGR));
            }
            img = imgMap.get(screenSize);
        }
    }

    private void createUIComponents() {
        menuBar = new JMenuBar();
        multiFunctionLabel = new MultiFunctionLabel();
        structureTreeRoot = new DefaultMutableTreeNode("root");
        structureTree = new JTree(structureTreeRoot);
        structureTree.setRootVisible(false);
    }

    private ActualTimeControlCallBack actualTimeControlCallBack = new ActualTimeControlCallBack() {
        @Override
        public void onMouseMove(MouseEvent mouseEvent, MultiFunctionLabel multiFunctionLabel, boolean isPressing) {
            Point actualClickPoint = getActualClickPoint(mouseEvent.getPoint(), true);
            if (actualClickPoint == null) {
                return;
            }
            if (injectMouseEvent) {
                if (canUseCompleteMouse) {
                    if (isPressing) {
                        if ((mouseEvent.getModifiersEx() & MouseEvent.BUTTON1_DOWN_MASK) != 0) {
                            hosRemoteDevice.onMouseMove(HosRemoteDevice.MOUSE_LEFT, actualClickPoint.x, actualClickPoint.y);
                        } else if ((mouseEvent.getModifiersEx() & MouseEvent.BUTTON2_DOWN_MASK) != 0) {
                            hosRemoteDevice.onMouseMove(HosRemoteDevice.MOUSE_MIDDLE, actualClickPoint.x, actualClickPoint.y);
                        } else if ((mouseEvent.getModifiersEx() & MouseEvent.BUTTON3_DOWN_MASK) != 0) {
                            hosRemoteDevice.onMouseMove(HosRemoteDevice.MOUSE_RIGHT, actualClickPoint.x, actualClickPoint.y);
                        }
                    } else {
                        hosRemoteDevice.onMouseMove(null, actualClickPoint.x, actualClickPoint.y);
                    }
                }
            } else {
                hosRemoteDevice.onTouchMove(actualClickPoint.x, actualClickPoint.y);
            }
        }

        @Override
        public void onMouseUp(MouseEvent mouseEvent, MultiFunctionLabel multiFunctionLabel) {
            Point actualClickPoint = getActualClickPoint(mouseEvent.getPoint(), true);
            if (actualClickPoint == null) {
                return;
            }
            if (injectMouseEvent) {
                String mouseButton = getMouseButton(mouseEvent);
                if (canUseCompleteMouse) {
                    hosRemoteDevice.onMouseUp(mouseButton, actualClickPoint.x, actualClickPoint.y);
                } else if (mouseButton.equals(HosRemoteDevice.MOUSE_LEFT)) {
                    hosRemoteDevice.executeShellCommand(String.format("uinput -M -m %s %s -c 0", actualClickPoint.x, actualClickPoint.y), 5);
                } else if (mouseButton.equals(HosRemoteDevice.MOUSE_RIGHT)) {
                    hosRemoteDevice.executeShellCommand(String.format("uinput -M -m %s %s -c 1", actualClickPoint.x, actualClickPoint.y), 5);
                }
            } else {
                hosRemoteDevice.onTouchUp(actualClickPoint.x, actualClickPoint.y);
            }
        }

        @Override
        public void onMouseDown(MouseEvent mouseEvent, MultiFunctionLabel multiFunctionLabel) {
            Point actualClickPoint = getActualClickPoint(mouseEvent.getPoint(), true);
            if (actualClickPoint == null) {
                return;
            }
            lastPressPoint = actualClickPoint;
            if (injectMouseEvent) {
                String mouseButton = getMouseButton(mouseEvent);
                if (canUseCompleteMouse) {
                    hosRemoteDevice.onMouseDown(mouseButton, actualClickPoint.x, actualClickPoint.y);
                }
            } else {
                hosRemoteDevice.onTouchDown(actualClickPoint.x, actualClickPoint.y);
            }
        }
    };

    private Point getActualClickPoint(Point point, boolean allowOverStep) {
        if (multiFunctionLabel.getImage() == null) {
            return null;
        }
        int iconWidth = multiFunctionLabel.getCurrentSize().width;
        int iconHeight = multiFunctionLabel.getCurrentSize().height;
        int offsetX = (multiFunctionLabel.getWidth() - iconWidth) / 2;
        int offsetY = (multiFunctionLabel.getHeight() - iconHeight) / 2;
        if (point.x < offsetX || point.x > offsetX + iconWidth || point.y < offsetY || point.y > offsetY + iconHeight) {
            if (!allowOverStep) {
                return null;
            }
            if (point.x < offsetX) {
                point.x = offsetX + 2;
                point.y = offsetY + iconHeight / 2;
            } else if (point.x > offsetX + iconWidth) {
                point.x = offsetX + iconWidth / 2;
                point.y = offsetY + iconHeight / 2;
            } else if (point.y < offsetY) {
                point.x = offsetX + iconWidth / 2;
                point.y = offsetY + 2;
            } else {
                point.x = offsetX + iconWidth / 2;
                point.y = offsetY + iconHeight - 2;
            }
        }
        double widthScaleRate = 1.0 * iconWidth / multiFunctionLabel.getImage().getWidth();
        double heightScaleRate = 1.0 * iconHeight / multiFunctionLabel.getImage().getHeight();
        int actualClickX = (int) ((point.x - offsetX) / widthScaleRate / 1f);
        int actualClickY = (int) ((point.y - offsetY) / heightScaleRate / 1f);
        return new Point(actualClickX, actualClickY);
    }

    private final ActionListener btnScreenCaptureListener = e -> {
        if (btnEnterScreenCapture.getText().equals("停止投屏")) {
            if (hosRemoteDevice != null) {
                lblTip.setVisible(false);
                hosRemoteDevice.stopCaptureScreen();
            }
            multiFunctionLabel.setScreenCapturingMode(false);
            multiFunctionLabel.setImage(null);
            multiFunctionLabel.setTipMessage(MultiFunctionLabel.DEFAULT_TIP_MESSAGE);
            multiFunctionLabel.setRectangles(Collections.emptyList());
            btnEnterScreenCapture.setText("进入投屏");
            rightBarPanel.setVisible(false);
            controlPanel.setVisible(false);
            hosRemoteDevice = null;
            return;
        }
        Device device = (Device) cmbSn.getSelectedItem();
        if (device == null || !device.isOnline()) {
            MessageUtil.showInfoMessage(MainForm.this, "设备不存在");
            return;
        }
        setTitle("HOScrcpy-" + device);
        btnEnterScreenCapture.setText("停止投屏");
        // 如果之前已经投屏过,则进行恢复
        if (hosRemoteDevice != null && hosRemoteDevice.getSn().equals(device.getSn())) {
            multiFunctionLabel.setScreenCapturingMode(true);
            multiFunctionLabel.setRectangles(Collections.emptyList());
            if (img != null) {
                changeFrameByImgSize(img.getWidth(), img.getHeight());
            }
        } else {
            if (hosRemoteDevice != null) {
                hosRemoteDevice.stopCaptureScreen();
            }
            startScreenCapture(device);
        }
        rightBarPanel.setVisible(false);
        controlPanel.setVisible(true);
        btnSeeWidget.setSelected(false);
    };

    private final ActionListener btnRefreshDeviceListener = e -> {
        btnRefreshDevice.setEnabled(false);
        cmbSn.removeAllItems();
        CompletableFuture.runAsync(() -> {
            try {
                List<Device> devices = HdcUtil.getLocalDevices();
                devices.addAll(HdcUtil.getRemoteDevice());
                SwingUtilities.invokeLater(() -> {
                    for (Device device : devices) {
                        cmbSn.addItem(device);
                    }
                    if (!devices.isEmpty()) {
                        cmbSn.setSelectedItem(devices.get(0));
                    }
                });
            } finally {
                SwingUtilities.invokeLater(() -> {
                    btnRefreshDevice.setEnabled(true);
                });
            }
        });
    };

    private final ActionListener btnSeeWidgetListener = e -> {
        if (btnSeeWidget.isSelected()) {
            Device device = (Device) cmbSn.getSelectedItem();
            if (device == null || !device.isOnline()) {
                btnSeeWidget.setSelected(false);
                MessageUtil.showInfoMessage(MainForm.this, "设备不存在");
                return;
            }
            if (!device.isOnline()) {
                MessageUtil.showInfoMessage(MainForm.this, String.format("%s设备连接已断开", device.toString()));
                return;
            }
            btnEnterScreenCapture.setText("进入投屏");
            btnSeeWidget.setEnabled(false);
            btnRefreshLayout.setEnabled(false);
            btnEnterScreenCapture.setEnabled(false);

            if (!hadInitScreenCapture()) {
                try {
                    CompletableFuture<Void> future = CompletableFuture.runAsync(() -> {
                        dumpLayoutByCmd(device);
                    });
                    future.get(8, TimeUnit.SECONDS);
                } catch (Exception ex) {
                    MessageUtil.showInfoMessage(MainForm.this, "结构树获取失败");
                    return;
                } finally {
                    btnSeeWidget.setEnabled(true);
                    btnEnterScreenCapture.setEnabled(true);
                    btnRefreshLayout.setEnabled(true);
                }

            } else if (!dumpLayoutByStream()) {
                btnEnterScreenCapture.setEnabled(true);
                btnRefreshLayout.setEnabled(false);
                btnSeeWidget.setEnabled(true);
                btnSeeWidget.setSelected(false);
                MessageUtil.showInfoMessage(MainForm.this, "结构树获取失败,请重试");
                return;
            }
            // 切换面板
            CardLayout layout = (CardLayout) rightBarPanel.getLayout();
            layout.show(rightBarPanel, "Card1");
            controlPanel.setVisible(false);
            btnRefreshLayout.setEnabled(true);
            btnEnterScreenCapture.setEnabled(true);
            multiFunctionLabel.setScreenCapturingMode(false);
            btnSeeWidget.setEnabled(true);
            showRightBarPanel();
        } else {
            // 如果没开启过投屏就不显示
            if (!hadInitScreenCapture()) {
                multiFunctionLabel.setScreenCapturingMode(false);
                multiFunctionLabel.setImage(null);
                controlPanel.setVisible(false);
                rightBarPanel.setVisible(false);
                // 将当前宽度减小一半
                setSize(getWidth() / 2, getHeight());
                return;
            }
            controlPanel.setVisible(true);
            btnRefreshLayout.setEnabled(false);
            btnSeeWidget.setEnabled(true);
            multiFunctionLabel.setScreenCapturingMode(true);
            multiFunctionLabel.setRectangles(Collections.emptyList());
            isFirstTimeEnterScreenCapture = true;
            rightBarPanel.setVisible(false);
            btnEnterScreenCapture.setText("停止投屏");
            // 将左半边进行收窄贴边
            if (multiFunctionLabel.getImage() != null) {
                int height = multiFunctionLabel.getImage().getHeight();
                int width = multiFunctionLabel.getImage().getWidth();
                double aspectRatio = (double) width / height;
                double resultWidth = multiFunctionLabel.getHeight() * aspectRatio;
                setSize((int) resultWidth + 20, getSize().height);
            }
            if (!hosRemoteDevice.isOnline()) {
                MessageUtil.showInfoMessage(MainForm.this, String.format("%s设备连接已断开", hosRemoteDevice.getSn()));
            }
        }
    };


    private final ActionListener btnRefreshLayoutListener = e -> {
        Device device = (Device) cmbSn.getSelectedItem();
        if (device == null || !device.isOnline()) {
            btnSeeWidget.setSelected(false);
            MessageUtil.showInfoMessage(MainForm.this, "设备不存在");
            return;
        }
        if (!device.isOnline()) {
            MessageUtil.showInfoMessage(MainForm.this, String.format("%s设备连接已断开", device.toString()));
            return;
        }
        btnEnterScreenCapture.setText("进入投屏");
        btnSeeWidget.setSelected(true);
        // 如果之前没有进行过初始化
        if (!hadInitScreenCapture()) {
            try {
                CompletableFuture<Void> future = CompletableFuture.runAsync(() -> {
                    dumpLayoutByCmd(device);
                });
                future.get(8, TimeUnit.SECONDS);
            } catch (Exception ex) {
                MessageUtil.showInfoMessage(MainForm.this, "结构树获取失败");
                return;
            } finally {
                btnSeeWidget.setEnabled(true);
                btnEnterScreenCapture.setEnabled(true);
                btnRefreshLayout.setEnabled(true);
            }

        } else if (!dumpLayoutByStream()) {
            btnEnterScreenCapture.setEnabled(true);
            btnRefreshLayout.setEnabled(false);
            btnSeeWidget.setEnabled(true);
            btnSeeWidget.setSelected(false);
            MessageUtil.showInfoMessage(MainForm.this, "结构树获取失败,请重试");
            return;
        }


        // 切换面板
        CardLayout layout = (CardLayout) rightBarPanel.getLayout();
        layout.show(rightBarPanel, "Card1");
        controlPanel.setVisible(false);
        btnRefreshLayout.setEnabled(true);
        btnEnterScreenCapture.setEnabled(true);
        multiFunctionLabel.setScreenCapturingMode(false);
        btnSeeWidget.setEnabled(true);
        showRightBarPanel();

    };


    private ActionListener btnExpandAllListener = new ActionListener() {
        @Override
        public void actionPerformed(ActionEvent e) {
            if (btnExpandAll.getText().equals("展开全部")) {
                btnExpandAll.setText("收起所有");
                TreeUtil.expandTree(structureTree, new TreePath(structureTreeRoot));
            } else {
                btnExpandAll.setText("展开全部");
                TreeUtil.collapseTree(structureTree);
            }
            structureTree.updateUI();
        }
    };

    /**
     * 展示右侧面板
     */
    private void showRightBarPanel() {
        if (rightBarPanel.isVisible()) {
            return;
        }
        rightBarPanel.setVisible(true);
        if (isFrameMaximized()) {
            splitPanel.setDividerLocation(0.7);
        } else {
            Dimension frameSize = getSize();
            setSize(frameSize.width + RIGHT_BAR_SIZE, frameSize.height);
            repaint();
            revalidate();
            splitPanel.setEnabled(false);
            splitPanel.setDividerLocation(splitPanel.getWidth() - RIGHT_BAR_SIZE);
            splitPanel.setEnabled(true);
            layoutSplitPanel.setDividerLocation((int) (frameSize.getHeight() / 2));
        }

    }

    /**
     * 判断当前窗口是否已经处于最大化状态
     *
     * @return 是否已经处于最大化状态
     */
    private boolean isFrameMaximized() {
        int state = getExtendedState();
        return (state & Frame.MAXIMIZED_BOTH) == Frame.MAXIMIZED_BOTH;
    }

    private boolean hadInitScreenCapture() {
        Device device = (Device) cmbSn.getSelectedItem();
        return hosRemoteDevice != null && device != null && hosRemoteDevice.getSn().equals(device.getSn());
    }


    private void setAttributeContent(Object data) {
        JsonStructure jsonStructure = data == null ? null : (JsonStructure) data;
        Point position = null;
        if (jsonStructure != null && jsonStructure.getPosition() == null) {
            String bounds = jsonStructure.getBounds();
            if (StringUtils.isNotBlank(bounds)) {
                Rectangle rectangle = TreeUtil.convertBoundsToRectangle(bounds);
                int avgX = rectangle.x + (rectangle.width / 2);
                int avgY = rectangle.y + (rectangle.height / 2);
                position = new Point(avgX, avgY);
            }
        } else if (jsonStructure != null && jsonStructure.getPosition() != null) {
            position = jsonStructure.getPosition();
        }

        if (jsonStructure != null) {
            jsonStructure.getAttributes().put("centerPosition", jsonStructure.getCenterPosition());
            jsonStructure.getAttributes().put("xpath", jsonStructure.getTreeNodePath());
            jsonStructure.getAttributes().put("range", jsonStructure.getBounds());
            jsonStructure.getAttributes().put("refRange", jsonStructure.getScale());
            jsonStructure.getAttributes().put("position", String.format("[%s,%s]", position == null ? "" : position.x, position == null ? "" : position.y));
        }
        int i = 0;
        attributePanel.removeAll();
        for (Map.Entry<String, String> entry : FIX_ATTRIBUTE_MAP.entrySet()) {
            addChildrenWidgetPanel(entry.getValue(), jsonStructure == null ? "" : (String) jsonStructure.getAttributes().get(entry.getKey()), i);
            i += 2;
        }

        if (jsonStructure != null) {
            for (Map.Entry<String, Object> entry : jsonStructure.getAttributes().entrySet()) {
                if (FIX_ATTRIBUTE_MAP.containsKey(entry.getKey())) {
                    continue;
                }
                if (entry.getValue() instanceof String) {
                    addChildrenWidgetPanel(entry.getKey(), (String) entry.getValue(), i);
                } else {
                    addChildrenWidgetPanel(entry.getKey(), "", i);
                }
                i += 2;
            }
        }
        attributePanel.updateUI();
    }


    private void dumpLayoutByCmd(Device device) {
        String layout = device.getLayout(null);
        if (layout == null) {
            throw new RuntimeException("get layout failed");
        }
        BufferedImage screenshot = device.getScreenshot(null);
        if (screenshot == null) {
            throw new RuntimeException("get screenshout failed");
        }
        layoutJson = layout;
        JsonStructure jsonStructure = new GsonBuilder().excludeFieldsWithoutExposeAnnotation().create().fromJson(layout, JsonStructure.class);
        multiFunctionLabel.setImage(screenshot);
        multiFunctionLabel.setTipMessage("");
        multiFunctionLabel.setRectangles(Collections.emptyList());
        if (StringUtils.isBlank((String) jsonStructure.getAttributes().getOrDefault("type", ""))) {
            jsonStructure.getAttributes().put("type", "Root");
        }
        structureTreeRoot.setUserObject(jsonStructure);
        structureTreeRoot.add(TreeUtil.convertJsonStructureToJTreeNode(jsonStructure));
        DefaultTreeModel mode = (DefaultTreeModel) structureTree.getModel();
        mode.nodeChanged(structureTreeRoot);
        structureTree.setRootVisible(true);
        structureTree.expandRow(0);
        structureTree.setRootVisible(false);
        structureTree.updateUI();
    }


    MouseAdapter structureTreeMouseListener = new MouseAdapter() {
        @Override
        public void mouseClicked(MouseEvent e) {
            DefaultMutableTreeNode treeNode = (DefaultMutableTreeNode) structureTree.getLastSelectedPathComponent();
            if (treeNode == null) {
                setAttributeContent(null);
                return;
            }
            Object object = treeNode.getUserObject();
            if (object instanceof JsonStructure) {
                JsonStructure jsonStructure = (JsonStructure) treeNode.getUserObject();
                jsonStructure.setTreeNodePath(TreeUtil.getTreeNodePath(treeNode));
                setAttributeContent(jsonStructure);
                multiFunctionLabel.setRectangles(Collections.singletonList(jsonStructure.getRectangle()));
            } else {
                setAttributeContent(null);
            }
        }
    };


    private void addChildrenWidgetPanel(String name, String value, int index) {
        GridBagConstraints gridBagConstraints = new GridBagConstraints();
        GridBagConstraints innerGridBagConstraints = new GridBagConstraints();
        innerGridBagConstraints.anchor = GridBagConstraints.WEST;
        innerGridBagConstraints.fill = GridBagConstraints.BOTH;
        gridBagConstraints.gridx = 0;
        gridBagConstraints.gridy = (index);
        gridBagConstraints.weightx = 0.2;
        gridBagConstraints.weighty = 1;
        gridBagConstraints.fill = GridBagConstraints.BOTH;
        GridBagLayout layout = new GridBagLayout();
        JPanel jPanel = new JPanel(layout);
        JLabel attributeName = new JLabel(name);
        attributeName.setPreferredSize(new Dimension(105, 17));
        JTextField attributeValue = new JTextField();
        attributeValue.setEditable(false);
        attributeValue.setText(value);
        attributeValue.setHorizontalAlignment(JTextField.LEFT);
        attributeValue.setPreferredSize(new Dimension(49, 28));
        innerGridBagConstraints.weightx = 0.2;
        innerGridBagConstraints.weighty = 1;
        innerGridBagConstraints.gridx = 0;
        innerGridBagConstraints.gridy = 0;
        jPanel.add(attributeName, innerGridBagConstraints);
        innerGridBagConstraints.weightx = 0.8;
        innerGridBagConstraints.weighty = 1;
        innerGridBagConstraints.gridx = 1;
        innerGridBagConstraints.gridy = 0;
        jPanel.add(attributeValue, innerGridBagConstraints);
        jPanel.setBorder(BorderFactory.createEtchedBorder());
        jPanel.setPreferredSize(new Dimension(144, 40));
        gridBagConstraints.weightx = 1;
        jPanel.setBorder(BorderFactory.createEmptyBorder());
        attributePanel.add(jPanel, gridBagConstraints);
        gridBagConstraints.gridy = (index + 1);
        attributePanel.add(new JSeparator(), gridBagConstraints);
    }


    private void updateWidgetInfoByClickPoint(Point point) {
        Point actualClickPoint = getActualClickPoint(point, false);
        if (actualClickPoint == null) {
            return;
        }
        if (multiFunctionLabel.getImage() == null || structureTreeRoot == null) {
            return;
        }
        DefaultMutableTreeNode treeNode = TreeUtil.findMinRangeTreeNode(structureTreeRoot, actualClickPoint);
        if (treeNode == null || treeNode.getUserObject() == null) {
            return;
        }
        int imageWidth = multiFunctionLabel.getImage().getWidth();
        int imageHeight = multiFunctionLabel.getImage().getHeight();
        JsonStructure jsonStructure = (JsonStructure) treeNode.getUserObject();
        jsonStructure.setPosition(new Point(actualClickPoint.x, actualClickPoint.y));
        jsonStructure.setScale(String.format("%.2f, %.2f", 1.0f * actualClickPoint.x / imageWidth, 1.0f * actualClickPoint.y / imageHeight));
        jsonStructure.setTreeNodePath(TreeUtil.getTreeNodePath(treeNode));
        setAttributeContent(jsonStructure);
        multiFunctionLabel.setRectangles(Collections.singletonList(jsonStructure.getRectangle()));
        structureTree.setSelectionPath(new TreePath(treeNode.getPath()));
        structureTree.expandPath(new TreePath(treeNode.getPath()));
        structureTree.scrollPathToVisible(new TreePath(treeNode.getPath()));
    }

    private boolean dumpLayoutByStream() {
        if (!hosRemoteDevice.isOnline()) {
            MessageUtil.showInfoMessage(MainForm.this, String.format("%s设备连接已断开", hosRemoteDevice.getSn()));
            return false;
        }
        try {
            structureTreeRoot.removeAllChildren();
            structureTreeRoot.setUserObject(null);
            structureTree.updateUI();
            setAttributeContent(null);
            contentPanel.setCursor(Cursor.getPredefinedCursor(Cursor.WAIT_CURSOR));
            SwingWorker<JsonStructure, Void> swingWorker = new SwingWorker<JsonStructure, Void>() {
                @Override
                protected JsonStructure doInBackground() throws Exception {
                    if (imageQueue.isEmpty()) {
                        Device device = (Device) cmbSn.getSelectedItem();
                        BufferedImage screenshot = device.getScreenshot(null);
                        if (screenshot == null) {
                            throw new IOException("could not get screenshot");
                        }
                        multiFunctionLabel.setImage(screenshot);
                    } else {
                        int type = imageQueue.getLast().getType();
                        BufferedImage origImage = imageQueue.getLast();
                        BufferedImage newImage = new BufferedImage(origImage.getWidth(), origImage.getHeight(), type);
                        Graphics2D graphics = newImage.createGraphics();
                        graphics.drawImage(origImage, 0, 0, null);
                        graphics.dispose();
                        multiFunctionLabel.setImage(newImage);
                    }
                    String layout = hosRemoteDevice.getLayout();
                    layoutJson = layout;
                    return new GsonBuilder().excludeFieldsWithoutExposeAnnotation().create().fromJson(layout, JsonStructure.class);
                }

                @Override
                protected void done() {
                    try {
                        JsonStructure jsonStructure = get();
                        if (jsonStructure == null) {
                            MessageUtil.showInfoMessage(MainForm.this, "页面结构文件获取失败");
                            return;
                        }
                        multiFunctionLabel.setRectangles(Collections.emptyList());
                        if (StringUtils.isBlank((String) jsonStructure.getAttributes().getOrDefault("type", ""))) {
                            jsonStructure.getAttributes().put("type", "Root");
                        }
                        structureTreeRoot.setUserObject(jsonStructure);
                        structureTreeRoot.add(TreeUtil.convertJsonStructureToJTreeNode(jsonStructure));
                        DefaultTreeModel mode = (DefaultTreeModel) structureTree.getModel();
                        mode.nodeChanged(structureTreeRoot);
                        structureTree.setRootVisible(true);
                        structureTree.expandRow(0);
                        structureTree.setRootVisible(false);
                        structureTree.updateUI();

                    } catch (Exception ex) {
                        Log.error(TAG, "can not dump layout", ex);
                        MessageUtil.showInfoMessage(MainForm.this, "结构文件获取失败,请重试");
                    } finally {
                        contentPanel.setCursor(Cursor.getPredefinedCursor(Cursor.DEFAULT_CURSOR));
                    }
                }
            };
            swingWorker.execute();

            return true;
        } catch (Exception ex) {
            Log.error(TAG, "can not dump layout2", ex);
            return false;
        }
    }

    private void treeSearchAction() {
        lastTreeSearchConent = txtTreeSearch.getText().trim();
        treeSearchResult.clear();
        if (StringUtils.isBlank(lastTreeSearchConent)) {
            return;
        }
        TreeUtil.findTreeNodeByCondition(treeSearchResult, structureTreeRoot, lastTreeSearchConent, cmbFuzzyMatch.isSelected());
        if (treeSearchResult.isEmpty()) {
            lblCount.setText("0/0");
            MessageUtil.showInfoMessage(MainForm.this, "没有此节点信息!");
            return;
        }
        Object userObject = treeSearchResult.get(0).getUserObject();
        // 同步控件详情显示
        setAttributeContent(userObject);
        JsonStructure jsonStructure = (JsonStructure) userObject;
        multiFunctionLabel.setRectangles(Collections.singletonList(TreeUtil.convertBoundsToRectangle(jsonStructure.getBounds())));
        lblCount.setText(String.format("1/%s", treeSearchResult.size()));
        structureTree.setSelectionPath(new TreePath(treeSearchResult.get(0)));
        structureTree.expandPath(new TreePath(treeSearchResult.get(0).getPath()));
        structureTree.scrollPathToVisible(new TreePath(treeSearchResult.get(0).getPath()));
    }


    private final ActionListener btnPreviousListener = e -> {
        treeSearchAction();
        if (treeSearchResult.isEmpty()) {
            return;
        }
        currentSelectedTreeSearchIndex = currentSelectedTreeSearchIndex - 1 < 0 ? treeSearchResult.size() - 1 : currentSelectedTreeSearchIndex - 1;
        Object userObject = treeSearchResult.get(currentSelectedTreeSearchIndex).getUserObject();
        setAttributeContent(userObject);
        JsonStructure jsonStructure = (JsonStructure) userObject;
        multiFunctionLabel.setRectangles(Collections.singletonList(TreeUtil.convertBoundsToRectangle(jsonStructure.getBounds())));
        lblCount.setText(String.format("%s/%s", currentSelectedTreeSearchIndex + 1, treeSearchResult.size()));
        structureTree.setSelectionPath(new TreePath(treeSearchResult.get(currentSelectedTreeSearchIndex)));
        structureTree.expandPath(new TreePath(treeSearchResult.get(currentSelectedTreeSearchIndex).getPath()));
        structureTree.scrollPathToVisible(new TreePath(treeSearchResult.get(currentSelectedTreeSearchIndex).getPath()));
    };

    private final ActionListener btnNextListener = e -> {
        treeSearchAction();
        if (treeSearchResult.isEmpty()) {
            return;
        }
        currentSelectedTreeSearchIndex = currentSelectedTreeSearchIndex + 1 >= treeSearchResult.size() ? 0 : currentSelectedTreeSearchIndex + 1;
        Object userObject = treeSearchResult.get(currentSelectedTreeSearchIndex).getUserObject();
        setAttributeContent(userObject);
        JsonStructure jsonStructure = (JsonStructure) userObject;
        multiFunctionLabel.setRectangles(Collections.singletonList(TreeUtil.convertBoundsToRectangle(jsonStructure.getBounds())));
        lblCount.setText(String.format("%s/%s", currentSelectedTreeSearchIndex + 1, treeSearchResult.size()));
        structureTree.setSelectionPath(new TreePath(treeSearchResult.get(currentSelectedTreeSearchIndex)));
        structureTree.expandPath(new TreePath(treeSearchResult.get(currentSelectedTreeSearchIndex).getPath()));
        structureTree.scrollPathToVisible(new TreePath(treeSearchResult.get(currentSelectedTreeSearchIndex).getPath()));
    };

    private final ActionListener menuItemSettingListener = e -> {
        SettingDialog settingDialog = new SettingDialog(MainForm.this);
        settingDialog.setSize(new Dimension(400, 200));
        settingDialog.setLocationRelativeTo(MainForm.this);
        settingDialog.setMinimumSize(new Dimension(400, 200));
        settingDialog.setVisible(true);
    };

    private final ActionListener menuItemInputLayoutListener = e -> {
        LayoutInputForm layoutInputForm = new LayoutInputForm();
        Object[] options = {"确定", "取消"};
        int result = JOptionPane.showOptionDialog(MainForm.this, layoutInputForm.getContentPanel(), "选择文件输入", JOptionPane.YES_NO_OPTION, JOptionPane.PLAIN_MESSAGE, null, options, null);
        if (result != JOptionPane.YES_OPTION) {
            return;
        }
        if (!layoutInputForm.checkJsonPath() || !layoutInputForm.checkPicPath()) {
            return;
        }
        File json = layoutInputForm.getJson();
        File pic = layoutInputForm.getPic();
        try {
            JsonStructure jsonStructure;
            try {
                jsonStructure = new GsonBuilder().excludeFieldsWithoutExposeAnnotation().create().fromJson(FileUtil.readFileContent(json), JsonStructure.class);
            } catch (Exception ex) {
                MessageUtil.showInfoMessage(MainForm.this, "json文件结构不符合要求");
                return;
            }
            if (jsonStructure == null) {
                MessageUtil.showInfoMessage(MainForm.this, "json文件解析为空");
                return;
            }
            if (StringUtils.isBlank((String) jsonStructure.getAttributes().getOrDefault("type", ""))) {
                jsonStructure.getAttributes().put("type", "Root");
            }
            layoutJson = FileUtil.readFileContent(json);
            structureTreeRoot.removeAllChildren();
            structureTreeRoot.setUserObject(jsonStructure);
            structureTreeRoot.add(TreeUtil.convertJsonStructureToJTreeNode(jsonStructure));
            DefaultTreeModel model = (DefaultTreeModel) structureTree.getModel();
            model.nodeChanged(structureTreeRoot);
            structureTree.setRootVisible(true);
            structureTree.expandRow(0);

            structureTree.updateUI();

            // 非控件查看模式进入
            if (multiFunctionLabel.isScreenCapturingMode() || !rightBarPanel.isVisible()) {
                controlPanel.setVisible(false);
                multiFunctionLabel.setScreenCapturingMode(false);
                multiFunctionLabel.setImage(ImageIO.read(pic));
                showRightBarPanel();
                btnSeeWidget.setSelected(false);
            }
        } catch (Exception ex) {
            Log.error(TAG, "input custom file failed", ex);
            MessageUtil.showInfoMessage(MainForm.this, "自定义文件输入解析失败");
        }
    };

    private final ActionListener menuItemExportLayoutListener = e -> {
        Device device = (Device) cmbSn.getSelectedItem();
        if (device == null) {
            MessageUtil.showInfoMessage(MainForm.this, "设备不存在");
            return;
        }
        JFileChooser jFileChooser = new JFileChooser();
        jFileChooser.setFileSelectionMode(JFileChooser.FILES_ONLY);
        int result = jFileChooser.showSaveDialog(MainForm.this);
        if (result != JFileChooser.APPROVE_OPTION) {
            return;
        }
        try {
            File file = jFileChooser.getSelectedFile();
            String filePath = file.getCanonicalPath();
            // 获取分隔符最后以一个字段作为文件名
            String[] split = filePath.split("\\\\");
            String fileName = split[split.length - 1].split("\\\\")[0];
            String savePath = file.getParent();
            CompletableFuture<Void> future = CompletableFuture.runAsync(() -> {
                String layout;
                BufferedImage image;
                if (rightBarPanel.isVisible() && multiFunctionLabel.getImage() != null && StringUtils.isNotBlank(layoutJson)) {
                    image = multiFunctionLabel.getImage();
                    layout = layoutJson;
                    try {
                        FileUtil.createFileByString(new File(savePath + "/" + fileName + ".json"), layout);
                        ImageIO.write(image, "jpeg", new File(savePath + "/" + fileName + ".jpeg"));
                    } catch (Exception ex) {
                        throw new RuntimeException(ex);
                    }
                } else {
                    if (!device.isOnline()) {
                        MessageUtil.showInfoMessage(MainForm.this, String.format("%s设备连接已断开,无法导出", device.getSn()));
                        return;
                    }
                    // 判断当前设备是否进行过初始化
                    if (hosRemoteDevice != null && hosRemoteDevice.getSn().equals(device.getSn())) {
                        layout = hosRemoteDevice.getLayout();
                        if (layout != null) {
                            FileUtil.createFileByString(new File(savePath + "/" + fileName + ".json"), layout);
                        }
                    } else {
                        layout = device.getLayout(null);
                        FileUtil.createFileByString(new File(savePath + "/" + fileName + ".json"), layout);
                    }
                    image = device.getScreenshot(null);
                    if (image == null) {
                        MessageUtil.showInfoMessage(MainForm.this, "图片截取失败");
                        return;
                    }
                    try {
                        ImageIO.write(image, "jpeg", new File(savePath + "/" + fileName + ".jpeg"));
                    } catch (IOException ex) {
                        throw new RuntimeException(ex);
                    }
                }
            });
            future.get(8, TimeUnit.SECONDS);
            MessageUtil.showInfoMessage(MainForm.this, "导出成功");
        } catch (Exception ex) {
            Log.error(TAG, "export layout fail", ex);
            MessageUtil.showInfoMessage(MainForm.this, "导出失败");
        }
    };

    private final ActionListener btnMouseEventListener = e -> {
        if (hosRemoteDevice == null) {
            MessageUtil.showInfoMessage(MainForm.this, "请先进入投屏模式再使用此功能");
            return;
        }
        if (!btnMouseEvent.isSelected()) {
            injectMouseEvent = false;
            return;
        }
        // 判断当前设备uitest版本
        String uitestVersionResult = hosRemoteDevice.executeShellCommand("uitest --version", 7);
        if (StringUtils.isBlank(uitestVersionResult) || compareUitestVersion("5.1.1.3", uitestVersionResult) > 0) {
            canUseCompleteMouse = false;
            if (isFirstTimeShowMouseTip) {
                MessageUtil.showInfoMessage(MainForm.this, "当前系统只支持鼠标左右键单机事件,不支持拖拽.\n如需鼠标拖拽,请升级设备系统版本");
                isFirstTimeShowMouseTip = false;
            }
        } else {
            canUseCompleteMouse = true;
        }
        injectMouseEvent = btnMouseEvent.isSelected();
    };

    private final ActionListener btnRebootListener = e -> {
        int option = JOptionPane.showConfirmDialog(MainForm.this, "是否确认重启?", "是否确认重启", JOptionPane.YES_NO_OPTION);
        if (option == JOptionPane.YES_OPTION) {
            if (hosRemoteDevice != null) {
                hosRemoteDevice.executeShellCommand("reboot", 3);
            }
        }
    };


    DumpLayoutCallBack dumpLayoutCallBack = new DumpLayoutCallBack() {
        @Override
        public void normalDumpLayoutMode(Point point) {
            if (multiFunctionLabel.getImage() == null || structureTreeRoot == null) {
                return;
            }
            updateWidgetInfoByClickPoint(point);
        }
    };

    private final ScreenCapCallback newSoScreenCallBack = new ScreenCapCallback() {
        @Override
        public void onData(ByteBuffer byteBuffer) {
            try {
                decodeH264(byteBuffer.array());
            } catch (Exception ex) {
                Log.info(TAG, "decodeH264 error: " + ex);
            }
        }

        @Override
        public void onException(Throwable throwable) {
            Log.error(TAG, "get h264 error", throwable);
            if (!new Device(hosRemoteDevice.getSn()).isOnline()) {
                MessageUtil.showInfoMessage(MainForm.this, String.format("%s设备连接已断开", hosRemoteDevice.getSn()));
            } else if (throwable.getMessage().contains("can not find scrcpy pid")) {
                // 尝试使用图片流进入
                CompletableFuture.runAsync(() -> {
                    startScreenCaptureByImageMode();
                });
                return;
            } else {
                MessageUtil.showInfoMessage(MainForm.this, "投屏失败:\n" + throwable);
            }
            lblTip.setVisible(false);
            hosRemoteDevice = null;
            multiFunctionLabel.setScreenCapturingMode(false);
            controlPanel.setVisible(false);
        }

        @Override
        public void onReady() {
            Log.info(TAG, "get h264 ready");
            multiFunctionLabel.setScreenCapturingMode(true);
            multiFunctionLabel.setTipMessage(MultiFunctionLabel.STREAM_READY_TIP_MESSAGE);
            hosRemoteDevice.executeShellCommand("uinput -M -m 100 100 200 200 --trace", 2);
        }
    };

    /**
     * 为显示页面和控件树添加文件拖入事件
     */
    private void addDragFileListener() {
        DropTargetAdapter structureTreeDragAdapter = new DropTargetAdapter() {
            @Override
            public void drop(DropTargetDropEvent dtde) {
                if (multiFunctionLabel.isScreenCapturingMode()) {
                    return;
                }
                try {
                    Transferable tf = dtde.getTransferable();
                    if (!tf.isDataFlavorSupported(DataFlavor.javaFileListFlavor)) {
                        dtde.rejectDrop();
                        return;
                    }
                    dtde.acceptDrop(DnDConstants.ACTION_COPY_OR_MOVE);
                    List transferData = (List) tf.getTransferData(DataFlavor.javaFileListFlavor);
                    if (transferData.size() != 1) {
                        MessageUtil.showInfoMessage(MainForm.this, "不支持多文件的拖入!");
                        dtde.dropComplete(true);
                        return;
                    }
                    File f = (File) transferData.get(0);
                    if (!f.exists()) {
                        MessageUtil.showInfoMessage(MainForm.this, "文件路径不存在");
                        dtde.dropComplete(true);
                        return;
                    }
                    if (!f.getName().endsWith(".jpeg") && !f.getName().endsWith(".png") && !f.getName().endsWith("jpg") && !f.getName().endsWith(".json")) {
                        MessageUtil.showInfoMessage(MainForm.this, "只支持jpeg、png、jpg以及json文件的拖入");
                        dtde.dropComplete(true);
                        return;
                    }
                    File parentFolder = new File(f.getParent());
                    String fileName = f.getName().substring(0, f.getName().lastIndexOf("."));
                    if (f.getName().endsWith("json")) {
                        loadJsonFile(f);
                        // 尝试在json同目录下寻找同名图片自动进行加载
                        List<File> imgs = new ArrayList<>();
                        imgs.add(new File(parentFolder, fileName + ".jpeg"));
                        imgs.add(new File(parentFolder, fileName + ".png"));
                        imgs.add(new File(parentFolder, fileName + ".jpg"));
                        for (File file : imgs) {
                            if (file.exists()) {
                                loadImageFile(file);
                                break;
                            }
                        }
                    } else {
                        loadImageFile(f);
                        // 尝试查找同名的json进行加载
                        File jsonFile = new File(parentFolder, fileName + ".json");
                        if (jsonFile.exists()) {
                            loadJsonFile(jsonFile);
                        }
                    }
                    dtde.dropComplete(true);
                } catch (Exception ex) {
                    Log.error(TAG, "structureTree add dragListener failed", ex);
                }
            }
        };
        new DropTarget(structureTree, DnDConstants.ACTION_COPY_OR_MOVE, structureTreeDragAdapter);
        new DropTarget(multiFunctionLabel, DnDConstants.ACTION_COPY_OR_MOVE, structureTreeDragAdapter);
    }

    private void loadImageFile(File f) throws IOException {
        if (multiFunctionLabel.isScreenCapturingMode()) {
            return;
        }
        multiFunctionLabel.setRectangles(Collections.emptyList());
        multiFunctionLabel.setImage(ImageIO.read(f));
        multiFunctionLabel.updateUI();
    }

    /**
     * 加载json文件并展开控件树面板进行展示
     *
     * @param f json文件
     */
    private void loadJsonFile(File f) {
        JsonStructure jsonStructure = null;
        try {
            String layout = FileUtil.readFileContent(f);
            jsonStructure = new GsonBuilder().excludeFieldsWithoutExposeAnnotation().create().fromJson(layout, JsonStructure.class);
            layoutJson = layout;
        } catch (Exception ex) {
            MessageUtil.showInfoMessage(MainForm.this, "json文件结构不符合要求");
            return;
        }
        if (jsonStructure == null) {
            MessageUtil.showInfoMessage(MainForm.this, "json文件结构解析为空");
            return;
        }
        if (StringUtils.isBlank(jsonStructure.getAttributes().getOrDefault("type", "").toString())) {
            jsonStructure.getAttributes().put("type", "Root");
        }
        structureTreeRoot.removeAllChildren();
        structureTreeRoot.setUserObject(jsonStructure);
        structureTreeRoot.add(TreeUtil.convertJsonStructureToJTreeNode(jsonStructure));
        DefaultTreeModel model = (DefaultTreeModel) structureTree.getModel();
        model.nodeChanged(structureTreeRoot);
        structureTree.setRootVisible(true);
        structureTree.expandRow(0);
        structureTree.setRootVisible(false);
        structureTree.updateUI();
        showRightBarPanel();
    }

    /**
     * 投屏失败时的恢复动作
     */
    private void doActionWhenScreenCaptureError() {
        hosRemoteDevice = null;
        multiFunctionLabel.setScreenCapturingMode(false);
        btnEnterScreenCapture.setText("进入投屏");
        controlPanel.setVisible(false);
        btnRefreshLayout.setEnabled(false);
        btnSeeWidget.setSelected(false);
        btnSeeWidget.setEnabled(true);
        multiFunctionLabel.setImage(null);
        multiFunctionLabel.setTipMessage(MultiFunctionLabel.DEFAULT_TIP_MESSAGE);
        multiFunctionLabel.setRectangles(Collections.emptyList());
    }

    private final KeyBoardCallBack keyBoardCallBack = new KeyBoardCallBack() {
        @Override
        public void onKeyBoardDown(KeyEvent keyEvent, int keyCode, boolean isPressingShift) {
            if (!multiFunctionLabel.isScreenCapturingMode() || hosRemoteDevice == null) {
                return;
            }
            String cmd = String.format("uinput -K -d %d -u %d", keyCode, keyCode);
            if (keyEvent == null) {
                // 事件为空就直接粘贴keyCode
            } else if (keyEvent.getKeyChar() == '<' || keyEvent.getKeyChar() == '>'
                    || keyEvent.getKeyChar() == '?' || keyEvent.getKeyChar() == '.') {
                // 对这4个没有键值码的字符进行特殊处理
                cmd = String.format("uitest uiInput text '%s'", keyEvent.getKeyChar());
            } else if (Character.isLetter(keyEvent.getKeyChar())) {
                // 原始输入是大写的情况
                if (KeyCodeUtil.isUpperLetter(keyEvent.getKeyChar())) {
                    cmd = String.format("uinput -K -d 2047 -d %d -u %d -u 2047", keyCode, keyCode);
                }
            } else {
                // 如果同时按下了shift
                if (isPressingShift) {
                    cmd = String.format("uinput -K -d 2047 -d %d -u %d -u 2047", keyCode, keyCode);
                }
            }
            String finalCmd = cmd;
            inputTextThreadPool.submit(() -> {
                hosRemoteDevice.executeShellCommand(finalCmd, 5);
            });
        }

        @Override
        public void onPressPaste() {
            if (!multiFunctionLabel.isScreenCapturingMode() || hosRemoteDevice == null) {
                return;
            }
            multiFunctionLabel.setCursor(Cursor.getPredefinedCursor(Cursor.WAIT_CURSOR));
            SwingWorker<Void, Void> swingWorker = new SwingWorker<Void, Void>() {
                @Override
                protected Void doInBackground() throws Exception {
                    Clipboard clipboard = Toolkit.getDefaultToolkit().getSystemClipboard();
                    // 检查粘贴板是否有内容
                    if (!clipboard.isDataFlavorAvailable(DataFlavor.stringFlavor)) {
                        return null;
                    }
                    try {
                        String content = (String) clipboard.getData(DataFlavor.stringFlavor);
                        if (StringUtils.isBlank(content)) {
                            return null;
                        }
                        inputTextThreadPool.submit(() -> {
                            String cmd = String.format("uitest uiInput text '%s'", content);
                            hosRemoteDevice.executeShellCommand(cmd, 5);
                        });
                    } catch (Exception ex) {
                        Log.info(TAG, "get clipboard content fail : " + ex);
                    }
                    return null;
                }

                @Override
                protected void done() {
                    multiFunctionLabel.setCursor(Cursor.getPredefinedCursor(Cursor.DEFAULT_CURSOR));
                }
            };

            swingWorker.execute();
        }

        @Override
        public void onChineseCharInput(String content) {
            if (!multiFunctionLabel.isScreenCapturingMode()) {
                return;
            }
            inputTextThreadPool.submit(() -> {
                hosRemoteDevice.executeShellCommand(String.format("uitest uiInput text '%s'", content), 10);
            });
        }
    };

    private int compareUitestVersion(String targetVersion, String deviceUitestVersionResult) {
        try {
            String[] lines = deviceUitestVersionResult.split(System.lineSeparator());
            String deviceUitestVersion = lines[lines.length - 1];
            String[] targetLinkSplit = targetVersion.split("\\.");
            String[] deviceLinkSplit = deviceUitestVersion.split("\\.");
            int min = Math.min(targetLinkSplit.length, deviceLinkSplit.length);
            for (int i = 0; i < min; i++) {
                if (Integer.parseInt(targetLinkSplit[i]) > Integer.parseInt(deviceLinkSplit[i])) {
                    return 1;
                } else if (Integer.parseInt(targetLinkSplit[i]) < Integer.parseInt(deviceLinkSplit[i])) {
                    return -1;
                }
            }
            return 0;
        } catch (Exception ex) {
            Log.info(TAG, "parse uitest version fail: " + ex);
            return -1;
        }
    }

    private void initButtons() {
        btnVolumeDown.setIcon(new ImageIcon(FileUtil.readResourceFileByteArray("pic/VolumeDown.png")));
        btnVolumeUp.setIcon(new ImageIcon(FileUtil.readResourceFileByteArray("pic/VolumeUp.png")));
        btnPower.setIcon(new ImageIcon(FileUtil.readResourceFileByteArray("pic/Power.png")));
        btnMouseEvent.setIcon(new ImageIcon(FileUtil.readResourceFileByteArray("pic/Mouse.png")));
        btnBack.setIcon(new ImageIcon(FileUtil.readResourceFileByteArray("pic/GoBack.png")));
        btnReboot.setIcon(new ImageIcon(FileUtil.readResourceFileByteArray("pic/Reboot.png")));
        btnVolumeUp.setPreferredSize(new Dimension(30, 30));
        btnVolumeDown.setPreferredSize(new Dimension(30, 30));
        btnPower.setPreferredSize(new Dimension(30, 30));
        btnBack.setPreferredSize(new Dimension(30, 30));
        btnMouseEvent.setPreferredSize(new Dimension(30, 30));
        btnReboot.setPreferredSize(new Dimension(30, 30));
        btnBack.setToolTipText("返回键");
        btnVolumeDown.setToolTipText("音量减键");
        btnVolumeUp.setToolTipText("音量加键");
        btnMouseEvent.setToolTipText("注入鼠标事件");
        btnPower.setToolTipText("电源键");
        btnReboot.setToolTipText("重启设备");
    }

    private String getMouseButton(MouseEvent mouseEvent) {
        if (mouseEvent.getButton() == MouseEvent.BUTTON1) {
            return HosRemoteDevice.MOUSE_LEFT;
        } else if (mouseEvent.getButton() == MouseEvent.BUTTON2) {
            return HosRemoteDevice.MOUSE_MIDDLE;
        } else {
            return HosRemoteDevice.MOUSE_RIGHT;
        }
    }

    private final MouseWheelCallBack mouseWheelCallBack = new MouseWheelCallBack() {
        @Override
        public void onMouseWheelChange(Point wheelPoint, boolean isMoueUp) {
            if (hosRemoteDevice == null || !multiFunctionLabel.isScreenCapturingMode()) {
                return;
            }
            Point actualClickPoint = getActualClickPoint(wheelPoint, true);
            if (actualClickPoint == null) {
                return;
            }
            if (isMoueUp) {
                if (canUseCompleteMouse) {
                    hosRemoteDevice.onMouseWheelUp(actualClickPoint.x, actualClickPoint.y);
                    hosRemoteDevice.onMouseWheelStop(actualClickPoint.x, actualClickPoint.y);
                } else {
                    hosRemoteDevice.executeShellCommand(String.format("uinput -M -m %s %s -s -500", actualClickPoint.x, actualClickPoint.y), 5);
                }
            } else {
                if (canUseCompleteMouse) {
                    hosRemoteDevice.onMouseWheelDown(actualClickPoint.x, actualClickPoint.y);
                    hosRemoteDevice.onMouseWheelStop(actualClickPoint.x, actualClickPoint.y);
                } else {
                    hosRemoteDevice.executeShellCommand(String.format("uinput -M -m %s %s -s 500", actualClickPoint.x, actualClickPoint.y), 5);
                }
            }
        }
    };

    private final ActionListener btnRemoteIpManagerListener = e -> {
        RemoteManager remoteManager = new RemoteManager(MainForm.this, "管理远程IP");
        remoteManager.setSize(400, 600);
        remoteManager.setLocationRelativeTo(MainForm.this);
        remoteManager.setVisible(true);
    };

    private void startScreenCaptureByImageMode() {
        lblTip.setVisible(true);
        lblTip.setText("当前使用图片流投屏模式");
        hosRemoteDevice.stopImageScreenCapture();
        hosRemoteDevice.startImageScreenCapture(new ScreenCapCallback() {
            @Override
            public void onData(ByteBuffer byteBuffer) {
                try {
                    BufferedImage bufferedImage = ImageIO.read(new ByteArrayInputStream(byteBuffer.array()));
                    if (bufferedImage == null) {
                        return;
                    }
                    if (multiFunctionLabel.isScreenCapturingMode()) {
                        multiFunctionLabel.setImage(bufferedImage);
                    }
                } catch (IOException e) {
                    Log.info(TAG, "process image error: " + e);
                }
            }

            @Override
            public void onException(Throwable throwable) {
                Log.error(TAG, "get image error", throwable);
                MessageUtil.showInfoMessage(MainForm.this, "获取图片流失败:\n" + throwable);
                hosRemoteDevice = null;
                multiFunctionLabel.setScreenCapturingMode(false);
                controlPanel.setVisible(false);
            }

            @Override
            public void onReady() {
                Log.info(TAG, "get image ready");
            }
        });
    }
}
