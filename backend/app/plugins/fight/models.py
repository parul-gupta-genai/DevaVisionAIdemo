"""
SOW 2.7 — fight/quarrel detection zones and their incident log.

The client designates the camera zones; this is where those and the resulting
incidents live. Geometry is stored in the DeepStream mux space (1280x720), the
same space restricted zones, fire zones and counting lines use, so a zone
survives a camera changing resolution.

Nothing recorded here is a finding of fact. Detection is an automated visual
analytics aid; every incident requires human verification and does not replace
human security intervention.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String,
    Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.persistence import Base

FIGHT_EVENT_TYPES = ("FIGHT_DETECTED", "FIGHT_CLEARED")
ZONE_KINDS = ("DETECT", "EXCLUDE")


class FightZone(Base):
    """One fight-detection or exclusion area on one camera."""

    __tablename__ = "fight_zones"

    zone_id = Column(String, primary_key=True, index=True)
    camera_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    points = Column(JSON, nullable=False)

    # EXCLUDE is what makes this survivable on a real site: a gym, a
    # play area, a training mat or a loading crew that wrestles cargo will
    # otherwise generate incidents all day.
    zone_kind = Column(String, nullable=False, default="DETECT", index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    sensitivity = Column(String, nullable=False, default="standard")
    severity = Column(String, nullable=True)

    # Per-zone threshold overrides. NULL means "use the preset".
    min_score = Column(Float, nullable=True)
    min_frames = Column(Integer, nullable=True)
    confirm_sec = Column(Float, nullable=True)
    engage_separation = Column(Float, nullable=True)
    clear_sec = Column(Float, nullable=True)
    alert_cooldown_sec = Column(Float, nullable=True)

    schedule = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    events = relationship("FightEvent", back_populates="zone", passive_deletes=True)

    __table_args__ = (
        UniqueConstraint("camera_id", "name", name="uq_fight_zone_camera_name"),
        Index("ix_fight_zone_camera_active", "camera_id", "is_active"),
    )


class FightEvent(Base):
    """
    A logged fight/quarrel indication.

    Kept out of camera_events because that table is a rolling 30-day frame
    stream read 20 rows at a time — the wrong shape for "show me every
    incident at the loading bay this quarter", which is the question an
    incident review or an HR process actually asks.
    """

    __tablename__ = "fight_events"

    event_id = Column(String, primary_key=True, index=True)
    zone_id = Column(String, ForeignKey("fight_zones.zone_id", ondelete="SET NULL"),
                     nullable=True, index=True)
    zone_name = Column(String, nullable=True)
    camera_id = Column(String, nullable=True, index=True)
    camera_name = Column(String, nullable=True)

    event_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False, server_default=func.now(),
                       index=True)
    started_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    score = Column(Float, nullable=True)
    track_ids = Column(JSON, nullable=True)
    bbox = Column(JSON, nullable=True)
    snapshot_path = Column(String, nullable=True)

    acknowledged = Column(Boolean, nullable=False, default=False, index=True)
    acknowledged_by = Column(String, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    ack_note = Column(Text, nullable=True)

    # Whether a human confirmed this was a real fight. The module is an aid,
    # so the record has to be able to say "reviewed, and it was nothing" —
    # otherwise the log reads as a list of confirmed assaults, which it is not.
    verified = Column(String, nullable=True, index=True)   # confirmed/dismissed

    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    zone = relationship("FightZone", back_populates="events")

    __table_args__ = (
        Index("ix_fight_events_cam_time", "camera_id", "timestamp"),
        Index("ix_fight_events_open", "acknowledged", "timestamp"),
    )
