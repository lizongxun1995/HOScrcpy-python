package utils.callbacks;

import java.awt.event.KeyEvent;

public interface KeyBoardCallBack {
    void onKeyBoardDown(KeyEvent keyEvent, int keyCode, boolean isPressingShift);

    void onPressPaste();

    void onChineseCharInput(String content);
}
