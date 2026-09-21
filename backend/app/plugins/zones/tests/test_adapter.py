"""
SOW 2.9 — Alert generation and event logging.

The adapter turns zone hits into published events and log rows. Its two
load-bearing jobs beyond that: a camera with no zone must produce absolutely
nothing, and a camera with both zone plugins enabled must produce ONE alert
rather than two.
"""

from datetime import datetime

import pytest

from app.engine.base import FrameData, NormalizedDetection, TrackerContext
from app.plugins.zones import adapter, service

SQUARE = [[100, 100], [500, 100], [500, 500], [100, 500]]
INSIDE = [250, 200, 350, 400]

MAPPING = {
    "entry": "RESTRICTION_ALERT",
    "loiter": "RESTRICTION_LOITERING",
    "draw": "RESTRICTION_ZONE_DRAW",
    "track": "RESTRICTION_INTRUDER_TRACK",
}


def zone(**over):
    z = {
        "zone_id": "z1", "name": "Switchyard", "points": SQUARE,
        "classes": [0], "min_confidence": 0.4, "min_box_px": 0,
        "anchor": "FEET", "min_dwell_sec": 0.0, "loiter_sec": None,
        "exit_grace_sec": 3.0, "alert_cooldown_sec": 0.0,
        "severity": "critical", "is_active": True, "schedule": None,
    }
    z.update(over)
    return z


def frame(t=100.0, dets=None):
    return FrameData(frame=None,
                     detections=dets if dets is not None else
                     [NormalizedDetection(bbox=list(INSIDE), track_id=1,
                                          class_id=0, confidence=0.9)],
                     camera_id="cam1", timestamp=t, camera_url="Gate Camera")


class FakeLog:
    def __init__(self):
        self.rows = []

    def record(self, row):
        self.rows.append(row)


class FakeRegistry:
    def __init__(self, zones):
        self.zones = zones

    def for_camera(self, camera_id):
        return self.zones


@pytest.fixture
def wired(monkeypatch):
    """Adapter with its registry, log and snapshot writer replaced."""
    log = FakeLog()
    monkeypatch.setattr(adapter, "zone_event_log", log)
    monkeypatch.setattr(adapter, "zone_registry", FakeRegistry([zone()]))
    monkeypatch.setattr(adapter, "save_event_snapshot",
                        lambda *a, **k: "snapshots/zone/x.jpg")
    monkeypatch.setattr(adapter, "frame_for_snapshot", lambda *a, **k: None)
    return log


def run(ctx=None, fr=None):
    return adapter.run("RestrictionZonePlugin", fr or frame(),
                       ctx or TrackerContext(), MAPPING)


def kinds(events):
    return [e.event_type for e in events]


# ----------------------------------------------------------------------
# A camera with no zone
# ----------------------------------------------------------------------
def test_a_camera_with_no_zone_produces_nothing(monkeypatch):
    """
    This plugin used to publish a full-frame polygon overlay every frame on
    every camera whether or not anybody had drawn a zone.
    """
    monkeypatch.setattr(adapter, "zone_registry", FakeRegistry([]))
    assert run() == []


# ----------------------------------------------------------------------
# Two plugins, one alert
# ----------------------------------------------------------------------
def test_the_primary_plugin_always_owns_the_camera():
    assert adapter.owns_camera(adapter.PRIMARY_PLUGIN, "cam1") is True


def test_the_secondary_plugin_stands_down_when_both_are_enabled(monkeypatch):
    from config.config import config
    monkeypatch.setattr(config, "CAMERA_PLUGINS", {
        "cam1": ["RestrictionZonePlugin", "IntrusionDetectionPlugin"]})
    assert adapter.owns_camera("RestrictionZonePlugin", "cam1") is False


def test_the_secondary_plugin_evaluates_when_it_is_the_only_one(monkeypatch):
    from config.config import config
    monkeypatch.setattr(config, "CAMERA_PLUGINS", {
        "cam1": ["RestrictionZonePlugin"]})
    assert adapter.owns_camera("RestrictionZonePlugin", "cam1") is True


def test_a_stood_down_plugin_emits_nothing(wired, monkeypatch):
    from config.config import config
    monkeypatch.setattr(config, "CAMERA_PLUGINS", {
        "cam1": ["RestrictionZonePlugin", "IntrusionDetectionPlugin"]})
    assert run() == []
    assert wired.rows == []


def test_ownership_fails_open_if_the_config_is_unreadable(monkeypatch):
    """Losing the plugin list must not silently stop zone monitoring."""
    import config.config as cfg
    monkeypatch.delattr(cfg, "config", raising=False)
    assert adapter.owns_camera("RestrictionZonePlugin", "cam1") is True


# ----------------------------------------------------------------------
# What gets published
# ----------------------------------------------------------------------
def test_the_zone_outline_is_published_even_with_nobody_in_it(wired, monkeypatch):
    monkeypatch.setattr(adapter, "zone_registry", FakeRegistry([zone()]))
    events = run(fr=frame(dets=[]))
    assert kinds(events) == ["RESTRICTION_ZONE_DRAW"]
    assert events[0].metadata["zone_count"] == 1


def test_an_intrusion_publishes_outline_alert_and_live_box(wired):
    events = run()
    assert kinds(events) == ["RESTRICTION_ZONE_DRAW", "RESTRICTION_ALERT",
                             "RESTRICTION_INTRUDER_TRACK"]


def test_the_alert_carries_what_an_operator_needs(wired):
    alert = next(e for e in run() if e.event_type == "RESTRICTION_ALERT")
    md = alert.metadata
    assert md["zone_name"] == "Switchyard"
    assert md["severity"] == "critical"
    assert md["class_name"] == "person"
    assert md["description"] == "Person entered Switchyard"
    assert md["schedule"] == "Always armed"
    assert md["zone"] == SQUARE
    assert alert.snapshot_path == "snapshots/zone/x.jpg"
    # The events feed reads a legacy key; both must be present.
    assert md["time_spent"] == md["dwell_seconds"]


def test_loitering_uses_the_loiter_event_type(wired, monkeypatch):
    monkeypatch.setattr(adapter, "zone_registry",
                        FakeRegistry([zone(loiter_sec=10)]))
    ctx = TrackerContext()
    run(ctx, frame(t=100.0))
    events = run(ctx, frame(t=115.0))
    assert "RESTRICTION_LOITERING" in kinds(events)


# ----------------------------------------------------------------------
# Event logging
# ----------------------------------------------------------------------
def test_every_alert_is_logged(wired):
    run()
    assert len(wired.rows) == 1
    row = wired.rows[0]
    assert row["zone_name"] == "Switchyard"
    assert row["camera_id"] == "cam1"
    assert row["camera_name"] == "Gate Camera"
    assert row["event_type"] == service.ZONE_ENTRY
    assert row["severity"] == "critical"
    assert row["snapshot_path"] == "snapshots/zone/x.jpg"
    assert isinstance(row["timestamp"], datetime)
    assert row["track_id"] == "1"                      # stringified for the column


def test_an_exit_is_logged_but_never_alerted(wired):
    ctx = TrackerContext()
    run(ctx, frame(t=100.0))
    events = run(ctx, frame(t=110.0, dets=[]))
    assert "RESTRICTION_ALERT" not in kinds(events)
    assert [r["event_type"] for r in wired.rows][-1] == service.ZONE_EXIT


def test_a_legacy_config_zone_does_not_forge_a_foreign_key(wired, monkeypatch):
    """A zone with no database row must leave zone_id NULL, not dangling."""
    monkeypatch.setattr(adapter, "zone_registry",
                        FakeRegistry([zone(zone_id="legacy:cam1")]))
    run()
    assert wired.rows[0]["zone_id"] is None
    assert wired.rows[0]["zone_name"] == "Switchyard"


def test_a_real_zone_keeps_its_foreign_key(wired):
    run()
    assert wired.rows[0]["zone_id"] == "z1"


# ----------------------------------------------------------------------
# Nothing here may take the pipeline down
# ----------------------------------------------------------------------
def test_an_evaluation_failure_is_contained(wired, monkeypatch):
    monkeypatch.setattr(service, "evaluate",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert run() == []


def test_a_snapshot_failure_still_publishes_and_logs_the_alert(wired, monkeypatch):
    monkeypatch.setattr(adapter, "save_event_snapshot",
                        lambda *a, **k: (_ for _ in ()).throw(IOError("disk full")))
    events = run()
    assert "RESTRICTION_ALERT" in kinds(events)
    assert len(wired.rows) == 1
    assert wired.rows[0]["snapshot_path"] is None


def test_a_logging_failure_does_not_lose_the_alert(wired, monkeypatch):
    class Broken:
        def record(self, row):
            raise RuntimeError("queue closed")

    monkeypatch.setattr(adapter, "zone_event_log", Broken())
    assert "RESTRICTION_ALERT" in kinds(run())


# ----------------------------------------------------------------------
# Detector classes
# ----------------------------------------------------------------------
def test_required_classes_falls_back_to_person(monkeypatch):
    class Broken:
        def all_classes(self):
            raise RuntimeError("no db")

    monkeypatch.setattr(adapter, "zone_registry", Broken())
    assert adapter.required_classes() == [0]


# ----------------------------------------------------------------------
# The plugin surface the engine sees
# ----------------------------------------------------------------------
def test_the_plugin_declares_its_contract():
    from app.plugins.restriction.plugin import RestrictionZonePlugin

    p = RestrictionZonePlugin()
    assert p.plugin_name == "RestrictionZonePlugin"
    # Zone work is pure geometry; snapshots reuse the engine's cached frame.
    assert RestrictionZonePlugin.needs_frame is False
    # All state lives in TrackerContext, keyed by camera.
    assert RestrictionZonePlugin.thread_safe is True


def test_the_plugin_delegates_evaluation_to_the_shared_monitor(wired):
    from app.plugins.restriction.plugin import RestrictionZonePlugin

    events = RestrictionZonePlugin().process_frame(frame(), TrackerContext())
    assert "RESTRICTION_ALERT" in kinds(events)


def test_both_plugins_share_one_state_bucket():
    """
    The dedup only works because both advance the same visits and cooldowns,
    under a name that belongs to neither plugin.
    """
    assert adapter.MONITOR_STATE == "ZoneMonitor"
    assert adapter.MONITOR_STATE != adapter.PRIMARY_PLUGIN
