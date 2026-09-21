import asyncio
import copy
import threading
from typing import List, Dict, Any
from loguru import logger
from concurrent.futures import ThreadPoolExecutor

from app.engine.base import BaseDetectionPlugin, FrameData, TrackerContext, DetectionEvent
from app.plugins.anpr.factory import ANPRFactory
from app.plugins.anpr.tracker import ANPRTracker
from app.plugins.anpr.validator import PlateValidator
from app.plugins.anpr.service import anpr_service
from app.plugins.anpr.config_parser import anpr_app_config
from app.plugins.anpr.utils import save_snapshot
from app.plugins.anpr.events import ANPREventType
from app.plugins.anpr.watchlist import is_blacklist, plate_watchlist
from app.plugins.anpr.gates import (
    DENY, decide_access, event_type_for, resolve_direction,
)
from app.plugins.anpr.repository import gate_registry

class ANPRPlugin(BaseDetectionPlugin):
    """
    Enterprise ANPR Plugin.
    Handles Vehicle detection (via core), Plate Detection (via internal YOLO),
    OCR extraction (PP-OCRv5), Temporal Fusion, and Regex validation.
    """

    # Reads raw pixels (vehicle crops -> plate detect -> OCR -> snapshots).
    needs_frame = True
    # Vehicle tracks are per-camera (in TrackerContext); the shared YOLO and
    # OCR sessions are not reentrant, so inference runs under _model_lock.
    thread_safe = True

    def __init__(self, app_config=None):
        super().__init__(app_config)
        self.plate_detector = ANPRFactory.get_plate_detector()
        self.ocr_engine = ANPRFactory.get_ocr_engine()
        # Guards the shared detector/OCR sessions. Only inference is inside it,
        # so cameras still overlap on cropping, fusion and event building.
        self._model_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=4)
        logger.info("Initialized ANPRPlugin via ANPRFactory.")
        
        # Start the background service for DB logging if there's a loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(anpr_service.start())
        except RuntimeError:
            pass # No loop running yet

    @property
    def plugin_name(self) -> str:
        return "ANPRPlugin"

    def get_required_classes(self) -> List[int]:
        # Typically vehicles: 2 (car), 3 (motorcycle), 5 (bus), 7 (truck)
        return [2, 3, 5, 7]

    def _tracker_for(self, tracker_context: TrackerContext, camera_id: str) -> ANPRTracker:
        """
        One ANPRTracker per camera. A single shared tracker keyed by
        DeepStream track_id (which is only unique within a stream) merged
        different cameras' vehicles, and finalized tracks were attributed to
        whichever camera's frame happened to trigger the stale-track sweep.
        """
        state = tracker_context.get_state(self.plugin_name, camera_id)
        tracker = state.get("tracker")
        if tracker is None:
            tracker = ANPRTracker(
                track_timeout=anpr_app_config.fusion.track_timeout_seconds
            )
            state["tracker"] = tracker
        return tracker

    def process_frame(self, frame_data: FrameData, tracker_context: TrackerContext) -> List[DetectionEvent]:
        events = []
        camera_id = frame_data.camera_id
        timestamp = frame_data.timestamp
        frame = frame_data.frame

        if frame is None:
            return events

        h, w = frame.shape[:2]
        tracker = self._tracker_for(tracker_context, camera_id)

        # 1. Iterate over vehicle detections provided by the core pipeline
        if not frame_data.detections:
            # Cleanup Stale Tracks and Emit Final Events even if no detections this frame
            return self._cleanup_and_emit(tracker, camera_id, timestamp)

        for det in frame_data.detections:
            if det.track_id is None:
                continue
                
            track_id = det.track_id
            class_id = det.class_id
            
            # 2 (car), 3 (motorcycle), 5 (bus), 7 (truck)
            if class_id not in [2, 3, 5, 7]:
                continue
                
            vehicle_box = det.bbox
            
            # Crop vehicle
            vx1, vy1, vx2, vy2 = map(int, vehicle_box)
                
            # Boundary checks
            vx1, vy1 = max(0, vx1), max(0, vy1)
            vx2, vy2 = min(w, vx2), min(h, vy2)
            
            if vx2 - vx1 < 20 or vy2 - vy1 < 20:
                continue
                
            vehicle_crop = frame[vy1:vy2, vx1:vx2]

            # 2. Plate Detection within the vehicle crop
            with self._model_lock:
                plates = self.plate_detector.detect_plates(vehicle_crop)

            # Plate boxes in full-frame coordinates for the overlay
            plate_boxes = [
                [vx1 + int(pb[0]), vy1 + int(pb[1]), vx1 + int(pb[2]), vy1 + int(pb[3])]
                for _, _, pb in plates
            ]
            
            # Map COCO classes to vehicle types
            type_map = {
                2: "LMV",
                3: "2-Wheeler",
                5: "HMV-Bus",
                7: "HMV-Truck"
            }
            v_type_str = type_map.get(int(class_id), "Unknown")
            
            # Retrieve or create track
            vehicle_track = tracker.get_or_create_track(track_id, timestamp, vehicle_type=v_type_str)
            # Record where the vehicle was, so a bidirectional gate can tell
            # an arrival from a departure when the track finalises.
            vehicle_track.update(
                timestamp,
                point=((vx1 + vx2) / 2.0, (vy1 + vy2) / 2.0),
            )
            
            if vehicle_track.best_vehicle_snapshot is None:
                # Store the raw numpy array, the background service will handle saving it
                vehicle_track.best_vehicle_snapshot = vehicle_crop.copy()
                
            # Capture a live base64 snapshot for the frontend if the vehicle is very close
            is_close = (vy2 - vy1) > (h * 0.3) or (vx2 - vx1) > (w * 0.3)
            if is_close and not hasattr(vehicle_track, 'b64_snapshot'):
                import cv2, base64
                ret, buffer = cv2.imencode('.jpg', vehicle_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                if ret:
                    vehicle_track.b64_snapshot = f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"
            
            for plate_crop, p_conf, p_bbox in plates:
                # 3. OCR Extraction (the detector already applies conditional
                # enhancement; enhancing twice smears characters and hurt OCR)
                with self._model_lock:
                    ocr_results = self.ocr_engine.recognize(plate_crop)
                
                for res in ocr_results:
                    raw_text = res["text"]
                    ocr_conf = res["confidence"]
                    
                    if ocr_conf < anpr_app_config.ocr.confidence_threshold:
                        continue
                        
                    # 4. Validation & Repair
                    is_valid, repaired_text = PlateValidator.repair_and_validate(raw_text, confidence=ocr_conf)
                    
                    if is_valid and repaired_text:
                        # 5. Temporal Fusion
                        vehicle_track.fusion.add_observation(repaired_text, float(ocr_conf), timestamp)
                        
                        # Save the best plate snapshot dynamically based on highest OCR conf seen
                        if not hasattr(vehicle_track, 'max_ocr_seen') or ocr_conf > vehicle_track.max_ocr_seen:
                            vehicle_track.max_ocr_seen = ocr_conf
                            vehicle_track.best_plate_snapshot = plate_crop.copy()

            # Emit a live event so the plate and vehicle box are drawn in the frontend
            best_plate, best_conf = vehicle_track.fusion.get_best_plate()
            if not best_plate and plate_boxes:
                # Plate located but number not confirmed yet — draw the box now
                events.append(DetectionEvent(
                    plugin_name=self.plugin_name,
                    event_type="ANPR_STATS",
                    camera_id=camera_id,
                    timestamp=timestamp,
                    confidence=1.0,
                    metadata={
                        "drawings": [
                            {
                                "type": "rect",
                                "coords": pb,
                                "color": [255, 200, 0],
                                "thickness": 2
                            }
                            for pb in plate_boxes
                        ]
                    }
                ))
            if best_plate:
                import cv2, base64
                b64_veh = getattr(vehicle_track, 'b64_snapshot', None)
                if not b64_veh and vehicle_crop is not None and vehicle_crop.size > 0:
                    ret, buf = cv2.imencode('.jpg', vehicle_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                    if ret:
                        b64_veh = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
                        vehicle_track.b64_snapshot = b64_veh

                b64_plate = getattr(vehicle_track, 'b64_plate_snapshot', None)
                if not b64_plate and hasattr(vehicle_track, 'best_plate_snapshot') and vehicle_track.best_plate_snapshot is not None:
                    ret, buf = cv2.imencode('.jpg', vehicle_track.best_plate_snapshot, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                    if ret:
                        b64_plate = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
                        vehicle_track.b64_plate_snapshot = b64_plate

                live_event = DetectionEvent(
                    plugin_name=self.plugin_name,
                    event_type="LIVE_TRACKING",
                    camera_id=camera_id,
                    timestamp=timestamp,
                    confidence=float(best_conf),
                    metadata={
                        "plate_number": best_plate,
                        "vehicle_type": getattr(vehicle_track, 'vehicle_type', 'Vehicle'),
                        "vehicle_snapshot": b64_veh,
                        "plate_snapshot": b64_plate,
                        "drawings": (
                            [
                                {
                                    "type": "rect",
                                    "coords": vehicle_box,
                                    "color": [0, 255, 0],
                                    "thickness": 2
                                }
                            ]
                            + [
                                {
                                    "type": "rect",
                                    "coords": pb,
                                    "color": [255, 200, 0],
                                    "thickness": 2
                                }
                                for pb in plate_boxes
                            ]
                            + [
                                {
                                    "type": "text",
                                    "coords": [
                                        plate_boxes[0][0] if plate_boxes else vehicle_box[0],
                                        max(0, (plate_boxes[0][1] if plate_boxes else vehicle_box[1]) - 10)
                                    ],
                                    "text": f"{best_plate} ({best_conf:.2f})",
                                    "color": [255, 255, 255],
                                    "thickness": 2,
                                    "scale": 0.8
                                }
                            ]
                        )
                    }
                )
                events.append(live_event)

        # 6. Cleanup Stale Tracks and Emit Final Events
        events.extend(self._cleanup_and_emit(tracker, camera_id, timestamp))
        return events

    def _cleanup_and_emit(self, tracker: ANPRTracker, camera_id: str, timestamp: float) -> List[DetectionEvent]:
        events = []
        # tracker is this camera's own, so a finalized plate can only ever be
        # attributed to the camera that actually saw the vehicle.
        finalized_tracks = tracker.cleanup_stale_tracks(timestamp)
        
        for track in finalized_tracks:
            best_plate, best_conf = track.fusion.get_best_plate()
            
            if best_plate:
                # Save snapshots synchronously to avoid numpy JSON serialization errors
                veh_path = None
                plate_path = None
                if track.best_vehicle_snapshot is not None:
                    veh_path = save_snapshot(track.best_vehicle_snapshot, prefix="veh")
                if track.best_plate_snapshot is not None:
                    plate_path = save_snapshot(track.best_plate_snapshot, prefix="plate")
                
                # Dispatch async DB log task
                track_info = {
                    "track_id": str(track.track_id),
                    "camera_id": camera_id,
                    "start_time": track.start_time,
                    "end_time": track.last_seen,
                    "best_plate": best_plate,
                    "plate_confidence": float(best_conf),
                    "vehicle_type": track.vehicle_type,
                    "vehicle_snapshot": veh_path,
                    "plate_snapshot": plate_path
                }
                
                # Match the read against the blacklist/whitelist here rather
                # than only in the database writer: a hit has to reach the
                # live overlay, the events feed and the alert engine, and the
                # writer thread can do none of those. The index is cached, so
                # this is a dict lookup, not a query.
                entry, match_kind = plate_watchlist.match(best_plate)
                track_info["watchlist_id"] = entry["id"] if entry else None
                track_info["watchlist_match_kind"] = match_kind

                # Gate-wise outcome (SOW 2.6): which way the vehicle went
                # through this gate, and whether the client's rules permit it.
                gate = gate_registry.for_camera(camera_id)
                direction = decision = deny_reason = None
                if gate is not None:
                    direction = resolve_direction(
                        gate["role"], track.first_point, track.last_point,
                        axis=gate["axis"], invert=gate["invert"],
                        min_travel_px=gate["min_travel_px"],
                    )
                    decision, deny_reason = decide_access(
                        entry["list_type"] if entry else None,
                        gate["access_rules"],
                    )
                track_info["direction"] = direction

                self.executor.submit(anpr_service._handle_track, {"track_info": track_info})

                # Emit WebSocket Event for real-time frontend
                metadata = {
                    "plate_number": best_plate,
                    "track_id": track.track_id,
                    "vehicle_type": track.vehicle_type,
                    "vehicle_snapshot": veh_path,
                    "plate_snapshot": plate_path,
                    "drawings": []
                }
                if gate is not None:
                    metadata.update({
                        "gate_id": gate["gate_id"],
                        "gate_name": gate["name"],
                        "direction": direction,
                        "access": decision,
                        "access_reason": deny_reason,
                    })
                if entry is not None:
                    metadata.update({
                        "list_type": entry["list_type"],
                        "list_reason": entry["reason"],
                        "list_priority": entry["priority"],
                        "listed_plate": entry["plate_number"],
                        "match_kind": match_kind,
                    })
                event = DetectionEvent(
                    plugin_name=self.plugin_name,
                    event_type=ANPREventType.NEW_PLATE.value,
                    camera_id=camera_id,
                    timestamp=track.last_seen,
                    confidence=float(best_conf),
                    metadata=metadata
                )
                events.append(event)

                # The gate pass itself, as its own event, so "who came in
                # this morning" and "who was turned away" are answerable
                # without reconstructing them from plate reads.
                if gate is not None:
                    events.append(DetectionEvent(
                        plugin_name=self.plugin_name,
                        event_type=event_type_for(direction, decision),
                        camera_id=camera_id,
                        timestamp=track.last_seen,
                        confidence=float(best_conf),
                        metadata=dict(metadata),
                    ))
                    if decision == DENY:
                        logger.warning(
                            f"ACCESS DENIED at {gate['name']}: {best_plate} "
                            f"({deny_reason})"
                        )

                if entry is not None:
                    blacklisted = is_blacklist(entry["list_type"])
                    if blacklisted:
                        logger.warning(
                            f"BLACKLIST PLATE {best_plate} on {camera_id} "
                            f"(listed as {entry['plate_number']}, {match_kind})"
                        )
                    hit_meta = dict(metadata)
                    hit_meta["severity"] = "critical" if blacklisted else "info"
                    if blacklisted:
                        # The key the alert engine reads, so a blacklisted
                        # vehicle dispatches SMS/email with no extra wiring.
                        hit_meta["active_alerts"] = ["BLACKLIST_MATCH"]
                    events.append(DetectionEvent(
                        plugin_name=self.plugin_name,
                        event_type=(ANPREventType.BLACKLIST_MATCH.value if blacklisted
                                    else ANPREventType.WHITELIST_MATCH.value),
                        camera_id=camera_id,
                        timestamp=track.last_seen,
                        confidence=float(best_conf),
                        metadata=hit_meta,
                    ))
                
        return events
