import time
import threading
import cv2
import numpy as np
from typing import List, Dict, Any, Set
import uuid
import os
from loguru import logger

from app.engine.base import BaseDetectionPlugin, FrameData, TrackerContext, DetectionEvent
from config.config import config
from app.engine.snapshots import save_event_snapshot, frame_for_snapshot

class AttendanceDetectionPlugin(BaseDetectionPlugin):
    """
    Real OpenCV Appearance-based Re-Identification.
    Migrated from legacy IdentityAnalyticsPlugin.
    """

    # Reads raw pixels (per-person crops -> HSV histogram signatures).
    needs_frame = True
    # The identity registry below is DELIBERATELY shared across cameras (an
    # employee must keep one id between the CHECK IN and CHECK OUT cameras),
    # so it cannot move into per-camera TrackerContext state. It is guarded by
    # _identity_lock instead; everything camera-scoped lives in TrackerContext.
    thread_safe = True

    def __init__(self, app_config=None):
        super().__init__(app_config)
        # ---- Shared identity registry (guarded by _identity_lock) ----------
        self._identity_lock = threading.Lock()
        # Database of known signatures: ID -> histogram
        self.known_signatures = {}
        self.next_id = 1
        # Check In / Check Out presence, global by design
        self.employee_presence: Set[int] = set()
        self.last_seen: Dict[int, float] = {}

        # Authorized database (for features 15, 17)
        # Simulate that ID 1 to 100 are authorized employees for easier testing
        # (read-only after construction)
        self.authorized_ids = frozenset(range(1, 100))

        logger.info("Initialized AttendanceDetectionPlugin")

    def _camera_state(self, tracker_context: TrackerContext, camera_id: str) -> dict:
        state = tracker_context.get_state(self.plugin_name, camera_id)
        if "previous_centroids" not in state:
            # Centroids are in THIS camera's pixel space and the log feed is
            # rendered per camera — sharing either across cameras produced
            # phantom line crossings and cross-camera log bleed.
            state["previous_centroids"] = {}   # employee id -> (cx, cy)
            state["recent_logs"] = []
        return state

    def _resolve_identity(self, sig) -> int:
        """
        Matches a colour signature against the shared registry, registering a
        new employee id when nothing is close enough. Returns the employee id.
        """
        with self._identity_lock:
            best_match_id = None
            best_score = 0.0
            for k_id, k_sig in self.known_signatures.items():
                score = cv2.compareHist(sig, k_sig, cv2.HISTCMP_CORREL)
                if score > best_score:
                    best_score = score
                    best_match_id = k_id

            if best_match_id is None or best_score < 0.7:
                # New person
                best_match_id = self.next_id
                self.known_signatures[best_match_id] = sig
                self.next_id += 1
            else:
                # Update signature slowly
                self.known_signatures[best_match_id] = (
                    0.9 * self.known_signatures[best_match_id] + 0.1 * sig
                )

            self.last_seen[best_match_id] = time.time()
            return best_match_id

    def _evict_stale_identities(self) -> Set[int]:
        """Drops identities unseen for 5 minutes. Returns the ids removed."""
        with self._identity_lock:
            now = time.time()
            stale = [i for i, ts in self.last_seen.items() if now - ts > 300]
            for stale_id in stale:
                self.known_signatures.pop(stale_id, None)
                self.last_seen.pop(stale_id, None)
                self.employee_presence.discard(stale_id)
            return set(stale)

    @property
    def plugin_name(self) -> str:
        return "AttendanceDetectionPlugin"

    def get_required_classes(self) -> List[int]:
        # Person
        return [0]

    def ccw(self, A, B, C):
        return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])

    def intersect(self, A, B, C, D):
        return self.ccw(A,C,D) != self.ccw(B,C,D) and self.ccw(A,B,C) != self.ccw(A,B,D)

    def extract_signature(self, image_crop):
        hsv = cv2.cvtColor(image_crop, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [8, 8], [0, 180, 0, 256])
        cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        return hist.flatten()

    def process_frame(self, frame_data: FrameData, tracker_context: TrackerContext) -> List[DetectionEvent]:
        events = []
        camera_id = frame_data.camera_id
        timestamp = frame_data.timestamp
        frame = frame_data.frame
        
        if frame is None or not frame_data.detections:
            return events
        
        auth_in_frame = []
        unauth_count = 0

        state = self._camera_state(tracker_context, camera_id)
        previous_centroids = state["previous_centroids"]
        recent_logs = state["recent_logs"]

        line = config.get_checkin_line_for_camera(camera_id)

        for det in frame_data.detections:
            if det.track_id is None or det.class_id != 0:
                continue
                
            x1, y1, x2, y2 = map(int, det.bbox)
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            if x2 - x1 < 10 or y2 - y1 < 10:
                continue
                
            crop = frame[y1:y2, x1:x2]
            sig = self.extract_signature(crop)

            # Match against (and update) the shared identity registry.
            best_match_id = self._resolve_identity(sig)

            if best_match_id in self.authorized_ids:
                auth_in_frame.append(f"Employee {best_match_id}")
                
                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2
                current_centroid = (center_x, center_y)
                
                if line and best_match_id in previous_centroids:
                    prev_centroid = previous_centroids[best_match_id]
                    A, B = line
                    C = prev_centroid
                    D = current_centroid
                    
                    if self.intersect(A, B, C, D):
                        AB_x = B[0] - A[0]
                        AB_y = B[1] - A[1]
                        CD_x = D[0] - C[0]
                        CD_y = D[1] - C[1]
                        cross = AB_x * CD_y - AB_y * CD_x
                        
                        action = None
                        is_checkout_cam = "CHECK OUT" in camera_id.upper()
                        is_checkin_cam = "CHECK IN" in camera_id.upper()

                        # employee_presence is the shared turnstile state —
                        # read-modify-write it atomically.
                        with self._identity_lock:
                            if is_checkout_cam:
                                action = "CHECK OUT"
                                self.employee_presence.discard(best_match_id)
                            elif is_checkin_cam:
                                action = "CHECK IN"
                                self.employee_presence.add(best_match_id)
                            elif cross < 0:
                                # Crossed left-to-right (Check In)
                                if best_match_id not in self.employee_presence:
                                    action = "CHECK IN"
                                    self.employee_presence.add(best_match_id)
                            else:
                                # Crossed right-to-left (Check Out)
                                if best_match_id in self.employee_presence:
                                    action = "CHECK OUT"
                                    self.employee_presence.discard(best_match_id)

                        if action == "CHECK IN":
                            logger.success(f"✅ Employee {best_match_id} CHECKED IN on {camera_id}")
                        elif action == "CHECK OUT":
                            logger.info(f"🚪 Employee {best_match_id} CHECKED OUT from {camera_id}")

                        if action:
                            snap = save_event_snapshot(
                                "attendance", camera_id,
                                frame_for_snapshot(frame_data, tracker_context, camera_id),
                                bbox=[x1, y1, x2, y2],
                            )
                            log_entry = {
                                "employee": f"Emp {best_match_id}",
                                "action": action,
                                "time": timestamp,
                                "snapshot_file": snap
                            }
                            recent_logs.append(log_entry)
                            
                            drawings = []
                            
                            event = DetectionEvent(
                                plugin_name=self.plugin_name,
                                event_type=action.replace(" ", "_"),
                                camera_id=camera_id,
                                timestamp=timestamp,
                                confidence=1.0,
                                metadata={
                                    "employee_id": best_match_id,
                                    "action": action,
                                    "drawings": drawings,
                                    "snapshot_file": snap
                                }
                            )
                            events.append(event)
                                
                previous_centroids[best_match_id] = current_centroid
            else:
                unauth_count += 1

        # Evict stale tracking data (Memory Leak Fix)
        # Remove IDs not seen in 5 minutes (300 seconds)
        evicted = self._evict_stale_identities()
        for stale_id in evicted:
            previous_centroids.pop(stale_id, None)

        # An identity evicted here is gone from the SHARED registry, but its
        # centroid entry survives on every OTHER camera's state — those are
        # only pruned when that camera happens to evict the same id, which it
        # never will now the id is gone. Prune anything no longer in the
        # registry so per-camera centroid maps cannot grow without bound.
        if evicted:
            with self._identity_lock:
                known = set(self.known_signatures)
            for gone in [i for i in previous_centroids if i not in known]:
                previous_centroids.pop(gone, None)

        # Trim in place — rebinding the local would not write back to state.
        del recent_logs[:-4]

        # We need a way to continuously supply "attendance_logs" and "authorized_employees" 
        # to the frontend even if no event is currently firing. We can emit a STATE event.
        state_drawings = []
        if line:
            # Draw the check-in line
            state_drawings.append({
                "type": "rect", # API server.py needs to handle line if we want a line, but server.py only has rect and text right now.
                # Fake a line with a thin rect
                "coords": [line[0][0], line[0][1], line[1][0], line[1][1] + 2],
                "color": [255, 0, 0],
                "thickness": -1
            })
            
        state_event = DetectionEvent(
            plugin_name=self.plugin_name,
            event_type="ATTENDANCE_STATE",
            camera_id=camera_id,
            timestamp=timestamp,
            confidence=1.0,
            metadata={
                "authorized_employees_in_frame": list(set(auth_in_frame)),
                "unauthorized_count": unauth_count,
                "attendance_logs": list(recent_logs),
                "drawings": state_drawings
            }
        )
        events.append(state_event)
                    
        return events
