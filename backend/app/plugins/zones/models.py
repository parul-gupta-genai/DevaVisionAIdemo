"""
Restricted zones and their event log.

The client defines the areas and the operating rules; this is where both
live. Zones were previously a bare list of points in a config dict with one
entry — "default" — shared by every camera on the site, which meant there was
nowhere to record what a zone was called, when it applied, or what it was
supposed to catch. Every one of those is a rule the client is entitled to
set, so each is a column here rather than a constant in a plugin.

Geometry is stored in the DeepStream mux space (1280x720), the same space
counting lines and parking bays use, so a zone survives a camera changing
resolution.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String,
    Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.persistence import Base

ZONE_EVENT_TYPES = ("ZONE_ENTRY", "ZONE_LOITERING", "ZONE_EXIT")
SEVERITIES = ("critical", "warning", "info")


class RestrictedZone(Base):
    """One client-defined restricted area on one camera, with its rules."""

    __tablename__ = "restricted_zones"

    zone_id = Column(String, primary_key=True, index=True)
    camera_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    # [[x, y], ...] in mux space, at least 3 points.
    points = Column(JSON, nullable=False)

    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # ---- what the zone watches for -------------------------------------
    # COCO class ids; [0] (person) unless the client says otherwise.
    object_classes = Column(JSON, nullable=True)
    min_confidence = Column(Float, nullable=False, default=0.4)
    # Which point of the detection box must be inside: FEET, CENTER, HEAD or
    # BOX (any overlap). FEET is where a person is standing, which is what
    # "in the zone" means in an overhead view.
    anchor = Column(String, nullable=False, default="FEET")
    # Boxes shorter than this are ignored — too few pixels to be trusted.
    min_box_px = Column(Integer, nullable=False, default=0)

    # ---- when it applies ------------------------------------------------
    # NULL = armed around the clock. Otherwise a list of
    # {"start": "HH:MM", "end": "HH:MM", "days": [0-6]} in local time.
    schedule = Column(JSON, nullable=True)

    # ---- how it behaves -------------------------------------------------
    min_dwell_sec = Column(Float, nullable=False, default=2.0)
    # NULL disables loitering escalation for this zone.
    loiter_sec = Column(Float, nullable=True)
    exit_grace_sec = Column(Float, nullable=False, default=3.0)
    alert_cooldown_sec = Column(Float, nullable=False, default=30.0)
    severity = Column(String, nullable=False, default="warning")

    notes = Column(Text, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    events = relationship("ZoneEvent", back_populates="zone",
                          passive_deletes=True)

    __table_args__ = (
        # Two zones on one camera sharing a name makes every alert ambiguous.
        UniqueConstraint("camera_id", "name", name="uq_zone_camera_name"),
        Index("ix_zone_camera_active", "camera_id", "is_active"),
    )


class ZoneEvent(Base):
    """
    A logged zone occurrence.

    Kept separately from camera_events rather than only inside it: that table
    is a rolling 30-day frame stream pruned on a timer and read 20 rows at a
    time, which is the wrong shape for "show me every breach of the
    switchyard in August" — the question the client will actually ask.
    """

    __tablename__ = "zone_events"

    event_id = Column(String, primary_key=True, index=True)
    # A deleted zone must not take its history with it, so the FK nulls out
    # and the denormalised name keeps the record readable.
    zone_id = Column(String, ForeignKey("restricted_zones.zone_id", ondelete="SET NULL"),
                     nullable=True, index=True)
    zone_name = Column(String, nullable=True)
    camera_id = Column(String, nullable=True, index=True)
    camera_name = Column(String, nullable=True)

    event_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    # When the track first entered, so a breach can be replayed from its start
    # rather than from the moment the dwell rule confirmed it.
    started_at = Column(DateTime, nullable=True)
    dwell_seconds = Column(Float, nullable=True)

    track_id = Column(String, nullable=True)
    class_id = Column(Integer, nullable=True)
    class_name = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
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

    zone = relationship("RestrictedZone", back_populates="events")

    __table_args__ = (
        Index("ix_zone_events_cam_time", "camera_id", "timestamp"),
        Index("ix_zone_events_zone_time", "zone_id", "timestamp"),
        Index("ix_zone_events_open", "acknowledged", "timestamp"),
    )
