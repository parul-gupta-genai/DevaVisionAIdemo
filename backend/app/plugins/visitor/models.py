from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from database.persistence import Base

class Visitor(Base):
    __tablename__ = "visitors"

    visitor_id = Column(String, primary_key=True, index=True)
    google_form_submission_id = Column(String, index=True, nullable=True)
    name = Column(String, index=True)
    role = Column(String, default="VISITOR", index=True) # VISITOR or EMPLOYEE
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    photo = Column(String, nullable=True)
    company = Column(String, nullable=True)
    id_document_number = Column(String, nullable=True)
    vehicle_number = Column(String, nullable=True)
    face_embedding = Column(Vector(512), nullable=True) # 512-dimensional pgvector array
    first_seen = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    total_visits = Column(Integer, default=0)
    status = Column(String, default="REGISTERED") # REGISTERED, UNKNOWN
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    visits = relationship("Visit", back_populates="visitor")
    events = relationship("VisitorEvent", back_populates="visitor")


class Visit(Base):
    __tablename__ = "visits"

    visit_id = Column(String, primary_key=True, index=True)
    visitor_id = Column(String, ForeignKey("visitors.visitor_id"), index=True)
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime, nullable=True)
    camera_id = Column(String, nullable=False)
    track_id = Column(String, nullable=False)
    snapshot_path = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    duration = Column(Float, nullable=True)
    visit_number = Column(Integer, nullable=True)
    days_since_previous = Column(Float, nullable=True)
    is_return = Column(Boolean, nullable=True)

    # Extended fields for Accompanying Person Detection & Gate Validation
    expected_accompanying_persons = Column(Integer, default=0, nullable=False)
    detected_accompanying_persons = Column(Integer, default=0, nullable=False)
    additional_person_count = Column(Integer, default=0, nullable=False)
    validation_status = Column(String, default="MATCH", index=True) # MATCH, UNREGISTERED_ACCOMPANYING_PERSON, EXTRA_VISITOR_DETECTED
    host_employee_id = Column(String, nullable=True)
    vehicle_number = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    visitor = relationship("Visitor", back_populates="visits")
    events = relationship("VisitorEvent", back_populates="visit")


class VisitorEvent(Base):
    __tablename__ = "visitor_events"

    event_id = Column(String, primary_key=True, index=True)
    visitor_id = Column(String, ForeignKey("visitors.visitor_id"), index=True)
    visit_id = Column(String, ForeignKey("visits.visit_id"), nullable=True)
    event_type = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=func.now())
    camera = Column(String, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)

    visitor = relationship("Visitor", back_populates="events")
    visit = relationship("Visit", back_populates="events")


# ===================================================================== #
# Returning-visitor recognition and VMS integration
# ===================================================================== #
class VisitorPreRegistration(Base):
    """
    A visit the Visitor Management System expects.
    """

    __tablename__ = "visitor_preregistrations"

    prereg_id = Column(String, primary_key=True, index=True)
    vms_reference = Column(String, unique=True, index=True, nullable=True)
    visitor_id = Column(String, ForeignKey("visitors.visitor_id", ondelete="SET NULL"),
                        index=True, nullable=True)

    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    company = Column(String, nullable=True)
    host_name = Column(String, nullable=True)
    host_employee_id = Column(String, nullable=True)
    purpose = Column(String, nullable=True)
    vehicle_number = Column(String, nullable=True)
    id_document_number = Column(String, nullable=True)
    expected_accompanying_persons = Column(Integer, default=0, nullable=False)

    expected_from = Column(DateTime, nullable=True, index=True)
    expected_until = Column(DateTime, nullable=True)
    # EXPECTED -> ARRIVED -> DEPARTED, or CANCELLED / EXPIRED / EXTRA_PERSON_DETECTED.
    status = Column(String, nullable=False, default="EXPECTED", index=True)
    arrived_at = Column(DateTime, nullable=True)
    arrival_camera = Column(String, nullable=True)

    source = Column(String, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    visitor = relationship("Visitor")


class VisitorIntegration(Base):
    """
    A configured Visitor Management System / Visitor App.

    Inbound calls authenticate with a key we only ever store hashed; outbound
    webhooks are signed with the shared secret so the receiver can verify the
    payload came from us and was not replayed.
    """

    __tablename__ = "visitor_integrations"

    integration_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    # sha256 of the API key. The key itself is shown once, at creation, and
    # is not recoverable afterwards.
    api_key_hash = Column(String, nullable=True, index=True)
    api_key_prefix = Column(String, nullable=True)

    webhook_url = Column(String, nullable=True)
    webhook_secret = Column(String, nullable=True)
    # Which event types to deliver; empty means all of them.
    subscribed_events = Column(JSON, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_delivery_at = Column(DateTime, nullable=True)
    last_delivery_status = Column(String, nullable=True)
    failure_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class VisitorWebhookDelivery(Base):
    """
    One outbound delivery attempt, kept so a missed notification can be
    explained rather than guessed at.
    """

    __tablename__ = "visitor_webhook_deliveries"

    delivery_id = Column(String, primary_key=True, index=True)
    integration_id = Column(String,
                            ForeignKey("visitor_integrations.integration_id",
                                       ondelete="CASCADE"),
                            index=True, nullable=False)
    event_type = Column(String, nullable=False, index=True)
    visitor_id = Column(String, nullable=True, index=True)
    payload = Column(JSON, nullable=True)

    status = Column(String, nullable=False, default="PENDING", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    response_code = Column(Integer, nullable=True)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    delivered_at = Column(DateTime, nullable=True)
