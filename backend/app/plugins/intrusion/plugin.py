"""
Intrusion detection over client-defined restricted zones.

Shares one monitor with RestrictionZonePlugin (see app/plugins/zones/adapter),
so a camera with both enabled — 61 of the 62 zone-enabled cameras here —
raises one intrusion rather than two. This plugin is the primary evaluator
when both are on, because INTRUSION_DETECTED is the event type the alert
engine escalates and the events feed already renders.

Loitering is now an escalation of a confirmed intrusion rather than a separate
timer: a track has to satisfy the zone's dwell rule first, and the loitering
threshold is per zone instead of one global LOITERING_THRESHOLD_SECONDS. The
old timer also reset the moment a track's box slipped outside the polygon for
a single frame, so somebody pacing the boundary never accumulated any dwell
at all.
"""

from typing import List

from app.engine.base import BaseDetectionPlugin, DetectionEvent, FrameData, TrackerContext
from app.plugins.zones import adapter

EVENT_TYPES = {
    "entry": "INTRUSION_DETECTED",
    "loiter": "LOITERING_DETECTED",
    # Reuses the restriction overlay types: they are the same zones drawn on
    # the same video, and both are already excluded from database writes.
    "draw": "RESTRICTION_ZONE_DRAW",
    "track": "RESTRICTION_INTRUDER_TRACK",
}


class IntrusionDetectionPlugin(BaseDetectionPlugin):
    """Raises INTRUSION_DETECTED and LOITERING_DETECTED for restricted zones."""

    needs_frame = False
    thread_safe = True

    @property
    def plugin_name(self) -> str:
        return "IntrusionDetectionPlugin"

    def get_required_classes(self) -> List[int]:
        return adapter.required_classes()

    def process_frame(self, frame_data: FrameData,
                      tracker_context: TrackerContext) -> List[DetectionEvent]:
        return adapter.run(self.plugin_name, frame_data, tracker_context, EVENT_TYPES)

    def health(self) -> dict:
        from app.plugins.zones.repository import zone_event_log, zone_registry

        zone_registry.refresh()
        return {
            "status": "ok",
            "cameras_with_zones": len(zone_registry.by_camera),
            "zones": sum(len(v) for v in zone_registry.by_camera.values()),
            "event_log": zone_event_log.health(),
        }
