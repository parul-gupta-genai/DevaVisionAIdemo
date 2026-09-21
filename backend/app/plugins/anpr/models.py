from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, Boolean, DateTime
from sqlalchemy.orm import relationship
from database.session import Base
from sqlalchemy.sql import func
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class ANPRWatchlist(Base):
    __tablename__ = "anpr_watchlists"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    plate_number = Column(String, index=True, unique=True)
    list_type = Column(String) # Whitelist, Blacklist, VIP, Employee, Visitor, Contractor, Police, Stolen Vehicle, Expired Access
    priority = Column(Integer, default=0)
    notification_rules = Column(JSON)
    expiry = Column(Float, nullable=True) # Unix timestamp
    reason = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ANPRGate(Base):
    """
    A designated gate or entry point, and the client's access rules for it.

    ANPR previously recognised plates per camera with no notion of what the
    camera was watching, which left the direction columns below permanently
    null and made "who came in this morning" unanswerable. A gate names the
    camera's role so a recognition becomes an entry or an exit, and carries
    the access rules the SOW says the client provides.
    """

    __tablename__ = "anpr_gates"

    gate_id = Column(String, primary_key=True, default=generate_uuid, index=True)
    name = Column(String, nullable=False)
    # One camera per gate row; a gate watched by two cameras is two rows
    # sharing a name, which is also how a separate in and out lane is modelled.
    camera_id = Column(String, nullable=False, index=True)
    # ENTRY, EXIT or BIDIRECTIONAL. A designated gate answers direction by
    # definition; only BIDIRECTIONAL infers it from vehicle travel.
    role = Column(String, nullable=False, default="BIDIRECTIONAL")
    # Axis and orientation used for that inference.
    axis = Column(String, nullable=False, default="VERTICAL")
    invert = Column(Boolean, nullable=False, default=False)
    min_travel_px = Column(Float, nullable=False, default=40.0)

    # {"allow": [...], "deny": [...], "unlisted": "ALLOW"|"DENY"}
    access_rules = Column(JSON, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, index=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())


class ANPRVehicleTrack(Base):
    __tablename__ = "anpr_vehicle_tracks"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    track_id = Column(String, index=True)
    camera_id = Column(String, index=True)
    start_time = Column(Float)
    end_time = Column(Float, nullable=True)
    best_plate = Column(String, index=True, nullable=True)
    plate_confidence = Column(Float, nullable=True)
    vehicle_type = Column(String, nullable=True)
    vehicle_snapshot = Column(String, nullable=True)
    plate_snapshot = Column(String, nullable=True)
    direction = Column(String, nullable=True)
    lane = Column(String, nullable=True)

class ANPREvent(Base):
    __tablename__ = "anpr_events"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    event_type = Column(String, index=True) # PLATE_DETECTED, NEW_PLATE, WHITELIST_MATCH, BLACKLIST_MATCH, LOW_CONFIDENCE, OCR_FAILED, DUPLICATE_PLATE, TRACK_STARTED, TRACK_ENDED
    plate_number = Column(String, index=True, nullable=True)
    confidence = Column(Float, nullable=True)
    timestamp = Column(Float, index=True)
    camera_id = Column(String, index=True)
    track_id = Column(String, index=True, nullable=True)
    recognition_time_ms = Column(Float, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    detection_confidence = Column(Float, nullable=True)
    metadata_json = Column(JSON, nullable=True)

class ANPRPlateHistory(Base):
    __tablename__ = "anpr_plate_history"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    plate_number = Column(String, index=True)
    confidence = Column(Float)
    timestamp = Column(Float, index=True)
    camera_id = Column(String, index=True)
    track_id = Column(String, index=True, nullable=True)
    vehicle_snapshot = Column(String, nullable=True)
    plate_snapshot = Column(String, nullable=True)
    direction = Column(String, nullable=True)
    lane = Column(String, nullable=True)
    recognition_time_ms = Column(Float, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    detection_confidence = Column(Float, nullable=True)

class ANPRStatistics(Base):
    __tablename__ = "anpr_statistics"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    date_bucket = Column(String, index=True) # e.g. "2026-07-21" or "2026-07-21T14:00"
    camera_id = Column(String, index=True)
    total_detections = Column(Integer, default=0)
    unique_plates = Column(Integer, default=0)
    watchlist_matches = Column(Integer, default=0)
    metrics_json = Column(JSON, nullable=True) # Top vehicles, averages, etc.
