import json
import math
from typing import Any, Dict, List, Tuple

from loguru import logger

from app.engine.base import BaseDetectionPlugin, FrameData, TrackerContext, DetectionEvent
from config.config import config, sanitize_counting_line, redis_client
from app.engine.snapshots import save_event_snapshot, frame_for_snapshot

# All analytics geometry lives in the DeepStream mux space.
FRAME_W, FRAME_H = 1280, 720

# Minimum seconds between two counted crossings of the same line by the same
# track — suppresses double counts from tracker jitter right on the line.
CROSS_COOLDOWN_SEC = 1.0

# Per-track bookkeeping is pruned once it outgrows this many track ids.
MAX_TRACKED_IDS = 800
STALE_TRACK_SEC = 30.0

# Counts survive pipeline restarts/self-heals via Redis. Crossings persist
# immediately (human-rate); the unique-people total is throttled to this.
PERSIST_KEY_PREFIX = "counting:state:"
PERSIST_EVERY_SEC = 5.0

LINE_COLOR = [0, 240, 255]     # cyan counting line (matches legacy threshold style)
ARROW_COLOR = [16, 185, 129]   # emerald IN-direction indicator
LABEL_COLOR = [255, 255, 255]


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), hi)


def _parse_lines(raw: Any) -> List[Dict[str, Any]]:
    """
    Sanitizes the per-camera COUNTING_LINES config into usable line specs
    via the shared config.sanitize_counting_line normalizer (the API uses
    the same one strictly), silently skipping malformed entries so a bad
    config value can never take the pipeline down.
    """
    lines: List[Dict[str, Any]] = []
    if not isinstance(raw, (list, tuple)):
        return lines
    for idx, entry in enumerate(raw):
        norm = sanitize_counting_line(entry, idx)
        if norm is None:
            continue
        ax, ay = norm["start"]
        bx, by = norm["end"]
        lines.append({
            "id": norm["id"],
            "name": norm["name"],
            "a": (float(ax), float(ay)),
            "b": (float(bx), float(by)),
            # Geometry-scoped key: moving/redrawing a line resets its
            # side-tracking without touching accumulated counts.
            "key": f"{norm['id']}|{ax},{ay},{bx},{by}",
        })
    return lines


def _side_of_line(a: Tuple[float, float], b: Tuple[float, float], p: Tuple[float, float]) -> int:
    """Sign of the cross product (b-a) x (p-a): +1 is the IN side."""
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if cross > 0:
        return 1
    if cross < 0:
        return -1
    return 0


def _segments_intersect(p1, p2, a, b) -> bool:
    """True when the movement segment p1->p2 properly crosses segment a->b."""
    def orient(o, x, y):
        return (x[0] - o[0]) * (y[1] - o[1]) - (x[1] - o[1]) * (y[0] - o[0])

    d1 = orient(a, b, p1)
    d2 = orient(a, b, p2)
    d3 = orient(p1, p2, a)
    d4 = orient(p1, p2, b)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


class PeopleCountingPlugin(BaseDetectionPlugin):
    """
    Counts unique people and IN/OUT crossings over user-drawn counting lines.

    Lines come from config.COUNTING_LINES (per camera, 1280x720 mux space) and
    are re-read every frame, so lines drawn in the dashboard become active on
    the next frame — no pipeline, model, or tracker restart. A crossing counts
    as IN when the track ends on the right-hand side while walking the line
    from start to end; drawing the line the other way flips IN/OUT.
    """

    # Works purely off detection geometry.
    needs_frame = False
    # All state lives in TrackerContext, keyed by (plugin, camera).
    thread_safe = True

    def __init__(self, app_config=None):
        super().__init__(app_config)
        logger.info("Initialized PeopleCountingPlugin")

    @property
    def plugin_name(self) -> str:
        return "PeopleCountingPlugin"

    def get_required_classes(self) -> List[int]:
        return [0]

    def process_frame(self, frame_data: FrameData, tracker_context: TrackerContext) -> List[DetectionEvent]:
        camera_id = frame_data.camera_id
        timestamp = frame_data.timestamp
        events: List[DetectionEvent] = []

        state = tracker_context.get_state(self.plugin_name, camera_id)
        if "unique_ids" not in state:
            state["unique_ids"] = set()
            state["foot_prev"] = {}       # tid -> last foot point (cx, y2)
            state["last_seen"] = {}       # tid -> last timestamp
            state["line_sides"] = {}      # line key -> {tid: -1|1}
            state["line_cross_ts"] = {}   # line key -> {tid: last counted ts}
            # Totals are restored from Redis so a pipeline restart/self-heal
            # doesn't zero the day's counts.
            saved = self._load_persisted(camera_id)
            state["in_count"] = int(saved.get("in", 0))
            state["out_count"] = int(saved.get("out", 0))
            state["line_counts"] = {
                str(lid): {"in": int(lc.get("in", 0)), "out": int(lc.get("out", 0))}
                for lid, lc in (saved.get("line_counts") or {}).items()
                if isinstance(lc, dict)
            }
            # Tracker ids restart with the process; carry the old unique total
            # as a baseline and count fresh ids on top of it.
            state["unique_baseline"] = int(saved.get("unique_total", 0))
            state["last_persist"] = 0.0
            state["persisted_unique"] = state["unique_baseline"]

        lines = _parse_lines(config.get_counting_lines_for_camera(camera_id))

        # Drop side/cooldown tracking for lines that were removed or moved and
        # per-line counts for lines that no longer exist.
        active_keys = {ln["key"] for ln in lines}
        for stale_key in [k for k in state["line_sides"] if k not in active_keys]:
            state["line_sides"].pop(stale_key, None)
            state["line_cross_ts"].pop(stale_key, None)
        active_ids = {ln["id"] for ln in lines}
        for stale_id in [i for i in state["line_counts"] if i not in active_ids]:
            state["line_counts"].pop(stale_id, None)

        current_count = 0

        for det in frame_data.detections:
            if int(det.class_id) != 0:
                continue
            current_count += 1

            if det.track_id is None:
                continue
            tid = int(det.track_id)
            state["unique_ids"].add(tid)

            x1, y1, x2, y2 = det.bbox
            # Track the bottom-center of the bbox (feet position on the floor).
            foot = ((float(x1) + float(x2)) / 2.0, float(y2))
            prev_foot = state["foot_prev"].get(tid)

            for ln in lines:
                sides = state["line_sides"].setdefault(ln["key"], {})
                side = _side_of_line(ln["a"], ln["b"], foot)
                if side == 0:
                    continue  # exactly on the line — keep the previous side
                prev_side = sides.get(tid, 0)
                if prev_side == 0:
                    sides[tid] = side
                    continue
                if side == prev_side:
                    continue

                sides[tid] = side
                # Side flipped: only count it when the actual movement segment
                # crosses the drawn segment (walking around an endpoint is not
                # a crossing).
                if prev_foot is None or not _segments_intersect(prev_foot, foot, ln["a"], ln["b"]):
                    continue

                # Stamp the cooldown on EVERY intersecting flip, counted or
                # not: a track jittering across the line keeps refreshing the
                # stamp and counts exactly once, instead of re-counting each
                # time a full cooldown happens to elapse between flips
                # (which inflated in_count monotonically).
                cross_ts = state["line_cross_ts"].setdefault(ln["key"], {})
                suppressed = timestamp - cross_ts.get(tid, 0.0) < CROSS_COOLDOWN_SEC
                cross_ts[tid] = timestamp
                if suppressed:
                    continue

                direction = "IN" if side > 0 else "OUT"
                line_counts = state["line_counts"].setdefault(ln["id"], {"in": 0, "out": 0})
                if direction == "IN":
                    state["in_count"] += 1
                    line_counts["in"] += 1
                else:
                    state["out_count"] += 1
                    line_counts["out"] += 1
                self._persist_counts(state, camera_id, timestamp)

                events.append(DetectionEvent(
                    plugin_name=self.plugin_name,
                    event_type="LINE_CROSSED",
                    camera_id=camera_id,
                    timestamp=timestamp,
                    confidence=1.0,
                    metadata={
                        "track_id": tid,
                        "direction": direction,
                        "snapshot_file": save_event_snapshot(
                            "counting", camera_id,
                            frame_for_snapshot(frame_data, tracker_context, camera_id),
                            bbox=[x1, y1, x2, y2],
                        ),
                        "line_id": ln["id"],
                        "line_name": ln["name"],
                        "line_in": line_counts["in"],
                        "line_out": line_counts["out"],
                        "in_count": state["in_count"],
                        "out_count": state["out_count"],
                    }
                ))

            state["foot_prev"][tid] = foot
            state["last_seen"][tid] = timestamp

        self._prune_stale_tracks(state, timestamp)

        # Throttled persistence for the unique-people total (crossings above
        # persist immediately, this catches unique-count growth in between).
        unique_total = state["unique_baseline"] + len(state["unique_ids"])
        if (timestamp - state["last_persist"] >= PERSIST_EVERY_SEC
                and unique_total != state["persisted_unique"]):
            self._persist_counts(state, camera_id, timestamp)

        per_line = [
            {
                "id": ln["id"],
                "name": ln["name"],
                "in": state["line_counts"].get(ln["id"], {}).get("in", 0),
                "out": state["line_counts"].get(ln["id"], {}).get("out", 0),
            }
            for ln in lines
        ]

        # Always emit a PERSON_COUNT event for live footfall stats and so the
        # overlay renders the configured lines even with nobody in frame.
        events.append(DetectionEvent(
            plugin_name=self.plugin_name,
            event_type="PERSON_COUNT",
            camera_id=camera_id,
            timestamp=timestamp,
            confidence=1.0,
            metadata={
                "current_people_in_frame": current_count,
                "in_count": state["in_count"],
                "out_count": state["out_count"],
                "total_unique_people_seen": unique_total,
                "lines": per_line,
                "drawings": self._line_drawings(lines, state),
            }
        ))

        return events

    @staticmethod
    def _load_persisted(camera_id: str) -> Dict[str, Any]:
        try:
            raw = redis_client.get(f"{PERSIST_KEY_PREFIX}{camera_id}")
            if raw:
                saved = json.loads(raw)
                if isinstance(saved, dict):
                    return saved
        except Exception as exc:
            logger.warning(f"[{camera_id}] Could not restore counting state: {exc}")
        return {}

    @staticmethod
    def _persist_counts(state: Dict[str, Any], camera_id: str, now: float) -> None:
        # A Redis blip must never break the pipeline — best-effort only.
        unique_total = state["unique_baseline"] + len(state["unique_ids"])
        try:
            redis_client.set(f"{PERSIST_KEY_PREFIX}{camera_id}", json.dumps({
                "in": state["in_count"],
                "out": state["out_count"],
                "line_counts": state["line_counts"],
                "unique_total": unique_total,
                "ts": now,
            }))
            state["last_persist"] = now
            state["persisted_unique"] = unique_total
        except Exception:
            pass

    @staticmethod
    def _prune_stale_tracks(state: Dict[str, Any], now: float) -> None:
        if len(state["last_seen"]) <= MAX_TRACKED_IDS:
            return
        stale = [tid for tid, ts in state["last_seen"].items() if now - ts > STALE_TRACK_SEC]
        for tid in stale:
            state["last_seen"].pop(tid, None)
            state["foot_prev"].pop(tid, None)
            for sides in state["line_sides"].values():
                sides.pop(tid, None)
            for ts_map in state["line_cross_ts"].values():
                ts_map.pop(tid, None)

    @staticmethod
    def _line_drawings(lines: List[Dict[str, Any]], state: Dict[str, Any]) -> List[Dict[str, Any]]:
        drawings: List[Dict[str, Any]] = []
        for ln in lines:
            (ax, ay), (bx, by) = ln["a"], ln["b"]
            drawings.append({
                "type": "line",
                "coords": [[ax, ay], [bx, by]],
                "color": LINE_COLOR,
                "thickness": 2,
            })

            # IN-direction arrow from the midpoint: the normal (-dy, dx) points
            # to the cross>0 side, which is where a track ends after an IN.
            dx, dy = bx - ax, by - ay
            length = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / length, dx / length
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            tip_x, tip_y = mx + nx * 34, my + ny * 34
            drawings.append({
                "type": "line",
                "coords": [[mx, my], [tip_x, tip_y]],
                "color": ARROW_COLOR,
                "thickness": 2,
            })
            cos30, sin30 = math.cos(math.radians(30)), math.sin(math.radians(30))
            for s in (1.0, -1.0):
                hx = (-nx) * cos30 - (-ny) * sin30 * s
                hy = (-nx) * sin30 * s + (-ny) * cos30
                drawings.append({
                    "type": "line",
                    "coords": [[tip_x, tip_y], [tip_x + hx * 10, tip_y + hy * 10]],
                    "color": ARROW_COLOR,
                    "thickness": 2,
                })
            drawings.append({
                "type": "text",
                "coords": [
                    _clamp(tip_x + nx * 12 - 8, 4, FRAME_W - 30),
                    _clamp(tip_y + ny * 12 + 6, 18, FRAME_H - 4),
                ],
                "text": "IN",
                "color": ARROW_COLOR,
                "scale": 0.85,
            })

            line_counts = state["line_counts"].get(ln["id"], {"in": 0, "out": 0})
            drawings.append({
                "type": "text",
                "coords": [
                    _clamp(min(ax, bx) + 6, 4, FRAME_W - 220),
                    _clamp(min(ay, by) - 8, 18, FRAME_H - 6),
                ],
                "text": f"{ln['name']}  IN {line_counts['in']} | OUT {line_counts['out']}",
                "color": LABEL_COLOR,
                "scale": 0.9,
            })
        return drawings
