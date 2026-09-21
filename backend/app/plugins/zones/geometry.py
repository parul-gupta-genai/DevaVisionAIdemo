"""
Polygon geometry for restricted zones.

Deliberately dependency-free: no cv2, no shapely. The two plugins that use
this run inside the DeepStream process on the analytics thread, and the same
functions have to be callable from the API validator and from a plain test
run. Ray casting over a four-to-eight point polygon is a handful of
multiplications, so the heavyweight libraries bought nothing but an import.

All coordinates are in the DeepStream mux space (1280x720), the same space
counting lines and parking bays already use, so a zone drawn in the UI lands
exactly where the plugin tests it regardless of the camera's native
resolution.
"""

from typing import List, Optional, Sequence, Tuple

# Mirrors config.config.MUX_W/MUX_H. Duplicated rather than imported so this
# module stays importable without pulling in settings resolution; a test
# asserts the two never drift.
MUX_W, MUX_H = 1280, 720

# A zone smaller than this is almost always a mis-click rather than an
# intent — roughly a 22x22 box in mux space.
MIN_ZONE_AREA = 500.0
MIN_ZONE_POINTS = 3
MAX_ZONE_POINTS = 24

# Where on a detection box containment is tested.
ANCHORS = ("FEET", "CENTER", "HEAD", "BOX")
DEFAULT_ANCHOR = "FEET"


def clamp_point(x: float, y: float) -> Tuple[float, float]:
    return (min(max(float(x), 0.0), float(MUX_W)),
            min(max(float(y), 0.0), float(MUX_H)))


def polygon_area(points: Sequence[Sequence[float]]) -> float:
    """Unsigned shoelace area. Zero for collinear points."""
    n = len(points)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = points[i][0], points[i][1]
        x2, y2 = points[(i + 1) % n][0], points[(i + 1) % n][1]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def sanitize_polygon(points, min_area: float = MIN_ZONE_AREA) -> Optional[List[List[int]]]:
    """
    Normalizes a drawn polygon to clamped integer mux-space points, or returns
    None when it is unusable.

    Single source of truth shared by the API validator (strict: None -> HTTP
    422) and the zone registry (lenient: None -> skip the zone), so the two
    can never disagree about which polygons are real. Accepts lists of pairs
    and lists of {"x":..,"y":..} dicts, which is what the drawing canvas and
    the legacy RESTRICTED_ZONES config produce respectively.
    """
    if not isinstance(points, (list, tuple)) or not (
            MIN_ZONE_POINTS <= len(points) <= MAX_ZONE_POINTS):
        return None
    out: List[List[int]] = []
    for raw in points:
        try:
            if isinstance(raw, dict):
                x, y = raw["x"], raw["y"]
            else:
                x, y = raw[0], raw[1]
            if isinstance(x, bool) or isinstance(y, bool):
                return None
            cx, cy = clamp_point(x, y)
        except (TypeError, ValueError, KeyError, IndexError):
            return None
        pt = [int(round(cx)), int(round(cy))]
        # Drop a repeat of the previous point (drag jitter) and a closing
        # point that repeats the first — both are common from canvas input
        # and both make the shoelace area misleading.
        if out and out[-1] == pt:
            continue
        out.append(pt)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    if len(out) < MIN_ZONE_POINTS or polygon_area(out) < min_area:
        return None
    return out


def polygon_bounds(points: Sequence[Sequence[float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def point_in_polygon(x: float, y: float, points: Sequence[Sequence[float]]) -> bool:
    """
    Ray casting, with points exactly on an edge counted as inside.

    The boundary case is not pedantry here: a zone drawn along a wall puts the
    feet point of anyone walking beside that wall exactly on the edge for
    frames at a time, and a strict test makes the alert flicker.
    """
    n = len(points)
    if n < 3:
        return False
    if _on_boundary(x, y, points):
        return True
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = points[i][0], points[i][1]
        xj, yj = points[j][0], points[j][1]
        if (yi > y) != (yj > y):
            # x of the edge at height y; no division by zero because the
            # inequality above guarantees yj != yi.
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


def _on_boundary(x: float, y: float, points: Sequence[Sequence[float]],
                 eps: float = 1e-9) -> bool:
    n = len(points)
    for i in range(n):
        ax, ay = points[i][0], points[i][1]
        bx, by = points[(i + 1) % n][0], points[(i + 1) % n][1]
        cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
        if abs(cross) > eps:
            continue
        if (min(ax, bx) - eps <= x <= max(ax, bx) + eps
                and min(ay, by) - eps <= y <= max(ay, by) + eps):
            return True
    return False


def _segments_intersect(p1, p2, p3, p4) -> bool:
    def orient(a, b, c):
        v = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
        return 0 if v == 0 else (1 if v > 0 else 2)

    def on_seg(a, b, c):
        return (min(a[0], c[0]) <= b[0] <= max(a[0], c[0])
                and min(a[1], c[1]) <= b[1] <= max(a[1], c[1]))

    o1, o2 = orient(p1, p2, p3), orient(p1, p2, p4)
    o3, o4 = orient(p3, p4, p1), orient(p3, p4, p2)
    if o1 != o2 and o3 != o4:
        return True
    return ((o1 == 0 and on_seg(p1, p3, p2)) or (o2 == 0 and on_seg(p1, p4, p2))
            or (o3 == 0 and on_seg(p3, p1, p4)) or (o4 == 0 and on_seg(p3, p2, p4)))


def bbox_overlaps_polygon(bbox: Sequence[float],
                          points: Sequence[Sequence[float]]) -> bool:
    """
    True when any part of the box overlaps the zone.

    Corner-in-polygon plus vertex-in-box alone is not enough: a wide zone band
    crossing a tall person box has no corner or vertex inside the other, and
    that is exactly the "walked through the doorway" case, so edges are tested
    too.
    """
    x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    minx, miny, maxx, maxy = polygon_bounds(points)
    if x2 < minx or x1 > maxx or y2 < miny or y1 > maxy:
        return False
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    for cx, cy in corners:
        if point_in_polygon(cx, cy, points):
            return True
    for px, py in points:
        if x1 <= px <= x2 and y1 <= py <= y2:
            return True
    n = len(points)
    for i in range(n):
        a = (points[i][0], points[i][1])
        b = (points[(i + 1) % n][0], points[(i + 1) % n][1])
        for k in range(4):
            if _segments_intersect(a, b, corners[k], corners[(k + 1) % 4]):
                return True
    return False


def anchor_point(bbox: Sequence[float], anchor: str = DEFAULT_ANCHOR) -> Tuple[float, float]:
    """
    The single point used for containment.

    FEET (bottom centre) is the default because a person standing just outside
    a zone still has head and shoulders leaning over it in a ceiling-mounted
    view; where they are standing is what "inside the zone" means.
    """
    x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    cx = (x1 + x2) / 2.0
    a = (anchor or DEFAULT_ANCHOR).upper()
    if a == "CENTER":
        return cx, (y1 + y2) / 2.0
    if a == "HEAD":
        return cx, y1
    return cx, y2


def detection_in_zone(bbox: Sequence[float], points: Sequence[Sequence[float]],
                      anchor: str = DEFAULT_ANCHOR) -> bool:
    """Containment under the zone's configured anchor rule."""
    if not points or len(points) < MIN_ZONE_POINTS:
        return False
    if (anchor or "").upper() == "BOX":
        return bbox_overlaps_polygon(bbox, points)
    ax, ay = anchor_point(bbox, anchor)
    minx, miny, maxx, maxy = polygon_bounds(points)
    if ax < minx or ax > maxx or ay < miny or ay > maxy:
        return False        # cheap reject before the ray cast
    return point_in_polygon(ax, ay, points)


def box_height(bbox: Sequence[float]) -> float:
    return abs(float(bbox[3]) - float(bbox[1]))
