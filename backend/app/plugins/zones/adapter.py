"""
The bridge between the zone state machine and the plugin engine.

Two plugins are wired to restricted zones on this site — RestrictionZonePlugin
and IntrusionDetectionPlugin — and 61 of the 62 zone-enabled cameras have both
switched on. They are the same feature implemented twice, so running both
evaluators produced two alerts, two snapshots and two log rows for one person
stepping over one line.

They now share a single monitor. Exactly one of them evaluates a given
camera, chosen from the camera's plugin list rather than from whichever
happened to be scheduled first, so the event type a camera produces is stable
instead of depending on thread timing. The other contributes nothing on that
camera, which is the honest outcome for a duplicate.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from app.engine.base import DetectionEvent
from app.engine.snapshots import frame_for_snapshot, save_event_snapshot
from app.plugins.zones import service
from app.plugins.zones.repository import zone_event_log, zone_registry
from app.plugins.zones.rules import describe_schedule

# The shared state bucket. Deliberately not the plugin's own name: the point
# is that both plugins advance the *same* visits and cooldowns.
MONITOR_STATE = "ZoneMonitor"

# When both plugins are enabled on a camera, this one owns the evaluation.
# It emits INTRUSION_DETECTED, which the alert engine already escalates and
# the events feed already renders.
PRIMARY_PLUGIN = "IntrusionDetectionPlugin"


def owns_camera(plugin_name: str, camera_id: str) -> bool:
    """Whether this plugin is the one evaluating zones on this camera."""
    if plugin_name == PRIMARY_PLUGIN:
        return True
    try:
        from config.config import config
        allowed = config.get_allowed_plugins(camera_id) or []
    except Exception:
        return True
    return PRIMARY_PLUGIN not in allowed


def run(plugin_name: str, frame_data, tracker_context,
        mapping: Dict[str, str]) -> List[DetectionEvent]:
    """
    Evaluates this camera's zones and returns the events to publish.

    `mapping` names the event types this plugin uses for the four outcomes:
    entry, loiter, draw (the zone outline overlay) and track (the live
    intruder box). Both draw types are in the persistence layer's ignore
    list, so they light the overlay without writing a database row per frame.
    """
    camera_id = frame_data.camera_id
    zones = zone_registry.for_camera(camera_id)
    if not zones:
        # No zone drawn for this camera: emit nothing at all. Previously this
        # plugin published a full-frame polygon overlay every frame for every
        # camera whether or not anybody had configured one.
        return []
    if not owns_camera(plugin_name, camera_id):
        return []

    now = float(frame_data.timestamp)
    local_now = datetime.now()
    state = tracker_context.get_state(MONITOR_STATE, camera_id)

    try:
        hits = service.evaluate(camera_id, frame_data.detections, zones, state,
                                now=now, local_now=local_now)
    except Exception as exc:
        logger.error(f"Zone evaluation failed on {camera_id}: {exc}")
        return []

    events: List[DetectionEvent] = [
        DetectionEvent(
            plugin_name=plugin_name,
            event_type=mapping["draw"],
            camera_id=camera_id,
            timestamp=now,
            confidence=1.0,
            metadata={"drawings": service.zone_outline_drawings(zones, local_now),
                      "zone_count": len(zones)},
        )
    ]

    camera_name = getattr(frame_data, "camera_url", "") or camera_id
    zone_by_id = {z["zone_id"]: z for z in zones}

    for hit in hits:
        if hit.event_type == service.ZONE_EXIT:
            # Logged for the dwell record, never alarmed: somebody leaving a
            # restricted area is the outcome you wanted.
            _log(hit, camera_name, None, zone_by_id)
            continue

        snapshot = None
        try:
            snapshot = save_event_snapshot(
                "zone", camera_id,
                frame_for_snapshot(frame_data, tracker_context, camera_id),
                bbox=hit.bbox,
            )
        except Exception as exc:
            logger.warning(f"Zone snapshot failed on {camera_id}: {exc}")

        _log(hit, camera_name, snapshot, zone_by_id)

        events.append(DetectionEvent(
            plugin_name=plugin_name,
            event_type=(mapping["entry"] if hit.event_type == service.ZONE_ENTRY
                        else mapping["loiter"]),
            camera_id=camera_id,
            timestamp=hit.timestamp,
            confidence=float(hit.confidence or 1.0),
            snapshot_path=snapshot,
            metadata={
                "zone_id": hit.zone_id,
                "zone_name": hit.zone_name,
                "zone": hit.points,
                "severity": hit.severity,
                "track_id": hit.track_id,
                "class_id": hit.class_id,
                "class_name": hit.class_name,
                "dwell_seconds": hit.dwell_seconds,
                "time_spent": hit.dwell_seconds,      # legacy key the feed reads
                "schedule": describe_schedule(
                    (zone_by_id.get(hit.zone_id) or {}).get("schedule")),
                "description": hit.describe(),
                "snapshot_file": snapshot,
                "drawings": service.hit_drawings(hit),
            },
        ))

    live = [h for h in hits if h.event_type != service.ZONE_EXIT]
    if live:
        boxes: List[dict] = []
        for hit in live:
            boxes.extend(service.hit_drawings(hit))
        events.append(DetectionEvent(
            plugin_name=plugin_name,
            event_type=mapping["track"],
            camera_id=camera_id,
            timestamp=now,
            confidence=1.0,
            metadata={"drawings": boxes},
        ))

    return events


def _log(hit, camera_name: str, snapshot: Optional[str],
         zone_by_id: Dict[str, dict]) -> None:
    """Queues the zone event for the dedicated log. Never raises."""
    zone = zone_by_id.get(hit.zone_id) or {}
    # A zone read from the legacy config dict has no row to reference; the
    # FK must stay NULL rather than point at an id that does not exist.
    zone_id = hit.zone_id if not str(hit.zone_id).startswith("legacy:") else None
    try:
        zone_event_log.record({
            "zone_id": zone_id,
            "zone_name": hit.zone_name,
            "camera_id": hit.camera_id,
            "camera_name": camera_name,
            "event_type": hit.event_type,
            "severity": hit.severity,
            "timestamp": datetime.utcfromtimestamp(hit.timestamp),
            "started_at": datetime.utcfromtimestamp(hit.started_at),
            "dwell_seconds": hit.dwell_seconds,
            "track_id": str(hit.track_id) if hit.track_id is not None else None,
            "class_id": hit.class_id,
            "class_name": hit.class_name,
            "confidence": hit.confidence,
            "bbox": [int(v) for v in hit.bbox],
            "snapshot_path": snapshot,
            "details": {
                "anchor": zone.get("anchor"),
                "min_dwell_sec": zone.get("min_dwell_sec"),
                "schedule": describe_schedule(zone.get("schedule")),
            },
        })
    except Exception as exc:
        logger.warning(f"Could not queue zone event: {exc}")


def required_classes() -> List[int]:
    """
    Classes the detector must keep for zone monitoring.

    Derived from the zones that actually exist, so a site watching only for
    vehicles in a bay does not force person detection to be retained, and a
    site with no zones at all still asks for person (the historical default)
    rather than nothing.
    """
    try:
        return zone_registry.all_classes()
    except Exception:
        return [0]
