"""
SOW 2.8 — the alert mechanism: frames of evidence become an incident.

Confirmation is the reason this layer exists. A single frame that looks like
fire is not a fire; it is a reflection off a windscreen, a forklift beacon
sweeping past, or one bad auto-exposure step after a cloud moves. Alerting on
it is how a safety system becomes the thing every operator mutes, and a muted
system detects nothing. So evidence has to persist for a configured number of
seconds AND a configured number of frames, inside the same window, before
anyone is told. Both conditions are needed: seconds alone is satisfied by two
frames an hour apart, frames alone is satisfied by a 100ms burst.

The second rule is that incidents have to end. Without one the appliance
holds a fire "active" forever, the dashboard shows a permanent red banner,
and the next real fire on that camera is invisible inside the last one. An
incident clears after a quiet period, records how long it ran, and a later
one on the same zone starts fresh.

Nothing here is a substitute for a fire alarm system; see STATUTORY_NOTICE.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from app.plugins.fire import rules
from app.plugins.fire.detector import FIRE, SMOKE, STATUTORY_NOTICE  # noqa: F401
from app.plugins.zones.geometry import point_in_polygon, sanitize_polygon

FIRE_DETECTED = "FIRE_DETECTED"      # kept: the alert engine and the events
SMOKE_DETECTED = "SMOKE_DETECTED"    # feed already key off FIRE_DETECTED
FIRE_CLEARED = "FIRE_CLEARED"

EVENT_TYPES = (FIRE_DETECTED, SMOKE_DETECTED, FIRE_CLEARED)
EVENT_FOR_KIND = {FIRE: FIRE_DETECTED, SMOKE: SMOKE_DETECTED}

DETECT = "DETECT"
EXCLUDE = "EXCLUDE"

# The zone used when an operator has drawn none. Fire anywhere in shot is
# meaningful, so a camera with fire detection switched on is watched whole —
# the opposite of a restricted zone, which means nothing without geometry.
WHOLE_FRAME_ID = "whole-frame"

FIRE_COLOR = [255, 0, 0]    # Red (RGB) for Fire
SMOKE_COLOR = [255, 140, 0] # Orange (RGB) for Smoke
ZONE_COLOR = [239, 68, 68]

# Ceiling on tracked incidents per camera, so a camera flickering between
# many small regions cannot grow the state dict without bound.
MAX_TRACKED = 24

# The alert cooldown has to outlive the incident record that triggered it,
# because an incident record is closed and reopened by ordinary detection
# noise. Without that, a fire whose evidence lapses briefly would open a fresh
# incident with a clean history and page somebody again immediately.
#
# It does NOT outlive an all-clear. If the system has told an operator the
# fire is out, and it comes back, it must say so — a suppressed re-alarm after
# a stand-down is the dangerous direction to fail in. So emitting FIRE_CLEARED
# drops the cooldown, and the cooldown only ever suppresses repeat alerts
# WITHIN one continuous incident.
COOLDOWN_PREFIX = "cooldown:"

# Longest cooldown any preset can ask for, used to retire dead entries.
MAX_COOLDOWN_SEC = 3600.0


@dataclass
class Hit:
    """One thing that happened, ready to be published and logged."""

    event_type: str
    kind: str
    camera_id: str
    zone_id: Optional[str]
    zone_name: Optional[str]
    severity: str
    timestamp: float
    started_at: float
    score: float
    area_frac: float
    bbox: List[int] = field(default_factory=list)
    duration_sec: float = 0.0
    frames: int = 0

    def describe(self) -> str:
        where = self.zone_name or "camera view"
        if self.event_type == FIRE_CLEARED:
            return (f"{self.kind.title()} in {where} cleared after "
                    f"{self.duration_sec:.0f}s")
        return (f"{self.kind.title()} detected in {where} "
                f"(confirmed over {self.duration_sec:.0f}s, "
                f"confidence {self.score:.0%})")

    def as_dict(self) -> dict:
        return {
            "event_type": self.event_type, "kind": self.kind,
            "camera_id": self.camera_id, "zone_id": self.zone_id,
            "zone_name": self.zone_name, "severity": self.severity,
            "timestamp": self.timestamp, "started_at": self.started_at,
            "score": round(self.score, 3), "area_frac": round(self.area_frac, 5),
            "bbox": list(self.bbox), "duration_sec": round(self.duration_sec, 2),
            "frames": self.frames, "description": self.describe(),
        }


def _centroid(bbox) -> tuple:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _usable(zone: dict) -> Optional[List[List[int]]]:
    """A zone's geometry, or None if it no longer validates."""
    return sanitize_polygon(zone.get("points"))


def _split(zones: Sequence[dict]):
    """Active detect zones and exclusion polygons, geometry validated."""
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
    return {
        "zone_id": WHOLE_FRAME_ID, "name": None, "camera_id": camera_id,
        "points": None, "zone_kind": DETECT, "is_active": True,
        "watch": list(rules.KINDS), "sensitivity": rules.DEFAULT_SENSITIVITY,
        "overrides": {}, "schedule": None, "severity": None,
    }


def evaluate(camera_id: str, candidates: Sequence, zones: Sequence[dict],
             state: dict, now: float,
             local_now: Optional[datetime] = None) -> List[Hit]:
    """
    Advances the incident state machine by one frame.

    `state` is this camera's persistent bucket and is mutated in place.
    Returns only what changed: confirmations and clears, never a per-frame
    heartbeat — the overlay is built separately so the log stays an event log.
    """
    detect, exclude = _split(zones)
    implicit = False
    if not detect:
        if not zones:
            # Nobody drew anything: watch the whole frame. Fire in shot is
            # meaningful wherever it is, so a camera with the plugin switched
            # on is covered by default.
            detect, implicit = [(_whole_frame_zone(camera_id), None)], True
        elif exclude:
            # Only exclusions were drawn, which reads as "everywhere but
            # there" — the natural meaning of marking the welding bay.
            detect, implicit = [(_whole_frame_zone(camera_id), None)], True
        else:
            # Rows exist but none are usable: every zone deactivated, or the
            # geometry no longer validates. Both are states an operator
            # created, and quietly widening coverage to the whole frame would
            # monitor MORE than they asked for while looking like it obeyed.
            # The registry logs unusable geometry when it loads it.
            return []

    hits: List[Hit] = []
    seen_keys = set()

    for zone, points in detect:
        if not rules.is_armed(zone.get("schedule"), local_now):
            # A zone going out of schedule mid-incident still has to close it
            # out, or the log keeps a confirmed fire open forever.
            hits.extend(_close_out(state, zone, camera_id, now, implicit,
                                   prefix=f"{zone.get('zone_id')}|"))
            seen_keys.update(k for k in state
                             if k.startswith(COOLDOWN_PREFIX))
            continue

        watch = rules.sanitize_kinds(zone.get("watch"))
        tune = rules.tuning(zone.get("sensitivity"), zone.get("overrides"))

        for kind in watch:
            key = f"{zone.get('zone_id')}|{kind}"
            seen_keys.add(key)
            best = _best_candidate(candidates, kind, points, exclude, tune)
            hit = _advance(state, key, zone, kind, best, tune, camera_id, now,
                           implicit)
            if hit is not None:
                hits.append(hit)

    # Anything tracked but no longer evaluated (zone deleted, disarmed, or the
    # camera's zones changed) is closed out rather than left dangling.
    hits.extend(_expire(state, seen_keys, now))
    return hits


def _best_candidate(candidates, kind, points, exclude, tune):
    """The strongest qualifying candidate of `kind` inside this zone."""
    best = None
    for c in candidates or []:
        if getattr(c, "kind", None) != kind:
            continue
        if float(getattr(c, "score", 0.0)) < tune["min_score"]:
            continue
        if float(getattr(c, "area_frac", 0.0)) < tune["min_area_frac"]:
            continue
        cx, cy = _centroid(c.bbox)
        if points is not None and not point_in_polygon(cx, cy, points):
            continue
        if any(point_in_polygon(cx, cy, ex) for ex in exclude):
            continue
        if best is None or c.score > best.score:
            best = c
    return best


def _advance(state, key, zone, kind, best, tune, camera_id, now,
             implicit) -> Optional[Hit]:
    rec = state.get(key)

    # If video file loops or stream timestamp rewinds, reset stale record & cooldown
    if rec is not None and (now < rec.get("last_seen", 0) or now < rec.get("first_seen", 0)):
        state.pop(key, None)
        state.pop(f"{COOLDOWN_PREFIX}{key}", None)
        rec = None

    if best is None:
        if rec is None:
            return None
        quiet = now - rec["last_seen"]
        if quiet < tune["clear_sec"]:
            return None                       # flames drop out of band briefly
        state.pop(key, None)
        if not rec.get("alerted_at"):
            return None                       # never confirmed; nothing to clear
        # The operator has been told it is out. If it comes back, they must
        # hear about it, so the cooldown goes with the incident.
        state.pop(f"{COOLDOWN_PREFIX}{key}", None)
        return _hit(FIRE_CLEARED, kind, zone, rec, camera_id,
                    now, implicit, duration=rec["last_seen"] - rec["first_seen"])

    if rec is None:
        if len([k for k in state if not k.startswith(COOLDOWN_PREFIX)]) >= MAX_TRACKED:
            return None
        state[key] = {
            "first_seen": now, "last_seen": now, "frames": 1,
            "peak_score": float(best.score), "peak_area": float(best.area_frac),
            "bbox": [int(v) for v in best.bbox], "alerted_at": None,
            "polygon": getattr(best, "polygon", None),
            # Carried so _expire can still describe an incident whose zone has
            # been deleted out from under it.
            "camera_id": camera_id, "zone_name": zone.get("name"),
            "severity": (rules.sanitize_severity(zone.get("severity"))
                         if zone.get("severity") else rules.default_severity(kind)),
            "implicit": implicit,
        }
        return None

    # Evidence that arrives after the confirmation window has already lapsed
    # without confirming starts a new window: one flash every ten seconds is
    # not a fire, however many flashes there eventually are.
    if not rec.get("alerted_at") and (now - rec["first_seen"]) > _window(tune) \
            and not _confirmed(rec, tune, now):
        rec["first_seen"] = now
        rec["frames"] = 0
        rec["peak_score"] = 0.0
        # peak_area was left behind by the original reset, so an alert could
        # report an area from evidence that had already been discarded.
        rec["peak_area"] = 0.0

    rec["last_seen"] = now
    rec["frames"] += 1
    if best.score > rec["peak_score"]:
        rec["peak_score"] = float(best.score)
        rec["bbox"] = [int(v) for v in best.bbox]
        if getattr(best, "polygon", None):
            rec["polygon"] = getattr(best, "polygon", None)
    rec["peak_area"] = max(rec.get("peak_area", 0.0), float(best.area_frac))

    if not _confirmed(rec, tune, now):
        return None

    # The cooldown lives at zone level so it survives the incident record
    # being closed and reopened by a fire that flickers in and out.
    cooldown_key = f"{COOLDOWN_PREFIX}{key}"
    last = state.get(cooldown_key)
    if last is not None and (now - float(last)) < tune["alert_cooldown_sec"]:
        return None
    state[cooldown_key] = now
    rec["alerted_at"] = now
    return _hit(EVENT_FOR_KIND[kind], kind, zone, rec, camera_id, now,
                implicit, duration=now - rec["first_seen"])


# Worst-case seconds between two process_frame calls for one camera. The
# appliance measures ~1.1s (interval 15 at ~13.5fps), and the analytics queue
# drops whole batches under load, so the window is sized against a pessimistic
# gap rather than the typical one.
WORST_CASE_GAP_SEC = 2.5


def _window(tune) -> float:
    """
    How long evidence stays fresh.

    Wider than confirm_sec so a camera running slower than expected can still
    accumulate its sightings — and, critically, never narrower than the time
    min_frames sightings actually need. A per-zone min_frames of 60 inside a
    7-second window can never be reached, so the zone would sit in the UI
    looking armed while being incapable of ever raising an alert. An
    unreachable threshold is worse than a wrong one, because nothing about it
    looks broken.
    """
    return max(tune["confirm_sec"] * 3.0,
               tune["confirm_sec"] + 5.0,
               int(tune["min_frames"]) * WORST_CASE_GAP_SEC)


def _confirmed(rec, tune, now) -> bool:
    return (rec["frames"] >= int(tune["min_frames"])
            and (now - rec["first_seen"]) >= tune["confirm_sec"])


def _hit(event_type, kind, zone, rec, camera_id, now, implicit,
         duration) -> Hit:
    severity = (rules.sanitize_severity(zone.get("severity"))
                if zone.get("severity") else rules.default_severity(kind))
    camera_id = camera_id or rec.get("camera_id", "")
    return Hit(
        event_type=event_type, kind=kind, camera_id=camera_id,
        zone_id=(None if implicit else zone.get("zone_id")),
        zone_name=zone.get("name"),
        severity=severity, timestamp=now, started_at=rec["first_seen"],
        score=float(rec["peak_score"]), area_frac=float(rec.get("peak_area", 0.0)),
        bbox=list(rec.get("bbox") or []), duration_sec=float(max(0.0, duration)),
        frames=int(rec.get("frames", 0)),
    )


def _close_out(state: dict, zone: dict, camera_id: str, now: float,
               implicit: bool, prefix: str) -> List[Hit]:
    """
    Ends every incident under `prefix`, reporting the ones somebody was told
    about. Cooldown entries are left alone: they outlive their incident.
    """
    out = []
    for key in [k for k in state
                if k.startswith(prefix) and not k.startswith(COOLDOWN_PREFIX)]:
        rec = state.pop(key)
        state.pop(f"{COOLDOWN_PREFIX}{key}", None)
        if not rec.get("alerted_at"):
            continue                       # never confirmed; nothing to close
        kind = key.rsplit("|", 1)[-1]
        out.append(_hit(FIRE_CLEARED, kind, zone, rec, camera_id, now, implicit,
                        duration=rec["last_seen"] - rec["first_seen"]))
    return out


def _expire(state: dict, seen_keys, now) -> List[Hit]:
    """
    Closes out incidents that are no longer being evaluated at all — the zone
    was deleted, or the camera's configuration changed under a live fire.

    Silently dropping those was the original behaviour, which left the log
    holding a confirmed, never-cleared incident and the dashboard showing a
    permanent alarm for a zone that no longer exists.
    """
    out = []
    for key in [k for k in state if k not in seen_keys]:
        if key.startswith(COOLDOWN_PREFIX):
            # Not an incident, but it must not accumulate either: a cooldown
            # for a zone nobody is evaluating any more is dead weight. Read
            # defensively — closing an incident earlier in this same loop
            # already removes its paired cooldown.
            stamp = state.get(key)
            if stamp is None or (now - float(stamp)) > MAX_COOLDOWN_SEC:
                state.pop(key, None)
            continue
        rec = state.pop(key, None)
        if rec is None:
            continue
        state.pop(f"{COOLDOWN_PREFIX}{key}", None)
        if not rec.get("alerted_at"):
            continue
        zone_id, kind = key.rsplit("|", 1)
        out.append(_hit(
            FIRE_CLEARED, kind,
            {"zone_id": zone_id, "name": rec.get("zone_name"),
             "severity": rec.get("severity")},
            rec, rec.get("camera_id", ""), now, rec.get("implicit", False),
            duration=rec["last_seen"] - rec["first_seen"]))
    return out


# ----------------------------------------------------------------------
# overlay
# ----------------------------------------------------------------------
def zone_outline_drawings(zones: Sequence[dict],
                          local_now: Optional[datetime] = None) -> List[dict]:
    """
    Outlines for the configured zones. An operator who drew none sees none —
    a box around the whole frame is noise, not information.
    """
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
                    "thickness": 2, "opacity": 0.18})
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
    colour = FIRE_COLOR if hit.kind == FIRE else SMOKE_COLOR
    label = "FIRE" if hit.kind == FIRE else "SMOKE"
    x1, y1, _, _ = hit.bbox
    return [
        {"type": "rect", "coords": list(hit.bbox), "color": colour,
         "thickness": 3},
        {"type": "text", "text": f"{label} {hit.score:.0%}",
         "coords": [x1, max(0, y1 - 10)], "color": colour, "scale": 0.7,
         "thickness": 2},
    ]


def candidate_drawings(candidates: Sequence) -> List[dict]:
    """Live overlay for unconfirmed evidence, so an operator can see why."""
    out = []
    for c in candidates or []:
        if c.score < 0.35:
            continue
        colour = FIRE_COLOR if c.kind == FIRE else SMOKE_COLOR
        out.append({
            "type": "rect",
            "coords": list(c.bbox),
            "color": colour,
            "thickness": 2
        })
        label = f"{c.kind.upper()} ({int(c.score * 100)}%)"
        out.append({
            "type": "text",
            "coords": [c.bbox[0], max(14, c.bbox[1] - 4)],
            "text": label,
            "color": colour,
            "scale": 0.9
        })
    return out
