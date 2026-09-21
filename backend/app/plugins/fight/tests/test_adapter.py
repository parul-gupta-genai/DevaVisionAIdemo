"""SOW 2.7 — the engine contract, and what an indication carries."""

import math
from unittest.mock import patch

import pytest

from app.plugins.fight import adapter, service

H = 160.0
DT = 1.0 / 14.0


class Det:
    def __init__(self, track_id, bbox, class_id=0):
        self.track_id, self.bbox, self.class_id = track_id, bbox, class_id


class FakeFrameData:
    def __init__(self, detections, camera_id="cam1", timestamp=1000.0):
        self.detections, self.camera_id, self.timestamp = detections, camera_id, timestamp
        self.camera_url = f"rtsp://{camera_id}"
        self.frame = f"frame-{timestamp}"


class FakeCtx:
    def __init__(self):
        self.buckets = {}

    def get_state(self, bucket, camera_id):
        return self.buckets.setdefault((bucket, camera_id), {})


def person(cx, cy=400, h=H):
    w = h * 0.4
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]


def scuffle(step, x=500):
    return [Det(1, person(x + math.sin(step * 2.6) * 0.28 * H,
                          400 + math.sin(step * 3.7) * 0.10 * H)),
            Det(2, person(x + 0.6 * H + math.sin(step * 2.9 + 1) * 0.28 * H,
                          400 + math.sin(step * 4.1) * 0.10 * H))]


@pytest.fixture(autouse=True)
def env():
    with patch.object(adapter.fight_zone_registry, "for_camera", return_value=[]), \
         patch.object(adapter.fight_event_log, "record", return_value=True) as rec, \
         patch.object(adapter, "save_event_snapshot", return_value="snapshots/fight/x.jpg"), \
         patch.object(adapter, "frame_for_snapshot", return_value=None):
        yield rec


def run(ctx, n=60):
    events = []
    for i in range(n):
        events.extend(adapter.run("FightDetectionPlugin",
                                  FakeFrameData(scuffle(i), timestamp=1000.0 + i * DT),
                                  ctx))
    return events


def test_nothing_is_evaluated_until_the_zone_registry_has_loaded():
    ctx = FakeCtx()
    with patch.object(adapter.fight_zone_registry, "for_camera", return_value=None):
        assert run(ctx, 20) == []


def test_only_tracked_people_are_considered():
    """An untracked box has nothing to compare against between frames."""
    ctx = FakeCtx()
    for i in range(60):
        dets = [Det(None, person(500)), Det(2, person(500 + 0.6 * H), class_id=2)]
        adapter.run("FightDetectionPlugin",
                    FakeFrameData(dets, timestamp=1000.0 + i * DT), ctx)
    motion = ctx.get_state(adapter.STATE_BUCKET, "cam1").get("incidents", {})
    assert not [k for k in motion if k != "motion"]


def test_two_cameras_keep_separate_state():
    ctx = FakeCtx()
    for cam in ("cam1", "cam2"):
        adapter.run("FightDetectionPlugin",
                    FakeFrameData(scuffle(0), camera_id=cam), ctx)
    assert (adapter.STATE_BUCKET, "cam1") in ctx.buckets
    assert (adapter.STATE_BUCKET, "cam2") in ctx.buckets
    assert (ctx.buckets[(adapter.STATE_BUCKET, "cam1")]
            is not ctx.buckets[(adapter.STATE_BUCKET, "cam2")])


def test_state_stays_off_the_shared_plugin_instance():
    from app.plugins.fight.plugin import FightDetectionPlugin

    plugin = FightDetectionPlugin()
    ctx = FakeCtx()
    plugin.process_frame(FakeFrameData(scuffle(0)), ctx)
    leaked = [k for k, v in vars(plugin).items()
              if isinstance(v, dict) and v and k != "app_config"]
    assert not leaked, f"per-camera state on the shared plugin: {leaked}"


def test_an_indication_carries_severity_for_the_alert_engine():
    fights = [e for e in run(FakeCtx()) if e.event_type == service.FIGHT_DETECTED]
    assert fights and fights[0].metadata.get("severity") == "critical"


def test_every_indication_says_it_needs_human_verification():
    """SOW 2.7: no consumer may render an indication as a finding of fact."""
    fights = [e for e in run(FakeCtx()) if e.event_type == service.FIGHT_DETECTED]
    meta = fights[0].metadata
    assert meta.get("requires_human_verification") is True
    assert "does not replace" in meta.get("advisory_notice", "").lower()


def test_the_overlay_event_is_the_only_per_frame_one():
    events = run(FakeCtx())
    fights = [e for e in events if e.event_type == service.FIGHT_DETECTED]
    assert len(fights) == 1


class FakeClassifier:
    """Stand-in for ml_classifier.FightMLClassifier — returns a fixed score
    regardless of the frame buffer contents, so tests don't need real video."""

    def __init__(self, fixed_score):
        self.fixed_score = fixed_score
        self.test_accuracy = 0.85

    def score(self, frames):
        return self.fixed_score


def test_ml_confirmation_boosts_confidence_and_is_recorded():
    with patch.object(adapter, "_get_classifier", return_value=FakeClassifier(0.9)):
        fights = [e for e in run(FakeCtx()) if e.event_type == service.FIGHT_DETECTED]
    hit = fights[0]
    assert hit.metadata["ml_score"] == 0.9
    assert hit.metadata["ml_disagreed"] is False
    # boosted (or at worst unchanged if the heuristic was already at the 1.0 cap)
    assert hit.confidence >= hit.metadata["score"]


def test_ml_veto_downranks_but_does_not_drop_the_indication():
    with patch.object(adapter, "_get_classifier", return_value=FakeClassifier(0.05)):
        fights = [e for e in run(FakeCtx()) if e.event_type == service.FIGHT_DETECTED]
    # Still surfaced for human review (SOW 2.7: never silently discarded) —
    # just down-ranked and flagged so a reviewer can see the disagreement.
    assert len(fights) == 1
    hit = fights[0]
    assert hit.metadata["ml_score"] == 0.05
    assert hit.metadata["ml_disagreed"] is True
    assert hit.confidence < hit.metadata["score"]


def test_missing_classifier_leaves_the_heuristic_behaviour_unchanged():
    """If the model file isn't deployed yet, this must behave exactly like
    the plugin did before the ML classifier existed — no crash, no ml_score."""
    with patch.object(adapter, "_get_classifier", return_value=None):
        fights = [e for e in run(FakeCtx()) if e.event_type == service.FIGHT_DETECTED]
    hit = fights[0]
    assert "ml_score" not in hit.metadata
    assert hit.confidence == hit.metadata["score"]


def test_frame_buffer_is_populated_per_camera_not_shared():
    """Two cameras must not see each other's frames in the ML buffer —
    same per-camera isolation principle as the incident/motion state."""
    ctx = FakeCtx()
    fd1 = FakeFrameData(scuffle(0), camera_id="cam1")
    fd1.frame = "cam1-frame"
    fd2 = FakeFrameData(scuffle(0), camera_id="cam2")
    fd2.frame = "cam2-frame"
    adapter.run("FightDetectionPlugin", fd1, ctx)
    adapter.run("FightDetectionPlugin", fd2, ctx)
    buf1 = ctx.get_state(adapter.STATE_BUCKET, "cam1")["frame_buffer"]
    buf2 = ctx.get_state(adapter.STATE_BUCKET, "cam2")["frame_buffer"]
    assert list(buf1) == ["cam1-frame"]
    assert list(buf2) == ["cam2-frame"]


def test_the_incident_is_queued_unverified(env):
    run(FakeCtx())
    assert env.called
    payload = env.call_args[0][0]
    assert "verified" not in payload, "an unreviewed indication must not be pre-verified"
    for key in ("event_type", "severity", "timestamp", "score", "track_ids"):
        assert key in payload


def test_event_metadata_is_json_serialisable():
    import json
    for e in run(FakeCtx()):
        json.dumps(e.metadata, default=str)


def test_an_evaluation_fault_does_not_raise():
    ctx = FakeCtx()
    with patch.object(adapter.service, "evaluate", side_effect=RuntimeError("boom")):
        assert adapter.run("FightDetectionPlugin", FakeFrameData(scuffle(0)), ctx) == []


def test_a_snapshot_failure_does_not_lose_the_indication():
    with patch.object(adapter, "save_event_snapshot", side_effect=OSError("disk full")):
        events = run(FakeCtx())
    assert any(e.event_type == service.FIGHT_DETECTED for e in events)


class FakeFaceEmotionClassifier:
    def __init__(self, fixed_aggression=0.8, emotion="anger"):
        self.fixed_aggression = fixed_aggression
        self.emotion = emotion

    def analyze(self, frame_bgr):
        return [{
            "bbox": [10.0, 10.0, 50.0, 50.0],
            "emotion": self.emotion,
            "scores": {"anger": self.fixed_aggression},
            "aggression_score": self.fixed_aggression,
        }]


def test_face_emotion_integration_boosts_confidence_and_adds_metadata():
    import numpy as np
    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    ctx = FakeCtx()
    events = []
    fake_classifier = FakeFaceEmotionClassifier(0.85, "anger")
    with patch.object(adapter, "_get_face_emotion_classifier", return_value=fake_classifier):
        for i in range(60):
            fd = FakeFrameData(scuffle(i), timestamp=1000.0 + i * DT)
            fd.frame = dummy_frame
            events.extend(adapter.run("FightDetectionPlugin", fd, ctx))

    fights = [e for e in events if e.event_type == service.FIGHT_DETECTED]
    assert len(fights) == 1
    hit = fights[0]
    assert hit.metadata.get("face_aggression_score") == 0.85
    assert hit.metadata.get("face_emotions") == ["anger"]


def test_missing_face_emotion_classifier_leaves_detection_unaffected():
    with patch.object(adapter, "_get_face_emotion_classifier", return_value=None):
        fights = [e for e in run(FakeCtx()) if e.event_type == service.FIGHT_DETECTED]
    hit = fights[0]
    assert "face_aggression_score" not in hit.metadata

