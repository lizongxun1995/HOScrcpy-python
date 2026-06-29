"""UiSelector — chainable widget finder, similar to Android's UiSelector.

Builds on JsonStructure with fluent query methods.

Usage:
    ui = UIHierarchy(device)
    root = ui.dump()

    # Chainable queries
    results = (UiSelector(root)
               .type("Button")
               .text_contains("OK")
               .all())

    # Direct shortcuts on selector
    btn = UiSelector(root).id("submit_btn").first()
"""

from hos_scrcpy.ui.hierarchy import JsonStructure


class UiSelector:
    """Fluent selector for UI hierarchy nodes.

    Build predicates by chaining methods, then call .first() / .all() / .count().
    """

    def __init__(self, root: JsonStructure):
        self._root = root
        self._predicates: list = []

    def _match(self, node: JsonStructure) -> bool:
        return all(p(node) for p in self._predicates)

    # ---- attribute filters ----

    def type(self, type_name: str) -> "UiSelector":
        self._predicates.append(lambda n: n.type == type_name)
        return self

    def type_contains(self, value: str) -> "UiSelector":
        self._predicates.append(lambda n: value.lower() in n.type.lower())
        return self

    def text(self, value: str) -> "UiSelector":
        self._predicates.append(lambda n: n.text == value)
        return self

    def text_contains(self, value: str) -> "UiSelector":
        self._predicates.append(lambda n: value.lower() in n.text.lower())
        return self

    def id(self, value: str) -> "UiSelector":
        self._predicates.append(lambda n: n.id == value)
        return self

    def id_contains(self, value: str) -> "UiSelector":
        self._predicates.append(lambda n: value.lower() in n.id.lower())
        return self

    def description(self, value: str) -> "UiSelector":
        self._predicates.append(lambda n: n.description == value)
        return self

    def description_contains(self, value: str) -> "UiSelector":
        self._predicates.append(lambda n: value.lower() in n.description.lower())
        return self

    def key(self, value: str) -> "UiSelector":
        self._predicates.append(lambda n: n.key == value)
        return self

    def clickable(self, value: bool = True) -> "UiSelector":
        self._predicates.append(lambda n: n.is_clickable == value)
        return self

    def scrollable(self, value: bool = True) -> "UiSelector":
        self._predicates.append(lambda n: n.is_scrollable == value)
        return self

    def enabled(self, value: bool = True) -> "UiSelector":
        self._predicates.append(lambda n: n.is_enabled == value)
        return self

    def focused(self, value: bool = True) -> "UiSelector":
        self._predicates.append(lambda n: n.is_focused == value)
        return self

    def path(self, value: str) -> "UiSelector":
        """Exact path match (xpath-like)."""
        self._predicates.append(lambda n: n.path == value)
        return self

    def path_contains(self, value: str) -> "UiSelector":
        self._predicates.append(lambda n: value.lower() in n.path.lower())
        return self

    # ---- coordinate filter ----

    def at_point(self, x: int, y: int) -> "UiSelector":
        """Find the smallest widget containing point (x, y)."""
        def _contains_point(node: JsonStructure) -> bool:
            rx, ry, rw, rh = node.rectangle
            return rx <= x <= rx + rw and ry <= y <= ry + rh
        self._predicates.append(_contains_point)
        return self

    # ---- xpath ----

    def xpath(self, expr: str) -> "UiSelector":
        """Set the root to xpath search results for further chaining.

        Usage:
            (UiSelector(root)
             .xpath("//Button[@clickable=true]")
             .text_contains("OK")
             .first())
        """
        from hos_scrcpy.ui.xpath import find_by_xpath
        matches = find_by_xpath(self._root, expr)
        if not matches:
            self._predicates.append(lambda _n: False)
        else:
            match_ids = {id(m) for m in matches}
            self._predicates.append(lambda n: id(n) in match_ids)
        return self

    # ---- custom filter ----

    def where(self, predicate) -> "UiSelector":
        """Add a custom predicate function.

        Args:
            predicate: Callable(JsonStructure) -> bool
        """
        self._predicates.append(predicate)
        return self

    # ---- result methods ----

    def first(self) -> JsonStructure | None:
        """Return the first matching node, or None."""
        return self._root.find_first(self._match)

    def all(self) -> list[JsonStructure]:
        """Return all matching nodes."""
        return self._root.find_all(self._match)

    def count(self) -> int:
        """Return the count of matching nodes."""
        return len(self.all())

    def exists(self) -> bool:
        """Check if any node matches."""
        return self.first() is not None


class UIHierarchy:
    """Dump and query the device UI hierarchy.

    Wraps Device.dump_layout() with a parsed JsonStructure tree
    and provides find_* convenience methods.

    Usage:
        ui = UIHierarchy(device)
        root = ui.dump()

        buttons = ui.find_by_type("Button")
        login_btn = ui.find_by_id("login_button")
        target = ui.find_at_point(500, 300)
    """

    def __init__(self, device):
        self._device = device
        self._root: JsonStructure | None = None
        self._raw_json: str | None = None

    def dump(self) -> JsonStructure | None:
        """Dump current UI layout from device and return the root node."""
        import json
        self._raw_json = self._device.dump_layout()
        if not self._raw_json:
            return None
        data = json.loads(self._raw_json)
        self._root = JsonStructure(data)
        # If the root has no type, give it one
        if not self._root.type:
            self._root.attributes["type"] = "Root"
        # Compute paths for all nodes
        self._compute_paths(self._root, "")
        return self._root

    def _compute_paths(self, node: JsonStructure, parent_path: str):
        """Build xpath-like paths for the tree."""
        node.attributes["path"] = parent_path + "/" + node.type
        # Count same-type siblings for indexing
        counts: dict[str, int] = {}
        for child in node.children:
            t = child.type
            if t not in counts:
                counts[t] = 0
            else:
                counts[t] += 1
            child_path = f"{parent_path}/{t}[{counts[t]}]"
            child.attributes["path"] = child_path
            self._compute_paths(child, node.attributes["path"])

    @property
    def root(self) -> JsonStructure | None:
        return self._root

    @property
    def raw_json(self) -> str | None:
        return self._raw_json

    def selector(self) -> UiSelector:
        """Create a UiSelector for chainable queries.

        Raises RuntimeError if dump() hasn't been called yet.
        """
        if self._root is None:
            raise RuntimeError("Call dump() before creating a selector")
        return UiSelector(self._root)

    # ---- direct lookups ----

    def find_by_id(self, id: str) -> list[JsonStructure]:
        if self._root is None:
            return []
        return self._root.find_all(lambda n: n.id == id)

    def find_by_text(self, text: str) -> list[JsonStructure]:
        if self._root is None:
            return []
        return self._root.find_all(lambda n: n.text == text)

    def find_by_type(self, type_name: str) -> list[JsonStructure]:
        if self._root is None:
            return []
        return self._root.find_all(lambda n: n.type == type_name)

    def find_by_path(self, path: str) -> JsonStructure | None:
        if self._root is None:
            return None
        return self._root.find_first(lambda n: n.path == path)

    def find_at_point(self, x: int, y: int) -> JsonStructure | None:
        """Find the smallest widget containing (x, y).

        Mirrors TreeUtil.findMinRangeTreeNode.
        """
        if self._root is None:
            return None

        def _contains(n: JsonStructure) -> bool:
            rx, ry, rw, rh = n.rectangle
            return rx <= x <= rx + rw and ry <= y <= ry + rh

        candidates = self._root.find_all(_contains)
        if not candidates:
            return None

        # Pick the smallest by area
        candidates.sort(key=lambda n: n.rectangle[2] * n.rectangle[3])
        return candidates[0]
