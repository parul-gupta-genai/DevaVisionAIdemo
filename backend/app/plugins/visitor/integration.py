"""
Visitor Management System / Visitor App integration.

Follows the house pattern set by core/alert_engine.py — configuration by
environment or database row, silent when nothing is configured, one try/except
per destination so a broken receiver never takes anything else down — with one
deliberate difference.

The alert engine posts inline. That is acceptable for an SMS on a fire alarm;
it is not acceptable here, because this is called while a visitor is standing
at the door and the caller is a database worker that other analytics are
queued behind. A VMS that takes ten seconds to answer would stall them all. So
deliveries are queued and retried on a background thread, and every attempt is
recorded, because "the VMS never told me the visitor arrived" needs an answer
better than a shrug.
"""

import hashlib
import hmac
import json
import os
import queue
import secrets
import threading
import time
import uuid
from datetime import datetime
from typing import List, Optional

import requests
from loguru import logger

# Event types a VMS can subscribe to.
WEBHOOK_EVENTS = (
    "VISITOR_ARRIVED",           # an expected visitor was recognised at a gate
    "RETURNING_VISITOR",         # a known visitor came back
    "VISITOR_RECOGNIZED",        # a known visitor, first visit of the series
    "REPEAT_UNKNOWN_PERSON",     # an unenrolled person seen before, again
    "UNKNOWN_PERSON",            # somebody nobody has seen before
    "VISIT_COMPLETED",
)

DELIVERY_TIMEOUT_SEC = float(os.getenv("VMS_WEBHOOK_TIMEOUT_SEC", "5"))
MAX_ATTEMPTS = int(os.getenv("VMS_WEBHOOK_MAX_ATTEMPTS", "4"))


def new_api_key() -> tuple:
    """A key for a VMS to authenticate with, and what we store instead of it."""
    raw = "vms_" + secrets.token_urlsafe(32)
    return raw, hash_api_key(raw), raw[:11]


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sign(secret: str, body: bytes, timestamp: str) -> str:
    """
    Signature over timestamp and body.

    The timestamp is inside the signed material so a captured delivery cannot
    be replayed later; the receiver rejects anything too old.
    """
    mac = hmac.new(secret.encode("utf-8"),
                   f"{timestamp}.".encode("utf-8") + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


class VMSConnector:
    """Delivers visitor events to every subscribed VMS, with retries."""

    def __init__(self):
        self._queue: "queue.Queue[dict]" = queue.Queue(maxsize=1000)
        self._worker: Optional[threading.Thread] = None
        self._started = False
        self._lock = threading.Lock()
        self.dropped = 0
        # A single-endpoint deployment can be configured without touching the
        # database at all, exactly like the alert engine's Twilio settings.
        self.env_webhook = os.getenv("VMS_WEBHOOK_URL", "").strip()
        self.env_secret = os.getenv("VMS_WEBHOOK_SECRET", "").strip()

    # ------------------------------------------------------------------ #
    def _ensure_worker(self):
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            self._worker = threading.Thread(target=self._run, name="vms-webhook",
                                            daemon=True)
            self._worker.start()
            self._started = True

    def notify(self, event_type: str, payload: dict) -> bool:
        """
        Queues an event for delivery. Never blocks, never raises.

        Returns False when nothing is configured, so the caller can skip the
        bookkeeping entirely on a site with no VMS.
        """
        if not self.configured():
            return False
        self._ensure_worker()
        try:
            self._queue.put_nowait({
                "event_type": event_type,
                "payload": payload,
                "queued_at": time.time(),
            })
            return True
        except queue.Full:
            self.dropped += 1
            if self.dropped in (1, 10) or self.dropped % 100 == 0:
                logger.warning(f"VMS webhook queue full; dropped {self.dropped}")
            return False

    def configured(self) -> bool:
        if self.env_webhook:
            return True
        try:
            from database.session import SessionLocal
            from app.plugins.visitor.models import VisitorIntegration

            db = SessionLocal()
            try:
                return db.query(VisitorIntegration).filter(
                    VisitorIntegration.is_active.is_(True),
                    VisitorIntegration.webhook_url.isnot(None)).count() > 0
            finally:
                db.close()
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    def _targets(self, event_type: str) -> List[dict]:
        out = []
        if self.env_webhook:
            out.append({"integration_id": None, "url": self.env_webhook,
                        "secret": self.env_secret, "name": "env"})
        try:
            from database.session import SessionLocal
            from app.plugins.visitor.models import VisitorIntegration

            db = SessionLocal()
            try:
                rows = db.query(VisitorIntegration).filter(
                    VisitorIntegration.is_active.is_(True),
                    VisitorIntegration.webhook_url.isnot(None)).all()
                for r in rows:
                    subs = r.subscribed_events or []
                    if subs and event_type not in subs:
                        continue
                    out.append({"integration_id": r.integration_id,
                                "url": r.webhook_url,
                                "secret": r.webhook_secret or "",
                                "name": r.name})
            finally:
                db.close()
        except Exception as exc:
            logger.error(f"Could not load VMS integrations: {exc}")
        return out

    def _run(self):
        while True:
            job = self._queue.get()
            try:
                for target in self._targets(job["event_type"]):
                    self._deliver(target, job["event_type"], job["payload"])
            except Exception as exc:
                logger.error(f"VMS delivery loop error: {exc}")
            finally:
                self._queue.task_done()

    def _deliver(self, target: dict, event_type: str, payload: dict):
        body = json.dumps({
            "event": event_type,
            "sent_at": datetime.utcnow().isoformat() + "Z",
            "data": payload,
        }, default=str).encode("utf-8")

        timestamp = str(int(time.time()))
        headers = {"Content-Type": "application/json",
                   "X-DevaVisionAI-Event": event_type,
                   "X-DevaVisionAI-Timestamp": timestamp}
        if target.get("secret"):
            headers["X-DevaVisionAI-Signature"] = sign(target["secret"], body, timestamp)

        delivery_id = f"WHD-{uuid.uuid4().hex[:10].upper()}"
        code, error, attempts = None, None, 0

        for attempt in range(1, MAX_ATTEMPTS + 1):
            attempts = attempt
            try:
                resp = requests.post(target["url"], data=body, headers=headers,
                                     timeout=DELIVERY_TIMEOUT_SEC)
                code = resp.status_code
                if 200 <= code < 300:
                    error = None
                    break
                error = f"HTTP {code}"
                # A 4xx other than 429 is the receiver saying the request is
                # wrong; retrying an unchanged payload cannot fix that.
                if 400 <= code < 500 and code != 429:
                    break
            except Exception as exc:
                code, error = None, str(exc)[:200]
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(2 ** attempt, 15))

        ok = code is not None and 200 <= code < 300
        if not ok:
            logger.warning(
                f"VMS webhook to {target['name']} failed after {attempts} "
                f"attempt(s): {error}")
        self._record(delivery_id, target, event_type, payload, ok, attempts, code, error)

    def _record(self, delivery_id, target, event_type, payload, ok, attempts,
                code, error):
        if not target.get("integration_id"):
            return          # env-configured endpoint has no row to attach to
        try:
            from database.session import SessionLocal
            from app.plugins.visitor.models import (
                VisitorIntegration, VisitorWebhookDelivery,
            )

            db = SessionLocal()
            try:
                db.add(VisitorWebhookDelivery(
                    delivery_id=delivery_id,
                    integration_id=target["integration_id"],
                    event_type=event_type,
                    visitor_id=(payload or {}).get("visitor_id"),
                    payload=payload,
                    status="DELIVERED" if ok else "FAILED",
                    attempts=attempts, response_code=code, error=error,
                    delivered_at=datetime.utcnow() if ok else None,
                ))
                row = db.query(VisitorIntegration).filter(
                    VisitorIntegration.integration_id == target["integration_id"]).first()
                if row is not None:
                    row.last_delivery_at = datetime.utcnow()
                    row.last_delivery_status = "DELIVERED" if ok else "FAILED"
                    row.failure_count = 0 if ok else (row.failure_count or 0) + 1
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.error(f"Could not record VMS delivery: {exc}")


vms_connector = VMSConnector()


def authenticate(db, api_key: Optional[str]):
    """
    Resolves an inbound API key to its integration.

    Compares hashes, never the key itself, and uses a constant-time compare so
    the lookup cannot be turned into an oracle for guessing a key.
    """
    from app.plugins.visitor.models import VisitorIntegration

    if not api_key:
        return None
    digest = hash_api_key(api_key.strip())
    rows = db.query(VisitorIntegration).filter(
        VisitorIntegration.is_active.is_(True),
        VisitorIntegration.api_key_hash.isnot(None)).all()
    for row in rows:
        if hmac.compare_digest(row.api_key_hash or "", digest):
            return row
    return None
