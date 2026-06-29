def parse_bounds(bounds_str: str) -> tuple[int, int, int, int]:
    """Parse bounds string like '[x1,y1][x2,y2]' to (x, y, width, height)."""
    if not bounds_str:
        return (0, 0, 0, 0)
    try:
        bounds_str = bounds_str.replace("][", " ").replace("[", "").replace("]", "")
        parts = bounds_str.split(" ")
        if len(parts) < 2:
            return (0, 0, 0, 0)
        start_x, start_y = map(int, parts[0].split(","))
        end_x, end_y = map(int, parts[1].split(","))
        return (start_x, start_y, end_x - start_x, end_y - start_y)
    except (ValueError, IndexError):
        return (0, 0, 0, 0)


def bounds_to_rectangle(bounds_str: str) -> dict:
    """Convert bounds string to a rectangle dict with x, y, width, height."""
    x, y, w, h = parse_bounds(bounds_str)
    return {"x": x, "y": y, "width": w, "height": h}
