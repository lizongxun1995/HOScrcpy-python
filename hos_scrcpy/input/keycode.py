"""HarmonyOS key code constants — mapped from Java KeyCodeUtil.

Key codes are the HarmonyOS uinput key values used with 'uinput -K' commands.

Letter keys A-Z:  2017 + (ord(char) - 65)
Digit keys 0-9:   2000 + digit
"""


class KeyCode:
    # ---- navigation ----
    UP = 2012
    DOWN = 2013
    LEFT = 2014
    RIGHT = 2015
    ENTER = 2119
    BACKSPACE = 2055
    SPACE = 2050
    TAB = 2049
    ESCAPE = 2070

    # ---- modifiers ----
    SHIFT = 2047
    CTRL = 2072

    # ---- digits 0-9 ----
    DIGIT_0 = 2000
    DIGIT_1 = 2001
    DIGIT_2 = 2002
    DIGIT_3 = 2003
    DIGIT_4 = 2004
    DIGIT_5 = 2005
    DIGIT_6 = 2006
    DIGIT_7 = 2007
    DIGIT_8 = 2008
    DIGIT_9 = 2009

    # ---- letters A-Z ----
    A = 2017
    B = 2018
    C = 2019
    D = 2020
    E = 2021
    F = 2022
    G = 2023
    H = 2024
    I = 2025
    J = 2026
    K = 2027
    L = 2028
    M = 2029
    N = 2030
    O = 2031
    P = 2032
    Q = 2033
    R = 2034
    S = 2035
    T = 2036
    U = 2037
    V = 2038
    W = 2039
    X = 2040
    Y = 2041
    Z = 2042

    # ---- symbols ----
    EQUALS = 2058
    PLUS = 2066
    MINUS = 2057
    SEMICOLON = 2062
    OPEN_BRACKET = 2059
    CLOSE_BRACKET = 2060
    SLASH = 2113
    QUOTE = 2063
    COMMA = 2118
    PERIOD = 2117
    BACK_SLASH = 2061
    DIVIDE = 2064
    MULTIPLY = 2010
    SUBTRACT = 2057
    ADD = 2066
    DECIMAL = 2117
    BACK_QUOTE = 2056

    # ---- system keys ----
    BACK = 2
    HOME = 3
    POWER = 18
    VOLUME_UP = 16
    VOLUME_DOWN = 17


# Reverse mappings for convenience
_KEYCODE_TO_NAME: dict[int, str] = {}
_NAME_TO_KEYCODE: dict[str, int] = {}

for _name in dir(KeyCode):
    if not _name.startswith("_"):
        _val = getattr(KeyCode, _name)
        if isinstance(_val, int):
            _KEYCODE_TO_NAME[_val] = _name
            _NAME_TO_KEYCODE[_name.upper()] = _val


def keycode_for_char(char: str) -> int:
    """Get the HarmonyOS key code for a single character.

    Returns -1 if the character cannot be mapped.
    """
    if char.isalpha():
        offset = ord(char.upper()) - 65
        return 2017 + offset
    if char.isdigit():
        return 2000 + int(char)
    return -1


def name_for_keycode(keycode: int) -> str:
    """Get the name string for a key code value."""
    return _KEYCODE_TO_NAME.get(keycode, f"UNKNOWN({keycode})")


def keycode_for_name(name: str) -> int:
    """Get the key code value from a name string."""
    return _NAME_TO_KEYCODE.get(name.upper(), -1)
