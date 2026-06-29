package utils;

import java.awt.*;
import java.awt.event.KeyEvent;
import java.util.HashMap;

public class KeyCodeUtil {
    private static final HashMap<Integer, Integer> KEY_CODE_MAPPER = new HashMap<>();
    private static final HashMap<Integer, Integer> KEY_CODE_WITH_SHIFT_MAPPER = new HashMap<>();

    static {
        KEY_CODE_MAPPER.put(KeyEvent.VK_BACK_SPACE, 2055);
        KEY_CODE_MAPPER.put(KeyEvent.VK_ENTER, 2119);
        KEY_CODE_MAPPER.put(KeyEvent.VK_UP, 2012);
        KEY_CODE_MAPPER.put(KeyEvent.VK_DOWN, 2013);
        KEY_CODE_MAPPER.put(KeyEvent.VK_LEFT, 2014);
        KEY_CODE_MAPPER.put(KeyEvent.VK_RIGHT, 2015);
        KEY_CODE_MAPPER.put(KeyEvent.VK_SPACE, 2050);
        KEY_CODE_MAPPER.put(KeyEvent.VK_EQUALS, 2058);
        KEY_CODE_MAPPER.put(KeyEvent.VK_PLUS, 2066);
        KEY_CODE_MAPPER.put(KeyEvent.VK_MINUS, 2057);
        KEY_CODE_MAPPER.put(KeyEvent.VK_ESCAPE, 2070);
        KEY_CODE_MAPPER.put(KeyEvent.VK_SEMICOLON, 2062);
        KEY_CODE_MAPPER.put(KeyEvent.VK_OPEN_BRACKET, 2059);
        KEY_CODE_MAPPER.put(KeyEvent.VK_CLOSE_BRACKET, 2060);
        KEY_CODE_MAPPER.put(KeyEvent.VK_SLASH, 2113);
        KEY_CODE_MAPPER.put(KeyEvent.VK_QUOTE, 2063);
        KEY_CODE_MAPPER.put(KeyEvent.VK_COMMA, 2118);
        KEY_CODE_MAPPER.put(KeyEvent.VK_PERIOD, 2117);
        KEY_CODE_MAPPER.put(KeyEvent.VK_BACK_SLASH, 2061);
        KEY_CODE_MAPPER.put(KeyEvent.VK_TAB, 2049);
        KEY_CODE_MAPPER.put(KeyEvent.VK_DIVIDE, 2064);
        KEY_CODE_MAPPER.put(KeyEvent.VK_MULTIPLY, 2010);
        KEY_CODE_MAPPER.put(KeyEvent.VK_SUBTRACT, 2057);
        KEY_CODE_MAPPER.put(KeyEvent.VK_ADD, 2066);
        KEY_CODE_MAPPER.put(KeyEvent.VK_DECIMAL, 2117);
        KEY_CODE_MAPPER.put(KeyEvent.VK_BACK_QUOTE, 2056);


        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_COMMA, 2118);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_PERIOD, 2117);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_SLASH, 2113);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_BACK_QUOTE, 2056);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_0, 2000);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_1, 2001);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_2, 2002);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_3, 2003);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_4, 2004);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_5, 2005);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_6, 2006);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_7, 2007);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_8, 2008);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_9, 2009);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_SUBTRACT, 2057);
        KEY_CODE_WITH_SHIFT_MAPPER.put(KeyEvent.VK_ADD, 2058);
    }

    public static boolean isSupport(KeyEvent keyEvent) {
        if (keyEvent.getModifiers() == Event.SHIFT_MASK) {
            if (KEY_CODE_WITH_SHIFT_MAPPER.containsKey(keyEvent.getKeyCode())) {
                return true;
            }
        }
        // 响应ctrl + v 粘贴
        if (keyEvent.getModifiers() == Event.CTRL_MASK) {
            if (keyEvent.getKeyCode() == KeyEvent.VK_V) {
                return true;
            }
        }
        return Character.isLetterOrDigit(keyEvent.getKeyChar()) || KEY_CODE_MAPPER.containsKey(keyEvent.getKeyCode());
    }

    public static boolean isPasteAction(KeyEvent keyEvent) {
        return keyEvent.getModifiers() == Event.CTRL_MASK && keyEvent.getKeyCode() == KeyEvent.VK_V;
    }

    public static int getKeyCode(KeyEvent keyEvent) {
        if (keyEvent.getModifiers() == Event.SHIFT_MASK && KEY_CODE_WITH_SHIFT_MAPPER.containsKey(keyEvent.getKeyCode())) {
            return KEY_CODE_WITH_SHIFT_MAPPER.get(keyEvent.getKeyCode());
        }
        if (KEY_CODE_MAPPER.containsKey(keyEvent.getKeyCode())) {
            return KEY_CODE_MAPPER.get(keyEvent.getKeyCode());
        }
        char c = keyEvent.getKeyChar();
        if (Character.isLetter(c)) {
            c = Character.toUpperCase(c);
            int result = (int) c - 65;
            return result + 2017;
        } else if (Character.isDigit(c)) {
            int result = (int) c - 48;
            return result + 2000;
        }
        return -1;
    }

    public static boolean isUpperLetter(Character c) {
        return Character.isLetter(c) && Character.isUpperCase(c);
    }
}
