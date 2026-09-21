import threading
import time
from sqlalchemy.orm import Session
from app.plugins.anpr.models import (
    ANPREvent, ANPRGate, ANPRVehicleTrack, ANPRPlateHistory, ANPRWatchlist,
)
from typing import Dict, List, Optional

from loguru import logger


GATE_TTL_SEC = 30.0


class GateRegistry:
    """
    Camera -> gate, cached for the analytics thread.

    The plugin resolves a gate for every finalised vehicle track, which on a
    busy site is several times a second across every camera. That cannot be a
    query each time, and it must never raise into the pipeline: a database
    blip degrades ANPR to plate logging without a gate, not to an exception
    on the streaming path.
    """

    def __init__(self, ttl_sec: float = GATE_TTL_SEC):
        self.ttl_sec = ttl_sec
        self.by_camera: Dict[str, dict] = {}
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def invalidate(self) -> None:
        with self._lock:
            self._fetched_at = 0.0

    def refresh(self, force: bool = False) -> None:
        if not force and (time.time() - self._fetched_at) < self.ttl_sec:
            return
        with self._lock:
            if not force and (time.time() - self._fetched_at) < self.ttl_sec:
                return
            try:
                from database.session import SessionLocal

                db = SessionLocal()
                try:
                    rows = (db.query(ANPRGate)
                            .filter(ANPRGate.is_active.is_(True)).all())
                    self.by_camera = {r.camera_id: gate_to_dict(r) for r in rows}
                finally:
                    db.close()
                self._fetched_at = time.time()
            except Exception as exc:
                # Keep serving the previous snapshot rather than blanking it.
                logger.warning(f"Gate registry refresh failed: {exc}")
                self._fetched_at = time.time()

    def for_camera(self, camera_id: str) -> Optional[dict]:
        self.refresh()
        return self.by_camera.get(camera_id)


def gate_to_dict(row: ANPRGate) -> dict:
    """Plain dict for the analytics thread; never hands out an ORM row."""
    from app.plugins.anpr.gates import normalise_role, sanitize_rules

    try:
        rules = sanitize_rules(row.access_rules)
    except ValueError:
        # A rule saved before validation tightened must not break the gate.
        rules = sanitize_rules(None)
    return {
        "gate_id": row.gate_id,
        "name": row.name,
        "camera_id": row.camera_id,
        "role": normalise_role(row.role),
        "axis": row.axis or "VERTICAL",
        "invert": bool(row.invert),
        "min_travel_px": float(row.min_travel_px or 40.0),
        "access_rules": rules,
    }


gate_registry = GateRegistry()


class ANPRRepository:
    def __init__(self, db_session: Session):
        self.db = db_session

    def create_event(self, event_data: dict) -> ANPREvent:
        db_event = ANPREvent(**event_data)
        self.db.add(db_event)
        self.db.commit()
        self.db.refresh(db_event)
        return db_event

    def create_vehicle_track(self, track_data: dict) -> ANPRVehicleTrack:
        db_track = ANPRVehicleTrack(**track_data)
        self.db.add(db_track)
        self.db.commit()
        self.db.refresh(db_track)
        return db_track

    def get_watchlist_match(self, plate_number: str) -> Optional[ANPRWatchlist]:
        """
        Exact lookup on the normalised plate.

        Kept for callers that want strict equality; live matching goes through
        app.plugins.anpr.watchlist, which also tolerates OCR confusions and
        honours expiry. Normalising here at least means a list entry typed as
        "UP 16 B 3895" is found by a read of "UP16B3895".
        """
        from app.plugins.anpr.watchlist import normalise
        target = normalise(plate_number)
        if not target:
            return None
        return (
            self.db.query(ANPRWatchlist)
            .filter(ANPRWatchlist.plate_number == target)
            .first()
        )

    def get_watchlist_by_id(self, watchlist_id: str) -> Optional[ANPRWatchlist]:
        if not watchlist_id:
            return None
        return (
            self.db.query(ANPRWatchlist)
            .filter(ANPRWatchlist.id == watchlist_id)
            .first()
        )
    
    def log_plate_history(self, history_data: dict) -> ANPRPlateHistory:
        db_history = ANPRPlateHistory(**history_data)
        self.db.add(db_history)
        self.db.commit()
        self.db.refresh(db_history)
        return db_history
