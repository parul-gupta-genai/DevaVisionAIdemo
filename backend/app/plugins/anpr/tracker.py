import time
from typing import Dict, Any, List, Optional
from app.plugins.anpr.fusion import TemporalFusion

class TrackedVehicle:
    def __init__(self, track_id: int, start_time: float, vehicle_type: str = "car"):
        self.track_id = track_id
        self.start_time = start_time
        self.last_seen = start_time
        self.vehicle_type = vehicle_type
        self.fusion = TemporalFusion()
        self.best_plate_snapshot = None
        self.best_vehicle_snapshot = None
        self.finalized = False
        self.reported = False # True if we already triggered NEW_PLATE
        # Where the vehicle was first and last seen, in mux space. A
        # bidirectional gate infers entry vs exit from the travel between
        # them; a designated gate ignores them.
        self.first_point = None
        self.last_point = None

    def update(self, current_time: float, point=None):
        self.last_seen = current_time
        if point is not None:
            if self.first_point is None:
                self.first_point = (float(point[0]), float(point[1]))
            self.last_point = (float(point[0]), float(point[1]))

class ANPRTracker:
    def __init__(self, track_timeout: float = 3.0):
        self.active_tracks: Dict[int, TrackedVehicle] = {}
        self.track_timeout = track_timeout

    def get_or_create_track(self, track_id: int, current_time: float, vehicle_type: str = "car") -> TrackedVehicle:
        if track_id not in self.active_tracks:
            self.active_tracks[track_id] = TrackedVehicle(track_id, current_time, vehicle_type)
        return self.active_tracks[track_id]

    def cleanup_stale_tracks(self, current_time: float) -> List[TrackedVehicle]:
        """
        Removes tracks that haven't been seen in `track_timeout` seconds.
        Returns the finalized tracks so events can be dispatched.
        """
        stale_ids = []
        finalized_tracks = []
        for tid, track in self.active_tracks.items():
            if current_time - track.last_seen > self.track_timeout:
                stale_ids.append(tid)
                track.finalized = True
                finalized_tracks.append(track)
                
        for tid in stale_ids:
            del self.active_tracks[tid]
            
        return finalized_tracks
