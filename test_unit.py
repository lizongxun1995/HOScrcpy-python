"""Unit tests for hos_scrcpy library — no device needed.

Run with: pytest test_unit.py -v
"""
import pytest
from hos_scrcpy.input.keycode import KeyCode, keycode_for_char, name_for_keycode
from hos_scrcpy.utils.bounds import parse_bounds, bounds_to_rectangle
from hos_scrcpy.ui.hierarchy import JsonStructure
from hos_scrcpy.ui.selector import UiSelector, UIHierarchy
from hos_scrcpy.ui.xpath import find_by_xpath, xpath_for, _build_parent_map
from hos_scrcpy.interfaces import (
    HOScrcpyError, ScreenshotError, DeviceOfflineError,
    CommandNotSupportedError, StreamError, UIHierarchyError,
)


# =============================================================================
# KeyCode
# =============================================================================

class TestKeyCode:
    def test_constants(self):
        assert KeyCode.ENTER == 2119
        assert KeyCode.A == 2017
        assert KeyCode.Z == 2042
        assert KeyCode.DIGIT_5 == 2005
        assert KeyCode.SHIFT == 2047
        assert KeyCode.HOME == 2126
        assert KeyCode.BACK == 2110
        assert KeyCode.POWER == 2129

    def test_keycode_for_char(self):
        assert keycode_for_char("A") == 2017
        assert keycode_for_char("5") == 2005
        assert keycode_for_char("z") == 2042
        assert keycode_for_char("!") == -1  # no direct mapping
        assert keycode_for_char(" ") == KeyCode.SPACE

    def test_name_for_keycode(self):
        assert name_for_keycode(2119) == "ENTER"
        assert name_for_keycode(2126) == "HOME"
        assert name_for_keycode(9999) is None


# =============================================================================
# Bounds
# =============================================================================

class TestBounds:
    def test_parse_bounds(self):
        r = parse_bounds("[100,200][300,400]")
        assert r == (100, 200, 200, 200)

    def test_parse_bounds_empty(self):
        assert parse_bounds("") == (0, 0, 0, 0)

    def test_parse_bounds_invalid(self):
        assert parse_bounds("garbage") == (0, 0, 0, 0)

    def test_parse_bounds_zero_area(self):
        r = parse_bounds("[0,0][0,0]")
        assert r == (0, 0, 0, 0)

    def test_bounds_to_rectangle(self):
        d = bounds_to_rectangle("[10,20][110,120]")
        assert d == {"x": 10, "y": 20, "width": 100, "height": 100}

    def test_bounds_to_rectangle_empty(self):
        assert bounds_to_rectangle("") == {"x": 0, "y": 0, "width": 0, "height": 0}


# =============================================================================
# JsonStructure (UI hierarchy node)
# =============================================================================

SAMPLE_NODE = {
    "attributes": {
        "type": "Button",
        "text": "OK",
        "bounds": "[0,0][100,50]",
        "id": "btn_ok",
        "clickable": "true",
        "enabled": "true",
        "visible": "true",
    },
    "children": [],
    "index": 0,
}

SAMPLE_TREE = {
    "attributes": {"type": "Root"},
    "children": [
        {
            "attributes": {"type": "Button", "text": "OK", "bounds": "[0,0][100,50]", "id": "btn_ok"},
            "children": [],
        },
        {
            "attributes": {"type": "Button", "text": "Cancel", "bounds": "[120,0][220,50]", "id": "btn_cancel"},
            "children": [],
        },
        {
            "attributes": {"type": "Text", "text": "Hello", "bounds": "[0,60][200,90]"},
            "children": [
                {
                    "attributes": {"type": "Span", "text": "World", "bounds": "[10,65][90,85]"},
                    "children": [],
                }
            ],
        },
    ],
}


class TestJsonStructure:
    def test_create_node(self):
        node = JsonStructure(SAMPLE_NODE)
        assert node.type == "Button"
        assert node.text == "OK"
        assert node.center == (50, 25)
        assert node.rectangle == (0, 0, 100, 50)
        assert node.id == "btn_ok"
        assert node.is_clickable is True
        assert node.is_enabled is True
        assert node.is_visible is True
        assert node.is_scrollable is False
        assert node.is_focused is False
        assert node.child_count == 0

    def test_create_empty_node(self):
        node = JsonStructure({})
        assert node.type == ""
        assert node.text == ""
        assert node.rectangle == (0, 0, 0, 0)
        assert node.center == (0, 0)
        assert node.child_count == 0
        assert node.bundle_name == ""

    def test_create_node_no_data(self):
        node = JsonStructure()
        assert node.type == ""
        assert node.children == []

    def test_iter_all(self):
        root = JsonStructure(SAMPLE_TREE)
        nodes = list(root.iter_all())
        assert len(nodes) == 5  # Root + 3 children + 1 grandchild
        assert nodes[0].type == "Root"
        assert nodes[1].type == "Button"
        assert nodes[2].type == "Button"
        assert nodes[3].type == "Text"
        assert nodes[4].type == "Span"

    def test_iter_children(self):
        root = JsonStructure(SAMPLE_TREE)
        children = list(root.iter_children())
        assert len(children) == 3

    def test_iter_descendants(self):
        root = JsonStructure(SAMPLE_TREE)
        descendants = list(root.iter_descendants())
        assert len(descendants) == 4  # excludes root

    def test_find_first(self):
        root = JsonStructure(SAMPLE_TREE)
        node = root.find_first(lambda n: n.text == "Cancel")
        assert node is not None
        assert node.type == "Button"

    def test_find_first_not_found(self):
        root = JsonStructure(SAMPLE_TREE)
        node = root.find_first(lambda n: n.text == "NotHere")
        assert node is None

    def test_find_all(self):
        root = JsonStructure(SAMPLE_TREE)
        buttons = root.find_all(lambda n: n.type == "Button")
        assert len(buttons) == 2

    def test_to_dict(self):
        node = JsonStructure(SAMPLE_NODE)
        d = node.to_dict()
        assert d["attributes"]["type"] == "Button"
        assert len(d["children"]) == 0

    def test_bool_attributes(self):
        """Verify _to_bool handles various formats."""
        btn = JsonStructure(SAMPLE_NODE)
        assert btn.is_clickable is True

        # Test different bool formats
        data = {
            "attributes": {"clickable": True, "enabled": 1, "visible": "true", "selected": "yes"},
            "children": [],
        }
        n = JsonStructure(data)
        assert n.is_clickable is True
        assert n.is_enabled is True
        assert n.is_visible is True
        assert n.is_selected is True

    def test_repr(self):
        node = JsonStructure(SAMPLE_NODE)
        r = repr(node)
        assert "Button" in r
        assert "OK" in r


# =============================================================================
# UiSelector
# =============================================================================

class TestUiSelector:
    def setup_method(self):
        self.root = JsonStructure(SAMPLE_TREE)

    def test_select_by_type(self):
        sel = UiSelector(self.root).type("Button")
        assert sel.count() == 2

    def test_select_first(self):
        sel = UiSelector(self.root).type("Button")
        assert sel.first().text == "OK"

    def test_select_by_text(self):
        sel = UiSelector(self.root).text("Cancel")
        assert sel.first().type == "Button"

    def test_select_text_contains(self):
        sel = UiSelector(self.root).text_contains("ell")
        assert sel.count() == 1
        assert sel.first().text == "Hello"

    def test_select_by_id(self):
        sel = UiSelector(self.root).id("btn_ok")
        assert sel.count() == 1
        assert sel.first().type == "Button"

    def test_select_not_found(self):
        sel = UiSelector(self.root).type("NotExist")
        assert sel.first() is None
        assert sel.count() == 0
        assert sel.exists() is False

    def test_chained_filters(self):
        sel = (UiSelector(self.root)
               .type("Button")
               .clickable(True))
        assert sel.count() == 2

    def test_at_point(self):
        sel = UiSelector(self.root).at_point(50, 25)
        assert sel.count() >= 1

    def test_at_point_outside(self):
        sel = UiSelector(self.root).at_point(9999, 9999)
        assert sel.count() == 0

    def test_all_returns_list(self):
        sel = UiSelector(self.root).type("Button")
        results = sel.all()
        assert isinstance(results, list)
        assert len(results) == 2


# =============================================================================
# XPath
# =============================================================================

class TestXPath:
    def setup_method(self):
        self.root = JsonStructure(SAMPLE_TREE)

    def test_find_by_type(self):
        results = find_by_xpath(self.root, "//Button")
        assert len(results) == 2

    def test_find_by_text(self):
        results = find_by_xpath(self.root, "//Button[@text='OK']")
        assert len(results) == 1
        assert results[0].text == "OK"

    def test_find_wildcard(self):
        results = find_by_xpath(self.root, "//*[@text='Hello']")
        assert len(results) == 1
        assert results[0].type == "Text"

    def test_find_nested(self):
        results = find_by_xpath(self.root, "//Text/Span")
        assert len(results) == 1
        assert results[0].type == "Span"

    def test_find_absolute_path(self):
        results = find_by_xpath(self.root, "/Root")
        assert len(results) == 1

    def test_find_not_found(self):
        results = find_by_xpath(self.root, "//NonExistent")
        assert len(results) == 0

    def test_find_empty_expr(self):
        results = find_by_xpath(self.root, "")
        assert len(results) == 0

    def test_xpath_for(self):
        buttons = find_by_xpath(self.root, "//Button")
        assert len(buttons) >= 1
        path = xpath_for(buttons[0], self.root)
        assert "Button" in path
        assert "btn_ok" in path or "OK" in path

    def test_xpath_for_without_root(self):
        node = JsonStructure(SAMPLE_NODE)
        path = xpath_for(node)
        assert "Button" in path

    def test_build_parent_map(self):
        parent_map = _build_parent_map(self.root)
        # Root has 3 children
        assert len(parent_map) == 4  # 3 direct + 1 grandchild

    def test_xpath_filter(self):
        from hos_scrcpy.ui.xpath import xpath_filter
        results = xpath_filter(self.root, {"type": "Button"})
        assert len(results) == 2


# =============================================================================
# Custom exceptions
# =============================================================================

class TestExceptions:
    def test_exception_hierarchy(self):
        assert issubclass(ScreenshotError, HOScrcpyError)
        assert issubclass(DeviceOfflineError, HOScrcpyError)
        assert issubclass(CommandNotSupportedError, HOScrcpyError)
        assert issubclass(StreamError, HOScrcpyError)
        assert issubclass(UIHierarchyError, HOScrcpyError)

    def test_screenshot_error_has_message(self):
        try:
            raise ScreenshotError("test error")
        except ScreenshotError as e:
            assert str(e) == "test error"

    def test_catch_base_exception(self):
        try:
            raise DeviceOfflineError("device gone")
        except HOScrcpyError as e:
            assert isinstance(e, DeviceOfflineError)

    def test_chained_exception(self):
        try:
            try:
                raise ValueError("inner")
            except ValueError as inner:
                raise ScreenshotError("outer") from inner
        except ScreenshotError as e:
            assert isinstance(e.__cause__, ValueError)


# =============================================================================
# HOSDevice class signature (no device needed)
# =============================================================================

class TestHOSDeviceInterface:
    def test_class_has_expected_methods(self):
        from hos_scrcpy import HOSDevice
        assert hasattr(HOSDevice, "connect")
        assert hasattr(HOSDevice, "list_devices")
        assert hasattr(HOSDevice, "list_remote")
        assert callable(HOSDevice.connect)
        assert callable(HOSDevice.list_devices)
        assert callable(HOSDevice.list_remote)
