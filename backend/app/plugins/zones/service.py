"""
The restricted-zone state machine.

Written as a pure function over a state dict so it can be exercised without a
pipeline, a camera or a database: give it zones, detections and a clock, and
it returns the events that should fire. Both RestrictionZonePlugin and
IntrusionDetectionPlugin call it with the *same* state bucket, so a site with
both enabled — which is 61 of the 62 zone-enabled cameras here — logs one
intrusion rather than two.

Three rules do the work that turns a tripwire into something an operator can
live with:

  * a track must be inside for `min_dwell_sec` before it counts, so a box
    that jitters over the boundary for two frames is not an intrusion;
  * leaving is only believed after `exit_grace_sec`, so a person half
    occluded by a pillar does not close and reopen a visit every second;
  * a zone will not raise another entry alert within `alert_cooldown_sec`,
    so a doorway with a queue behind it produces an alert, not a stream.

Before this, one person standing still in view produced an alert on their
first frame and a loitering alert every LOITERING_THRESHOLD_SECONDS
thereafter, on every camera, around the clock, against a zone nobody had
drawn — 127,000 zone alerts in the last seven days on this appliance.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from app.plugins.zones.geometry import box_height, detection_in_zone
from app.plugins.zones.rules import class_label, is_armed

# Event types this module produces. ENTRY and LOITERING are alerts; EXIT
# closes the record with a total dwell and is logged, not alarmed.
ZONE_ENTRY = "ZONE_ENTRY"
ZONE_LOITERING = "ZONE_LOITERING"
ZONE_EXIT = "ZONE_EXIT"

# A visit's state is dropped this long after the track was last seen inside,
# whether it walked out of the zone or out of the frame.
DEFAULT_EXIT_GRACE_SEC = 3.0
# Hard cap on tracked visits per zone, so a camera minting new track ids
# cannot grow this dict without bound.
MAX_TRACKS_PER_ZONE = 512


@dataclass
class ZoneHit:
    """One thing that happened in a zone, ready to become an event and a row."""
    zone_id: str
    zone_name: str
    camera_id: str
    event_type: str
    severity: str
    track_id: Optional[int]
    class_id: int
    class_name: str
    confidence: float
    bbox: List[float]
    dwell_seconds: float
    started_at: float
    timestamp: float
    points: List[List[int]] = field(default_factory=list)

    @property
    def is_alert(self) -> bool:
        return self.event_type in (ZONE_ENTRY, ZONE_LOITERING)

    def describe(self) -> str:
        who = class_label(self.class_id)
        if self.event_type == ZONE_ENTRY:
            return f"{who.capitalize()} entered {self.zone_name}"
        if self.event_type == ZONE_LOITERING:
            return (f"{who.capitalize()} loitering in {self.zone_name} "
                    f"for {int(self.dwell_seconds)}s")
        return (f"{who.capitalize()} left {self.zone_name} "
                f"after {int(self.dwell_seconds)}s")


def _visits(state: Dict[str, Any], zone_id: str) -> Dict[Any, dict]:
    return state.setdefault("visits", {}).setdefault(zone_id, {})


def _eligible(det, zone: dict) -> bool:
    """Whether this detection is one the zone is configured to care about."""
    if det.class_id not in zone["classes"]:
        return False
    if float(det.confidence or 0.0) < zone["min_confidence"]:
        return False
    min_px = zone.get("min_box_px") or 0
    if min_px and box_height(det.bbox) < min_px:
        # Too few pixels to trust: a 20px-tall box at the far end of a yard
        # is as likely to be a bush as a person.
        return False
    return True


def evaluate(camera_id: str,
             detections: Sequence[Any],
             zones: Sequence[dict],
             state: Dict[str, Any],
             now: Optional[float] = None,
             local_now: Optional[datetime] = None) -> List[ZoneHit]:
    """
    Advances every armed zone on this camera by one frame.

    `now` is the frame timestamp used for dwell arithmetic; `local_now` is
    wall-clock time used only to decide whether a zone's schedule has it
    armed. They are separate because dwell must be measured against the frame
    clock, while "after 18:00" is a question about the wall clock.
    """
    now = time.time() if now is None else float(now)
    local_now = local_now or datetime.now()
    hits: List[ZoneHit] = []
    cooldowns: Dict[str, float] = state.setdefault("cooldowns", {})

    for zone in zones:
        if not zone.get("is_active", True):
            continue
        zone_id = zone["zone_id"]
        visits = _visits(state, zone_id)

        if not is_armed(zone.get("schedule"), local_now):
            # Disarmed: forget any visit in progress rather than holding it
            # open, so an entry alert cannot fire the instant the zone arms
            # for somebody who was already standing there legitimately.
            if visits:
                visits.clear()
            continue

        points = zone["points"]
        anchor = zone.get("anchor") or "FEET"
        min_dwell = float(zone.get("min_dwell_sec") or 0.0)
        loiter_sec = zone.get("loiter_sec")
        cooldown = float(zone.get("alert_cooldown_sec") or 0.0)
        severity = zone.get("severity") or "warning"

        for det in detections:
            if det.track_id is None or not _eligible(det, zone):
                continue
            if not detection_in_zone(det.bbox, points, anchor):
                continue

            visit = visits.get(det.track_id)
            if visit is None:
                if len(visits) >= MAX_TRACKS_PER_ZONE:
                    oldest = min(visits, key=lambda k: visits[k]["last_inside"])
                    visits.pop(oldest, None)
                visit = {
                    "first_inside": now,
                    "last_inside": now,
                    "alerted": False,
                    "last_loiter": now,
                    "class_id": det.class_id,
                    "bbox": list(det.bbox),
                    "confidence": float(det.confidence or 0.0),
                }
                visits[det.track_id] = visit
            visit["last_inside"] = now
            visit["bbox"] = list(det.bbox)
            visit["confidence"] = float(det.confidence or 0.0)

            dwell = now - visit["first_inside"]

            if not visit["alerted"] and dwell >= min_dwell:
                # None, not 0.0: a zone that has never alerted must always be
                # allowed to. Defaulting to epoch 0 only happens to work
                # because wall-clock timestamps are large, and silently
                # swallows the first alert under any other clock.
                last = cooldowns.get(zone_id)
                if cooldown <= 0.0 or last is None or (now - last) >= cooldown:
                    cooldowns[zone_id] = now
                    visit["alerted"] = True
                    visit["last_loiter"] = now
                    hits.append(_hit(zone, camera_id, ZONE_ENTRY, severity,
                                     det.track_id, visit, dwell, now, points))
                # Inside the cooldown the alert is deliberately NOT marked as
                # sent: the person is still in the zone, so it fires as soon
                # as the cooldown lapses rather than being lost entirely.

            if loiter_sec and visit["alerted"] and dwell >= float(loiter_sec):
                if (now - visit["last_loiter"]) >= float(loiter_sec):
                    visit["last_loiter"] = now
                    hits.append(_hit(zone, camera_id, ZONE_LOITERING, severity,
                                     det.track_id, visit, dwell, now, points))

        grace = float(zone.get("exit_grace_sec") or DEFAULT_EXIT_GRACE_SEC)
        for track_id in [t for t, v in visits.items()
                         if (now - v["last_inside"]) >= grace]:
            visit = visits.pop(track_id)
            if visit["alerted"]:
                # Dwell is measured to the last frame the track was actually
                # inside, not to now — the grace period is confirmation that
                # they left, not time spent in the zone.
                hits.append(_hit(zone, camera_id, ZONE_EXIT, "info", track_id,
                                 visit, visit["last_inside"] - visit["first_inside"],
                                 now, points))

    return hits


def _hit(zone, camera_id, event_type, severity, track_id, visit, dwell, now,
         points) -> ZoneHit:
    return ZoneHit(
        zone_id=zone["zone_id"],
        zone_name=zone.get("name") or "Restricted Zone",
        camera_id=camera_id,
        event_type=event_type,
        severity=severity,
        track_id=track_id,
        class_id=visit["class_id"],
        class_name=class_label(visit["class_id"]),
        confidence=visit["confidence"],
        bbox=list(visit["bbox"]),
        dwell_seconds=round(max(0.0, dwell), 2),
        started_at=visit["first_inside"],
        timestamp=now,
        points=points,
    )


# --------------------------------------------------------------------------
# Overlay drawings. Stateless and derived purely from the zones and the hits,
# so a plugin can build them without touching the state machine.
# --------------------------------------------------------------------------

SEVERITY_BGR = {
    "critical": [0, 0, 255],
    "warning": [0, 140, 255],
    "info": [255, 200, 0],
}


def zone_outline_drawings(zones: Sequence[dict],
                          local_now: Optional[datetime] = None) -> List[dict]:
    """
    The zone boundaries as the operator should see them: solid while armed,
    dimmed while the schedule has them off. A zone that looks identical
    whether or not it is enforcing is a zone nobody trusts.
    """
    local_now = local_now or datetime.now()
    out: List[dict] = []
    for zone in zones:
        if not zone.get("is_active", True):
            continue
        armed = is_armed(zone.get("schedule"), local_now)
        colour = SEVERITY_BGR.get(zone.get("severity") or "warning",
                                  SEVERITY_BGR["warning"])
        if not armed:
            colour = [150, 150, 150]
        out.append({
            "type": "poly",
            "coords": zone["points"],
            "color": colour,
            "thickness": 2,
            "opacity": 0.30 if armed else 0.12,
        })
        label = zone.get("name") or "Restricted Zone"
        if not armed:
            label += " (off)"
        anchor_pt = min(zone["points"], key=lambda p: (p[1], p[0]))
        out.append({
            "type": "text",
            "text": label,
            "coords": [int(anchor_pt[0]), max(0, int(anchor_pt[1]) - 8)],
            "color": colour,
            "scale": 0.6,
            "thickness": 2,
        })
    return out


def hit_drawings(hit: ZoneHit) -> List[dict]:
    colour = SEVERITY_BGR.get(hit.severity, SEVERITY_BGR["warning"])
    x1, y1, x2, y2 = [int(v) for v in hit.bbox]
    label = ("INTRUDER" if hit.event_type == ZONE_ENTRY
             else f"LOITERING ({int(hit.dwell_seconds)}s)")
    return [
        {"type": "rect", "coords": [x1, y1, x2, y2], "color": colour, "thickness": 3},
        {"type": "text", "text": label, "coords": [x1, max(0, y1 - 10)],
         "color": colour, "scale": 0.7, "thickness": 2},
    ]
