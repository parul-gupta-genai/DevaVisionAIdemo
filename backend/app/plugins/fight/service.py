"""
SOW 2.7 — turning frames of agitation into a reportable incident.

Confirmation exists for the same reason it does in fire detection: one frame
that looks like a fight is two people who happened to move sharply at the
same moment. Evidence must persist for both a configured time AND a
configured number of frames inside one window; either alone is satisfied by a
burst, or by two frames minutes apart.

The windows here are deliberately shorter than fire's. A quarrel that has to
persist for ten seconds before anyone is told is a quarrel nobody can
intervene in, and intervention is the entire point.

Incidents also have to END, or the dashboard holds a permanent red banner and
the next real incident on that camera is invisible inside the last one.

This is an automated visual analytics aid. Every incident carries
ADVISORY_NOTICE: detection is indicative only and does not replace human
security intervention or verification.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from app.plugins.fight import dynamics, rules
from app.plugins.fight.dynamics import ADVISORY_NOTICE  # noqa: F401
from app.plugins.zones.geometry import point_in_polygon, sanitize_polygon

FIGHT_DETECTED = "FIGHT_DETECTED"
FIGHT_CLEARED = "FIGHT_CLEARED"
EVENT_TYPES = (FIGHT_DETECTED, FIGHT_CLEARED)

DETECT = "DETECT"
EXCLUDE = "EXCLUDE"
WHOLE_FRAME_ID = "whole-frame"

FIGHT_COLOR = [0, 0, 255]
ZONE_COLOR = [255, 140, 0]

MAX_TRACKED = 16
COOLDOWN_PREFIX = "cooldown:"
MAX_COOLDOWN_SEC = 3600.0
WORST_CASE_GAP_SEC = 0.5      # this plugin runs every frame, not sampled


@dataclass
class Hit:
    event_type: str
    camera_id: str
    zone_id: Optional[str]
    zone_name: Optional[str]
    severity: str
    timestamp: float
    started_at: float
    score: float
    track_ids: List[str] = field(default_factory=list)
    bbox: List[int] = field(default_factory=list)
    duration_sec: float = 0.0
    frames: int = 0

    def describe(self) -> str:
        where = self.zone_name or "camera view"
        who = " and ".join(str(t) for t in self.track_ids) or "two people"
        if self.event_type == FIGHT_CLEARED:
            return (f"Fight/quarrel indication in {where} ended after "
                    f"{self.duration_sec:.0f}s")
        return (f"Possible fight or quarrel in {where} between tracks {who} "
                f"(confirmed over {self.duration_sec:.1f}s, "
                f"confidence {self.score:.0%}) — requires human verification")


def _usable(zone: dict):
    return sanitize_polygon(zone.get("points"))


def _split(zones: Sequence[dict]):
    detect, exclude = [], []
    for z in zones or []:
        if not z.get("is_active", True):
            continue
        points = _usable(z)
        if points is None:
            continue
        if str(z.get("zone_kind") or DETECT).upper() == EXCLUDE:
            exclude.append(points)
        else:
            detect.append((z, points))
    return detect, exclude


def _whole_frame_zone(camera_id: str) -> dict:
    return {"zone_id": WHOLE_FRAME_ID, "name": None, "camera_id": camera_id,
            "points": None, "zone_kind": DETECT, "is_active": True,
            "sensitivity": rules.DEFAULT_SENSITIVITY, "overrides": {},
            "schedule": None, "severity": None}


def _window(tune) -> float:
    """Never narrower than the time min_frames frames actually need."""
    return max(tune["confirm_sec"] * 3.0, tune["confirm_sec"] + 3.0,
               int(tune["min_frames"]) * WORST_CASE_GAP_SEC)


def _confirmed(rec, tune, now) -> bool:
    return (rec["frames"] >= int(tune["min_frames"])
            and (now - rec["first_seen"]) >= tune["confirm_sec"])


def evaluate(camera_id: str, boxes: Sequence, zones: Sequence[dict],
             state: dict, now: float,
             local_now: Optional[datetime] = None) -> List[Hit]:
    """
    Advances the incident state machine by one frame.

    `boxes` is [(track_id, bbox), ...] for the people in this frame. `state`
    is this camera's persistent bucket, mutated in place. Returns only what
    changed — confirmations and clears — never a per-frame heartbeat.
    """
    detect, exclude = _split(zones)
    implicit = False
    if not detect:
        if not zones or exclude:
            detect, implicit = [(_whole_frame_zone(camera_id), None)], True
        else:
            # Zones exist but none are usable: every one deactivated, or the
            # geometry no longer validates. Both are states an operator
            # created, and widening to the whole frame would watch MORE than
            # they asked for while appearing to obey.
            return []

    pair_scores = dynamics.evaluate_pairs(state.setdefault("motion", {}),
                                          boxes, now)
    box_by_track = {t: b for t, b in (boxes or [])}

    hits: List[Hit] = []
    seen_keys = set()

    for zone, points in detect:
        armed = rules.is_armed(zone.get("schedule"), local_now)
        tune = rules.tuning(zone.get("sensitivity"), zone.get("overrides"))
        zone_id = zone.get("zone_id")

        if not armed:
            hits.extend(_close_out(state, zone, camera_id, now, implicit,
                                   prefix=f"{zone_id}|"))
            continue

        best = _best_pair(pair_scores, box_by_track, points, exclude, tune)
        key = f"{zone_id}|pair"
        seen_keys.add(key)
        hit = _advance(state, key, zone, best, tune, camera_id, now, implicit)
        if hit is not None:
            hits.append(hit)

    seen_keys.update(k for k in state if k.startswith(COOLDOWN_PREFIX))
    seen_keys.add("motion")
    hits.extend(_expire(state, seen_keys, now))
    return hits


def _best_pair(pair_scores, box_by_track, points, exclude, tune):
    """The strongest qualifying pair inside this zone, or None."""
    best = None
    for (ta, tb), score in (pair_scores or {}).items():
        if score < tune["min_score"]:
            continue
        ba, bb = box_by_track.get(ta), box_by_track.get(tb)
        if ba is None or bb is None:
            continue
        if dynamics.separation(ba, bb) > tune["engage_separation"]:
            continue
        cx = (ba[0] + ba[2] + bb[0] + bb[2]) / 4.0
        cy = (ba[1] + ba[3] + bb[1] + bb[3]) / 4.0
        if points is not None and not point_in_polygon(cx, cy, points):
            continue
        if any(point_in_polygon(cx, cy, ex) for ex in exclude):
            continue
        bbox = [int(min(ba[0], bb[0])), int(min(ba[1], bb[1])),
                int(max(ba[2], bb[2])), int(max(ba[3], bb[3]))]
        if best is None or score > best[0]:
            best = (score, [str(ta), str(tb)], bbox)
    return best


def _advance(state, key, zone, best, tune, camera_id, now, implicit):
    rec = state.get(key)

    if best is None:
        if rec is None:
            return None
        if (now - rec["last_seen"]) < tune["clear_sec"]:
            return None                      # people separate for a moment
        state.pop(key, None)
        if not rec.get("alerted_at"):
            return None
        state.pop(f"{COOLDOWN_PREFIX}{key}", None)
        return _hit(FIGHT_CLEARED, zone, rec, camera_id, now, implicit,
                    duration=rec["last_seen"] - rec["first_seen"])

    score, tracks, bbox = best
    if rec is None:
        if len([k for k in state
                if not k.startswith(COOLDOWN_PREFIX) and k != "motion"]) >= MAX_TRACKED:
            return None
        state[key] = {"first_seen": now, "last_seen": now, "frames": 1,
                      "peak_score": score, "tracks": tracks, "bbox": bbox,
                      "alerted_at": None, "camera_id": camera_id,
                      "zone_name": zone.get("name"),
                      "severity": rules.sanitize_severity(zone.get("severity")),
                      "implicit": implicit}
        return None

    if not rec.get("alerted_at") and (now - rec["first_seen"]) > _window(tune) \
            and not _confirmed(rec, tune, now):
        rec.update(first_seen=now, frames=0, peak_score=0.0)

    rec["last_seen"] = now
    rec["frames"] += 1
    if score > rec["peak_score"]:
        rec.update(peak_score=score, tracks=tracks, bbox=bbox)

    if not _confirmed(rec, tune, now):
        return None
    cooldown_key = f"{COOLDOWN_PREFIX}{key}"
    last = state.get(cooldown_key)
    if last is not None and (now - float(last)) < tune["alert_cooldown_sec"]:
        return None
    state[cooldown_key] = now
    rec["alerted_at"] = now
    return _hit(FIGHT_DETECTED, zone, rec, camera_id, now, implicit,
                duration=now - rec["first_seen"])


def _hit(event_type, zone, rec, camera_id, now, implicit, duration) -> Hit:
    return Hit(
        event_type=event_type,
        camera_id=camera_id or rec.get("camera_id", ""),
        zone_id=(None if implicit else zone.get("zone_id")),
        zone_name=zone.get("name") or rec.get("zone_name"),
        severity=(rules.sanitize_severity(zone.get("severity"))
                  if zone.get("severity") else rec.get("severity",
                                                       rules.DEFAULT_SEVERITY)),
        timestamp=now, started_at=rec["first_seen"],
        score=float(rec["peak_score"]), track_ids=list(rec.get("tracks") or []),
        bbox=list(rec.get("bbox") or []), duration_sec=float(max(0.0, duration)),
        frames=int(rec.get("frames", 0)),
    )


def _close_out(state, zone, camera_id, now, implicit, prefix) -> List[Hit]:
    out = []
    for key in [k for k in state
                if k.startswith(prefix) and not k.startswith(COOLDOWN_PREFIX)]:
        rec = state.pop(key)
        state.pop(f"{COOLDOWN_PREFIX}{key}", None)
        if rec.get("alerted_at"):
            out.append(_hit(FIGHT_CLEARED, zone, rec, camera_id, now, implicit,
                            duration=rec["last_seen"] - rec["first_seen"]))
    return out


def _expire(state, seen_keys, now) -> List[Hit]:
    """Closes out incidents whose zone stopped being evaluated at all."""
    out = []
    for key in [k for k in state if k not in seen_keys]:
        if key.startswith(COOLDOWN_PREFIX):
            stamp = state.get(key)
            if stamp is None or (now - float(stamp)) > MAX_COOLDOWN_SEC:
                state.pop(key, None)
            continue
        rec = state.pop(key, None)
        if not isinstance(rec, dict) or not rec.get("alerted_at"):
            continue
        state.pop(f"{COOLDOWN_PREFIX}{key}", None)
        zone_id = key.rsplit("|", 1)[0]
        out.append(_hit(FIGHT_CLEARED,
                        {"zone_id": zone_id, "name": rec.get("zone_name"),
                         "severity": rec.get("severity")},
                        rec, rec.get("camera_id", ""), now,
                        rec.get("implicit", False),
                        duration=rec["last_seen"] - rec["first_seen"]))
    return out


# ----------------------------------------------------------------------
# overlay
# ----------------------------------------------------------------------
def zone_outline_drawings(zones, local_now=None) -> List[dict]:
    out = []
    for z in zones or []:
        if not z.get("is_active", True):
            continue
        points = _usable(z)
        if points is None:
            continue
        excluded = str(z.get("zone_kind") or DETECT).upper() == EXCLUDE
        armed = rules.is_armed(z.get("schedule"), local_now)
        colour = [120, 120, 120] if (excluded or not armed) else ZONE_COLOR
        out.append({"type": "poly", "coords": points, "color": colour,
                    "thickness": 2, "opacity": 0.15})
        label = z.get("name") or ""
        if excluded:
            label = f"{label} (excluded)".strip()
        elif not armed:
            label = f"{label} (off)".strip()
        if label:
            out.append({"type": "text", "text": label,
                        "coords": [points[0][0], max(0, points[0][1] - 8)],
                        "color": colour, "scale": 0.55, "thickness": 2})
    return out


def hit_drawings(hit: Hit) -> List[dict]:
    if not hit.bbox or len(hit.bbox) != 4:
        return []
    x1, y1, _, _ = hit.bbox
    return [
        {"type": "rect", "coords": list(hit.bbox), "color": FIGHT_COLOR,
         "thickness": 3},
        {"type": "text", "text": f"POSSIBLE FIGHT {hit.score:.0%}",
         "coords": [x1, max(0, y1 - 10)], "color": FIGHT_COLOR, "scale": 0.7,
         "thickness": 2},
    ]
