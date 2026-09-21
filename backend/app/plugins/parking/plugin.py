from typing import List, Dict, Any
from loguru import logger
from shapely.geometry import Point, Polygon
import time

from app.engine.base import BaseDetectionPlugin, FrameData, TrackerContext, DetectionEvent
from config.config import config
from app.engine.snapshots import save_event_snapshot, frame_for_snapshot

class ParkingAnalyticsPlugin(BaseDetectionPlugin):
    """
    Handles Vehicle Detection and Parking Occupancy.
    """

    # Works purely off detection geometry and the configured bay polygons.
    needs_frame = False
    # previous_occupancy / last_alert_time are keyed by camera_id.
    thread_safe = True

    def __init__(self, app_config=None):
        super().__init__(app_config)
        # COCO Classes for vehicles: 2=car, 3=motorcycle, 5=bus, 7=truck
        self.vehicle_classes = {2, 3, 5, 7}
        self.previous_occupancy = {}
        self.last_alert_time = {}
        logger.info("Initialized ParkingAnalyticsPlugin")

    @property
    def plugin_name(self) -> str:
        return "ParkingAnalyticsPlugin"

    def get_required_classes(self) -> List[int]:
        return list(self.vehicle_classes)

    def process_frame(self, frame_data: FrameData, tracker_context: TrackerContext) -> List[DetectionEvent]:
        camera_id = frame_data.camera_id
        camera_url = getattr(frame_data, 'camera_url', camera_id)
        timestamp = frame_data.timestamp
        events = []
        
        spots = config.get_parking_spots_for_camera(camera_url)
        if not spots:
            # Fallback to 2 default green boxes if none are configured
            spots = [
                [[200, 300], [500, 300], [450, 600], [150, 600]], # Bay 1
                [[550, 300], [850, 300], [800, 600], [500, 600]]  # Bay 2
            ]
            
        # Shapely polygons are rebuilt only when the bays actually change.
        # Constructing them per frame made this the most expensive plugin on
        # the appliance at 8.3ms a call — more than the fire detector — for
        # geometry that changes when an operator edits a bay, i.e. almost
        # never. Compared by value so a live config update still takes effect.
        state = tracker_context.get_state(self.plugin_name, camera_id)
        if state.get("spots_src") != spots:
            state["spots_src"] = spots
            state["spot_polys"] = [Polygon(spot) for spot in spots]
        spot_polys = state["spot_polys"]
        
        occupied_spots = [False] * len(spots)
        vehicle_count = 0
        
        for det in frame_data.detections:
            if det.class_id not in self.vehicle_classes:
                continue
                
            vehicle_count += 1
            
            x1, y1, x2, y2 = det.bbox
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            center_point = Point(center_x, center_y)
            
            for idx, poly in enumerate(spot_polys):
                if poly.contains(center_point):
                    occupied_spots[idx] = True
                        
        total_spots = len(spots)
        occupied_count = sum(occupied_spots)
        available_count = total_spots - occupied_count
        
        drawings = []
        for idx, spot in enumerate(spots):
            color = [0, 0, 255] if occupied_spots[idx] else [0, 255, 0]
            drawings.append({
                "type": "poly",
                "coords": spot,
                "color": color,
                "thickness": 3,
                "opacity": 0.35
            })
            drawings.append({
                "type": "text",
                "text": f"Bay {idx + 1}",
                "coords": [spot[0][0], spot[0][1] - 10],
                "color": color,
                "scale": 0.6,
                "thickness": 2
            })
            
        # Detect state transitions for alerts
        if camera_id not in self.previous_occupancy:
            self.previous_occupancy[camera_id] = [False] * len(spots)
            self.last_alert_time[camera_id] = [0.0] * len(spots)
            
        now = time.time()
        for idx, (is_occupied, was_occupied) in enumerate(zip(occupied_spots, self.previous_occupancy[camera_id])):
            if is_occupied and not was_occupied:
                if now - self.last_alert_time[camera_id][idx] > 5.0: # 5 second cooldown
                    events.append(DetectionEvent(
                        plugin_name=self.plugin_name,
                        event_type="PARKING_ALERT",
                        camera_id=camera_id,
                        timestamp=timestamp,
                        confidence=1.0,
                        metadata={
                            "severity": "warning",
                            "bay_id": idx + 1,
                            "status": "OCCUPIED",
                            "snapshot_file": save_event_snapshot(
                                "parking", camera_id,
                                frame_for_snapshot(frame_data, tracker_context, camera_id),
                            ),
                            "description": f"Car entered Parking Bay {idx + 1}!"
                        }
                    ))
                    self.last_alert_time[camera_id][idx] = now
                    
        self.previous_occupancy[camera_id] = occupied_spots
            
        event = DetectionEvent(
            plugin_name=self.plugin_name,
            event_type="PARKING_STATS",
            camera_id=camera_id,
            timestamp=timestamp,
            confidence=1.0,
            metadata={
                "vehicle_count": vehicle_count,
                "total_spots": total_spots,
                "occupied_spots": occupied_count,
                "available_spots": available_count,
                "spot_status": occupied_spots,
                "drawings": drawings
            }
        )
        events.append(event)
            
        return events
