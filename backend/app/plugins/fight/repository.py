"""
Fight zone storage, the snapshot the plugin matches against, and the event
writer.

Same three-concern shape as restricted zones, for the same reason: they share
a cache invalidation. The plugin needs every zone for a camera on every
sampled frame, on the analytics thread, so a query there would put a database
round trip in the hot path of 25 cameras; and an incident must be recorded
without ever stalling the frame that detected it.
"""

import queue
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence

from loguru import logger
from sqlalchemy import func as sqlfunc

from app.plugins.fight import rules
from app.plugins.fight.models import FightEvent, FightZone
from app.plugins.zones.geometry import sanitize_polygon

REGISTRY_TTL_SEC = 15.0
# Backoff after a failed refresh. Without it a database outage means every
# camera retries the connection on every frame, which turns a recoverable
# blip into an outage of its own.
REGISTRY_RETRY_SEC = 10.0
WRITE_QUEUE_MAX = 2000
WRITE_BATCH = 50

OVERRIDE_COLUMNS = ("min_score", "min_frames", "confirm_sec",
                    "engage_separation", "clear_sec", "alert_cooldown_sec")


def new_zone_id() -> str:
    return f"FT-{uuid.uuid4().hex[:10].upper()}"


def new_event_id() -> str:
    return f"FGV-{uuid.uuid4().hex[:12].upper()}"


class FightZoneRepository:
    def __init__(self, db):
        self.db = db

    # ---------------- zones ----------------
    def list_zones(self, camera_id: Optional[str] = None,
                   active_only: bool = False) -> List[FightZone]:
        q = self.db.query(FightZone)
        if camera_id:
            q = q.filter(FightZone.camera_id == camera_id)
        if active_only:
            q = q.filter(FightZone.is_active.is_(True))
        return q.order_by(FightZone.camera_id, FightZone.name).all()

    def get_zone(self, zone_id: str) -> Optional[FightZone]:
        return self.db.query(FightZone).filter(FightZone.zone_id == zone_id).first()

    def name_taken(self, camera_id: str, name: str,
                   exclude_id: Optional[str] = None) -> bool:
        q = self.db.query(FightZone).filter(
            FightZone.camera_id == camera_id, FightZone.name == name)
        if exclude_id:
            q = q.filter(FightZone.zone_id != exclude_id)
        return q.count() > 0

    def create_zone(self, **fields) -> FightZone:
        row = FightZone(zone_id=new_zone_id(), **fields)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        fight_zone_registry.invalidate()
        return row

    def update_zone(self, zone: FightZone, **fields) -> FightZone:
        for key, value in fields.items():
            setattr(zone, key, value)
        self.db.commit()
        self.db.refresh(zone)
        fight_zone_registry.invalidate()
        return zone

    def delete_zone(self, zone_id: str) -> bool:
        row = self.get_zone(zone_id)
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        fight_zone_registry.invalidate()
        return True

    def cameras_with_zones(self) -> List[str]:
        rows = self.db.query(FightZone.camera_id).filter(
            FightZone.is_active.is_(True)).distinct().all()
        return [r[0] for r in rows]

    # ---------------- events ----------------
    def list_events(self, *, camera_id=None, zone_id=None, event_type=None,
                    severity=None, acknowledged=None, verified=None,
                    since=None, until=None, limit=50, offset=0):
        q = self.db.query(FightEvent)
        if camera_id:
            q = q.filter(FightEvent.camera_id == camera_id)
        if zone_id:
            q = q.filter(FightEvent.zone_id == zone_id)
        if event_type:
            q = q.filter(FightEvent.event_type == event_type)
        if severity:
            q = q.filter(FightEvent.severity == severity)
        if acknowledged is not None:
            q = q.filter(FightEvent.acknowledged.is_(bool(acknowledged)))
        if verified:
            q = q.filter(FightEvent.verified == verified)
        if since:
            q = q.filter(FightEvent.timestamp >= since)
        if until:
            q = q.filter(FightEvent.timestamp <= until)
        total = q.count()
        rows = (q.order_by(FightEvent.timestamp.desc())
                .offset(max(0, offset)).limit(max(1, min(500, limit))).all())
        return rows, total

    def get_event(self, event_id: str) -> Optional[FightEvent]:
        return self.db.query(FightEvent).filter(
            FightEvent.event_id == event_id).first()

    def acknowledge(self, event_id: str, who: Optional[str],
                    note: Optional[str] = None) -> Optional[FightEvent]:
        row = self.get_event(event_id)
        if row is None:
            return None
        row.acknowledged = True
        row.acknowledged_by = who
        row.acknowledged_at = datetime.utcnow()
        row.ack_note = note
        self.db.commit()
        self.db.refresh(row)
        return row

    def summary(self, since: Optional[datetime] = None) -> dict:
        since = since or (datetime.utcnow() - timedelta(days=7))
        base = self.db.query(FightEvent).filter(FightEvent.timestamp >= since)
        by_verdict = dict(
            self.db.query(FightEvent.verified, sqlfunc.count(FightEvent.event_id))
            .filter(FightEvent.timestamp >= since)
            .group_by(FightEvent.verified).all())
        by_camera = [
            {"camera_id": c, "camera_name": n, "count": k}
            for c, n, k in
            self.db.query(FightEvent.camera_id, FightEvent.camera_name,
                          sqlfunc.count(FightEvent.event_id))
            .filter(FightEvent.timestamp >= since)
            .group_by(FightEvent.camera_id, FightEvent.camera_name)
            .order_by(sqlfunc.count(FightEvent.event_id).desc()).limit(20).all()]
        return {
            "since": since.isoformat(),
            "total": base.count(),
            "unacknowledged": base.filter(FightEvent.acknowledged.is_(False)).count(),
            "by_verdict": by_verdict,
            "by_camera": by_camera,
            "advisory_notice": rules.ADVISORY_NOTICE,
        }


# --------------------------------------------------------------------------
# The snapshot the plugin reads
# --------------------------------------------------------------------------

def zone_to_snapshot(row: FightZone) -> Optional[dict]:
    """
    Turns a stored zone into the plain dict the state machine consumes, or
    None when its geometry no longer validates — a row corrupted by a bad
    write can then only disable itself, rather than raise on the analytics
    thread of every frame.
    """
    points = sanitize_polygon(row.points)
    if points is None:
        return None
    overrides = {k: getattr(row, k) for k in OVERRIDE_COLUMNS
                 if getattr(row, k, None) is not None}
    return {
        "zone_id": row.zone_id,
        "name": row.name,
        "camera_id": row.camera_id,
        "points": points,
        "zone_kind": (row.zone_kind or "DETECT").upper(),
        "is_active": bool(row.is_active),
        "sensitivity": rules.sanitize_sensitivity(row.sensitivity),
        "severity": row.severity or None,
        "overrides": overrides,
        "schedule": row.schedule or None,
    }


class FightZoneRegistry:
    """Per-camera zone snapshot, refreshed on a TTL and on every edit."""

    def __init__(self, ttl_sec: float = REGISTRY_TTL_SEC):
        self.ttl_sec = ttl_sec
        self.by_camera: Dict[str, List[dict]] = {}
        self.loaded = False
        self._loaded_at = 0.0
        self._last_error_log = 0.0
        self._lock = threading.Lock()

    def invalidate(self) -> None:
        self._loaded_at = 0.0

    def refresh(self, force: bool = False) -> None:
        if not force and (time.monotonic() - self._loaded_at) < self.ttl_sec:
            return
        if not self._lock.acquire(blocking=False):
            return                      # another thread is already reloading
        try:
            if not force and (time.monotonic() - self._loaded_at) < self.ttl_sec:
                return
            from database.session import SessionLocal

            db = SessionLocal()
            try:
                by_camera: Dict[str, List[dict]] = {}
                for row in FightZoneRepository(db).list_zones(active_only=True):
                    snap = zone_to_snapshot(row)
                    if snap is None:
                        logger.warning(
                            f"Fight zone {row.zone_id} ({row.name}) has unusable "
                            f"geometry and was skipped")
                        continue
                    by_camera.setdefault(row.camera_id, []).append(snap)
                self.by_camera = by_camera
                self.loaded = True
                self._loaded_at = time.monotonic()
            finally:
                db.close()
        except Exception as exc:
            # Keep the previous snapshot. A database blip must not silently
            # reconfigure fight detection on every camera on the site.
            self._loaded_at = time.monotonic() - self.ttl_sec + REGISTRY_RETRY_SEC
            if (time.monotonic() - self._last_error_log) > 60.0:
                self._last_error_log = time.monotonic()
                logger.error(f"Fight zone registry refresh failed: {exc}")
        finally:
            self._lock.release()

    def for_camera(self, camera_id: str) -> List[dict]:
        """
        This camera's zones, or None while the registry has never loaded.

        The distinction matters and is easy to get wrong. An empty list means
        "nobody drew a zone", which the service reads as "watch the whole
        frame". If a database outage at startup also returned an empty list,
        every camera on the site would silently switch to whole-frame
        monitoring WITH ITS EXCLUSION ZONES MISSING — so the gym and the
        loading crew that an operator carefully excluded would start
        raising fight alarms, which is exactly the failure that gets a
        security aid muted.

        None therefore means "not known yet"; the caller holds off rather than
        guessing. Once a load has succeeded the previous snapshot is kept
        across later failures, so a blip never disarms anything.
        """
        self.refresh()
        if not self.loaded:
            return None
        return self.by_camera.get(camera_id, [])


fight_zone_registry = FightZoneRegistry()


# --------------------------------------------------------------------------
# The event log writer
# --------------------------------------------------------------------------

class FightEventLog:
    """Queues fight events and writes them from one background thread."""

    def __init__(self):
        self._queue: "queue.Queue[dict]" = queue.Queue(maxsize=WRITE_QUEUE_MAX)
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._lock = threading.Lock()
        self.dropped = 0
        self.written = 0

    def _ensure_worker(self) -> None:
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            self._thread = threading.Thread(target=self._run, name="fight-event-log",
                                            daemon=True)
            self._thread.start()
            self._started = True

    def record(self, payload: dict) -> bool:
        self._ensure_worker()
        try:
            self._queue.put_nowait(payload)
            return True
        except queue.Full:
            self.dropped += 1
            if self.dropped in (1, 10, 100) or self.dropped % 500 == 0:
                logger.warning(f"Fight event queue full; dropped {self.dropped}")
            return False

    def _run(self) -> None:
        while True:
            batch = [self._queue.get()]
            try:
                while len(batch) < WRITE_BATCH:
                    batch.append(self._queue.get_nowait())
            except queue.Empty:
                pass
            try:
                self._flush(batch)
            except Exception as exc:
                logger.error(f"Fight event write failed ({len(batch)} rows): {exc}")
            finally:
                for _ in batch:
                    self._queue.task_done()

    def _flush(self, batch: Sequence[dict]) -> None:
        from database.session import SessionLocal

        db = SessionLocal()
        try:
            try:
                for payload in batch:
                    db.add(FightEvent(event_id=new_event_id(), **payload))
                db.commit()
                self.written += len(batch)
                return
            except Exception as exc:
                # One malformed payload would otherwise take the other 49
                # confirmed incidents down with it. Retry row by row so a
                # single bad record loses only itself, and say which.
                db.rollback()
                logger.warning(
                    f"Fight event batch of {len(batch)} failed ({exc}); "
                    f"retrying rows individually")

            for payload in batch:
                try:
                    db.add(FightEvent(event_id=new_event_id(), **payload))
                    db.commit()
                    self.written += 1
                except Exception as exc:
                    db.rollback()
                    self.dropped += 1
                    logger.error(
                        f"Dropped unwritable fight event for camera "
                        f"{payload.get('camera_id')}: {exc}")
        finally:
            db.close()

    def health(self) -> dict:
        return {"queued": self._queue.qsize(), "written": self.written,
                "dropped": self.dropped}


fight_event_log = FightEventLog()
