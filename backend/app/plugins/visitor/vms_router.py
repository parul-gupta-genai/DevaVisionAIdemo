"""
The Visitor Management System / Visitor App integration surface.

Two audiences, deliberately separated:

  /vms/*            called BY the VMS, authenticated with an API key it holds.
                    Never a session cookie: the caller is a server, not a
                    logged-in human, and giving it a user account would make
                    every visitor appointment look like it was created by
                    whichever operator's credentials were reused.

  /integrations/*   called by an administrator in this UI to register a VMS
                    and mint its key. Session-authenticated and scoped.
"""

import base64
from datetime import datetime, timedelta
from typing import List, Optional

import numpy as np
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_permissions
from app.plugins.visitor.integration import (
    WEBHOOK_EVENTS, authenticate, new_api_key, vms_connector,
)
from app.plugins.visitor.models import (
    Visit, Visitor, VisitorIntegration, VisitorPreRegistration,
    VisitorWebhookDelivery,
)
from database.session import SessionLocal

vms_router = APIRouter(prefix="/api/visitors", tags=["Visitor VMS Integration"])

# Reuses the face module's scopes: an operator who may enrol a face is the
# same person who may register an expected visitor.
VMS_MANAGE = "face:enrol"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _new_id(prefix: str) -> str:
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


# ===================================================================== #
# Inbound: called by the VMS
# ===================================================================== #
def vms_caller(x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
               db: Session = Depends(get_db)) -> VisitorIntegration:
    row = authenticate(db, x_api_key)
    if row is None:
        raise HTTPException(401, detail={
            "code": "invalid_api_key",
            "message": "Provide a valid X-API-Key issued for this integration.",
        })
    return row


class PreRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    vms_reference: Optional[str] = Field(None, max_length=128)
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    host_name: Optional[str] = None
    purpose: Optional[str] = None
    expected_from: Optional[datetime] = None
    expected_until: Optional[datetime] = None
    # Optional face photo so the visitor is recognised on arrival. Without it
    # the appointment is still recorded and matched by name when they are
    # enrolled at reception.
    photo_base64: Optional[str] = None


class PreRegisterResponse(BaseModel):
    prereg_id: str
    vms_reference: Optional[str] = None
    visitor_id: Optional[str] = None
    status: str
    face_enrolled: bool
    known_visitor: bool
    previous_visits: int = 0
    last_seen: Optional[datetime] = None
    message: str


def _decode_photo(b64: str):
    try:
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        import cv2
        data = np.frombuffer(base64.b64decode(b64), np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


@vms_router.post("/vms/preregister", response_model=PreRegisterResponse)
def preregister(body: PreRegisterRequest,
                integration: VisitorIntegration = Depends(vms_caller),
                db: Session = Depends(get_db)):
    """
    Records a visit the VMS expects, optionally enrolling the visitor's face.

    Re-sending the same vms_reference updates the appointment rather than
    creating a second one — a VMS that retries on a timeout must not produce
    two expected visits for one appointment.

    The response tells the VMS whether this is somebody already on file and
    how often they have visited, which is what lets the Visitor App greet a
    returning visitor differently from a first-timer.
    """
    row = None
    if body.vms_reference:
        row = db.query(VisitorPreRegistration).filter(
            VisitorPreRegistration.vms_reference == body.vms_reference).first()

    face_enrolled = False
    visitor_id = row.visitor_id if row else None
    known, previous_visits, last_seen = False, 0, None

    if body.photo_base64:
        image = _decode_photo(body.photo_base64)
        if image is None:
            raise HTTPException(422, detail={
                "code": "bad_photo", "message": "photo_base64 is not a readable image."})
        try:
            from app.plugins.face.service import detect_faces
            from app.plugins.visitor.repository import VisitorRepository

            faces = detect_faces(image)
            if not faces:
                raise HTTPException(422, detail={
                    "code": "no_face", "message": "No face found in the photo."})
            if len(faces) > 1:
                raise HTTPException(422, detail={
                    "code": "multiple_faces",
                    "message": "The photo contains more than one face."})

            embedding = [float(x) for x in np.asarray(faces[0]["embedding"]).ravel()]
            repo = VisitorRepository(db)
            match, sim = repo.find_best_match(embedding, threshold=0.55)
            if match is not None:
                # Already on file — this is a returning visitor, and telling
                # the VMS so is the whole point of the endpoint.
                visitor_id = match.visitor_id
                known = match.status == "REGISTERED"
                previous_visits = match.total_visits or 0
                last_seen = match.last_seen
                if body.name and match.status != "REGISTERED":
                    # Put a name to a face first seen as an unknown walk-up.
                    match.name = body.name.strip()
                    match.status = "REGISTERED"
                    known = True
                match.face_embedding = embedding
                db.commit()
            else:
                created = repo.create_unknown_visitor(face_embedding=embedding)
                created.name = body.name.strip()
                created.status = "REGISTERED"
                created.role = "VISITOR"
                created.email = body.email
                created.phone = body.phone
                db.commit()
                visitor_id = created.visitor_id
            face_enrolled = True
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"VMS pre-registration face enrolment failed: {exc}")
            raise HTTPException(503, detail={
                "code": "face_engine_unavailable",
                "message": "Could not process the photo; the appointment was not saved.",
            })

    if visitor_id and not known:
        existing = db.query(Visitor).filter(Visitor.visitor_id == visitor_id).first()
        if existing is not None:
            previous_visits = existing.total_visits or 0
            last_seen = existing.last_seen
            known = (existing.total_visits or 0) > 0

    if row is None:
        row = VisitorPreRegistration(prereg_id=_new_id("PRE"),
                                     vms_reference=body.vms_reference)
        db.add(row)

    row.visitor_id = visitor_id
    row.name = body.name.strip()
    row.email = body.email
    row.phone = body.phone
    row.company = body.company
    row.host_name = body.host_name
    row.purpose = body.purpose
    row.expected_from = body.expected_from
    row.expected_until = body.expected_until
    row.source = integration.name
    if row.status not in ("ARRIVED", "DEPARTED"):
        row.status = "EXPECTED"
    db.commit()
    db.refresh(row)

    return PreRegisterResponse(
        prereg_id=row.prereg_id, vms_reference=row.vms_reference,
        visitor_id=visitor_id, status=row.status, face_enrolled=face_enrolled,
        known_visitor=bool(known), previous_visits=previous_visits,
        last_seen=last_seen,
        message=("Returning visitor — recognised from a previous visit."
                 if previous_visits else "Expected visit recorded."),
    )


@vms_router.get("/vms/expected")
def list_expected(status: str = Query("EXPECTED"),
                  integration: VisitorIntegration = Depends(vms_caller),
                  db: Session = Depends(get_db)):
    rows = (
        db.query(VisitorPreRegistration)
        .filter(VisitorPreRegistration.status == status)
        .order_by(VisitorPreRegistration.expected_from.asc().nullslast())
        .limit(500).all()
    )
    return {"count": len(rows), "items": [{
        "prereg_id": r.prereg_id, "vms_reference": r.vms_reference,
        "visitor_id": r.visitor_id, "name": r.name, "host_name": r.host_name,
        "purpose": r.purpose, "status": r.status,
        "expected_from": r.expected_from, "expected_until": r.expected_until,
        "arrived_at": r.arrived_at, "arrival_camera": r.arrival_camera,
    } for r in rows]}


@vms_router.get("/vms/visitors/{visitor_id}/history")
def vms_visitor_history(visitor_id: str, limit: int = Query(50, ge=1, le=500),
                        integration: VisitorIntegration = Depends(vms_caller),
                        db: Session = Depends(get_db)):
    """
    The visit history behind a returning-visitor decision.

    Exposed to the VMS so the Visitor App can show "4th visit, last here on
    12 August" rather than only a yes/no.
    """
    visitor = db.query(Visitor).filter(Visitor.visitor_id == visitor_id).first()
    if visitor is None:
        raise HTTPException(404, "No such visitor.")
    visits = (
        db.query(Visit).filter(Visit.visitor_id == visitor_id)
        .order_by(Visit.entry_time.desc()).limit(limit).all()
    )
    return {
        "visitor_id": visitor_id,
        "name": visitor.name,
        "role": visitor.role,
        "status": visitor.status,
        "total_visits": visitor.total_visits or 0,
        "first_seen": visitor.first_seen,
        "last_seen": visitor.last_seen,
        "is_returning": (visitor.total_visits or 0) > 1,
        "visits": [{
            "visit_id": v.visit_id, "entry_time": v.entry_time,
            "exit_time": v.exit_time, "camera_id": v.camera_id,
            "duration_sec": v.duration, "visit_number": v.visit_number,
            "days_since_previous": v.days_since_previous,
            "is_return": v.is_return,
        } for v in visits],
    }


@vms_router.post("/vms/expected/{prereg_id}/cancel")
def cancel_expected(prereg_id: str,
                    integration: VisitorIntegration = Depends(vms_caller),
                    db: Session = Depends(get_db)):
    row = db.query(VisitorPreRegistration).filter(
        VisitorPreRegistration.prereg_id == prereg_id).first()
    if row is None:
        raise HTTPException(404, "No such pre-registration.")
    if row.status == "ARRIVED":
        raise HTTPException(409, detail={
            "code": "already_arrived",
            "message": "That visitor has already arrived and cannot be cancelled.",
        })
    row.status = "CANCELLED"
    db.commit()
    return {"status": "CANCELLED", "prereg_id": prereg_id}


# ===================================================================== #
# Administration: called from this UI
# ===================================================================== #
class IntegrationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    subscribed_events: Optional[List[str]] = None


@vms_router.get("/integrations",
                dependencies=[require_permissions([VMS_MANAGE])])
def list_integrations(db: Session = Depends(get_db)):
    rows = db.query(VisitorIntegration).order_by(VisitorIntegration.name).all()
    return [{
        "integration_id": r.integration_id, "name": r.name,
        # Only the prefix; the key itself is unrecoverable by design.
        "api_key_prefix": r.api_key_prefix,
        "webhook_url": r.webhook_url,
        "has_secret": bool(r.webhook_secret),
        "subscribed_events": r.subscribed_events or [],
        "is_active": bool(r.is_active),
        "last_delivery_at": r.last_delivery_at,
        "last_delivery_status": r.last_delivery_status,
        "failure_count": r.failure_count or 0,
    } for r in rows]


@vms_router.post("/integrations",
                 dependencies=[require_permissions([VMS_MANAGE])])
def create_integration(body: IntegrationCreate, db: Session = Depends(get_db)):
    """
    Registers a VMS and mints its API key.

    The key is returned exactly once, here. It is stored only as a hash, so it
    cannot be shown again — losing it means issuing a new one.
    """
    if db.query(VisitorIntegration).filter(VisitorIntegration.name == body.name).first():
        raise HTTPException(409, detail={
            "code": "duplicate_name",
            "message": f"An integration called '{body.name}' already exists."})
    for e in body.subscribed_events or []:
        if e not in WEBHOOK_EVENTS:
            raise HTTPException(422, f"Unknown event '{e}'. "
                                     f"Valid: {', '.join(WEBHOOK_EVENTS)}")

    raw, digest, prefix = new_api_key()
    row = VisitorIntegration(
        integration_id=_new_id("VMS"), name=body.name.strip(),
        api_key_hash=digest, api_key_prefix=prefix,
        webhook_url=body.webhook_url, webhook_secret=body.webhook_secret,
        subscribed_events=body.subscribed_events, is_active=True,
    )
    db.add(row)
    db.commit()
    return {
        "integration_id": row.integration_id, "name": row.name,
        "api_key": raw,
        "warning": "This key is shown once and cannot be retrieved again.",
        "webhook_events": list(WEBHOOK_EVENTS),
    }


@vms_router.delete("/integrations/{integration_id}",
                   dependencies=[require_permissions([VMS_MANAGE])])
def delete_integration(integration_id: str, db: Session = Depends(get_db)):
    row = db.query(VisitorIntegration).filter(
        VisitorIntegration.integration_id == integration_id).first()
    if row is None:
        raise HTTPException(404, "No such integration.")
    db.delete(row)
    db.commit()
    return {"status": "deleted", "integration_id": integration_id}


@vms_router.get("/integrations/deliveries",
                dependencies=[require_permissions([VMS_MANAGE])])
def list_deliveries(integration_id: Optional[str] = None,
                    limit: int = Query(100, ge=1, le=500),
                    db: Session = Depends(get_db)):
    q = db.query(VisitorWebhookDelivery)
    if integration_id:
        q = q.filter(VisitorWebhookDelivery.integration_id == integration_id)
    rows = q.order_by(VisitorWebhookDelivery.created_at.desc()).limit(limit).all()
    return [{
        "delivery_id": r.delivery_id, "integration_id": r.integration_id,
        "event_type": r.event_type, "visitor_id": r.visitor_id,
        "status": r.status, "attempts": r.attempts,
        "response_code": r.response_code, "error": r.error,
        "created_at": r.created_at, "delivered_at": r.delivered_at,
    } for r in rows]


# ===================================================================== #
# Returning-visitor reporting, for this UI
# ===================================================================== #
@vms_router.get("/returning", dependencies=[Depends(get_current_user)])
def returning_visitors(days: int = Query(30, ge=1, le=365),
                       min_visits: int = Query(2, ge=2, le=100),
                       limit: int = Query(100, ge=1, le=500),
                       db: Session = Depends(get_db)):
    """Who has come back, how often, and when they were last here."""
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(Visitor)
        .filter(Visitor.total_visits >= min_visits)
        .filter((Visitor.last_seen.is_(None)) | (Visitor.last_seen >= since))
        .order_by(Visitor.total_visits.desc())
        .limit(limit).all()
    )
    return {"window_days": days, "count": len(rows), "items": [{
        "visitor_id": v.visitor_id, "name": v.name, "role": v.role,
        "status": v.status, "photo": ("/" + v.photo) if v.photo and not
        str(v.photo).startswith("/") else v.photo,
        "total_visits": v.total_visits or 0,
        "first_seen": v.first_seen, "last_seen": v.last_seen,
    } for v in rows]}
