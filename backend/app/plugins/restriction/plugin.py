"""
Restricted zone monitoring.

The zones, the rules, the schedules and the event log all live in
app/plugins/zones; this file is the engine's entry point into them.

What changed, and why: this plugin used to carry a four-point polygon
compiled into its constructor — the same rectangle across the middle of the
frame on every camera on the site — and alerted the first frame anybody's feet
landed inside it, around the clock. It also published a full-frame overlay
event on every processed frame of every camera whether or not a zone was
configured. Both are gone: zones are what the client drew, and a camera with
no zone produces nothing.
"""

from typing import List

from app.engine.base import BaseDetectionPlugin, DetectionEvent, FrameData, TrackerContext
from app.plugins.zones import adapter

# The event types this plugin publishes. RESTRICTION_ZONE_DRAW and
# RESTRICTION_INTRUDER_TRACK are live-overlay twins re-emitted every frame and
# are on the persistence layer's ignore list; the other two are alerts.
EVENT_TYPES = {
    "entry": "RESTRICTION_ALERT",
    "loiter": "RESTRICTION_LOITERING",
    "draw": "RESTRICTION_ZONE_DRAW",
    "track": "RESTRICTION_INTRUDER_TRACK",
}


class RestrictionZonePlugin(BaseDetectionPlugin):
    """Alerts when a watched class enters a client-defined restricted zone."""

    # Works purely off detection geometry; snapshots reuse the frame the
    # engine already cached for this camera.
    needs_frame = False
    # All mutable state lives in TrackerContext, keyed by camera.
    thread_safe = True

    @property
    def plugin_name(self) -> str:
        return "RestrictionZonePlugin"

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
