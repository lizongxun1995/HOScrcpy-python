"""uiautomator2-style convenience finder for HOScrcpy.

Usage:
    dev.dump_ui()                         # Refresh and return UI tree
    dev.click_by_text("Settings")         # Click element by text
    dev.click_by_id("submit_btn")         # Click element by ID
    dev.click_by_xpath("//Button[0]")     # Click by xpath
    dev.exists_text("OK")                 # Check if text exists
    dev.wait_id("submit_btn", timeout=5)  # Wait for element to appear
    info = dev.get_info_by_id("btn")      # Get element info dict

Design: each call auto-dumps the UI tree if not already dumped.
For wait_* methods, retries dump until timeout.
"""

import time
from hos_scrcpy.ui.hierarchy import JsonStructure
from hos_scrcpy.utils.logger import logger

TAG = "UIFinder"


class UIFinder:
    """Convenience wrapper for uiautomator2-style element finding on a device.

    Attached to HOSDevice via dev.finder or accessed through HOSDevice
    convenience methods.
    """

    def __init__(self, device, touch_controller=None):
        import hos_scrcpy.core.device as _d
        if isinstance(device, _d.Device):
            self._device = device
        else:
            self._device = device.device
        self._touch = touch_controller
        self._root: JsonStructure | None = None

    # ---- dump ----

    def dump(self) -> JsonStructure | None:
        """Dump and cache the current UI tree. Returns root node."""
        from hos_scrcpy.ui.selector import UIHierarchy
        ui = UIHierarchy(self._device)
        self._root = ui.dump()
        return self._root

    def _ensure_root(self) -> JsonStructure | None:
        """Ensure UI tree is loaded. Returns root or None."""
        if self._root is None:
            self.dump()
        return self._root

    # ---- find core ----

    def find(self, type: str = None, text: str = None, id: str = None,
             description: str = None, xpath: str = None,
             clickable: bool = None, scrollable: bool = None,
             enabled: bool = None, focused: bool = None,
             ) -> list[JsonStructure]:
        """Find elements matching criteria. Returns list (may be empty).

        Args:
            type: Component type (e.g. "Button", "Text", "*").
            text: Full text match.
            id: Full ID match (resource-id equivalent).
            description: Full description/content-desc match.
            xpath: XPath expression (overrides other filters if set).
            clickable: Filter by clickable state.
            scrollable: Filter by scrollable state.
            enabled: Filter by enabled state.
            focused: Filter by focused state.
        """
        if xpath:
            from hos_scrcpy.ui.xpath import find_by_xpath
            root = self._ensure_root()
            if root is None:
                return []
            results = find_by_xpath(root, xpath)
        else:
            from hos_scrcpy.ui.selector import UiSelector
            root = self._ensure_root()
            if root is None:
                return []
            sel = UiSelector(root)
            if type and type != "*":
                sel.type(type)
            if text is not None:
                sel.text(text)
            if id is not None:
                sel.id(id)
            if description is not None:
                sel.description(description)
            if clickable is not None:
                sel.clickable(clickable)
            if scrollable is not None:
                sel.scrollable(scrollable)
            if enabled is not None:
                sel.enabled(enabled)
            if focused is not None:
                sel.focused(focused)
            results = sel.all()

        return results

    def find_first(self, **kwargs) -> JsonStructure | None:
        """Find first matching element. Same kwargs as find()."""
        results = self.find(**kwargs)
        return results[0] if results else None

    # ---- click ----

    def click_by_text(self, text: str) -> bool:
        """Click the element with the given text. Returns True if clicked."""
        node = self.find_first(text=text)
        if node:
            self._click_node(node)
            return True
        logger.debug(f"{TAG}: text '{text}' not found")
        return False

    def click_by_id(self, id: str) -> bool:
        """Click the element with the given ID. Returns True if clicked."""
        node = self.find_first(id=id)
        if node:
            self._click_node(node)
            return True
        logger.debug(f"{TAG}: id '{id}' not found")
        return False

    def click_by_xpath(self, xpath: str) -> bool:
        """Click the first element matching the xpath. Returns True if clicked."""
        node = self.find_first(xpath=xpath)
        if node:
            self._click_node(node)
            return True
        logger.debug(f"{TAG}: xpath '{xpath}' not found")
        return False

    def click_by_description(self, description: str) -> bool:
        """Click the element with the given description. Returns True if clicked."""
        node = self.find_first(description=description)
        if node:
            self._click_node(node)
            return True
        logger.debug(f"{TAG}: description '{description}' not found")
        return False

    def _click_node(self, node: JsonStructure):
        """Click the center of a node."""
        cx, cy = node.center
        logger.debug(f"{TAG}: click {node.type} '{node.text}' center=({cx},{cy})")
        if self._touch:
            self._touch.click(cx, cy)
        else:
            from hos_scrcpy.input.touch import TouchController
            TouchController(self._device).click(cx, cy)

    # ---- exists ----

    def exists_text(self, text: str) -> bool:
        """Check if any element has the given text."""
        return self.find_first(text=text) is not None

    def exists_id(self, id: str) -> bool:
        """Check if any element has the given ID."""
        return self.find_first(id=id) is not None

    def exists_xpath(self, xpath: str) -> bool:
        """Check if the xpath returns any elements."""
        return len(self.find(xpath=xpath)) > 0

    def exists_description(self, description: str) -> bool:
        """Check if any element has the given description."""
        return self.find_first(description=description) is not None

    # ---- wait ----

    def wait_text(self, text: str, timeout: float = 5.0) -> JsonStructure | None:
        """Wait for an element with the given text to appear.

        Retries dump_layout every 500ms until found or timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.dump()
            node = self.find_first(text=text)
            if node:
                return node
            time.sleep(0.5)
        logger.debug(f"{TAG}: wait_text '{text}' timed out after {timeout}s")
        return None

    def wait_id(self, id: str, timeout: float = 5.0) -> JsonStructure | None:
        """Wait for an element with the given ID to appear."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.dump()
            node = self.find_first(id=id)
            if node:
                return node
            time.sleep(0.5)
        logger.debug(f"{TAG}: wait_id '{id}' timed out after {timeout}s")
        return None

    def wait_xpath(self, xpath: str, timeout: float = 5.0) -> JsonStructure | None:
        """Wait for an element matching the xpath to appear."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.dump()
            nodes = self.find(xpath=xpath)
            if nodes:
                return nodes[0]
            time.sleep(0.5)
        logger.debug(f"{TAG}: wait_xpath '{xpath}' timed out after {timeout}s")
        return None

    # ---- get info ----

    def get_text_by_id(self, id: str) -> str | None:
        """Get the text of an element by its ID."""
        node = self.find_first(id=id)
        return node.text if node else None

    def get_text_by_xpath(self, xpath: str) -> str | None:
        """Get the text of an element by xpath."""
        node = self.find_first(xpath=xpath)
        return node.text if node else None

    def get_bounds_by_id(self, id: str) -> tuple[int, int, int, int] | None:
        """Get (x, y, w, h) bounds of an element by ID."""
        node = self.find_first(id=id)
        return node.rectangle if node else None

    def get_center_by_id(self, id: str) -> tuple[int, int] | None:
        """Get (cx, cy) center of an element by ID."""
        node = self.find_first(id=id)
        return node.center if node else None

    def get_bounds_by_text(self, text: str) -> tuple[int, int, int, int] | None:
        """Get (x, y, w, h) bounds of an element by text."""
        node = self.find_first(text=text)
        return node.rectangle if node else None

    def get_center_by_text(self, text: str) -> tuple[int, int] | None:
        """Get (cx, cy) center of an element by text."""
        node = self.find_first(text=text)
        return node.center if node else None

    def get_info_by_id(self, id: str) -> dict | None:
        """Get full info dict for an element by ID."""
        node = self.find_first(id=id)
        return self._node_to_dict(node)

    def get_info_by_text(self, text: str) -> dict | None:
        """Get full info dict for an element by text."""
        node = self.find_first(text=text)
        return self._node_to_dict(node)

    def get_info_by_xpath(self, xpath: str) -> dict | None:
        """Get full info dict for an element by xpath."""
        node = self.find_first(xpath=xpath)
        return self._node_to_dict(node)

    @staticmethod
    def _node_to_dict(node: JsonStructure) -> dict | None:
        if node is None:
            return None
        return {
            "type": node.type,
            "text": node.text,
            "id": node.id,
            "key": node.key,
            "description": node.description,
            "hint": node.hint,
            "bounds": node.rectangle,
            "center": node.center,
            "clickable": node.is_clickable,
            "scrollable": node.is_scrollable,
            "enabled": node.is_enabled,
            "focused": node.is_focused,
            "visible": node.is_visible,
            "long_clickable": node.is_long_clickable,
            "selected": node.is_selected,
            "bundle": node.bundle_name,
            "hierarchy": node.hierarchy_path,
            "z_index": node.z_index,
        }

    # ---- count ----

    def count(self, **kwargs) -> int:
        """Count elements matching criteria. Same kwargs as find()."""
        return len(self.find(**kwargs))

    def count_text(self, text: str) -> int:
        return self.count(text=text)

    def count_id(self, id: str) -> int:
        return self.count(id=id)
