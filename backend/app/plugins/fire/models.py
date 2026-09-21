"""
SOW 2.8 — fire and smoke detection zones and their event log.

The client designates the feeds and the areas; this is where both live. Fire
detection previously had no configuration surface at all: it scanned every
pixel of every camera it was enabled on, with one hard-coded colour rule and
one hard-coded 3-second cooldown. That left no way to say "the welding bay is
orange all shift, ignore it", "watch the battery store harder than the car
park", or "this camera looks at a sodium lamp" — all of which are the
difference between a system that gets used and one that gets muted.

Geometry is stored in the DeepStream mux space (1280x720), the same space
restricted zones, counting lines and parking bays use, so a zone survives a
camera changing resolution.

This is an AI visual early-warning aid. It does not replace statutory fire
detection, alarm or suppression systems, and nothing in this schema should be
read as a fire alarm control panel record.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String,
    Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.persistence import Base

FIRE_EVENT_TYPES = ("FIRE_DETECTED", "SMOKE_DETECTED", "FIRE_CLEARED")
ZONE_KINDS = ("DETECT", "EXCLUDE")


class FireZone(Base):
    """One fire/smoke detection or exclusion area on one camera."""

    __tablename__ = "fire_zones"

    zone_id = Column(String, primary_key=True, index=True)
    camera_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    # [[x, y], ...] in mux space, at least 3 points.
    points = Column(JSON, nullable=False)

    # DETECT watches the area; EXCLUDE silences it. Exclusions are what make
    # the feature survivable on a real site — a welding bay, a kitchen pass,
    # an amber beacon or a sodium lamp is otherwise a permanent fire.
    zone_kind = Column(String, nullable=False, default="DETECT", index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # ---- what it watches for -------------------------------------------
    # ["fire"], ["smoke"] or both.
    watch = Column(JSON, nullable=True)
    sensitivity = Column(String, nullable=False, default="standard")
    # NULL means the per-kind default: critical for fire, warning for smoke.
    severity = Column(String, nullable=True)

    # ---- per-zone threshold overrides ----------------------------------
    # All nullable: NULL means "use the preset", which is what an operator who
    # never opened the advanced panel expects.
    min_score = Column(Float, nullable=True)
    min_frames = Column(Integer, nullable=True)
    confirm_sec = Column(Float, nullable=True)
    min_area_frac = Column(Float, nullable=True)
    clear_sec = Column(Float, nullable=True)
    alert_cooldown_sec = Column(Float, nullable=True)

    # ---- when it applies ------------------------------------------------
    # NULL = armed around the clock. Otherwise a list of
    # {"start": "HH:MM", "end": "HH:MM", "days": [0-6]} in local time.
    schedule = Column(JSON, nullable=True)

    notes = Column(Text, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    events = relationship("FireEvent", back_populates="zone", passive_deletes=True)

    __table_args__ = (
        # Two zones on one camera sharing a name makes every alert ambiguous.
        UniqueConstraint("camera_id", "name", name="uq_fire_zone_camera_name"),
        Index("ix_fire_zone_camera_active", "camera_id", "is_active"),
    )


class FireEvent(Base):
    """
    A logged fire or smoke incident.

    Kept out of camera_events for the same reason zone events are: that table
    is a rolling frame stream pruned on a timer and read 20 rows at a time,
    which is the wrong shape for "show me every fire alarm from the battery
    store this quarter" — the question an incident review actually asks.
    """

    __tablename__ = "fire_events"

    event_id = Column(String, primary_key=True, index=True)
    # A deleted zone must not take its history with it, so the FK nulls out
    # and the denormalised name keeps the record readable.
    zone_id = Column(String, ForeignKey("fire_zones.zone_id", ondelete="SET NULL"),
                     nullable=True, index=True)
    zone_name = Column(String, nullable=True)
    camera_id = Column(String, nullable=True, index=True)
    camera_name = Column(String, nullable=True)

    event_type = Column(String, nullable=False, index=True)
    # "fire" or "smoke" — kept alongside event_type so the two can be filtered
    # without parsing the type string.
    kind = Column(String, nullable=True, index=True)
    severity = Column(String, nullable=True, index=True)

    timestamp = Column(DateTime, nullable=False, server_default=func.now(),
                       index=True)
    # When the evidence first appeared, so an incident can be replayed from
    # its start rather than from the moment confirmation completed.
    started_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    score = Column(Float, nullable=True)
    area_frac = Column(Float, nullable=True)
    bbox = Column(JSON, nullable=True)
    snapshot_path = Column(String, nullable=True)

    acknowledged = Column(Boolean, nullable=False, default=False, index=True)
    acknowledged_by = Column(String, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    ack_note = Column(Text, nullable=True)

    # Named `details` rather than `metadata`, which is reserved on a
    # declarative class and shadows Base.metadata.
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    zone = relationship("FireZone", back_populates="events")

    __table_args__ = (
        Index("ix_fire_events_cam_time", "camera_id", "timestamp"),
        Index("ix_fire_events_zone_time", "zone_id", "timestamp"),
        Index("ix_fire_events_open", "acknowledged", "timestamp"),
    )
