"""
Catalogue access, plus the cached snapshot the plugin matches against.

The plugin needs the whole catalogue on every sampled frame, on the analytics
thread. Querying it there would put a database round trip in the hot path of
every camera, so it is loaded once into a plain-dict snapshot and refreshed on
a short TTL, invalidated immediately on any edit.
"""

import threading
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from loguru import logger
from sqlalchemy.orm import Session, selectinload

from app.plugins.ppe.models import (
    PPECameraConfig, PPEColour, PPEKitItem, PPEVendor, PPEViolation,
)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


class PPERepository:
    def __init__(self, db: Session):
        self.db = db

    # ---------------- colours ----------------
    def list_colours(self) -> List[PPEColour]:
        return self.db.query(PPEColour).order_by(PPEColour.name).all()

    def get_colour(self, colour_id: str) -> Optional[PPEColour]:
        return self.db.query(PPEColour).filter(PPEColour.colour_id == colour_id).first()

    def get_colour_by_name(self, name: str) -> Optional[PPEColour]:
        return self.db.query(PPEColour).filter(PPEColour.name == name).first()

    def create_colour(self, **fields) -> PPEColour:
        row = PPEColour(colour_id=_id("COL"), **fields)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_colour(self, colour_id: str) -> bool:
        row = self.get_colour(colour_id)
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def colour_in_use(self, colour_id: str) -> int:
        return self.db.query(PPEKitItem).filter(PPEKitItem.colour_id == colour_id).count()

    # ---------------- vendors ----------------
    def list_vendors(self, active_only: bool = True) -> List[PPEVendor]:
        q = self.db.query(PPEVendor).options(selectinload(PPEVendor.kit_items))
        if active_only:
            q = q.filter(PPEVendor.is_active.is_(True))
        return q.order_by(PPEVendor.name).all()

    def get_vendor(self, vendor_id: str) -> Optional[PPEVendor]:
        return (
            self.db.query(PPEVendor)
            .options(selectinload(PPEVendor.kit_items))
            .filter(PPEVendor.vendor_id == vendor_id)
            .first()
        )

    def create_vendor(self, **fields) -> PPEVendor:
        row = PPEVendor(vendor_id=_id("VEN"), **fields)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_vendor(self, vendor_id: str) -> bool:
        row = self.db.query(PPEVendor).filter(PPEVendor.vendor_id == vendor_id).first()
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    # ---------------- kit items ----------------
    def add_kit_item(self, vendor_id: str, **fields) -> PPEKitItem:
        row = PPEKitItem(item_id=_id("KIT"), vendor_id=vendor_id, **fields)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_kit_item(self, item_id: str) -> bool:
        row = self.db.query(PPEKitItem).filter(PPEKitItem.item_id == item_id).first()
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    # ---------------- camera config ----------------
    def get_camera_config(self, camera_id: str) -> Optional[PPECameraConfig]:
        return (
            self.db.query(PPECameraConfig)
            .filter(PPECameraConfig.camera_id == camera_id)
            .first()
        )

    def list_camera_configs(self) -> List[PPECameraConfig]:
        return self.db.query(PPECameraConfig).order_by(PPECameraConfig.camera_id).all()

    def upsert_camera_config(self, camera_id: str, **fields) -> PPECameraConfig:
        row = self.get_camera_config(camera_id)
        if row is None:
            row = PPECameraConfig(config_id=_id("PCF"), camera_id=camera_id)
            self.db.add(row)
        for k, v in fields.items():
            if v is not None:
                setattr(row, k, v)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_camera_config(self, camera_id: str) -> bool:
        row = self.get_camera_config(camera_id)
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    # ---------------- violations ----------------
    def log_violation(self, **fields) -> PPEViolation:
        fields.setdefault("timestamp", datetime.utcnow())
        row = PPEViolation(violation_id=_id("PPV"), **fields)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_violations(self, camera_id: Optional[str] = None,
                        violation_type: Optional[str] = None,
                        vendor_id: Optional[str] = None,
                        start=None, end=None,
                        limit: int = 100, offset: int = 0):
        q = self.db.query(PPEViolation)
        if camera_id:
            q = q.filter(PPEViolation.camera_id == camera_id)
        if violation_type:
            q = q.filter(PPEViolation.violation_type == violation_type)
        if vendor_id:
            q = q.filter(PPEViolation.vendor_id == vendor_id)
        if start:
            q = q.filter(PPEViolation.timestamp >= start)
        if end:
            q = q.filter(PPEViolation.timestamp <= end)
        total = q.count()
        rows = (
            q.order_by(PPEViolation.timestamp.desc())
            .offset(max(0, offset))
            .limit(max(1, min(limit, 500)))
            .all()
        )
        return rows, total


class KitCatalogue:
    """
    Plain-dict snapshot of the catalogue, refreshed on a TTL.

    Holds no ORM objects: the plugin reads this from analytics worker threads
    with no session of their own, and a detached instance would raise the
    moment a lazy attribute was touched.
    """

    def __init__(self, ttl_sec: float = 30.0):
        self.ttl_sec = ttl_sec
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        self.colours: Dict[str, list] = {}
        self.colour_names: Dict[str, str] = {}
        self.vendors: List[dict] = []
        self.camera_config: Dict[str, dict] = {}

    @property
    def configured(self) -> bool:
        """
        True once somebody has actually set up a catalogue.

        The plugin falls back to its previous fixed-colour behaviour while
        this is False, so installing this code changes nothing on the twelve
        cameras already running PPE until a vendor is defined.
        """
        return bool(self.vendors)

    def invalidate(self) -> None:
        self._loaded_at = 0.0

    def refresh(self, force: bool = False) -> None:
        if not force and (time.monotonic() - self._loaded_at) < self.ttl_sec:
            return
        if not self._lock.acquire(blocking=False):
            return
        try:
            if not force and (time.monotonic() - self._loaded_at) < self.ttl_sec:
                return
            from database.session import SessionLocal

            db = SessionLocal()
            try:
                repo = PPERepository(db)
                colours, names = {}, {}
                for c in repo.list_colours():
                    colours[c.colour_id] = c.hsv_ranges or []
                    names[c.colour_id] = c.name

                vendors = []
                for v in repo.list_vendors(active_only=True):
                    items = [{
                        "item_id": i.item_id,
                        "item_type": i.item_type,
                        "body_region": (i.body_region or "TORSO").upper(),
                        "colour_id": i.colour_id,
                        "is_required": bool(i.is_required),
                        "min_coverage": float(i.min_coverage or 0.0),
                    } for i in v.kit_items]
                    if not items:
                        # A vendor with no kit cannot be identified, and would
                        # otherwise "match" everyone with a vacuously complete
                        # kit of zero required items.
                        continue
                    vendors.append({
                        "vendor_id": v.vendor_id,
                        "name": v.name,
                        "code": v.code,
                        "display_hex": v.display_hex,
                        "kit_items": items,
                    })

                cams = {}
                for cfg in repo.list_camera_configs():
                    cams[cfg.camera_id] = {
                        "expected_vendor_ids": cfg.expected_vendor_ids or [],
                        "enforce": bool(cfg.enforce),
                        "alert_on": cfg.alert_on or ["NO_PPE", "WRONG_KIT"],
                        "severity": cfg.severity or "warning",
                        "alert_cooldown_sec": float(cfg.alert_cooldown_sec or 30.0),
                        "min_person_px": int(cfg.min_person_px or 80),
                    }

                self.colours, self.colour_names = colours, names
                self.vendors, self.camera_config = vendors, cams
                self._loaded_at = time.monotonic()
            finally:
                db.close()
        except Exception as exc:
            # Keep the previous snapshot: an unreachable database must not
            # silently switch every camera back to the fallback behaviour.
            logger.error(f"PPE catalogue refresh failed: {exc}")
        finally:
            self._lock.release()

    def vendors_for(self, camera_id: str) -> List[dict]:
        """Vendors expected on a camera; all of them when unrestricted."""
        cfg = self.camera_config.get(camera_id) or {}
        wanted = cfg.get("expected_vendor_ids") or []
        if not wanted:
            return self.vendors
        return [v for v in self.vendors if v["vendor_id"] in wanted]


kit_catalogue = KitCatalogue()
