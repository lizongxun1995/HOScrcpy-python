"""JsonStructure — UI tree node parsed from 'uitest dumpLayout' output.

Mirrors the Java JsonStructure entity with Pythonic accessors.
"""

from hos_scrcpy.utils.bounds import parse_bounds, bounds_to_rectangle


class JsonStructure:
    """A node in the UI hierarchy tree.

    Each node represents a UI widget with attributes like type, text, bounds, etc.
    The tree is parsed from the JSON output of 'uitest dumpLayout'.
    """

    def __init__(self, data: dict = None):
        data = data or {}
        self.attributes: dict = data.get("attributes", {}) if "attributes" in data else {}
        raw_children = data.get("children", [])
        self.children: list["JsonStructure"] = [
            JsonStructure(c) for c in raw_children
        ]
        self.index: int = data.get("index", 0)

    # ---- computed properties ----

    @property
    def type(self) -> str:
        return self.attributes.get("type", "")

    @property
    def text(self) -> str:
        return self.attributes.get("text", "")

    @property
    def description(self) -> str:
        return self.attributes.get("description", "")

    @property
    def raw_bounds(self) -> str:
        """Original bounds string, preferring origBounds over bounds."""
        return self.attributes.get("origBounds") or self.attributes.get("bounds", "")

    @property
    def rectangle(self) -> tuple[int, int, int, int]:
        """Bounds as (x, y, width, height)."""
        return parse_bounds(self.raw_bounds)

    @property
    def center(self) -> tuple[int, int]:
        """Center point of the widget bounds."""
        x, y, w, h = self.rectangle
        return (x + w // 2, y + h // 2)

    @property
    def bounds_dict(self) -> dict:
        """Bounds as dict with x, y, width, height."""
        return bounds_to_rectangle(self.raw_bounds)

    @property
    def id(self) -> str:
        return self.attributes.get("id", "")

    @property
    def key(self) -> str:
        return self.attributes.get("key", "")

    @property
    def path(self) -> str:
        return self.attributes.get("path", "")

    @staticmethod
    def _to_bool(value, default: bool = False) -> bool:
        """Normalize attribute values to bool: True/true/1/yes → True."""
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes")

    @property
    def is_clickable(self) -> bool:
        return self._to_bool(self.attributes.get("clickable", False))

    @property
    def is_scrollable(self) -> bool:
        return self._to_bool(self.attributes.get("scrollable", False))

    @property
    def is_focused(self) -> bool:
        return self._to_bool(self.attributes.get("focused", False))

    @property
    def is_enabled(self) -> bool:
        return self._to_bool(self.attributes.get("enabled", True), default=True)

    @property
    def is_visible(self) -> bool:
        return self._to_bool(self.attributes.get("visible", True), default=True)

    @property
    def is_selected(self) -> bool:
        return self._to_bool(self.attributes.get("selected", False))

    @property
    def is_long_clickable(self) -> bool:
        return self._to_bool(self.attributes.get("longClickable", False))

    @property
    def bundle_name(self) -> str:
        return self.attributes.get("bundleName", "")

    @property
    def ability_name(self) -> str:
        return self.attributes.get("abilityName", "")

    @property
    def hint(self) -> str:
        return self.attributes.get("hint", "")

    @property
    def z_index(self) -> str:
        return self.attributes.get("zIndex", "")

    @property
    def hierarchy_path(self) -> str:
        """Hierarchy index path like 'ROOT10,0,1,2' — HarmonyOS xpath equivalent."""
        return self.attributes.get("hierarchy", "")

    @property
    def hashcode(self) -> str:
        return self.attributes.get("hashcode", "")

    # ---- tree navigation ----

    def iter_all(self) -> "JsonStructure":
        """Iterate all descendant nodes (depth-first, including self)."""
        yield self
        for child in self.children:
            yield from child.iter_all()

    def iter_children(self) -> "JsonStructure":
        """Iterate direct children."""
        yield from self.children

    def iter_descendants(self) -> "JsonStructure":
        """Iterate all descendants (excluding self)."""
        for child in self.children:
            yield child
            yield from child.iter_descendants()

    def find_first(self, predicate) -> "JsonStructure | None":
        """Find the first node (depth-first) matching predicate."""
        for node in self.iter_all():
            if predicate(node):
                return node
        return None

    def find_all(self, predicate) -> list["JsonStructure"]:
        """Find all nodes matching predicate."""
        return [node for node in self.iter_all() if predicate(node)]

    @property
    def child_count(self) -> int:
        return len(self.children)

    # ---- serialization ----

    def to_dict(self) -> dict:
        """Convert back to a plain dict for JSON serialization."""
        return {
            "attributes": dict(self.attributes),
            "children": [c.to_dict() for c in self.children],
            "index": self.index,
        }

    def __repr__(self) -> str:
        info = f"type={self.type}"
        if self.text:
            info += f" text='{self.text}'"
        if self.id:
            info += f" id='{self.id}'"
        return f"JsonStructure({info})"

    def __str__(self) -> str:
        return self.type or "Root"
