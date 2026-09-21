"""
Zone storage, the snapshot the plugins match against, and the event writer.

Three separate concerns, one module, because they share the same cache
invalidation:

  * ZoneRepository — plain CRUD, used by the API.
  * zone_registry — a dict-of-dicts snapshot refreshed on a short TTL. The
    plugins need every zone for a camera on every sampled frame, on the
    analytics thread; a query there would put a database round trip in the
    hot path of 62 cameras.
  * zone_event_log — a bounded queue drained by one background thread. A
    breach must be recorded, but never at the cost of stalling the frame
    that detected it.
"""

import queue
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger
from sqlalchemy import func as sqlfunc

from app.plugins.zones.geometry import DEFAULT_ANCHOR, sanitize_polygon
from app.plugins.zones.rules import sanitize_classes
from app.plugins.zones.models import RestrictedZone, ZoneEvent

REGISTRY_TTL_SEC = 15.0
# How long to wait before retrying after a failed refresh. Without it a
# database outage means every camera retries the connection on every
# frame — 62 cameras at 6Hz is ~370 connection attempts a second, each
# logging an error, which turns a recoverable blip into an outage of its
# own.
REGISTRY_RETRY_SEC = 10.0
WRITE_QUEUE_MAX = 2000
WRITE_BATCH = 50


def new_zone_id() -> str:
    return f"ZONE-{uuid.uuid4().hex[:10].upper()}"


def new_event_id() -> str:
    return f"ZEV-{uuid.uuid4().hex[:12].upper()}"


class ZoneRepository:
    def __init__(self, db):
        self.db = db

    # ---------------- zones ----------------
    def list_zones(self, camera_id: Optional[str] = None,
                   active_only: bool = False) -> List[RestrictedZone]:
        q = self.db.query(RestrictedZone)
        if camera_id:
            q = q.filter(RestrictedZone.camera_id == camera_id)
        if active_only:
            q = q.filter(RestrictedZone.is_active.is_(True))
        return q.order_by(RestrictedZone.camera_id, RestrictedZone.name).all()

    def get_zone(self, zone_id: str) -> Optional[RestrictedZone]:
        return self.db.query(RestrictedZone).filter(
            RestrictedZone.zone_id == zone_id).first()

    def name_taken(self, camera_id: str, name: str,
                   exclude_id: Optional[str] = None) -> bool:
        q = self.db.query(RestrictedZone).filter(
            RestrictedZone.camera_id == camera_id, RestrictedZone.name == name)
        if exclude_id:
            q = q.filter(RestrictedZone.zone_id != exclude_id)
        return q.count() > 0

    def create_zone(self, **fields) -> RestrictedZone:
        row = RestrictedZone(zone_id=new_zone_id(), **fields)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        zone_registry.invalidate()
        return row

    def update_zone(self, zone: RestrictedZone, **fields) -> RestrictedZone:
        for key, value in fields.items():
            setattr(zone, key, value)
        self.db.commit()
        self.db.refresh(zone)
        zone_registry.invalidate()
        return zone

    def delete_zone(self, zone_id: str) -> bool:
        row = self.get_zone(zone_id)
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        zone_registry.invalidate()
        return True

    def cameras_with_zones(self) -> List[str]:
        rows = self.db.query(RestrictedZone.camera_id).filter(
            RestrictedZone.is_active.is_(True)).distinct().all()
        return [r[0] for r in rows]

    # ---------------- events ----------------
    def list_events(self, *, camera_id=None, zone_id=None, event_type=None,
                    severity=None, acknowledged=None, since=None, until=None,
                    limit=50, offset=0):
        q = self.db.query(ZoneEvent)
        if camera_id:
            q = q.filter(ZoneEvent.camera_id == camera_id)
        if zone_id:
            q = q.filter(ZoneEvent.zone_id == zone_id)
        if event_type:
            q = q.filter(ZoneEvent.event_type == event_type)
        if severity:
            q = q.filter(ZoneEvent.severity == severity)
        if acknowledged is not None:
            q = q.filter(ZoneEvent.acknowledged.is_(bool(acknowledged)))
        if since:
            q = q.filter(ZoneEvent.timestamp >= since)
        if until:
            q = q.filter(ZoneEvent.timestamp <= until)
        total = q.count()
        rows = (q.order_by(ZoneEvent.timestamp.desc())
                 .offset(max(0, offset)).limit(max(1, min(limit, 500))).all())
        return rows, total

    def get_event(self, event_id: str) -> Optional[ZoneEvent]:
        return self.db.query(ZoneEvent).filter(
            ZoneEvent.event_id == event_id).first()

    def acknowledge(self, event_id: str, user: str,
                    note: Optional[str] = None) -> Optional[ZoneEvent]:
        row = self.get_event(event_id)
        if row is None:
            return None
        # Idempotent: re-acknowledging keeps the original responder and time,
        # so a second click cannot rewrite who actually handled the breach.
        if not row.acknowledged:
            row.acknowledged = True
            row.acknowledged_by = user
            row.acknowledged_at = datetime.utcnow()
            row.ack_note = note
            self.db.commit()
            self.db.refresh(row)
        return row

    def summary(self, since: Optional[datetime] = None) -> dict:
        since = since or (datetime.utcnow() - timedelta(days=7))
        base = self.db.query(ZoneEvent).filter(ZoneEvent.timestamp >= since)

        by_type = dict(
            self.db.query(ZoneEvent.event_type, sqlfunc.count(ZoneEvent.event_id))
            .filter(ZoneEvent.timestamp >= since)
            .group_by(ZoneEvent.event_type).all())
        by_zone = [
            {"zone_id": z, "zone_name": n, "count": c}
            for z, n, c in
            self.db.query(ZoneEvent.zone_id, ZoneEvent.zone_name,
                          sqlfunc.count(ZoneEvent.event_id))
            .filter(ZoneEvent.timestamp >= since)
            .group_by(ZoneEvent.zone_id, ZoneEvent.zone_name)
            .order_by(sqlfunc.count(ZoneEvent.event_id).desc()).limit(20).all()]
        by_camera = [
            {"camera_id": c, "camera_name": n, "count": k}
            for c, n, k in
            self.db.query(ZoneEvent.camera_id, ZoneEvent.camera_name,
                          sqlfunc.count(ZoneEvent.event_id))
            .filter(ZoneEvent.timestamp >= since)
            .group_by(ZoneEvent.camera_id, ZoneEvent.camera_name)
            .order_by(sqlfunc.count(ZoneEvent.event_id).desc()).limit(20).all()]

        return {
            "since": since.isoformat(),
            "total": base.count(),
            "unacknowledged": base.filter(ZoneEvent.acknowledged.is_(False)).count(),
            "by_type": by_type,
            "by_zone": by_zone,
            "by_camera": by_camera,
        }


# --------------------------------------------------------------------------
# The snapshot the plugins read
# --------------------------------------------------------------------------

def zone_to_snapshot(row: RestrictedZone) -> Optional[dict]:
    """
    Turns a stored zone into the plain dict the state machine consumes.

    Returns None for a zone whose geometry no longer validates, so a row
    corrupted by a bad write can only disable itself rather than raise on the
    analytics thread of every frame.
    """
    points = sanitize_polygon(row.points)
    if points is None:
        return None
    return {
        "zone_id": row.zone_id,
        "name": row.name,
        "camera_id": row.camera_id,
        "points": points,
        "is_active": bool(row.is_active),
        "classes": sanitize_classes(row.object_classes),
        "min_confidence": float(row.min_confidence if row.min_confidence is not None else 0.4),
        "anchor": (row.anchor or DEFAULT_ANCHOR).upper(),
        "min_box_px": int(row.min_box_px or 0),
        "schedule": row.schedule or None,
        "min_dwell_sec": float(row.min_dwell_sec if row.min_dwell_sec is not None else 2.0),
        "loiter_sec": float(row.loiter_sec) if row.loiter_sec else None,
        "exit_grace_sec": float(row.exit_grace_sec if row.exit_grace_sec is not None else 3.0),
        "alert_cooldown_sec": float(
            row.alert_cooldown_sec if row.alert_cooldown_sec is not None else 30.0),
        "severity": row.severity or "warning",
    }


def _legacy_zone(camera_id: str) -> List[dict]:
    """
    A zone from the old RESTRICTED_ZONES config, for a camera that has one.

    Only explicit per-camera entries are honoured. The "default" catch-all is
    deliberately ignored: it put a live restricted zone across the middle of
    every camera on the site, which is how 62 cameras came to be monitoring an
    area nobody had chosen. A zone the client did not define is not a zone.
    """
    try:
        from config.config import config
        raw = (config.RESTRICTED_ZONES or {}).get(camera_id)
    except Exception:
        return []
    points = sanitize_polygon(raw) if raw else None
    if points is None:
        return []
    return [{
        "zone_id": f"legacy:{camera_id}",
        "name": "Restricted Zone",
        "camera_id": camera_id,
        "points": points,
        "is_active": True,
        "classes": [0],
        "min_confidence": 0.4,
        "anchor": DEFAULT_ANCHOR,
        "min_box_px": 0,
        "schedule": None,
        "min_dwell_sec": 2.0,
        "loiter_sec": 60.0,
        "exit_grace_sec": 3.0,
        "alert_cooldown_sec": 30.0,
        "severity": "warning",
    }]


class ZoneRegistry:
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
            return          # another thread is already reloading
        try:
            if not force and (time.monotonic() - self._loaded_at) < self.ttl_sec:
                return
            from database.session import SessionLocal

            db = SessionLocal()
            try:
                by_camera: Dict[str, List[dict]] = {}
                for row in ZoneRepository(db).list_zones(active_only=True):
                    snap = zone_to_snapshot(row)
                    if snap is None:
                        logger.warning(
                            f"Zone {row.zone_id} ({row.name}) has unusable "
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
            # disarm every restricted zone on the site.
            self._loaded_at = time.monotonic() - self.ttl_sec + REGISTRY_RETRY_SEC
            if (time.monotonic() - self._last_error_log) > 60.0:
                self._last_error_log = time.monotonic()
                logger.error(f"Zone registry refresh failed: {exc}")
        finally:
            self._lock.release()

    def for_camera(self, camera_id: str) -> List[dict]:
        self.refresh()
        zones = self.by_camera.get(camera_id)
        if zones:
            return zones
        if not self.loaded:
            # Never reached the database: fall back rather than pretend the
            # site has no zones.
            return _legacy_zone(camera_id)
        return _legacy_zone(camera_id)

    def all_classes(self) -> List[int]:
        """Every class any zone watches, for the engine's detector filter."""
        self.refresh()
        wanted = set()
        for zones in self.by_camera.values():
            for z in zones:
                wanted.update(z.get("classes") or [])
        return sorted(wanted) or [0]


zone_registry = ZoneRegistry()


# --------------------------------------------------------------------------
# The event log writer
# --------------------------------------------------------------------------

class ZoneEventLog:
    """Queues zone events and writes them from one background thread."""

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
            self._thread = threading.Thread(target=self._run, name="zone-event-log",
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
                logger.warning(f"Zone event queue full; dropped {self.dropped}")
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
                logger.error(f"Zone event write failed ({len(batch)} rows): {exc}")
            finally:
                for _ in batch:
                    self._queue.task_done()

    def _flush(self, batch: Sequence[dict]) -> None:
        from database.session import SessionLocal

        db = SessionLocal()
        try:
            for payload in batch:
                db.add(ZoneEvent(event_id=new_event_id(), **payload))
            db.commit()
            self.written += len(batch)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def health(self) -> dict:
        return {"queued": self._queue.qsize(), "written": self.written,
                "dropped": self.dropped}


zone_event_log = ZoneEventLog()
