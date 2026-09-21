"""
Data access for the face register, watchlist, event history and attendance.

Matching runs as a pgvector nearest-neighbour query rather than by pulling
every embedding into Python: the register is expected to reach thousands of
people, and the hot path runs per sampled frame per camera.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional, Sequence, Tuple

import numpy as np
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.plugins.face.models import (
    AttendanceRecord, FaceEnrolment, FaceEvent, FacePerson, FaceWatchlistEntry,
)


def new_person_id() -> str:
    return f"FP-{uuid.uuid4().hex[:10].upper()}"


def new_enrolment_id() -> str:
    return f"FE-{uuid.uuid4().hex[:10].upper()}"


def new_entry_id() -> str:
    return f"WL-{uuid.uuid4().hex[:10].upper()}"


def new_event_id() -> str:
    return f"FEV-{uuid.uuid4().hex[:10].upper()}"


def new_record_id() -> str:
    return f"AR-{uuid.uuid4().hex[:10].upper()}"


def to_list(vec) -> List[float]:
    """Normalises an embedding to a plain float list for pgvector."""
    if vec is None:
        return []
    arr = np.asarray(vec, dtype=np.float32).ravel()
    return [float(x) for x in arr]


def unit(vec) -> List[float]:
    """
    L2-normalises an embedding.

    Cosine distance does not care about magnitude, but the stored centroid is
    a mean of several vectors, and averaging un-normalised embeddings lets the
    one with the largest magnitude dominate the result.
    """
    arr = np.asarray(vec, dtype=np.float32).ravel()
    norm = float(np.linalg.norm(arr))
    if norm <= 0:
        return [float(x) for x in arr]
    return [float(x) for x in (arr / norm)]


class FaceRepository:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    # Register
    # ------------------------------------------------------------------ #
    def get_person(self, person_id: str) -> Optional[FacePerson]:
        return (
            self.db.query(FacePerson)
            .filter(FacePerson.person_id == person_id)
            .first()
        )

    def get_person_by_code(self, code: str) -> Optional[FacePerson]:
        if not code:
            return None
        return (
            self.db.query(FacePerson)
            .filter(FacePerson.person_code == code)
            .first()
        )

    def list_persons(
        self,
        person_type: Optional[str] = None,
        department: Optional[str] = None,
        company: Optional[str] = None,
        search: Optional[str] = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[FacePerson], int]:
        q = self.db.query(FacePerson)
        if active_only:
            q = q.filter(FacePerson.is_active.is_(True))
        if person_type:
            q = q.filter(FacePerson.person_type == person_type)
        if department:
            q = q.filter(FacePerson.department == department)
        if company:
            q = q.filter(FacePerson.company == company)
        if search:
            like = f"%{search}%"
            q = q.filter(or_(FacePerson.name.ilike(like),
                             FacePerson.person_code.ilike(like)))
        total = q.count()
        rows = (
            q.order_by(FacePerson.name)
            .offset(max(0, offset))
            .limit(max(1, min(limit, 500)))
            .all()
        )
        return rows, total

    def create_person(self, **fields) -> FacePerson:
        person = FacePerson(person_id=new_person_id(), **fields)
        self.db.add(person)
        self.db.commit()
        self.db.refresh(person)
        return person

    def add_enrolment(self, person_id: str, embedding, **quality) -> FaceEnrolment:
        row = FaceEnrolment(
            enrolment_id=new_enrolment_id(),
            person_id=person_id,
            face_embedding=unit(embedding),
            **quality,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def recompute_centroid(self, person_id: str) -> Optional[FacePerson]:
        """
        Rebuilds a person's matching vector from their accepted enrolments.

        Called after every enrolment add or removal so the vector the matcher
        uses is always the mean of exactly the images currently on file.
        """
        person = self.get_person(person_id)
        if person is None:
            return None

        rows = (
            self.db.query(FaceEnrolment.face_embedding)
            .filter(FaceEnrolment.person_id == person_id)
            .all()
        )
        vectors = [np.asarray(r[0], dtype=np.float32) for r in rows if r[0] is not None]
        if vectors:
            centroid = np.mean(np.stack(vectors), axis=0)
            person.face_embedding = unit(centroid)
            person.enrolment_count = len(vectors)
        else:
            person.face_embedding = None
            person.enrolment_count = 0
        self.db.commit()
        self.db.refresh(person)
        return person

    def delete_enrolment(self, enrolment_id: str) -> Optional[str]:
        row = (
            self.db.query(FaceEnrolment)
            .filter(FaceEnrolment.enrolment_id == enrolment_id)
            .first()
        )
        if row is None:
            return None
        person_id = row.person_id
        self.db.delete(row)
        self.db.commit()
        self.recompute_centroid(person_id)
        return person_id

    def list_enrolments(self, person_id: str) -> List[FaceEnrolment]:
        return (
            self.db.query(FaceEnrolment)
            .filter(FaceEnrolment.person_id == person_id)
            .order_by(FaceEnrolment.created_at.desc())
            .all()
        )

    # ------------------------------------------------------------------ #
    # Matching
    # ------------------------------------------------------------------ #
    def match(self, embedding, threshold: float) -> Tuple[Optional[FacePerson], float]:
        """
        Nearest active enrolled person, or (None, similarity) when nothing
        clears the threshold. The similarity is still returned on a miss so
        callers can log how close the best candidate was — the single most
        useful number when tuning the threshold during UAT.
        """
        vec = unit(embedding)
        if not vec:
            return None, -1.0

        distance = FacePerson.face_embedding.cosine_distance(vec)
        row = (
            self.db.query(FacePerson, distance.label("distance"))
            .filter(FacePerson.face_embedding.isnot(None))
            .filter(FacePerson.is_active.is_(True))
            .order_by(distance)
            .first()
        )
        if row is None:
            return None, -1.0

        person, dist = row
        similarity = 1.0 - float(dist)
        if similarity >= threshold:
            return person, similarity
        return None, similarity

    def nearest_enrolment(self, embedding, exclude_person_id: Optional[str] = None):
        """
        Closest individual enrolment image, used to catch duplicate enrolments.

        Compares against individual images rather than centroids: a person
        enrolled from three angles has a centroid that may sit further from
        any single new photo than the matching angle does, which would let a
        duplicate through.
        """
        vec = unit(embedding)
        if not vec:
            return None, -1.0

        distance = FaceEnrolment.face_embedding.cosine_distance(vec)
        q = (
            self.db.query(FaceEnrolment, distance.label("distance"))
            .join(FacePerson, FacePerson.person_id == FaceEnrolment.person_id)
            .filter(FacePerson.is_active.is_(True))
        )
        if exclude_person_id:
            q = q.filter(FaceEnrolment.person_id != exclude_person_id)
        row = q.order_by(distance).first()
        if row is None:
            return None, -1.0
        enrolment, dist = row
        return enrolment, 1.0 - float(dist)

    # ------------------------------------------------------------------ #
    # Watchlist
    # ------------------------------------------------------------------ #
    def active_watchlist_for(self, person_id: str, now: Optional[datetime] = None):
        now = now or datetime.utcnow()
        return (
            self.db.query(FaceWatchlistEntry)
            .filter(FaceWatchlistEntry.person_id == person_id)
            .filter(FaceWatchlistEntry.is_active.is_(True))
            .filter(or_(FaceWatchlistEntry.active_from.is_(None),
                        FaceWatchlistEntry.active_from <= now))
            .filter(or_(FaceWatchlistEntry.active_until.is_(None),
                        FaceWatchlistEntry.active_until >= now))
            .order_by(FaceWatchlistEntry.created_at.desc())
            .first()
        )

    def list_watchlist(self, category: Optional[str] = None,
                       active_only: bool = True) -> List[FaceWatchlistEntry]:
        q = self.db.query(FaceWatchlistEntry)
        if active_only:
            q = q.filter(FaceWatchlistEntry.is_active.is_(True))
        if category:
            q = q.filter(FaceWatchlistEntry.category == category)
        return q.order_by(FaceWatchlistEntry.created_at.desc()).all()

    def upsert_watchlist(self, person_id: str, category: str, **fields) -> FaceWatchlistEntry:
        entry = (
            self.db.query(FaceWatchlistEntry)
            .filter(FaceWatchlistEntry.person_id == person_id)
            .filter(FaceWatchlistEntry.category == category)
            .first()
        )
        if entry is None:
            entry = FaceWatchlistEntry(
                entry_id=new_entry_id(), person_id=person_id, category=category,
            )
            self.db.add(entry)
        for k, v in fields.items():
            if v is not None:
                setattr(entry, k, v)
        entry.is_active = fields.get("is_active", True)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def remove_watchlist(self, entry_id: str) -> bool:
        entry = (
            self.db.query(FaceWatchlistEntry)
            .filter(FaceWatchlistEntry.entry_id == entry_id)
            .first()
        )
        if entry is None:
            return False
        self.db.delete(entry)
        self.db.commit()
        return True

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #
    def log_event(self, event_type: str, **fields) -> FaceEvent:
        fields.setdefault("timestamp", datetime.utcnow())
        meta = fields.pop("metadata", None)
        row = FaceEvent(event_id=new_event_id(), event_type=event_type,
                        metadata_=meta, **fields)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_events(
        self,
        event_types: Optional[Sequence[str]] = None,
        person_id: Optional[str] = None,
        camera_id: Optional[str] = None,
        category: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[FaceEvent], int]:
        q = self.db.query(FaceEvent)
        if event_types:
            q = q.filter(FaceEvent.event_type.in_(list(event_types)))
        if person_id:
            q = q.filter(FaceEvent.person_id == person_id)
        if camera_id:
            q = q.filter(FaceEvent.camera_id == camera_id)
        if category:
            q = q.filter(FaceEvent.watchlist_category == category)
        if start:
            q = q.filter(FaceEvent.timestamp >= start)
        if end:
            q = q.filter(FaceEvent.timestamp <= end)
        total = q.count()
        rows = (
            q.order_by(FaceEvent.timestamp.desc())
            .offset(max(0, offset))
            .limit(max(1, min(limit, 500)))
            .all()
        )
        return rows, total

    def last_event_at(self, person_id: str, event_types: Sequence[str],
                      camera_id: Optional[str] = None) -> Optional[datetime]:
        q = (
            self.db.query(func.max(FaceEvent.timestamp))
            .filter(FaceEvent.person_id == person_id)
            .filter(FaceEvent.event_type.in_(list(event_types)))
        )
        if camera_id:
            q = q.filter(FaceEvent.camera_id == camera_id)
        return q.scalar()

    # ------------------------------------------------------------------ #
    # Attendance
    # ------------------------------------------------------------------ #
    def record_sighting(
        self,
        person_id: str,
        seen_at: datetime,
        camera_id: Optional[str],
        direction: Optional[str] = None,
        min_presence_sec: float = 60.0,
    ) -> Tuple[AttendanceRecord, Optional[str]]:
        """
        Folds one sighting into the person's row for that day.

        Returns (record, action) where action is CHECK_IN the first time the
        person is seen that day, CHECK_OUT when an exit is recorded after they
        have been present long enough, and None for a sighting that only
        refreshes the existing record. Keeping this decision in one place is
        what stops the same person being checked in twice by two cameras.
        """
        work_date = seen_at.date()
        record = (
            self.db.query(AttendanceRecord)
            .filter(AttendanceRecord.person_id == person_id)
            .filter(AttendanceRecord.work_date == work_date)
            .first()
        )

        action = None
        if record is None:
            record = AttendanceRecord(
                record_id=new_record_id(),
                person_id=person_id,
                work_date=work_date,
                first_seen=seen_at,
                last_seen=seen_at,
                check_in_time=seen_at,
                check_in_camera=camera_id,
                sightings=1,
                status="PRESENT",
            )
            self.db.add(record)
            action = "CHECK_IN"
        else:
            record.sightings = (record.sightings or 0) + 1
            if record.last_seen is None or seen_at > record.last_seen:
                record.last_seen = seen_at
            if record.check_in_time is None:
                record.check_in_time = seen_at
                record.check_in_camera = camera_id
                action = "CHECK_IN"

        if direction == "OUT" and record.check_in_time is not None:
            present_for = (seen_at - record.check_in_time).total_seconds()
            if present_for >= min_presence_sec:
                record.check_out_time = seen_at
                record.check_out_camera = camera_id
                action = "CHECK_OUT"

        if record.check_in_time and record.check_out_time:
            record.total_hours = round(
                (record.check_out_time - record.check_in_time).total_seconds() / 3600.0, 3
            )
            record.status = "PRESENT"
        elif record.check_in_time:
            record.total_hours = round(
                ((record.last_seen or seen_at) - record.check_in_time).total_seconds() / 3600.0, 3
            )
            record.status = "PARTIAL"

        self.db.commit()
        self.db.refresh(record)
        return record, action

    def attendance_for_day(self, day: date) -> List[AttendanceRecord]:
        return (
            self.db.query(AttendanceRecord)
            .filter(AttendanceRecord.work_date == day)
            .all()
        )

    def attendance_range(
        self,
        start: date,
        end: date,
        person_id: Optional[str] = None,
        person_type: Optional[str] = None,
        department: Optional[str] = None,
    ) -> List[Tuple[AttendanceRecord, FacePerson]]:
        """
        Joined so the report does not fetch a person row per record — the
        classic N+1 that turns a month-long report into thousands of queries.
        """
        q = (
            self.db.query(AttendanceRecord, FacePerson)
            .join(FacePerson, FacePerson.person_id == AttendanceRecord.person_id)
            .filter(AttendanceRecord.work_date >= start)
            .filter(AttendanceRecord.work_date <= end)
        )
        if person_id:
            q = q.filter(AttendanceRecord.person_id == person_id)
        if person_type:
            q = q.filter(FacePerson.person_type == person_type)
        if department:
            q = q.filter(FacePerson.department == department)
        return q.order_by(AttendanceRecord.work_date.desc(), FacePerson.name).all()

    def absentees_for_day(self, day: date, person_type: Optional[str] = None) -> List[FacePerson]:
        """Active enrolled people with no attendance row for that day."""
        present = (
            self.db.query(AttendanceRecord.person_id)
            .filter(AttendanceRecord.work_date == day)
            .subquery()
        )
        q = (
            self.db.query(FacePerson)
            .filter(FacePerson.is_active.is_(True))
            .filter(FacePerson.face_embedding.isnot(None))
            .filter(~FacePerson.person_id.in_(present))
        )
        if person_type:
            q = q.filter(FacePerson.person_type == person_type)
        return q.order_by(FacePerson.name).all()
