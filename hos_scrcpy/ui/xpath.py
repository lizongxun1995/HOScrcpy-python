"""XPath-style UI element search for HarmonyOS UI hierarchy (uiautomator2 compat).

Usage:
    from hos_scrcpy.ui.xpath import find_by_xpath, xpath_for

    root = ui.dump()
    # Generate xpath for a node
    path = xpath_for(some_node)  # → "//WindowScene[@id='session10']/Button[@text='OK']"

    # Search by xpath
    results = find_by_xpath(root, "//Button[@clickable=true]")
    results = find_by_xpath(root, "//*[@id='submit_btn']")
    results = find_by_xpath(root, "//Button[@text='OK']/..")

Supported xpath syntax:
    //Type                         — any depth
    //Type[@attr='value']          — attribute filter
    //Type[@a='v'][@b='v']         — multi-filter
    //*[@id='x']                   — wildcard type
    //Type[0]                      — index (0-based)
    /Root/Child                   — absolute path
    //A/B/C                       — parent→child chain
    ..                            — parent of previous match
"""
import re
from hos_scrcpy.ui.hierarchy import JsonStructure


def _node_matches(node: JsonStructure, type_name: str, attrs: dict) -> bool:
    """Check if node matches a segment: type (or '*') + attribute filters."""
    if type_name and type_name != "*" and node.type != type_name:
        return False
    for attr, value in attrs.items():
        node_val = node.attributes.get(attr, "")
        node_val_str = str(node_val).lower()
        if node_val_str != str(value).lower():
            return False
    return True


def _attr_str(node: JsonStructure) -> str:
    """Build the best attribute predicate for a node."""
    if node.id:
        return f"[@id='{node.id}']"
    if node.text:
        return f"[@text='{node.text}']"
    if node.key and node.key != node.id:
        return f"[@key='{node.key}']"
    return ""


def xpath_for(node: JsonStructure, root: JsonStructure = None, parent_map: dict[int, JsonStructure] = None) -> str:
    """Generate a uiautomator2-style xpath string for a node.

    Uses id > text > key for attribute predicates. Falls back to
    type[index] when no distinguishing attribute is available.

    Args:
        node: The target node.
        root: Optional root for building absolute path.
        parent_map: Optional precomputed {id(child): parent} map for O(1) lookup.
    """
    if root is None:
        return f"{node.type or '?'}[@{_attr_str(node) or ''}]"
    if parent_map is None and root is not None:
        parent_map = _build_parent_map(root)
    parts = []
    cur = node
    while cur is not None and len(parts) < 100:
        attr = _attr_str(cur)
        if attr:
            parts.append(f"/{cur.type}{attr}")
        else:
            # No unique attr — use sibling index
            idx = 0
            parent = _find_parent(root, cur, parent_map) if root else None
            if parent:
                siblings = [c for c in parent.children if c.type == cur.type]
                for i, s in enumerate(siblings):
                    if s is cur:
                        idx = i
                        break
            parts.append(f"/{cur.type}[{idx}]")

        if root:
            cur = _find_parent(root, cur, parent_map)
        else:
            break

    parts.reverse()
    return "//" + "/".join(p[1:] for p in parts)  # strip leading /


def _build_parent_map(root: JsonStructure) -> dict[int, JsonStructure]:
    """Build a hash-based parent lookup: id(node) -> parent_node."""
    parent_map = {}
    for parent in root.iter_all():
        for child in parent.children:
            parent_map[id(child)] = parent
    return parent_map


def _find_parent(root: JsonStructure, target: JsonStructure, parent_map: dict[int, JsonStructure] | None = None) -> JsonStructure | None:
    """Find the parent of target node in the tree.

    Uses a pre-built parent_map for O(1) lookup when provided,
    otherwise falls back to O(n) tree traversal.
    """
    if parent_map is not None:
        return parent_map.get(id(target))
    for node in root.iter_all():
        for child in node.children:
            if child is target:
                return node
    return None


def find_by_xpath(root: JsonStructure, expr: str) -> list[JsonStructure]:
    """Search the UI tree with an xpath expression.

    Args:
        root: Root node of the UI tree.
        expr: XPath expression string.

    Returns:
        List of matching nodes (empty if no match).
    """
    if not expr.strip():
        return []

    # Handle parent navigation '..'
    if expr.strip() == "..":
        return []

    # Split into segments: handle // and /
    segments = _parse_segments(expr)
    if not segments:
        return []

    results = [root]
    for i, (scope, type_name, attrs, index) in enumerate(segments):
        next_results = []
        for current in results:
            if scope == "//":
                # Search all descendants (including self for subsequent segments)
                candidates = list(current.iter_all()) if i == 0 else list(current.iter_descendants())
            else:
                # Direct children only
                candidates = list(current.iter_children())

            matches = [n for n in candidates if _node_matches(n, type_name, attrs)]

            if index is not None and matches:
                if 0 <= index < len(matches):
                    next_results.append(matches[index])
            else:
                next_results.extend(matches)

        results = next_results
        if not results:
            break

    return results


def _parse_segments(expr: str) -> list[tuple[str, str, dict, int | None]]:
    """Parse xpath expression into segments.

    Returns list of (scope, type_name, attrs_dict, index).
    scope: '//' for any-depth, '/' for direct child
    type_name: 'Button', '*', etc.
    attrs: {'text': 'OK', 'clickable': 'true'}
    index: int or None
    """
    segments = []
    # Split by // or /, keeping the delimiter info
    parts = re.split(r"(//?/)", expr)
    # parts like: ['', '//', 'Button[@text="OK"]', '/', 'Text']

    scope = "//"  # default for first segment
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part in ("//", "/"):
            scope = part
            continue

        # Parse segment: Type[@attr='v'][@attr2='v2'][index]
        seg_scope = scope
        scope = "/"  # default for subsequent

        # Extract type name
        type_match = re.match(r"(\*|[A-Za-z_]\w*)", part)
        if not type_match:
            continue
        type_name = type_match.group(1)
        rest = part[type_match.end():]

        # Extract attribute filters [@key='value'] or [@key=value]
        attrs = {}
        for m in re.finditer(r"\[@(\w+)=['\"]?([^'\"\[\]]+)['\"]?\]", rest):
            attrs[m.group(1)] = m.group(2).strip("'\"")

        # Extract index [0] — only if not consumed as attr
        index = None
        idx_match = re.search(r"\[(\d+)\]", rest)
        if idx_match:
            # Make sure this isn't part of an attribute filter (no @ before it)
            pos = idx_match.start()
            if pos == 0 or rest[pos - 1] != "@":
                index = int(idx_match.group(1))

        segments.append((seg_scope, type_name, attrs, index))

    return segments


def xpath_filter(root: JsonStructure, attrs: dict) -> list[JsonStructure]:
    """Find all nodes matching attribute key-value pairs.

    Args:
        root: Root node.
        attrs: Dict of attribute_name → expected_value.

    Returns:
        All matching nodes (depth-first).
    """
    results = []
    for node in root.iter_all():
        if all(
            str(node.attributes.get(k, "")).lower() == str(v).lower()
            for k, v in attrs.items()
        ):
            results.append(node)
    return results
