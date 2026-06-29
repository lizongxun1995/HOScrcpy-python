package utils.callbacks;

import utils.swing.MultiFunctionLabel;

import java.awt.*;
import java.awt.event.MouseEvent;

public interface ActualTimeControlCallBack {
    void onMouseMove(MouseEvent mouseEvent, MultiFunctionLabel multiFunctionLabel, boolean isPressing);
    void onMouseUp(MouseEvent mouseEvent, MultiFunctionLabel multiFunctionLabel);
    void onMouseDown(MouseEvent mouseEvent, MultiFunctionLabel multiFunctionLabel);
}
