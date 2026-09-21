import time
import numpy as np
from typing import List
from app.engine.base import BaseDetectionPlugin, FrameData, TrackerContext, DetectionEvent
from app.engine.snapshots import save_event_snapshot, frame_for_snapshot

class CartonCountingPlugin(BaseDetectionPlugin):
    """
    Highly optimized carton (box) tracking plugin.
    Detects COCO class 28 (suitcase) which YOLO uses for cartons/boxes on the conveyor belt.
    Uses a custom centroid tracker to bypass ByteTrack's strict confidence thresholds.
    Counts cartons when they cross a vertical line.
    """

    # Only needs the frame DIMENSIONS (to place the exit line), never pixels.
    needs_frame = False
    # Every mutable field lives in TrackerContext, keyed by (plugin, camera).
    thread_safe = True

    CARTON_CLASSES = {24, 26, 28, 73, 41, 69, 56, 55}

    def __init__(self, app_config=None):
        super().__init__(app_config)
        # Tuning only — no per-camera state on the instance. Sharing the
        # centroid tracker and the counted set across cameras merged every
        # camera's cartons into one running total.
        self.max_distance = 250   # Max pixel distance to match objects on conveyor
        self.max_disappeared = 60 # Frames to keep track of a lost object

    def _camera_state(self, tracker_context: TrackerContext, frame_data: FrameData) -> dict:
        state = tracker_context.get_state(self.plugin_name, frame_data.camera_id)
        if "objects" not in state:
            # frame_shape is (height, width) and is always populated, even when
            # the frame surface itself was not copied.
            h, w = frame_data.frame_shape
            state.update({
                "objects": {},        # id -> (cx, cy)
                "disappeared": {},    # id -> frames_disappeared
                "next_id": 1,
                "carton_history": {}, # id -> last_x
                "counted_ids": set(),  # ids already counted (pruned with the tracker)
                "total_counted": 0,    # monotonic total, survives that pruning
                "exit_line_x": w // 2,
                "exit_line_y_min": int(h * 0.5),
                "exit_line_y_max": h,
            })
        return state

    @staticmethod
    def _forget(state: dict, obj_id) -> None:
        """Drops all per-object bookkeeping when the tracker retires an id.

        counted_ids and carton_history used to grow without bound for the
        life of the process; total_counted keeps the running total correct
        while the id sets stay proportional to what is actually on screen.
        """
        state["objects"].pop(obj_id, None)
        state["disappeared"].pop(obj_id, None)
        state["carton_history"].pop(obj_id, None)
        state["counted_ids"].discard(obj_id)

    def _compute_iou(self, boxA, boxB):
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        if float(boxAArea + boxBArea - interArea) == 0:
            return 0.0
        return interArea / float(boxAArea + boxBArea - interArea)

    def _update_tracker(self, state, input_centroids):
        objects = state["objects"]
        disappeared = state["disappeared"]
        rect_to_id = {}

        def _register(centroid, col):
            obj_id = state["next_id"]
            objects[obj_id] = centroid
            disappeared[obj_id] = 0
            rect_to_id[col] = obj_id
            state["next_id"] += 1

        if len(input_centroids) == 0:
            for obj_id in list(disappeared.keys()):
                disappeared[obj_id] += 1
                if disappeared[obj_id] > self.max_disappeared:
                    self._forget(state, obj_id)
            return rect_to_id

        if len(objects) == 0:
            for i in range(len(input_centroids)):
                _register(input_centroids[i], i)
            return rect_to_id

        object_ids = list(objects.keys())
        object_centroids = np.array(list(objects.values()))

        diff = object_centroids[:, np.newaxis, :] - input_centroids[np.newaxis, :, :]
        D = np.sqrt(np.sum(diff ** 2, axis=-1))

        rows = D.min(axis=1).argsort()
        cols = D.argmin(axis=1)[rows]

        used_rows, used_cols = set(), set()

        for (row, col) in zip(rows, cols):
            if row in used_rows or col in used_cols:
                continue
            if D[row, col] > self.max_distance:
                continue

            obj_id = object_ids[row]
            objects[obj_id] = input_centroids[col]
            disappeared[obj_id] = 0
            rect_to_id[col] = obj_id

            used_rows.add(row)
            used_cols.add(col)

        unused_rows = set(range(D.shape[0])) - used_rows
        unused_cols = set(range(D.shape[1])) - used_cols

        for row in unused_rows:
            obj_id = object_ids[row]
            disappeared[obj_id] += 1
            if disappeared[obj_id] > self.max_disappeared:
                self._forget(state, obj_id)

        for col in unused_cols:
            _register(input_centroids[col], col)

        return rect_to_id

    @property
    def plugin_name(self) -> str:
        return "CartonCountingPlugin"

    def get_required_classes(self) -> List[int]:
        # COCO classes that look like cartons/boxes:
        return sorted(self.CARTON_CLASSES)

    def process_frame(self, frame_data: FrameData, tracker_context: TrackerContext) -> List[DetectionEvent]:
        events = []
        state = self._camera_state(tracker_context, frame_data)

        exit_line_x = state["exit_line_x"]
        exit_line_y_min = state["exit_line_y_min"]
        exit_line_y_max = state["exit_line_y_max"]

        drawings = []

        # Draw the counting line segment (not full screen)
        drawings.append({
            "type": "line",
            "coords": [[exit_line_x, exit_line_y_min], [exit_line_x, exit_line_y_max]],
            "color": [0, 255, 0],
            "thickness": 3
        })

        valid_boxes = []
        input_centroids = []

        for det in frame_data.detections:
            if det.class_id in self.CARTON_CLASSES:
                x1, y1, x2, y2 = det.bbox

                # Prevent multiple overlapping classes (e.g. suitcase and handbag) on the same physical carton
                overlap = False
                for existing_box in valid_boxes:
                    if self._compute_iou((x1, y1, x2, y2), existing_box) > 0.4:
                        overlap = True
                        break

                if not overlap:
                    valid_boxes.append((x1, y1, x2, y2))
                    input_centroids.append([(x1+x2)/2, (y1+y2)/2])

        input_centroids = np.array(input_centroids) if input_centroids else np.array([])
        rect_to_id = self._update_tracker(state, input_centroids)

        counted_ids = state["counted_ids"]
        carton_history = state["carton_history"]

        for i, (x1, y1, x2, y2) in enumerate(valid_boxes):
            tid = rect_to_id.get(i, f"U-{i}")
            current_x = (x1 + x2) / 2
            current_y = (y1 + y2) / 2

            if tid not in counted_ids:
                if tid in carton_history:
                    last_x = carton_history[tid]
                    # Check if line was crossed AND if the carton is within the Y bounds of the exit line
                    if (last_x <= exit_line_x < current_x) or (last_x >= exit_line_x > current_x):
                        if exit_line_y_min <= current_y <= exit_line_y_max:
                            counted_ids.add(tid)
                            state["total_counted"] += 1
                            # CARTON_STATS is filtered out before the DB (it
                            # fires every frame for the overlay), so a counted
                            # carton needs its own recorded event or nothing
                            # ever reaches the events feed.
                            events.append(DetectionEvent(
                                plugin_name=self.plugin_name,
                                event_type="CARTON_COUNTED",
                                camera_id=frame_data.camera_id,
                                timestamp=frame_data.timestamp,
                                confidence=1.0,
                                metadata={
                                    "carton_id": str(tid),
                                    "total_cartons_counted": state["total_counted"],
                                    "snapshot_file": save_event_snapshot(
                                        "carton", frame_data.camera_id,
                                        frame_for_snapshot(frame_data, tracker_context,
                                                           frame_data.camera_id),
                                        bbox=[x1, y1, x2, y2],
                                    ),
                                }
                            ))
                carton_history[tid] = current_x

            color = [0, 255, 0] if tid in counted_ids else [255, 140, 0]

            drawings.append({
                "type": "rect",
                "coords": [x1, y1, x2, y2],
                "color": color,
                "thickness": 2
            })
            drawings.append({
                "type": "text",
                "coords": [x1, max(0, y1 - 10)],
                "color": color,
                "text": f"ID: {tid}",
                "scale": 0.8,
                "thickness": 2
            })

        # Emit stats every frame to update UI instantly
        events.append(DetectionEvent(
            plugin_name=self.plugin_name,
            event_type="CARTON_STATS",
            camera_id=frame_data.camera_id,
            timestamp=frame_data.timestamp,
            confidence=1.0,
            metadata={
                "total_cartons_counted": state["total_counted"],
                "drawings": drawings
            }
        ))

        return events
