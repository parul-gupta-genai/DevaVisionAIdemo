"""
Persistence for face-based attendance and watchlist monitoring.

Kept separate from the visitor plugin's tables on purpose. `visitors` is a
walk-up log — rows are created automatically for faces nobody enrolled, and an
UNKNOWN row is normal there. An employee or vendor register is the opposite:
every row is deliberately enrolled by an operator, carries an employee code and
an employment relationship, and must never gain rows as a side effect of
somebody walking past a camera.
"""

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer,
    JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from database.persistence import Base

# InsightFace buffalo_* recognition models emit 512-d embeddings. Declared once
# so the tables, the matcher and the enrolment validator cannot drift apart.
EMBEDDING_DIM = 512

PERSON_TYPES = ("EMPLOYEE", "VENDOR", "CONTRACTOR")
WATCHLIST_CATEGORIES = ("BLACKLIST", "VIP", "PERSON_OF_INTEREST", "EX_EMPLOYEE")
WATCHLIST_SEVERITIES = ("critical", "warning", "info")


class FacePerson(Base):
    """One enrolled human: an employee, a vendor's worker, or a contractor."""

    __tablename__ = "face_persons"

    person_id = Column(String, primary_key=True, index=True)
    # Employee/vendor code as the client knows it. Unique when present so an
    # enrolment drive cannot quietly register the same badge twice.
    person_code = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=False, index=True)
    person_type = Column(String, nullable=False, default="EMPLOYEE", index=True)

    department = Column(String, nullable=True, index=True)
    designation = Column(String, nullable=True)
    # Which vendor/contractor firm supplied this worker.
    company = Column(String, nullable=True, index=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # The embedding matched against at runtime: the centroid of this person's
    # accepted enrolment images, so several angles collapse into one vector and
    # the hot path stays a single indexed nearest-neighbour lookup.
    face_embedding = Column(Vector(EMBEDDING_DIM).with_variant(JSON(), "sqlite"), nullable=True)
    enrolment_count = Column(Integer, nullable=False, default=0)
    photo = Column(String, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, index=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    enrolments = relationship(
        "FaceEnrolment", back_populates="person",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class FaceEnrolment(Base):
    """
    One accepted enrolment image and the embedding taken from it.

    Individual images are kept rather than only the centroid so a bad capture
    can be removed and the centroid recomputed, which is what makes
    "rectify configuration-related issues found during UAT" a data fix rather
    than a re-enrolment drive.
    """

    __tablename__ = "face_enrolments"

    enrolment_id = Column(String, primary_key=True, index=True)
    person_id = Column(
        String, ForeignKey("face_persons.person_id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    face_embedding = Column(Vector(EMBEDDING_DIM).with_variant(JSON(), "sqlite"), nullable=False)
    snapshot_path = Column(String, nullable=True)

    # Quality evidence for the accept/reject decision, kept for audit.
    det_score = Column(Float, nullable=True)
    face_width = Column(Integer, nullable=True)
    face_height = Column(Integer, nullable=True)
    sharpness = Column(Float, nullable=True)
    source = Column(String, nullable=True)          # upload | snapshot | drive
    enrolled_by = Column(String, nullable=True)     # operator email

    created_at = Column(DateTime, server_default=func.now())

    person = relationship("FacePerson", back_populates="enrolments")


class FaceWatchlistEntry(Base):
    """
    A person flagged for monitoring.

    Separate from FacePerson because the two answer different questions — who
    is on site, versus who must raise an alarm on sight — and because a
    watchlist entry has its own lifetime: it is added, it expires, it is
    revoked, independently of whether the person stays enrolled.
    """

    __tablename__ = "face_watchlist"

    entry_id = Column(String, primary_key=True, index=True)
    person_id = Column(
        String, ForeignKey("face_persons.person_id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    category = Column(String, nullable=False, default="BLACKLIST", index=True)
    severity = Column(String, nullable=False, default="critical")
    reason = Column(Text, nullable=True)

    # Optional validity window; NULL means open-ended.
    active_from = Column(DateTime, nullable=True)
    active_until = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Restrict the alert to specific cameras; empty/NULL means every camera.
    camera_ids = Column(JSON, nullable=True)

    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    person = relationship("FacePerson")

    __table_args__ = (
        # One live entry per person per category; history is in face_events.
        UniqueConstraint("person_id", "category", name="uq_watchlist_person_category"),
    )


class FaceEvent(Base):
    """
    Every recognition outcome worth keeping: check-ins, check-outs, watchlist
    hits and unmatched faces. This is the "face event history" the monitoring
    dashboard reads, and it is deliberately append-only.
    """

    __tablename__ = "face_events"

    event_id = Column(String, primary_key=True, index=True)
    # NULL for an unrecognised face — the event still matters.
    person_id = Column(
        String, ForeignKey("face_persons.person_id", ondelete="SET NULL"),
        index=True, nullable=True,
    )
    event_type = Column(String, nullable=False, index=True)
    camera_id = Column(String, nullable=True, index=True)
    camera_name = Column(String, nullable=True)
    timestamp = Column(DateTime, nullable=False, server_default=func.now(), index=True)

    similarity = Column(Float, nullable=True)
    severity = Column(String, nullable=True)
    snapshot_path = Column(String, nullable=True)
    watchlist_category = Column(String, nullable=True, index=True)
    # Alembic reserves `metadata` on the declarative class, so map around it.
    metadata_ = Column("metadata", JSON, nullable=True)

    person = relationship("FacePerson")

    __table_args__ = (
        # The dashboard's hot query is "recent events, optionally per camera".
        Index("ix_face_events_ts_camera", "timestamp", "camera_id"),
    )


class AttendanceRecord(Base):
    """
    One person's attendance for one day — first in, last out, total hours.

    Derived state, rebuilt from face_events, but stored because the reports
    the client asked for are per-day-per-person and computing them by scanning
    the event log on every request does not survive a year of data.
    """

    __tablename__ = "face_attendance_records"

    record_id = Column(String, primary_key=True, index=True)
    person_id = Column(
        String, ForeignKey("face_persons.person_id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    work_date = Column(Date, nullable=False, index=True)

    first_seen = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    check_in_time = Column(DateTime, nullable=True)
    check_out_time = Column(DateTime, nullable=True)
    check_in_camera = Column(String, nullable=True)
    check_out_camera = Column(String, nullable=True)
    total_hours = Column(Float, nullable=True)
    sightings = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="PRESENT")  # PRESENT | PARTIAL

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    person = relationship("FacePerson")

    __table_args__ = (
        # One row per person per day — the upsert key for the whole report.
        UniqueConstraint("person_id", "work_date", name="uq_attendance_person_day"),
    )
