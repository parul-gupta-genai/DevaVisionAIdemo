"""
Face recognition: attendance and watchlist monitoring from one pass.

Both features need the same expensive thing — detect faces, align, embed,
match against the register. Running them as two plugins would do that work
twice per frame. This plugin does it once and fans the result out to both:
an enrolled person produces attendance, and a person who is also on the
watchlist additionally produces an alert.

Cost governs the whole design. On this hardware InsightFace runs on CPU
(cuDNN will not initialise alongside DeepStream's TensorRT context), at
roughly 180ms per pass. So:
  * only cameras that need it should enable this plugin,
  * it samples frames rather than running on all of them,
  * one camera at a time may be inside the engine, others skip that frame
    instead of queueing behind it,
  * database work happens off the analytics thread.
"""

import queue
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from app.engine.base import (
    BaseDetectionPlugin, DetectionEvent, FrameData, TrackerContext,
)
from app.engine.snapshots import frame_for_snapshot, save_event_snapshot
from app.plugins.face.config import (
    FaceTuning, checkin_camera_ids, checkout_camera_ids,
)
from app.plugins.face.service import FaceService, detect_faces, get_face_engine


class FaceRecognitionPlugin(BaseDetectionPlugin):
    # Works on raw pixels: the face detector runs on the frame itself, not on
    # DeepStream's person boxes.
    needs_frame = True
    # All mutable state is per camera in TrackerContext, and the shared engine
    # is guarded by its own lock.
    thread_safe = True

    def __init__(self, app_config=None):
        super().__init__(app_config)
        # Held while inside the face engine. Non-blocking: a camera that
        # cannot get it skips this frame rather than stalling its worker,
        # which is what keeps one slow pass from backing up every camera.
        self._engine_lock = threading.Lock()
        # Writes are queued and drained by one background thread so the
        # analytics pass never waits on Postgres.
        self._writes: "queue.Queue[dict]" = queue.Queue(maxsize=512)
        self._writer = threading.Thread(
            target=self._drain_writes, name="face-writer", daemon=True)
        self._writer_started = False
        self._dropped_writes = 0
        logger.info("Initialized FaceRecognitionPlugin")

    @property
    def plugin_name(self) -> str:
        return "FaceRecognitionPlugin"

    def get_required_classes(self) -> List[int]:
        # Person, used only to skip frames with nobody in them.
        return [0]

    # ------------------------------------------------------------------ #
    # Background persistence
    # ------------------------------------------------------------------ #
    def _ensure_writer(self) -> None:
        if not self._writer_started:
            self._writer_started = True
            self._writer.start()

    def _submit(self, job: dict) -> None:
        try:
            self._writes.put_nowait(job)
        except queue.Full:
            # Dropping a write is better than blocking the pipeline; the
            # count is surfaced so a persistent backlog is visible.
            self._dropped_writes += 1
            if self._dropped_writes in (1, 10, 100) or self._dropped_writes % 500 == 0:
                logger.warning(
                    f"Face write queue full; dropped {self._dropped_writes} records")

    def _drain_writes(self) -> None:
        from database.session import SessionLocal
        from app.plugins.face.repository import FaceRepository

        while True:
            job = self._writes.get()
            db = None
            try:
                db = SessionLocal()
                repo = FaceRepository(db)
                kind = job.pop("kind")
                if kind == "sighting":
                    repo.record_sighting(
                        job["person_id"], job["seen_at"], job["camera_id"],
                        direction=job.get("direction"),
                        min_presence_sec=job.get("min_presence_sec", 60.0),
                    )
                    if job.get("action"):
                        repo.log_event(
                            job["action"],
                            person_id=job["person_id"],
                            camera_id=job["camera_id"],
                            camera_name=job.get("camera_name"),
                            timestamp=job["seen_at"],
                            similarity=job.get("similarity"),
                            snapshot_path=job.get("snapshot_path"),
                            metadata=job.get("metadata"),
                        )
                elif kind == "event":
                    repo.log_event(job.pop("event_type"), **job)
            except Exception as exc:
                logger.error(f"Face write failed: {exc}")
            finally:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass
                self._writes.task_done()

    # ------------------------------------------------------------------ #
    # Per-camera state
    # ------------------------------------------------------------------ #
    @staticmethod
    def _state(ctx: TrackerContext, camera_id: str) -> dict:
        st = ctx.get_state("FaceRecognitionPlugin", camera_id)
        if "last_seen" not in st:
            # person_id -> monotonic time of the last event we raised for
            # them on THIS camera. Per camera on purpose: the same person
            # arriving at a second camera is a new, meaningful sighting.
            st["last_seen"] = {}
            st["last_alert"] = {}
            st["last_pass"] = 0.0
            st["recent"] = []
        return st

    def _direction_for(self, camera_id: str) -> Optional[str]:
        if camera_id in checkout_camera_ids():
            return "OUT"
        if camera_id in checkin_camera_ids():
            return "IN"
        return None

    # ------------------------------------------------------------------ #
    # Main pass
    # ------------------------------------------------------------------ #
    def process_frame(self, frame_data: FrameData,
                      tracker_context: TrackerContext) -> List[DetectionEvent]:
        events: List[DetectionEvent] = []
        camera_id = frame_data.camera_id
        frame = frame_data.frame
        if frame is None:
            return events

        state = self._state(tracker_context, camera_id)
        tuning = FaceTuning.current()

        # Nobody in frame: skip the 180ms pass entirely. The detector would
        # find nothing anyway, and this is the common case on most cameras.
        if not any(d.class_id == 0 for d in (frame_data.detections or [])):
            return events

        # One camera at a time inside the engine. try-acquire, never block.
        if not self._engine_lock.acquire(blocking=False):
            return events
        try:
            if get_face_engine() is None:
                return events
            faces = detect_faces(frame)
        except Exception as exc:
            logger.error(f"[{camera_id}] face detection failed: {exc}")
            return events
        finally:
            self._engine_lock.release()

        if not faces:
            return events

        self._ensure_writer()
        now_wall = datetime.utcnow()
        now_mono = time.monotonic()
        drawings = []

        from database.session import SessionLocal
        db = SessionLocal()
        try:
            service = FaceService(db, tuning)
            for face in faces[: tuning.max_faces_per_pass]:
                metrics = service.usable_face(face, frame)
                if metrics is None:
                    continue

                person, similarity = service.identify(face["embedding"])
                box = metrics["bbox"]

                if person is None:
                    drawings.append({
                        "type": "rect", "coords": box,
                        "color": [140, 140, 140], "thickness": 2,
                    })
                    drawings.append({
                        "type": "text", "text": "Unknown",
                        "coords": [box[0], max(0, box[1] - 6)],
                        "color": [140, 140, 140], "scale": 0.6,
                    })
                    continue

                events.extend(self._handle_match(
                    person, similarity, metrics, frame_data, tracker_context,
                    state, tuning, now_wall, now_mono, drawings, service,
                ))
        except Exception as exc:
            logger.error(f"[{camera_id}] face recognition pass failed: {exc}")
        finally:
            db.close()

        # A per-tick overlay event so boxes and names stay drawn between
        # recognitions. Filtered before the database like the other *_STATS.
        if drawings:
            events.append(DetectionEvent(
                plugin_name=self.plugin_name,
                event_type="FACE_STATS",
                camera_id=camera_id,
                timestamp=frame_data.timestamp,
                confidence=1.0,
                metadata={"drawings": drawings,
                          "recent": list(state["recent"])[-5:]},
            ))
        return events

    def _handle_match(self, person, similarity, metrics, frame_data,
                      tracker_context, state, tuning, now_wall, now_mono,
                      drawings, service) -> List[DetectionEvent]:
        """Turns one identified face into attendance and watchlist events."""
        events: List[DetectionEvent] = []
        camera_id = frame_data.camera_id
        box = metrics["bbox"]
        watch = service.repo.active_watchlist_for(person.person_id, now_wall)

        colour = [0, 200, 0]
        if watch is not None:
            colour = ([0, 0, 255] if watch.severity == "critical"
                      else [0, 165, 255] if watch.severity == "warning"
                      else [255, 200, 0])
        drawings.append({"type": "rect", "coords": box,
                         "color": colour, "thickness": 3})
        drawings.append({
            "type": "text",
            "text": f"{person.name} {similarity:.2f}"
                    + (f" [{watch.category}]" if watch is not None else ""),
            "coords": [box[0], max(0, box[1] - 6)],
            "color": colour, "scale": 0.6,
        })

        # ---- attendance ------------------------------------------------
        last = state["last_seen"].get(person.person_id)
        if last is None or (now_mono - last) >= tuning.debounce_sec:
            state["last_seen"][person.person_id] = now_mono
            snapshot = save_event_snapshot(
                "attendance_face", camera_id,
                frame_for_snapshot(frame_data, tracker_context, camera_id),
                bbox=box,
            )
            direction = self._direction_for(camera_id)
            # The authoritative CHECK_IN/CHECK_OUT decision belongs to the
            # attendance record (one row per person per day), so it is made
            # by the writer thread against the database, not guessed here.
            self._submit({
                "kind": "sighting",
                "person_id": person.person_id,
                "seen_at": now_wall,
                "camera_id": camera_id,
                "camera_name": frame_data.camera_url or camera_id,
                "direction": direction,
                "min_presence_sec": tuning.min_presence_sec,
                "action": "FACE_SIGHTING",
                "similarity": float(similarity),
                "snapshot_path": snapshot,
                "metadata": {"direction": direction,
                             "person_name": person.name,
                             "person_code": person.person_code},
            })
            state["recent"].append({
                "person": person.name,
                "code": person.person_code,
                "time": frame_data.timestamp,
                "similarity": round(float(similarity), 3),
            })
            del state["recent"][:-10]

            events.append(DetectionEvent(
                plugin_name=self.plugin_name,
                event_type="FACE_RECOGNISED",
                camera_id=camera_id,
                timestamp=frame_data.timestamp,
                confidence=float(similarity),
                metadata={
                    "person_id": person.person_id,
                    "person_name": person.name,
                    "person_code": person.person_code,
                    "person_type": person.person_type,
                    "department": person.department,
                    "direction": direction,
                    "similarity": round(float(similarity), 4),
                    "snapshot_file": snapshot,
                },
            ))

        # ---- watchlist --------------------------------------------------
        if watch is not None and similarity >= tuning.watchlist_threshold:
            cameras = watch.camera_ids or []
            if cameras and camera_id not in cameras:
                return events
            last_alert = state["last_alert"].get(person.person_id)
            if last_alert is not None and (now_mono - last_alert) < tuning.watchlist_cooldown_sec:
                return events
            state["last_alert"][person.person_id] = now_mono

            snapshot = save_event_snapshot(
                "watchlist", camera_id,
                frame_for_snapshot(frame_data, tracker_context, camera_id),
                bbox=box,
            )
            self._submit({
                "kind": "event",
                "event_type": "WATCHLIST_HIT",
                "person_id": person.person_id,
                "camera_id": camera_id,
                "camera_name": frame_data.camera_url or camera_id,
                "timestamp": now_wall,
                "similarity": float(similarity),
                "severity": watch.severity,
                "watchlist_category": watch.category,
                "snapshot_path": snapshot,
                "metadata": {"reason": watch.reason, "person_name": person.name},
            })
            logger.warning(
                f"WATCHLIST HIT: {person.name} [{watch.category}] on {camera_id} "
                f"({similarity:.2f})"
            )
            events.append(DetectionEvent(
                plugin_name=self.plugin_name,
                event_type="WATCHLIST_HIT",
                camera_id=camera_id,
                timestamp=frame_data.timestamp,
                confidence=float(similarity),
                metadata={
                    "person_id": person.person_id,
                    "person_name": person.name,
                    "category": watch.category,
                    "severity": watch.severity,
                    "reason": watch.reason,
                    "similarity": round(float(similarity), 4),
                    "snapshot_file": snapshot,
                    # Surfaced under the key the alert engine already reads,
                    # so a hit dispatches SMS/email without extra wiring.
                    "active_alerts": ["WATCHLIST_HIT"],
                },
            ))
        return events
