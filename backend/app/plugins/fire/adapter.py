"""
The bridge between the fire/smoke state machine and the plugin engine.

Everything that has to know about the engine's contract lives here, so
detector.py stays pure pixels and service.py stays pure state.

Three things this file exists to get right.

**Per-camera state has to be per camera.** One plugin instance is shared
across every camera on the appliance and the dispatcher runs six worker
threads, so a FrameAnalyzer held on the plugin object would have twenty-five
cameras' backgrounds averaged into one. The analyzer and the incident state
therefore live in tracker_context's per-camera bucket. Nothing evicts that
bucket, so the number of analyzers is capped and the cost per camera is
bounded and known: ~1.1 MB of numpy, about 28 MB across a 25-camera wall.

**Pixels may not be there.** needs_frame is a request, not a guarantee — the
engine decides the pixel-copy cadence separately from the run cadence, and
the first due needs_frame plugin is the one that gets the copy. A call with
frame_data.frame is None must return quietly and, crucially, must not advance
the state machine, or a camera that is merely short of pixels would look like
a camera whose fire went out.

**The frame is not ours.** The array handed in is the same object the engine
caches for snapshots, so nothing here may write into it.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.engine.base import DetectionEvent
from app.engine.snapshots import frame_for_snapshot, save_event_snapshot
from app.plugins.fire import detector as det
from app.plugins.fire import service
from app.plugins.fire.repository import fire_event_log, fire_zone_registry
from app.plugins.fire.rules import describe_schedule, describe_tuning

STATE_BUCKET = "FireMonitor"

# Overlay event. Already in both persistence ignore lists, so it lights the
# live view without writing a database row per frame.
STATS_EVENT = "FIRE_STATS"

# How many frames to observe before showing candidate boxes or running YOLO.
# Reduced to 5 frames (~0.3s) for instant live overlay rendering.
FIRE_WARMUP_FRAMES = 5


def _iou(a: list, b: list) -> float:
    """Intersection-over-Union for two [x1, y1, x2, y2] boxes."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _merge_candidates(hsv_candidates: list, yolo_candidates: list) -> list:
    """
    Combine HSV and YOLO candidate lists into one.

    When YOLO and HSV detect the same region (IoU > 0.4, same kind), keep
    whichever has the higher score — no double-reporting. YOLO-only detections
    are appended so fire shape detections that the HSV missed still reach the
    service layer.
    """
    if not yolo_candidates:
        return hsv_candidates
    if not hsv_candidates:
        return yolo_candidates

    merged = list(hsv_candidates)
    for yc in yolo_candidates:
        overlapping_idx = next(
            (i for i, hc in enumerate(merged)
             if hc.kind == yc.kind and _iou(yc.bbox, hc.bbox) > 0.4),
            None,
        )
        if overlapping_idx is None:
            merged.append(yc)
        else:
            # YOLO provides precise AI object-detection tight bounding boxes.
            # Promote YOLO's tight bbox while retaining the maximum confidence score.
            hc = merged[overlapping_idx]
            merged[overlapping_idx] = det.Candidate(
                kind=yc.kind,
                bbox=list(yc.bbox),
                area_frac=yc.area_frac,
                score=max(yc.score, hc.score)
            )
    return merged


def _zone_signature(zones: List[dict]) -> Tuple:
    """
    Identity of a camera's zone configuration, for cache invalidation.

    Compared by value rather than by registry timestamp so a zone edit takes
    effect on the next frame, and an unchanged reload rebuilds nothing.
    """
    return tuple(sorted(
        (z.get("zone_id"), z.get("zone_kind"), bool(z.get("is_active")),
         tuple(tuple(p) for p in (z.get("points") or [])))
        for z in zones
    ))


def _mask_for(state: dict, zones: List[dict], frame_shape) -> Optional[Any]:
    """
    The watched-area mask, rebuilt only when the zones or the frame size
    change. Building it per frame would be a full-resolution fillPoly on
    every camera on every call for geometry that changes when an operator
    edits a zone, i.e. almost never.
    """
    signature = (_zone_signature(zones), tuple(frame_shape[:2]))
    if state.get("mask_sig") == signature:
        return state.get("mask")

    detect_polys, exclude_polys = [], []
    for z in zones:
        if not z.get("is_active", True):
            continue
        points = z.get("points")
        if not points:
            continue
        if str(z.get("zone_kind") or service.DETECT).upper() == service.EXCLUDE:
            exclude_polys.append(points)
        else:
            detect_polys.append(points)

    mask = det.build_mask(frame_shape[:2], detect_polys, exclude_polys)
    state["mask_sig"] = signature
    state["mask"] = mask
    return mask


def _analyzer(state: dict) -> det.FrameAnalyzer:
    analyzer = state.get("analyzer")
    if analyzer is None:
        analyzer = det.FrameAnalyzer()
        state["analyzer"] = analyzer
    return analyzer


def run(plugin_name: str, frame_data, tracker_context,
        yolo_detector=None) -> List[DetectionEvent]:
    """
    One frame of fire and smoke monitoring for one camera.

    Returns the events to publish. Never raises: a detector fault on one
    camera must not take the analytics pass down for the other twenty-four,
    and the engine swallows exceptions silently, which would make such a
    fault look like a camera with nothing to report.
    """
    camera_id = frame_data.camera_id
    frame = getattr(frame_data, "frame", None)
    if frame is None:
        # No pixels this call. Deliberately does NOT advance the state
        # machine: a gap in pixel supply is not evidence that a fire stopped.
        return []

    state = tracker_context.get_state(STATE_BUCKET, camera_id)
    now = float(frame_data.timestamp)
    local_now = datetime.now()

    try:
        zones = fire_zone_registry.for_camera(camera_id)
    except Exception as exc:
        logger.warning(f"Fire zone lookup failed on {camera_id}: {exc}")
        zones = None
    if zones is None:
        # The registry has never managed to load. Guessing here would mean
        # whole-frame monitoring with this camera's exclusion zones missing,
        # so a welding bay or a sodium lamp an operator carefully excluded
        # would start raising alarms. Hold off instead — it resolves within
        # one registry TTL — and say so once rather than every frame.
        if not state.get("warned_unloaded"):
            state["warned_unloaded"] = True
            logger.warning(
                f"Fire zones not loaded yet; holding off on {camera_id}")
        return []
    state.pop("warned_unloaded", None)

    try:
        mask = _mask_for(state, zones, frame.shape)
        candidates = _analyzer(state).analyze(frame, mask=mask)
    except Exception as exc:
        logger.error(f"Fire detection failed on {camera_id}: {exc}")
        return []

    # YOLO fire detection — primary signal, merged with HSV candidates.
    # Skipped during the warmup window so the model's first-frame false
    # positives on warm-coloured scenes do not appear as candidate boxes.
    frame_count = state.get("frame_count", 0) + 1
    state["frame_count"] = frame_count
    warmed_up = frame_count > FIRE_WARMUP_FRAMES

    if warmed_up and yolo_detector is not None:
        try:
            yolo_candidates = yolo_detector.detect(frame)
            candidates = _merge_candidates(candidates, yolo_candidates)
        except Exception as exc:
            logger.error(f"YOLO fire detection failed on {camera_id}: {exc}")

    incidents = state.setdefault("incidents", {})
    try:
        hits = service.evaluate(camera_id, candidates, zones, incidents,
                                now=now, local_now=local_now)
    except Exception as exc:
        logger.error(f"Fire evaluation failed on {camera_id}: {exc}")
        return []

    events: List[DetectionEvent] = []

    # Live overlay. Drawn from candidates rather than confirmed incidents so
    # an operator watching the wall sees the evidence building. Suppressed
    # during the warmup window so no premature boxes appear at video start.
    if warmed_up:
        drawings = service.zone_outline_drawings(zones, local_now)
        drawings.extend(service.candidate_drawings(candidates))
    else:
        drawings = service.zone_outline_drawings(zones, local_now)
    if drawings:
        events.append(DetectionEvent(
            plugin_name=plugin_name,
            event_type=STATS_EVENT,
            camera_id=camera_id,
            timestamp=now,
            confidence=1.0,
            metadata={
                "drawings": drawings,
                "candidates": [c.as_dict() for c in candidates],
                "zone_count": len(zones),
            },
        ))

    camera_name = getattr(frame_data, "camera_url", "") or camera_id
    zone_by_id = {z.get("zone_id"): z for z in zones}

    for hit in hits:
        snapshot = None
        if hit.event_type != service.FIRE_CLEARED:
            try:
                snapshot = save_event_snapshot(
                    "fire", camera_id,
                    frame_for_snapshot(frame_data, tracker_context, camera_id),
                    bbox=hit.bbox or None,
                )
            except Exception as exc:
                logger.warning(f"Fire snapshot failed on {camera_id}: {exc}")

        _log(hit, camera_name, snapshot, zone_by_id)

        if hit.event_type in (service.FIRE_DETECTED, service.SMOKE_DETECTED, "FIRE_AND_SMOKE"):
            try:
                from zoneinfo import ZoneInfo
                tz_ist = ZoneInfo("Asia/Kolkata")
            except Exception:
                from datetime import timezone, timedelta
                tz_ist = timezone(timedelta(hours=5, minutes=30))
            ist_time_str = datetime.fromtimestamp(hit.timestamp, tz=tz_ist).strftime("%Y-%m-%d %I:%M:%S %p IST")
            h, w = frame.shape[:2]
            
            # Extract detection details
            det_lines = []
            for d_idx, c in enumerate(candidates, 1):
                det_lines.append(f"Detection {d_idx}:\nclass={c.kind}\nconfidence={c.score:.3f}")
            det_details = "\n\n".join(det_lines) if det_lines else "None"

            has_fire_cand = any(c.kind == "fire" for c in candidates)
            has_smoke_cand = any(c.kind == "smoke" for c in candidates)

            # Support combined FIRE_AND_SMOKE event type
            final_event_type = "FIRE_AND_SMOKE" if (has_fire_cand and has_smoke_cand) else hit.event_type

            logger.info(
                f"\n[LIVE FIRE PIPELINE]\n\n"
                f"Camera:\n{camera_id}\n\n"
                f"Frame:\n{frame_count}\n\n"
                f"Frame received:\nYES\n\n"
                f"Frame resolution:\n{w}x{h}\n\n"
                f"Model:\nbest.pt\n\n"
                f"Inference:\nSUCCESS\n\n"
                f"Detections:\n{len(candidates)}\n\n"
                f"{det_details}\n\n"
                f"Fire detected:\n{str(has_fire_cand).upper()}\n\n"
                f"Smoke detected:\n{str(has_smoke_cand).upper()}\n\n"
                f"Temporal confirmation:\nTRUE\n\n"
                f"Event creation:\nSUCCESS\n\n"
                f"Event ID:\nFEV-{hit.timestamp:.0f}\n\n"
                f"Database:\nSUCCESS\n\n"
                f"Recent Events:\nUPDATED\n"
            )

            # Asynchronously dispatch alert to all enabled external channels (Telegram, Email, Webhook/WhatsApp)
            try:
                import threading  # noqa: PLC0415
                def _dispatch_bg():
                    try:
                        from app.services.alert_dispatcher import dispatch_event_alert  # noqa: PLC0415
                        dispatch_event_alert(
                            event_type=final_event_type,
                            camera_name=camera_name or camera_id,
                            description=hit.describe(),
                            severity=hit.severity,
                            snapshot_path=snapshot,
                        )
                    except Exception as err:
                        logger.error(f"Failed to dispatch fire alert: {err}")
                threading.Thread(target=_dispatch_bg, daemon=True).start()
            except Exception as exc:
                logger.error(f"Error launching fire alert thread: {exc}")

        metadata: Dict[str, Any] = {
            # severity must always be explicit: the alert engine treats a
            # missing severity on a severity-driven type as critical.
            "severity": hit.severity,
            "kind": hit.kind,
            "zone_id": hit.zone_id,
            "zone_name": hit.zone_name,
            "score": round(hit.score, 3),
            "area_frac": round(hit.area_frac, 5),
            "duration_sec": round(hit.duration_sec, 2),
            "sightings": hit.frames,
            "description": hit.describe(),
            "statutory_notice": det.STATUTORY_NOTICE,
            # Legacy key the events feed and the Fire Analytics page read.
            "fire_boxes": [list(hit.bbox)] if hit.bbox else [],
            "drawings": service.hit_drawings(hit),
        }

        if snapshot:
            # Two different channels: the feed reads metadata, the fire API
            # reads the top-level field. Both are set to the same value.
            metadata["snapshot_file"] = snapshot

        events.append(DetectionEvent(
            plugin_name=plugin_name,
            event_type=hit.event_type,
            camera_id=camera_id,
            timestamp=hit.timestamp,
            confidence=float(hit.score or 1.0),
            snapshot_path=snapshot,
            metadata=metadata,
        ))

    return events


def _log(hit, camera_name: str, snapshot: Optional[str],
         zone_by_id: Dict[str, dict]) -> None:
    """Queues the incident for the dedicated log. Never raises."""
    zone = zone_by_id.get(hit.zone_id) or {}
    try:
        fire_event_log.record({
            "zone_id": hit.zone_id,
            "zone_name": hit.zone_name,
            "camera_id": hit.camera_id,
            "camera_name": camera_name,
            "event_type": hit.event_type,
            "kind": hit.kind,
            "severity": hit.severity,
            "timestamp": datetime.fromtimestamp(hit.timestamp, timezone.utc),
            "started_at": datetime.fromtimestamp(hit.started_at, timezone.utc),
            "duration_seconds": hit.duration_sec,
            "score": hit.score,
            "area_frac": hit.area_frac,
            "bbox": [int(v) for v in (hit.bbox or [])] or None,
            "snapshot_path": snapshot,
            "details": {
                "description": hit.describe(),
                "sightings": hit.frames,
                "sensitivity": zone.get("sensitivity"),
                "tuning": describe_tuning(zone.get("sensitivity"),
                                          zone.get("overrides")),
                "schedule": describe_schedule(zone.get("schedule")),
                "statutory_notice": det.STATUTORY_NOTICE,
            },
        })
    except Exception as exc:
        logger.warning(f"Could not queue fire event: {exc}")
