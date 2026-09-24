from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, Index, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from database.session import Base

class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    rtsp_url = Column(String, nullable=True)
    source_type = Column(String, nullable=False, server_default="rtsp")
    source = Column(String, nullable=True)
    active = Column(Boolean, default=True, server_default="true")
    state = Column(String, nullable=True, server_default="STOPPED")
    edge_id = Column(String, nullable=True, server_default="edge-01")
    created_at = Column(DateTime(timezone=True), default=func.now())


class CameraEvent(Base):
    __tablename__ = "camera_events"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, default=func.now())
    events = Column(JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"), nullable=False)

    __table_args__ = (
        Index("idx_camera_timestamp", "camera_id", "timestamp"),
    )
