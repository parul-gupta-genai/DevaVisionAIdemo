"""
The bridge between the fight state machine and the plugin engine.

Two things it still has to get right, both learned the hard way in 2.8.

Per-camera state lives in tracker_context's bucket, never on the plugin
instance — one instance serves every camera and the dispatcher runs six
worker threads, so instance state would interleave twenty-five cameras'
motion histories into one.

When the zone registry has never loaded, evaluation holds off rather than
guessing. Guessing "no zones" during a database outage would mean whole-frame
monitoring with every EXCLUDE zone missing, so the gym and the loading crew
an operator carefully excluded would start raising incidents — which is
exactly how a security aid gets switched off.

ML CLASSIFIER (added on top of the original bbox-only heuristic):

service.evaluate() still runs every frame on box arithmetic alone — that
part is unchanged and just as cheap as before. Separately, this module keeps
a short rolling buffer of recent raw frames per camera (a plain deque in the
per-camera state bucket) and, ONLY on the frames where evaluate() actually
returns a FIGHT_DETECTED hit, runs that buffer through the trained
motion/optical-flow classifier in ml_classifier.py. That's the expensive
part (dense optical flow over ~20 frames), so gating it behind an
already-flagged hit keeps it rare — for a 25-camera wall where fights are
(hopefully) uncommon, this adds negligible average load, unlike running it
every frame would.

The ML score is used to ADJUST, not override, the heuristic's own verdict:
  - ML agrees (score above FIGHT_CONFIRM_THRESHOLD): the event is emitted
    with combined/boosted confidence.
  - ML disagrees strongly (score below FIGHT_VETO_THRESHOLD): the event's
    confidence is reduced and it's marked "ml_disagreed" in metadata rather
    than silently dropped — a human reviewer can still see and override it.
    Silently swallowing a heuristic hit felt too aggressive for a security
    aid whose stated purpose is "every indication requires human
    verification" (see plugin.py's docstring); down-ranking a likely false
    positive is the safer middle ground until this combination has been
    validated against real camera footage.
  - Classifier unavailable (model file missing, or frame buffer too short
    yet) or ML score in between: behaves exactly as before this change —
    the heuristic's own event goes out unmodified.
"""

from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from app.engine.base import DetectionEvent
from app.engine.snapshots import frame_for_snapshot, save_event_snapshot
from app.plugins.fight import service
from app.plugins.fight.dynamics import ADVISORY_NOTICE
from app.plugins.fight.repository import fight_event_log, fight_zone_registry
from app.plugins.fight.rules import describe_schedule, describe_tuning

STATE_BUCKET = "FightMonitor"
STATS_EVENT = "FIGHT_STATS"

PERSON_CLASS = 0

# How many recent frames to keep per camera for the ML classifier. Matches
# ml_classifier.py's N_SAMPLE_FRAMES so the buffer is exactly one clip's
# worth once full — no point holding more.
FRAME_BUFFER_SIZE = 20

# Score thresholds for the ML second-opinion. Deliberately conservative
# (wide "unsure" middle band) until validated on real footage — see the
# module docstring above.
FIGHT_CONFIRM_THRESHOLD = 0.6
FIGHT_VETO_THRESHOLD = 0.2

_classifier = None
_classifier_load_failed = False
_face_emotion = None
_face_emotion_load_failed = False


def _get_classifier():
    """Lazy-load the ML classifier once per process; never raise past here —
    a missing/broken model file must not take down the (working) heuristic.
    """
    global _classifier, _classifier_load_failed
    if _classifier is not None or _classifier_load_failed:
        return _classifier
    try:
        from app.plugins.fight.ml_classifier import FightMLClassifier
        _classifier = FightMLClassifier()
        logger.info(
            f"Fight ML classifier loaded (test_accuracy={_classifier.test_accuracy})"
        )
    except Exception as exc:
        _classifier_load_failed = True
        logger.warning(
            f"Fight ML classifier unavailable ({exc}); continuing with the "
            "box-only heuristic alone, unchanged from before this feature."
        )
    return _classifier


def _get_face_emotion_classifier():
    """Lazy-load the face emotion classifier once per process; never raise past here."""
    global _face_emotion, _face_emotion_load_failed
    if _face_emotion is not None or _face_emotion_load_failed:
        return _face_emotion
    try:
        from app.plugins.fight.face_emotion import FaceEmotionClassifier
        _face_emotion = FaceEmotionClassifier()
        logger.info("Fight face emotion classifier loaded")
    except Exception as exc:
        _face_emotion_load_failed = True
        logger.warning(
            f"Fight face emotion classifier unavailable ({exc}); continuing without facial aggression signals."
        )
    return _face_emotion


def _person_boxes(frame_data) -> List[tuple]:
    """
    Tracked people only.

    A detection with no track_id is useless here: every signal this module
    uses is a difference between two observations of the SAME person, so an
    untracked box has nothing to compare against.
    """
    out = []
    for det in getattr(frame_data, "detections", None) or []:
        if getattr(det, "class_id", None) != PERSON_CLASS:
            continue
        track_id = getattr(det, "track_id", None)
        bbox = getattr(det, "bbox", None)
        if track_id is None or not bbox or len(bbox) < 4:
            continue
        out.append((track_id, [float(v) for v in bbox[:4]]))
    return out


def run(plugin_name: str, frame_data, tracker_context) -> List[DetectionEvent]:
    """
    One frame of fight monitoring for one camera. Never raises: the engine
    swallows exceptions, so a raising plugin looks exactly like a quiet one.
    """
    camera_id = frame_data.camera_id
    state = tracker_context.get_state(STATE_BUCKET, camera_id)
    now = float(frame_data.timestamp)
    local_now = datetime.now()

    try:
        zones = fight_zone_registry.for_camera(camera_id)
    except Exception as exc:
        logger.warning(f"Fight zone lookup failed on {camera_id}: {exc}")
        zones = None
    if zones is None:
        if not state.get("warned_unloaded"):
            state["warned_unloaded"] = True
            logger.warning(f"Fight zones not loaded yet; holding off on {camera_id}")
        return []
    state.pop("warned_unloaded", None)

    boxes = _person_boxes(frame_data)

    # Cheap: append to the rolling buffer every frame. The buffer itself is
    # just a deque of references to already-decoded frame arrays (no copy,
    # no resize, no optical flow here) — that work only happens below, and
    # only on the rare frame where a hit actually fires.
    frame_buffer = state.setdefault("frame_buffer", deque(maxlen=FRAME_BUFFER_SIZE))
    frame_pixels = getattr(frame_data, "frame", None)
    if frame_pixels is not None:
        frame_buffer.append(frame_pixels)

    try:
        hits = service.evaluate(camera_id, boxes, zones,
                                state.setdefault("incidents", {}),
                                now=now, local_now=local_now)
    except Exception as exc:
        logger.error(f"Fight evaluation failed on {camera_id}: {exc}")
        return []

    events: List[DetectionEvent] = []

    drawings = service.zone_outline_drawings(zones, local_now)
    if drawings:
        events.append(DetectionEvent(
            plugin_name=plugin_name, event_type=STATS_EVENT, camera_id=camera_id,
            timestamp=now, confidence=1.0,
            metadata={"drawings": drawings, "zone_count": len(zones),
                      "people_tracked": len(boxes)}))

    camera_name = getattr(frame_data, "camera_url", "") or camera_id
    zone_by_id = {z.get("zone_id"): z for z in zones}

    for hit in hits:
        ml_score = None
        face_aggression = None
        face_emotions = None
        adjusted_confidence = float(hit.score or 1.0)
        ml_disagreed = False

        if hit.event_type == service.FIGHT_DETECTED:
            classifier = _get_classifier()
            if classifier is not None and len(frame_buffer) >= 2:
                try:
                    ml_score = classifier.score(list(frame_buffer))
                except Exception as exc:
                    logger.warning(f"Fight ML scoring failed on {camera_id}: {exc}")

            if ml_score is not None:
                if ml_score >= FIGHT_CONFIRM_THRESHOLD:
                    # Both signals agree — boost confidence, capped at 1.0.
                    adjusted_confidence = min(1.0, adjusted_confidence * 0.6 + ml_score * 0.4 + 0.1)
                elif ml_score <= FIGHT_VETO_THRESHOLD:
                    # ML strongly disagrees — down-rank, don't drop (see
                    # module docstring: a human still reviews this either
                    # way, so we surface the disagreement rather than
                    # silently discarding a heuristic hit).
                    adjusted_confidence = adjusted_confidence * 0.5
                    ml_disagreed = True
                # else: in the unsure middle band, leave the heuristic's own
                # confidence untouched.

            face_emotion_cls = _get_face_emotion_classifier()
            if face_emotion_cls is not None and frame_pixels is not None and hasattr(frame_pixels, "shape"):
                try:
                    results = face_emotion_cls.analyze(frame_pixels)
                    if results:
                        face_aggression = max((r["aggression_score"] for r in results), default=0.0)
                        face_emotions = [r["emotion"] for r in results]
                        if face_aggression >= 0.5:
                            adjusted_confidence = min(1.0, adjusted_confidence + 0.1)
                except Exception as exc:
                    logger.warning(f"Fight face emotion scoring failed on {camera_id}: {exc}")

        snapshot = None
        if hit.event_type != service.FIGHT_CLEARED:
            try:
                # The snapshot still comes from whatever frame the engine
                # last cached for this camera (unrelated to frame_buffer
                # above, which is this plugin's own short ML window).
                snapshot = save_event_snapshot(
                    "fight", camera_id,
                    frame_for_snapshot(frame_data, tracker_context, camera_id),
                    bbox=hit.bbox or None)
            except Exception as exc:
                logger.warning(f"Fight snapshot failed on {camera_id}: {exc}")

        _log(hit, camera_name, snapshot, zone_by_id)
        if hit.event_type == service.FIGHT_DETECTED:
            logger.warning(
                f"FIGHT indication on {camera_id}: {hit.describe()}"
                + (f" (ml_score={ml_score:.2f})" if ml_score is not None else "")
                + (f" (face_aggression={face_aggression:.2f})" if face_aggression is not None else "")
            )

        metadata: Dict[str, Any] = {
            "severity": hit.severity,
            "zone_id": hit.zone_id,
            "zone_name": hit.zone_name,
            "score": round(hit.score, 3),
            "track_ids": list(hit.track_ids),
            "duration_sec": round(hit.duration_sec, 2),
            "frames": hit.frames,
            "description": hit.describe(),
            # Carried on every event so no consumer can render an indication
            # as a finding of fact.
            "advisory_notice": ADVISORY_NOTICE,
            "requires_human_verification": True,
            "drawings": service.hit_drawings(hit),
        }
        if ml_score is not None:
            metadata["ml_score"] = round(ml_score, 3)
            metadata["ml_disagreed"] = ml_disagreed
        if face_aggression is not None:
            metadata["face_aggression_score"] = round(face_aggression, 3)
            metadata["face_emotions"] = face_emotions
        if snapshot:
            metadata["snapshot_file"] = snapshot

        events.append(DetectionEvent(
            plugin_name=plugin_name, event_type=hit.event_type,
            camera_id=camera_id, timestamp=hit.timestamp,
            confidence=adjusted_confidence, snapshot_path=snapshot,
            metadata=metadata))

    return events


def _log(hit, camera_name: str, snapshot: Optional[str],
         zone_by_id: Dict[str, dict]) -> None:
    zone = zone_by_id.get(hit.zone_id) or {}
    try:
        fight_event_log.record({
            "zone_id": hit.zone_id, "zone_name": hit.zone_name,
            "camera_id": hit.camera_id, "camera_name": camera_name,
            "event_type": hit.event_type, "severity": hit.severity,
            "timestamp": datetime.utcfromtimestamp(hit.timestamp),
            "started_at": datetime.utcfromtimestamp(hit.started_at),
            "duration_seconds": hit.duration_sec, "score": hit.score,
            "track_ids": [str(t) for t in (hit.track_ids or [])] or None,
            "bbox": [int(v) for v in (hit.bbox or [])] or None,
            "snapshot_path": snapshot,
            # Deliberately NOT set: `verified` stays null until a person
            # records a judgement. An unreviewed indication must never read
            # as a confirmed fight.
            "details": {
                "description": hit.describe(), "frames": hit.frames,
                "sensitivity": zone.get("sensitivity"),
                "tuning": describe_tuning(zone.get("sensitivity"),
                                          zone.get("overrides")),
                "schedule": describe_schedule(zone.get("schedule")),
                "advisory_notice": ADVISORY_NOTICE,
            },
        })
    except Exception as exc:
        logger.warning(f"Could not queue fight event: {exc}")
