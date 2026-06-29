"""Smoke tests for hos_scrcpy package — no device needed."""
from hos_scrcpy.input.keycode import KeyCode, keycode_for_char, name_for_keycode

# Key codes
assert KeyCode.ENTER == 2119
assert KeyCode.A == 2017
assert KeyCode.Z == 2042
assert KeyCode.DIGIT_5 == 2005
assert KeyCode.SHIFT == 2047

# Char mapping
assert keycode_for_char("A") == 2017
assert keycode_for_char("5") == 2005
assert keycode_for_char("z") == 2042
assert keycode_for_char("!") == -1

# Name lookup
assert name_for_keycode(2119) == "ENTER"
print("KeyCode: OK")

from hos_scrcpy.utils.bounds import parse_bounds, bounds_to_rectangle

r = parse_bounds("[100,200][300,400]")
assert r == (100, 200, 200, 200), f"got {r}"
d = bounds_to_rectangle("[10,20][110,120]")
assert d == {"x": 10, "y": 20, "width": 100, "height": 100}
print("Bounds: OK")

from hos_scrcpy.ui.hierarchy import JsonStructure

data = {
    "attributes": {"type": "Button", "text": "OK", "bounds": "[0,0][100,50]"},
    "children": [],
}
node = JsonStructure(data)
assert node.type == "Button"
assert node.text == "OK"
assert node.center == (50, 25)
assert len(node.children) == 0
assert node.is_clickable is False
assert node.is_visible is True
assert node.bundle_name == ""
assert node.hierarchy_path == ""
print("JsonStructure: OK")

from hos_scrcpy.ui.selector import UiSelector

root = JsonStructure(
    {
        "attributes": {"type": "Root"},
        "children": [
            {
                "attributes": {"type": "Button", "text": "OK", "bounds": "[0,0][100,50]"},
                "children": [],
            },
            {
                "attributes": {
                    "type": "Button",
                    "text": "Cancel",
                    "bounds": "[120,0][220,50]",
                },
                "children": [],
            },
            {
                "attributes": {
                    "type": "Text",
                    "text": "Hello",
                    "bounds": "[0,60][200,90]",
                },
                "children": [],
            },
        ],
    }
)

sel = UiSelector(root).type("Button")
assert sel.count() == 2
assert sel.first().text == "OK"
assert UiSelector(root).text("Cancel").first().type == "Button"
assert UiSelector(root).text_contains("ell").count() == 1
assert UiSelector(root).type("NotExist").first() is None
print("UiSelector: OK")

from hos_scrcpy import HOSDevice, Device

assert hasattr(HOSDevice, "connect")
assert hasattr(HOSDevice, "list_devices")
print("HOSDevice: OK")

print("\nALL SMOKE TESTS PASSED")
