"""
Returning-visitor recognition.

Two things had to be fixed before "is this a repeat visitor" could be answered
at all:

1.  Every face match created a Visit and incremented total_visits. One person
    walking past three cameras therefore registered three visits, and someone
    lingering in view of one camera registered a new visit every time their
    track was re-acquired. A visit count built that way cannot support a
    returning-visitor claim, because it counts sightings, not visits.

2.  A recognised visitor produced the same event whether it was their first
    appearance or their twentieth. The information needed — how many times
    before, how long since — was in the database and never surfaced.

A visit here is a session: sightings within `session_gap` of the last one
continue the current visit; a longer gap starts a new one.
"""

import os
from datetime import datetime, timedelta
from typing import Optional, Tuple

from loguru import logger
from sqlalchemy import func

from app.plugins.visitor.models import Visit, Visitor


def session_gap_sec() -> float:
    """
    How long a person must be unseen before their next sighting counts as a
    new visit. Half an hour by default: long enough that stepping out for a
    cigarette is the same visit, short enough that morning and afternoon
    appointments are two.
    """
    try:
        return max(60.0, float(os.getenv("VISITOR_SESSION_GAP_SEC", "1800")))
    except (TypeError, ValueError):
        return 1800.0


def returning_after_days() -> float:
    """
    Minimum gap for a visit to be called a *return* rather than a continuation
    of the same day's business. A second visit four hours later is still the
    same person on the same errand.
    """
    try:
        return max(0.0, float(os.getenv("VISITOR_RETURN_AFTER_HOURS", "12")) / 24.0)
    except (TypeError, ValueError):
        return 0.5


class ReturningVisitorTracker:
    """Resolves a sighting into a visit, and says what kind of visit it is."""

    def __init__(self, db):
        self.db = db

    def last_visit(self, visitor_id: str) -> Optional[Visit]:
        return (
            self.db.query(Visit)
            .filter(Visit.visitor_id == visitor_id)
            .order_by(Visit.entry_time.desc())
            .first()
        )

    def visit_count(self, visitor_id: str) -> int:
        return self.db.query(func.count(Visit.visit_id)).filter(
            Visit.visitor_id == visitor_id).scalar() or 0

    def resolve(self, visitor_id: str, camera_id: str, track_id: str,
                seen_at: Optional[datetime] = None,
                confidence: float = 0.0,
                snapshot_path: Optional[str] = None) -> Tuple[Optional[Visit], dict]:
        """
        Folds a sighting into this visitor's history.

        Returns (visit, context). `visit` is None when the sighting merely
        continued the visit already in progress — the caller should not raise
        an arrival event for it. `context` always describes the person's
        history, so the caller can label the event.
        """
        now = seen_at or datetime.utcnow()
        previous = self.last_visit(visitor_id)
        gap = session_gap_sec()

        if previous is not None and previous.entry_time is not None:
            # Compare against the last time they were SEEN, not the time the
            # visit began: someone in view for two hours would otherwise start
            # a second visit while still standing there.
            last_seen = previous.exit_time or previous.entry_time
            since = (now - last_seen).total_seconds()
            if since < gap:
                # Same visit; extend it and say nothing new happened.
                previous.exit_time = now
                if previous.entry_time:
                    previous.duration = (now - previous.entry_time).total_seconds()
                self.db.commit()
                return None, self._context(visitor_id, previous, continuing=True)

        seq = self.visit_count(visitor_id) + 1
        days_since = None
        if previous is not None and previous.entry_time is not None:
            days_since = round(
                (now - (previous.exit_time or previous.entry_time)).total_seconds()
                / 86400.0, 4)

        is_return = seq > 1 and (days_since is None or days_since >= returning_after_days())

        from app.plugins.visitor.repository import generate_visit_id

        visit = Visit(
            visit_id=generate_visit_id(),
            visitor_id=visitor_id,
            entry_time=now,
            camera_id=camera_id,
            track_id=str(track_id),
            confidence=confidence,
            snapshot_path=snapshot_path,
            visit_number=seq,
            days_since_previous=days_since,
            is_return=bool(is_return),
        )
        self.db.add(visit)

        visitor = self.db.query(Visitor).filter(Visitor.visitor_id == visitor_id).first()
        if visitor is not None:
            if not visitor.first_seen:
                visitor.first_seen = now
            visitor.last_seen = now
            # Counts visits, not sightings — see the module docstring.
            visitor.total_visits = seq
        self.db.commit()
        self.db.refresh(visit)
        return visit, self._context(visitor_id, visit, continuing=False)

    def _context(self, visitor_id: str, visit: Visit, continuing: bool) -> dict:
        visitor = self.db.query(Visitor).filter(Visitor.visitor_id == visitor_id).first()
        return {
            "visitor_id": visitor_id,
            "visit_id": visit.visit_id if visit else None,
            "visit_number": visit.visit_number if visit else None,
            "days_since_previous": visit.days_since_previous if visit else None,
            "is_return": bool(visit.is_return) if visit and visit.is_return is not None else False,
            "continuing_visit": continuing,
            "total_visits": (visitor.total_visits if visitor else None),
            "first_seen": visitor.first_seen.isoformat() if visitor and visitor.first_seen else None,
            "last_seen": visitor.last_seen.isoformat() if visitor and visitor.last_seen else None,
            "status": visitor.status if visitor else None,
            "name": visitor.name if visitor else None,
            "role": visitor.role if visitor else None,
        }


def classify(context: dict, matched_status: str) -> str:
    """
    The event type for a sighting, given the visitor's history.

    A repeat appearance of somebody nobody ever enrolled is its own outcome:
    the fourth time an unregistered person walks in is worth knowing about,
    and calling it UNKNOWN_PERSON for the fourth time — as this did — throws
    that away.
    """
    from app.plugins.visitor.events import VisitorEventType

    registered = matched_status == "REGISTERED"
    returning = bool(context.get("is_return"))

    if registered:
        if context.get("role") == "EMPLOYEE":
            return VisitorEventType.EMPLOYEE_RECOGNIZED.value
        return (VisitorEventType.RETURNING_VISITOR.value if returning
                else VisitorEventType.VISITOR_RECOGNIZED.value)
    if returning or (context.get("visit_number") or 0) > 1:
        return VisitorEventType.REPEAT_UNKNOWN_PERSON.value
    return VisitorEventType.UNKNOWN_PERSON.value


def match_pre_registration(db, visitor_id: str, name: Optional[str] = None,
                           now: Optional[datetime] = None):
    """
    Links an arrival to the appointment the VMS told us to expect.

    Matches on the visitor id first; falls back to an exact name match among
    entries whose window is open, which is what happens when the VMS sent an
    appointment without a photo and the face was enrolled separately.
    """
    from app.plugins.visitor.models import VisitorPreRegistration

    now = now or datetime.utcnow()
    q = (
        db.query(VisitorPreRegistration)
        .filter(VisitorPreRegistration.status == "EXPECTED")
        .filter((VisitorPreRegistration.expected_until.is_(None))
                | (VisitorPreRegistration.expected_until >= now))
    )
    row = q.filter(VisitorPreRegistration.visitor_id == visitor_id).first()
    if row is None and name:
        row = q.filter(func.lower(VisitorPreRegistration.name) == name.strip().lower()).first()
    return row


def mark_arrived(db, prereg, visitor_id: str, camera_id: str,
                 now: Optional[datetime] = None) -> bool:
    """Marks an expected visit as arrived. Idempotent."""
    if prereg is None or prereg.status != "EXPECTED":
        return False
    try:
        prereg.status = "ARRIVED"
        prereg.arrived_at = now or datetime.utcnow()
        prereg.arrival_camera = camera_id
        if not prereg.visitor_id:
            prereg.visitor_id = visitor_id
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        logger.error(f"Could not mark pre-registration arrived: {exc}")
        return False
