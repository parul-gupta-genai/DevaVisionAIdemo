"""
SOW 2.8 — the bridge to the plugin engine.

These are the tests for the engine contract rather than the detection logic:
what happens when pixels are missing, when the zone registry has not loaded,
when one camera's state must not leak into another's, and whether the events
that come out carry what the feed, the alert engine and the log each need.
"""

from unittest.mock import patch

import numpy as np
import pytest

from app.plugins.fire import adapter, detector as det, service


H, W = 720, 1280


class FakeFrameData:
    def __init__(self, camera_id="cam1", frame=None, timestamp=1000.0):
        self.camera_id = camera_id
        self.frame = frame
        self.timestamp = timestamp
        self.camera_url = f"rtsp://{camera_id}"
        self.detections = []


class FakeTrackerContext:
    """Mirrors the engine's per-camera state bucket."""

    def __init__(self):
        self.buckets = {}

    def get_state(self, bucket, camera_id):
        return self.buckets.setdefault((bucket, camera_id), {})


def flame_frame(phase=0, cx=640, cy=400):
    """
    A flame front on a textured yard.

    The shape has to change substantially between calls, because that is both
    what a real flame does and the only thing the detector uses to tell one
    from a traffic cone. The plugin samples roughly once a second, so
    consecutive calls see a flame that has moved on a long way — a gently
    breathing blob is not a realistic stimulus at this rate.
    """
    import cv2
    rng = np.random.default_rng(phase % 977)
    f = np.full((H, W, 3), 70, np.uint8)
    f[:, ::40] = 190
    f[::40, :] = 190
    for i in range(6):
        ph = phase * 2.3 + i * 1.7
        rx = max(10, int(75 + 45 * np.sin(ph) + rng.integers(-18, 19)))
        ry = max(10, int(80 + 50 * np.sin(ph * 1.6 + 0.9) + rng.integers(-18, 19)))
        ox = int(28 * np.sin(ph * 0.7)) + int(rng.integers(-10, 11))
        oy = int(24 * np.sin(ph * 1.1)) + int(rng.integers(-10, 11))
        cv2.ellipse(f, (cx + ox, cy + oy), (rx, ry), 0, 0, 360,
                    (20, int(190 + rng.integers(-35, 36)), 255), -1)
    return f


@pytest.fixture(autouse=True)
def zones_loaded():
    """Default: the registry has loaded and this camera has no zones."""
    with patch.object(adapter.fire_zone_registry, "for_camera", return_value=[]):
        yield


@pytest.fixture(autouse=True)
def no_db_writes():
    with patch.object(adapter.fire_event_log, "record", return_value=True) as rec:
        yield rec


@pytest.fixture(autouse=True)
def no_snapshots():
    with patch.object(adapter, "save_event_snapshot",
                      return_value="snapshots/fire/x.jpg"), \
         patch.object(adapter, "frame_for_snapshot", return_value=None):
        yield


# ----------------------------------------------------------------------
# missing pixels
# ----------------------------------------------------------------------
def test_a_call_without_pixels_returns_nothing():
    ctx = FakeTrackerContext()
    assert adapter.run("FireDetectionPlugin", FakeFrameData(frame=None), ctx) == []


def test_a_call_without_pixels_does_not_advance_the_state_machine():
    """
    needs_frame is a request, not a guarantee. A gap in pixel supply must not
    look like a fire going out, or a camera the engine is starving of frames
    would report an all-clear on a live fire.
    """
    ctx = FakeTrackerContext()
    for i in range(6):
        adapter.run("FireDetectionPlugin",
                    FakeFrameData(frame=flame_frame(i), timestamp=1000.0 + i), ctx)
    before = dict(ctx.get_state(adapter.STATE_BUCKET, "cam1").get("incidents", {}))

    for i in range(30):
        adapter.run("FireDetectionPlugin",
                    FakeFrameData(frame=None, timestamp=1010.0 + i), ctx)
    after = ctx.get_state(adapter.STATE_BUCKET, "cam1").get("incidents", {})
    assert set(after) == set(before), "a pixel gap changed the incident state"


# ----------------------------------------------------------------------
# registry not loaded
# ----------------------------------------------------------------------
def test_nothing_is_evaluated_until_the_zone_registry_has_loaded():
    """
    Guessing "no zones" during a database outage would mean whole-frame
    monitoring with this camera's EXCLUSION zones missing — the welding bay
    would start alarming. Holding off is the safe read.
    """
    ctx = FakeTrackerContext()
    with patch.object(adapter.fire_zone_registry, "for_camera", return_value=None):
        out = [adapter.run("FireDetectionPlugin",
                           FakeFrameData(frame=flame_frame(i), timestamp=1000.0 + i),
                           ctx)
               for i in range(10)]
    assert all(o == [] for o in out)


def test_evaluation_resumes_once_the_registry_loads():
    ctx = FakeTrackerContext()
    with patch.object(adapter.fire_zone_registry, "for_camera", return_value=None):
        adapter.run("FireDetectionPlugin", FakeFrameData(frame=flame_frame(0)), ctx)
    events = []
    for i in range(10):
        events.extend(adapter.run(
            "FireDetectionPlugin",
            FakeFrameData(frame=flame_frame(i), timestamp=1000.0 + i), ctx))
    assert any(e.event_type == service.FIRE_DETECTED for e in events)


# ----------------------------------------------------------------------
# per-camera isolation
# ----------------------------------------------------------------------
def test_two_cameras_do_not_share_an_analyzer():
    """
    One plugin instance serves every camera. A shared FrameAnalyzer would
    average twenty-five backgrounds into one and make smoke undetectable
    everywhere.
    """
    ctx = FakeTrackerContext()
    for cam in ("cam1", "cam2"):
        adapter.run("FireDetectionPlugin",
                    FakeFrameData(camera_id=cam, frame=flame_frame(0)), ctx)
    a1 = ctx.get_state(adapter.STATE_BUCKET, "cam1")["analyzer"]
    a2 = ctx.get_state(adapter.STATE_BUCKET, "cam2")["analyzer"]
    assert a1 is not a2


def test_state_stays_in_the_tracker_context_not_on_the_plugin():
    from app.plugins.fire.plugin import FireDetectionPlugin

    plugin = FireDetectionPlugin()
    ctx = FakeTrackerContext()
    plugin.process_frame(FakeFrameData(frame=flame_frame(0)), ctx)
    assert ctx.buckets, "nothing was written to the per-camera bucket"
    leaked = [k for k, v in vars(plugin).items()
              if isinstance(v, dict) and v and k != "app_config"]
    assert not leaked, f"per-camera state left on the shared plugin: {leaked}"


# ----------------------------------------------------------------------
# the frame is not ours
# ----------------------------------------------------------------------
def test_the_incoming_frame_is_never_modified():
    """The engine caches this same array and later hands it to the snapshotter."""
    ctx = FakeTrackerContext()
    frame = flame_frame(0)
    original = frame.copy()
    adapter.run("FireDetectionPlugin", FakeFrameData(frame=frame), ctx)
    assert np.array_equal(frame, original)


# ----------------------------------------------------------------------
# what the events carry
# ----------------------------------------------------------------------
def _run_until_fire(ctx, n=12):
    events = []
    for i in range(n):
        events.extend(adapter.run(
            "FireDetectionPlugin",
            FakeFrameData(frame=flame_frame(i), timestamp=1000.0 + i), ctx))
    return events


def test_a_confirmed_fire_carries_severity_for_the_alert_engine():
    """A missing severity is treated as critical by the alert engine."""
    fires = [e for e in _run_until_fire(FakeTrackerContext())
             if e.event_type == service.FIRE_DETECTED]
    assert fires
    assert fires[0].metadata.get("severity") == "critical"


def test_a_confirmed_fire_carries_the_snapshot_on_both_channels():
    """The feed reads metadata; the fire API reads the top-level field."""
    fires = [e for e in _run_until_fire(FakeTrackerContext())
             if e.event_type == service.FIRE_DETECTED]
    assert fires[0].snapshot_path
    assert fires[0].metadata.get("snapshot_file") == fires[0].snapshot_path


def test_a_confirmed_fire_keeps_the_legacy_fire_boxes_key():
    fires = [e for e in _run_until_fire(FakeTrackerContext())
             if e.event_type == service.FIRE_DETECTED]
    boxes = fires[0].metadata.get("fire_boxes")
    assert boxes and len(boxes[0]) == 4


def test_every_incident_carries_the_statutory_notice():
    fires = [e for e in _run_until_fire(FakeTrackerContext())
             if e.event_type == service.FIRE_DETECTED]
    text = fires[0].metadata.get("statutory_notice", "").lower()
    assert "does not replace" in text or "not replace" in text


def test_the_overlay_event_is_the_only_per_frame_one():
    events = _run_until_fire(FakeTrackerContext(), n=50)
    stats = [e for e in events if e.event_type == adapter.STATS_EVENT]
    fires = [e for e in events if e.event_type == service.FIRE_DETECTED]
    assert len(stats) > len(fires), "the incident event is not rate limited"
    assert len(fires) == 1


def test_the_incident_is_queued_for_the_dedicated_log(no_db_writes):
    _run_until_fire(FakeTrackerContext())
    assert no_db_writes.called
    payload = no_db_writes.call_args[0][0]
    for key in ("event_type", "kind", "severity", "timestamp", "started_at",
                "camera_id", "score", "bbox", "details"):
        assert key in payload, f"log payload is missing {key}"


def test_event_metadata_is_json_serialisable():
    """Anything not JSON-safe is dropped downstream, silently."""
    import json

    for e in _run_until_fire(FakeTrackerContext()):
        json.dumps(e.metadata, default=str)


# ----------------------------------------------------------------------
# robustness
# ----------------------------------------------------------------------
def test_a_detector_fault_on_one_camera_does_not_raise():
    """The engine swallows exceptions, so a raising plugin looks like silence."""
    ctx = FakeTrackerContext()
    with patch.object(det.FrameAnalyzer, "analyze", side_effect=RuntimeError("boom")):
        assert adapter.run("FireDetectionPlugin",
                           FakeFrameData(frame=flame_frame(0)), ctx) == []


def test_a_snapshot_failure_does_not_lose_the_alert():
    ctx = FakeTrackerContext()
    with patch.object(adapter, "save_event_snapshot",
                      side_effect=OSError("disk full")):
        events = _run_until_fire(ctx)
    assert any(e.event_type == service.FIRE_DETECTED for e in events)


def test_the_zone_mask_is_cached_between_frames():
    ctx = FakeTrackerContext()
    poly = [[100, 100], [1100, 100], [1100, 650], [100, 650]]
    zones = [{"zone_id": "Z", "name": "Yard", "camera_id": "cam1",
              "points": poly, "zone_kind": "DETECT", "is_active": True,
              "watch": ["fire"], "sensitivity": "standard", "overrides": {},
              "schedule": None, "severity": None}]
    with patch.object(adapter.fire_zone_registry, "for_camera", return_value=zones), \
         patch.object(adapter.det, "build_mask",
                      wraps=adapter.det.build_mask) as build:
        for i in range(6):
            adapter.run("FireDetectionPlugin",
                        FakeFrameData(frame=flame_frame(i), timestamp=1000.0 + i),
                        ctx)
    assert build.call_count == 1, (
        f"the zone mask was rebuilt {build.call_count} times for unchanged zones")
