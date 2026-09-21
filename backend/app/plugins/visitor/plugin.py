import time
from datetime import datetime
from typing import List
from loguru import logger

from app.engine.snapshots import save_event_snapshot
from app.engine.base import BaseDetectionPlugin, FrameData, TrackerContext, DetectionEvent
from app.plugins.visitor.repository import VisitorRepository
from app.plugins.visitor.events import VisitorEventType
from app.plugins.visitor.integration import vms_connector
from app.plugins.visitor.returning import (
    ReturningVisitorTracker, classify, mark_arrived, match_pre_registration,
)
from database.session import SessionLocal

import threading

class VisitorPlugin(BaseDetectionPlugin):
    """
    Enterprise Visitor Identity Management Plugin.
    Recognizes visitors, matches them against the database,
    and logs unique visits without duplicating the visitor.
    """

    # Needs pixels: face embeddings are extracted here, from the person crop.
    # The DeepStream SGIE cannot supply them (see _get_face_engine).
    needs_frame = True
    # All tracking state lives in TrackerContext, keyed by (plugin, camera).
    # events_lock guards the entries that background DB threads write into;
    # _face_lock guards the shared (non-reentrant) insightface session.
    thread_safe = True

    # Tracks unseen for this long are forgotten.
    TRACK_TTL_SEC = 15
    # Face extraction is CPU work on the analytics pool — bound it.
    MAX_FACE_EXTRACTIONS_PER_FRAME = 2
    # Frames to wait before retrying extraction on a track that had no face.
    #
    # MUST NOT be a multiple of PLUGIN_FRAME_SAMPLING["VisitorPlugin"], and
    # attempts are only stamped when pixels were actually present. This plugin
    # runs every frame but the probe supplies pixels only every Nth frame; with
    # both set to 5 and the attempt stamped unconditionally, a track first seen
    # on a frame where frame_num % 5 != 0 retried on 5, 10, 15... frames later
    # — every one of them the same residue, every one of them pixel-less. Four
    # of five tracks could never be identified at all.
    FACE_RETRY_FRAMES = 3
    # Below this det_score a face is too poor to enrol or match on.
    MIN_FACE_SCORE = 0.5
    # Retries of a failed face-engine build before giving up for good.
    MAX_FACE_INIT_ATTEMPTS = 5

    def __init__(self, app_config=None):
        super().__init__(app_config)
        logger.info("Initialized VisitorPlugin (Tripwire).")

        # Guards the per-camera entries that _async_db_match writes into from
        # background threads (pending_events / known_visitors_cache).
        self.events_lock = threading.Lock()

        self._face_lock = threading.Lock()
        # Separate from _face_lock and acquired NON-blockingly: face detection
        # is the most expensive thing in the plugin, and one shared engine
        # cannot be reentered. Blocking here would park an analytics worker
        # per camera waiting its turn — at 25 cameras that starves the pool.
        # Skipping instead costs nothing: FACE_RETRY_FRAMES brings the track
        # back around shortly.
        self._inference_lock = threading.Lock()
        self._face_engine = None
        self._face_engine_ready = False
        self._face_init_failures = 0

    def _get_face_engine(self):
        """
        Lazily builds the SAME face engine visitor registration uses
        (app/plugins/visitor/router.py -> FaceFactory.create).

        This matters for correctness, not tidiness. Enrolled vectors in
        Visitor.face_embedding come from insightface: SCRFD face detection,
        5-point alignment, then ArcFace. The DeepStream face SGIE instead
        runs ArcFace straight over the PERSON bbox with no detection or
        alignment, so its output lives in a completely different part of the
        embedding space. Matching one against the other — which is what this
        plugin used to do — cannot identify anyone, and writing those vectors
        back as UNKNOWN visitors permanently pollutes the column.

        Returns None when insightface is unavailable; the caller then skips
        matching entirely rather than storing incomparable vectors.
        """
        if self._face_engine_ready:
            return self._face_engine

        with self._face_lock:
            if self._face_engine_ready:
                return self._face_engine
            try:
                from detection.face_factory import FaceFactory
                from config.config import config as app_config

                engine = FaceFactory.create(app_config.FACE_BACKEND)
                if getattr(engine, "app", None) is None:
                    raise RuntimeError("face backend loaded but has no model")
                self._face_engine = engine
                # Latch ready ONLY on success. Setting it before the attempt
                # meant one transient failure — models still downloading, or
                # cuDNN failing to init alongside DeepStream's TensorRT
                # context — disabled visitor recognition for the life of the
                # process, signalled by a single startup line.
                self._face_engine_ready = True
                logger.info(
                    "VisitorPlugin face engine ready "
                    f"({app_config.FACE_BACKEND}) — runtime embeddings now "
                    "match the enrolled ones."
                )
            except Exception as exc:
                self._face_engine = None
                self._face_init_failures += 1
                if self._face_init_failures >= self.MAX_FACE_INIT_ATTEMPTS:
                    self._face_engine_ready = True   # give up, stop retrying
                if self._face_init_failures in (1, self.MAX_FACE_INIT_ATTEMPTS):
                    logger.error(
                        f"VisitorPlugin: no usable face engine "
                        f"(attempt {self._face_init_failures}/"
                        f"{self.MAX_FACE_INIT_ATTEMPTS}): {exc}. Visitor "
                        "recognition is DISABLED until it succeeds — refusing "
                        "to match or enrol whole-person SGIE vectors against "
                        "enrolled face embeddings, which would silently "
                        "corrupt the visitor DB."
                    )
            return self._face_engine

    def _extract_face(self, frame, bbox):
        """
        Runs face detect + align + ArcFace on one person crop.
        Returns (embedding_list, face_crop) or (None, None).
        """
        engine = self._get_face_engine()
        if engine is None or frame is None:
            return None, None

        h, w = frame.shape[:2]
        x1 = max(0, int(bbox[0]))
        y1 = max(0, int(bbox[1]))
        x2 = min(w, int(bbox[2]))
        y2 = min(h, int(bbox[3]))
        if x2 - x1 < 24 or y2 - y1 < 24:
            return None, None

        person_crop = frame[y1:y2, x1:x2]
        # Global, non-blocking: another camera's extraction is already using
        # the engine, so yield this worker instead of queueing behind it.
        if not self._inference_lock.acquire(blocking=False):
            return None, None
        try:
            faces = engine.detect_and_extract(person_crop)
        except Exception as exc:
            logger.error(f"Face extraction failed: {exc}")
            return None, None
        finally:
            self._inference_lock.release()

        if not faces:
            return None, None

        best = max(faces, key=lambda f: f.get("confidence", 0.0))
        if best.get("confidence", 0.0) < self.MIN_FACE_SCORE:
            return None, None
        embedding = best.get("embedding")
        if embedding is None:
            return None, None

        fx1, fy1, fx2, fy2 = (int(v) for v in best["bbox"])
        fx1 = max(0, fx1); fy1 = max(0, fy1)
        fx2 = min(person_crop.shape[1], fx2); fy2 = min(person_crop.shape[0], fy2)
        face_crop = (
            person_crop[fy1:fy2, fx1:fx2].copy()
            if fx2 > fx1 and fy2 > fy1 else None
        )
        return list(embedding), face_crop

    def _camera_state(self, tracker_context: TrackerContext, camera_id: str) -> dict:
        """
        Per-camera tracking state. DeepStream track ids are only unique within
        a stream, so a single shared set of track_* dicts let two cameras'
        tracks collide — one camera's crossing could log the other's visitor.
        """
        state = tracker_context.get_state(self.plugin_name, camera_id)
        if "track_last_seen" not in state:
            state["pending_events"] = []       # filled by async DB threads
            state["known_visitors_cache"] = {} # track_id -> {visitor_id, name, role}
            state["track_last_seen"] = {}      # track_id -> timestamp (for eviction)
            state["track_y_history"] = {}      # track_id -> int (last known centre y)
            state["track_face_cache"] = {}     # track_id -> dict(embedding, crop)
            state["face_attempt_frame"] = {}   # track_id -> last extraction frame
            state["track_crossed"] = set()     # track_ids that crossed the line
            state["logged_visits"] = set()     # track_ids already logged
        return state

    @property
    def plugin_name(self) -> str:
        return "VisitorPlugin"

    def get_required_classes(self) -> List[int]:
        # 0 = person in COCO dataset
        return [0]

    def process_frame(self, frame_data: FrameData, tracker_context: TrackerContext) -> List[DetectionEvent]:
        current_time = time.time()
        camera_id = frame_data.camera_id
        timestamp = frame_data.timestamp

        state = self._camera_state(tracker_context, camera_id)
        track_last_seen = state["track_last_seen"]
        track_y_history = state["track_y_history"]
        track_face_cache = state["track_face_cache"]
        track_crossed = state["track_crossed"]
        logged_visits = state["logged_visits"]

        # Flush any events that were resolved asynchronously in background threads
        with self.events_lock:
            events = state["pending_events"][:]
            state["pending_events"].clear()
            known_visitors_cache = state["known_visitors_cache"]

            # Evict stale tracks to prevent memory leaks
            stale_ids = [
                tid for tid, ts in track_last_seen.items()
                if current_time - ts > self.TRACK_TTL_SEC
            ]
            for tid in stale_ids:
                del track_last_seen[tid]
                track_y_history.pop(tid, None)
                track_face_cache.pop(tid, None)
                track_crossed.discard(tid)
                logged_visits.discard(tid)
                known_visitors_cache.pop(tid, None)

        # frame_shape is always populated by the probe, even when the frame
        # surface itself was not copied.
        h, w = frame_data.frame_shape
        line_y = int(h * 0.5) # The physical tripwire line at 50% height

        person_tracks = []
        for det in frame_data.detections:
            if det.track_id is not None and det.class_id == 0:
                track_id = det.track_id
                x1, y1, x2, y2 = det.bbox
                person_tracks.append({"track_id": track_id, "bbox": [x1, y1, x2, y2]})
                track_last_seen[track_id] = current_time

        # Acquire a real (detected + aligned) face embedding for tracks that
        # still lack one. Bounded per frame because this is CPU work sharing
        # the analytics pool; tracks that already crossed go first since they
        # are the ones about to need an identity.
        face_attempts = state.setdefault("face_attempt_frame", {})
        # Only attempt at all when this frame actually carries pixels. The
        # probe supplies them on its own schedule, so a frame without them can
        # never yield a face and must not consume a retry slot.
        if frame_data.frame is not None:
            pending_faces = [
                p for p in person_tracks
                if p["track_id"] not in track_face_cache
                and frame_data.frame_num - face_attempts.get(p["track_id"], -10**9)
                >= self.FACE_RETRY_FRAMES
            ]
            pending_faces.sort(key=lambda p: p["track_id"] not in track_crossed)

            for p in pending_faces[: self.MAX_FACE_EXTRACTIONS_PER_FRAME]:
                tid = p["track_id"]
                embedding, face_crop = self._extract_face(frame_data.frame, p["bbox"])
                # Stamp the attempt only after a real try on real pixels,
                # so a pixel-less or engine-busy frame cannot phase-lock a
                # track out of ever being identified.
                face_attempts[tid] = frame_data.frame_num
                if embedding is not None:
                    track_face_cache[tid] = {"embedding": embedding, "crop": face_crop}

        # Drop attempt bookkeeping for tracks that are gone.
        for gone in [t for t in face_attempts if t not in track_last_seen]:
            face_attempts.pop(gone, None)

        margin_x = int(w * 0.2)
        line_start_x = margin_x
        line_end_x = w - margin_x
        
        # Check line crossings and trigger events
        for p in person_tracks:
            tid = p["track_id"]
            px1, py1, px2, py2 = p["bbox"]
            current_y = int((py1 + py2) / 2) # Center of person bounding box
            current_x = int((px1 + px2) / 2)
            
            last_y = track_y_history.get(tid)
            if last_y is not None:
                # Only consider it a crossing if they are horizontally within the line boundaries
                if line_start_x <= current_x <= line_end_x:
                    # Crossed going down OR crossed going up
                    if (last_y < line_y <= current_y) or (last_y > line_y >= current_y):
                        track_crossed.add(tid)
                        logger.info(f"[{camera_id}] Person {tid} crossed the tripwire!")
            track_y_history[tid] = current_y

            # If they crossed the line AND we have a face AND haven't logged them yet
            if tid in track_crossed and tid not in logged_visits:
                if tid in track_face_cache:
                    logged_visits.add(tid)
                    face_data = track_face_cache[tid]
                    logger.info(f"[{camera_id}] Triggering DB match for {tid} (Crossed line + Face acquired)")

                    threading.Thread(
                        target=self._async_db_match,
                        args=(state, face_data["embedding"], tid, camera_id,
                              timestamp, face_data["crop"]),
                        daemon=True
                    ).start()
            
        # Collect drawings for the UI
        drawings = [
            {
                "type": "line",
                "coords": [[line_start_x, line_y], [line_end_x, line_y]],
                "color": [0, 255, 255], # Yellow tripwire
                "thickness": 2
            }
        ]
        
        # For every person tracked on screen, if we know who they are, draw their name!
        for p in person_tracks:
            tid = p["track_id"]
            if tid in known_visitors_cache:
                info = known_visitors_cache[tid]
                px1, py1, px2, py2 = p["bbox"]
                
                role = info.get('role', 'VISITOR')
                is_unknown = (role == 'UNKNOWN')
                
                if role == 'EMPLOYEE':
                    color = [255, 200, 50] # Cyan/Blueish for employees
                elif role == 'VISITOR':
                    color = [50, 255, 50] # Green for visitors
                else:
                    color = [50, 50, 255] # Red for unknown
                    
                text_prefix = role
                
                # Emit a drawing event for the UI!
                drawings.append({
                    "type": "text",
                    "coords": [float(px1), float(max(20, py1 - 25))],
                    "color": color,
                    "text": f"{text_prefix}: {info['name']} (ID: {info['visitor_id']})",
                    "scale": 0.6,
                    "thickness": 2
                })
                
        events.append(DetectionEvent(
            plugin_name=self.plugin_name,
            event_type="VISITOR_TRACK",
            camera_id=camera_id,
            timestamp=timestamp,
            confidence=1.0,
            metadata={"drawings": drawings}
        ))
            
        return events

    def _record_result(self, state: dict, track_id: int, info: dict, event: DetectionEvent) -> None:
        """Publishes an async DB result back into this camera's state."""
        with self.events_lock:
            cache = state["known_visitors_cache"]
            cache[track_id] = info
            # Keep cache small to avoid memory leak
            if len(cache) > 1000:
                cache.clear()
            state["pending_events"].append(event)

    def _async_db_match(self, state: dict, embedding_list: List[float], track_id: int, camera_id: str, timestamp: float, face_crop=None):
        """
        Runs on a background thread. `state` is this camera's TrackerContext
        dict — passed in rather than looked up, so the result lands on the
        camera that actually saw the crossing.
        """
        import cv2
        import os
        import uuid

        # Was a CWD-relative write; see the note in the PPE plugin. These are
        # also stored as visitor.photo, so a bad path persists in the record.
        # prune=False: this is also stored as visitor.photo and is the
        # registry's picture of that person, so it must outlive the rolling
        # window that event snapshots age out of.
        snapshot_path = save_event_snapshot("visitors", camera_id, face_crop,
                                            prune=False)

        db = SessionLocal()
        try:
            repo = VisitorRepository(db)
            match, sim = repo.find_best_match(embedding_list, threshold=0.55)
            
            if match:
                visitor_id = match.visitor_id
                
                with self.events_lock:
                    cached = state["known_visitors_cache"].get(track_id)
                    if cached and cached["visitor_id"] == visitor_id:
                        # The track ID still belongs to the same person. Avoid DB spam.
                        return
                        
                # If they are registered, it's a recognition. If unknown, it's just tracking an unknown person.
                if match.status == 'REGISTERED':
                    event_type = VisitorEventType.EMPLOYEE_RECOGNIZED if match.role == 'EMPLOYEE' else VisitorEventType.VISITOR_RECOGNIZED
                else:
                    event_type = VisitorEventType.UNKNOWN_PERSON
                    # Update the UNKNOWN visitor's photo with the latest snapshot so it shows up in the UI
                    if snapshot_path:
                        match.photo = snapshot_path
                        db.commit()
                    
                conf = sim

                # Resolve the sighting into a VISIT rather than counting it as
                # one. Walking past three cameras used to register three
                # visits, which made any returning-visitor claim meaningless.
                tracker = ReturningVisitorTracker(db)
                visit, history = tracker.resolve(
                    visitor_id, camera_id, track_id,
                    confidence=conf, snapshot_path=snapshot_path)
                if visit is None:
                    # Still inside the visit already in progress; nothing new
                    # to announce.
                    return

                event_type = classify(history, match.status)

                prereg = match_pre_registration(db, visitor_id, match.name)
                if prereg is not None and mark_arrived(db, prereg, visitor_id, camera_id):
                    event_type = VisitorEventType.VISITOR_ARRIVED.value
                    history["expected"] = True
                    history["host_name"] = prereg.host_name
                    history["purpose"] = prereg.purpose
                    history["vms_reference"] = prereg.vms_reference

                repo.log_event(
                    event_type=event_type,
                    visitor_id=visitor_id,
                    visit_id=visit.visit_id,
                    camera=camera_id,
                    metadata={"similarity": conf, **history}
                )
                vms_connector.notify(event_type, {
                    "visitor_id": visitor_id, "name": match.name,
                    "role": match.role, "camera_id": camera_id,
                    "similarity": conf, "snapshot": snapshot_path, **history,
                })
                
                self._record_result(
                    state, track_id,
                    {"visitor_id": visitor_id, "name": match.name, "role": match.role},
                    DetectionEvent(
                        plugin_name=self.plugin_name,
                        event_type=event_type,
                        camera_id=camera_id,
                        timestamp=timestamp,
                        confidence=conf,
                        metadata={"visitor_id": visitor_id, "name": match.name,
                                  "track_id": track_id, "snapshot_file": snapshot_path,
                                  **history}
                    ),
                )
                logger.info(f"[{camera_id}] Appended pending event: {event_type} for track {track_id}")
            else:
                unknown_visitor = repo.create_unknown_visitor(face_embedding=embedding_list, snapshot_path=snapshot_path)
                event_type = VisitorEventType.UNKNOWN_PERSON
                
                # Through the tracker as well, so a brand-new visitor's first
                # visit carries the same numbering as every later one.
                visit, history = ReturningVisitorTracker(db).resolve(
                    unknown_visitor.visitor_id, camera_id, track_id,
                    confidence=0.0, snapshot_path=snapshot_path)

                repo.log_event(
                    event_type=event_type.value,
                    visitor_id=unknown_visitor.visitor_id,
                    visit_id=visit.visit_id if visit else None,
                    camera=camera_id,
                    metadata=history,
                )
                vms_connector.notify(event_type.value, {
                    "visitor_id": unknown_visitor.visitor_id, "name": "Unknown",
                    "role": "UNKNOWN", "camera_id": camera_id,
                    "snapshot": snapshot_path, **history,
                })
                
                self._record_result(
                    state, track_id,
                    {"visitor_id": unknown_visitor.visitor_id, "name": "Unknown", "role": "UNKNOWN"},
                    DetectionEvent(
                        plugin_name=self.plugin_name,
                        event_type=event_type.value,
                        camera_id=camera_id,
                        timestamp=timestamp,
                        confidence=0.0,
                        metadata={"visitor_id": unknown_visitor.visitor_id, "track_id": track_id, "snapshot_file": snapshot_path}
                    ),
                )
                logger.info(f"[{camera_id}] Appended pending event: {event_type.value} for track {track_id}")
        except Exception as e:
            logger.error(f"[{camera_id}] Async DB match failed: {e}")
        finally:
            db.close()
