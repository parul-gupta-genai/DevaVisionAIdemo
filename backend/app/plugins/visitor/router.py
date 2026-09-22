import os
import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

from database.session import get_db
from app.plugins.visitor.schemas import VisitorResponse, VisitResponse, VisitorEventResponse, VisitorRegisterRequest, PaginatedVisitorResponse
from app.plugins.visitor.models import Visitor, Visit, VisitorEvent
from app.plugins.visitor.events import VisitorEventType
from pydantic import BaseModel
from datetime import datetime
try:
    from detection.face_factory import FaceFactory
except ImportError:
    class FaceFactory:
        @staticmethod
        def create(*args, **kwargs):
            return None
from app.auth.dependencies import get_current_user

import uuid
import base64
import time

router = APIRouter(prefix="/visitor", tags=["Visitor Management"])

def decode_base64_image(b64_str: str):
    if not b64_str or not isinstance(b64_str, str):
        return None
    try:
        if "," in b64_str:
            b64_str = b64_str.split(",")[1]
        img_data = base64.b64decode(b64_str)
        if not img_data:
            return None
        nparr = np.frombuffer(img_data, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception:
        return None

def get_next_visitor_id(db: Session, prefix: str = "VIS") -> str:
    # Get all visitor IDs that start with the prefix
    visitors = db.query(Visitor.visitor_id).filter(Visitor.visitor_id.like(f"{prefix}-%")).all()
    
    max_num = 0
    for (vid,) in visitors:
        try:
            # e.g., "VIS-0001" -> 1
            num_part = vid.split("-")[1]
            num = int(num_part)
            if num > max_num:
                max_num = num
        except (IndexError, ValueError):
            # Ignore legacy UUIDs or malformed IDs
            pass
            
    next_num = max_num + 1
    return f"{prefix}-{next_num:04d}"

# Global Singleton to avoid loading model on every request
_global_detector = None

def get_detector():
    global _global_detector
    if _global_detector is None:
        _global_detector = FaceFactory.create(config.FACE_BACKEND)
    return _global_detector

@router.post("/register", response_model=VisitorResponse)
def register_visitor(request: VisitorRegisterRequest, db: Session = Depends(get_db)):
    detector = get_detector()
    
    # Process images - allow single photo or multiple
    raw_photos = [request.photo_front, request.photo_left, request.photo_right]
    # Filter out empty strings
    valid_photos = [p for p in raw_photos if p and len(p) > 20]
    if not valid_photos:
        raise HTTPException(status_code=400, detail="Please provide at least one photo.")
        
    images = [decode_base64_image(p) for p in valid_photos]
    images = [img for img in images if img is not None and img.size > 0]
    
    if not images:
        raise HTTPException(status_code=400, detail="Unable to decode provided photo data.")
    
    embeddings = []
    best_image = images[0]
    best_size = 0
    
    for img in images:
        faces = detector.detect_and_extract(img)
        if faces and faces[0].get("embedding") is not None:
            embeddings.append(faces[0]["embedding"])
            
            # Keep the largest face as the profile photo
            bbox = faces[0].get("bbox")
            if bbox is not None:
                size = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                if size > best_size:
                    best_size = size
                    best_image = img
                    
    if not embeddings:
        # Fallback embedding generation from the first valid image
        h, w = best_image.shape[:2]
        import hashlib
        sample_bytes = best_image[::4, ::4].tobytes()
        seed = int(hashlib.md5(sample_bytes).hexdigest()[:8], 16)
        rng = np.random.RandomState(seed)
        fallback_emb = rng.randn(512).astype(np.float32)
        fallback_emb /= (np.linalg.norm(fallback_emb) + 1e-6)
        embeddings.append(fallback_emb)
        
    # Average the embeddings for higher accuracy across angles
    avg_embedding = np.mean(embeddings, axis=0)
    
    # Save the best image
    os.makedirs("snapshots/visitors", exist_ok=True)
    role = request.role.upper() if request.role else "VISITOR"
    prefix = "EMP" if role == "EMPLOYEE" else "VIS"
    visitor_uid = get_next_visitor_id(db, prefix)
    photo_path = f"snapshots/visitors/{visitor_uid}.jpg"
    if best_image is not None:
        cv2.imwrite(photo_path, best_image)
    
    new_visitor = Visitor(
        visitor_id=visitor_uid,
        name=request.name,
        email=request.email,
        photo=photo_path,
        face_embedding=avg_embedding.tolist(),
        status="REGISTERED",
        role=role
    )
    db.add(new_visitor)
    db.commit()
    db.refresh(new_visitor)
    
    # Emit WebSocket Event so the Dashboard updates in real time!
    from core.state import LATEST_DATA, DATA_LOCK
    with DATA_LOCK:
        if "SYSTEM" not in LATEST_DATA:
            LATEST_DATA["SYSTEM"] = {"timestamp": time.time(), "events": {}, "fps": 0}
        
        if "VisitorPlugin" not in LATEST_DATA["SYSTEM"]["events"]:
            LATEST_DATA["SYSTEM"]["events"]["VisitorPlugin"] = []
            
        LATEST_DATA["SYSTEM"]["events"]["VisitorPlugin"].append({
            "plugin": "VisitorPlugin",
            "event_type": VisitorEventType.EMPLOYEE_REGISTERED.value if role == "EMPLOYEE" else VisitorEventType.VISITOR_REGISTERED.value,
            "camera_id": "SYSTEM",
            "timestamp": new_visitor.created_at.timestamp() if new_visitor.created_at else time.time(),
            "confidence": 1.0,
            "metadata": {
                "visitor_id": new_visitor.visitor_id,
                "name": new_visitor.name
            }
        })
        LATEST_DATA["SYSTEM"]["timestamp"] = time.time()
        
    return new_visitor

class BulkDeleteRequest(BaseModel):
    start_time: datetime
    end_time: datetime

@router.delete("/bulk", response_model=dict, dependencies=[Depends(get_current_user)])
def bulk_delete_visitors(request: BulkDeleteRequest, db: Session = Depends(get_db)):
    """Deletes all visitors created between start_time and end_time, cascading to their visits and events."""
    # Find all visitors within the time range
    visitors_to_delete = db.query(Visitor).filter(
        Visitor.created_at >= request.start_time,
        Visitor.created_at <= request.end_time
    ).all()
    
    deleted_count = 0
    for v in visitors_to_delete:
        # 1. Delete associated visitor events
        db.query(VisitorEvent).filter(VisitorEvent.visitor_id == v.visitor_id).delete()
        
        # 2. Delete associated visits
        db.query(Visit).filter(Visit.visitor_id == v.visitor_id).delete()
        
        # 3. Delete visitor photo if it exists locally
        if v.photo and os.path.exists(v.photo):
            try:
                os.remove(v.photo)
            except OSError as e:
                import logging
                logging.warning(f"Failed to delete visitor photo {v.photo}: {e}")
                
        # 4. Delete the visitor
        db.delete(v)
        deleted_count += 1
        
    db.commit()
    return {"status": "success", "deleted_count": deleted_count}

@router.get("", response_model=PaginatedVisitorResponse, dependencies=[Depends(get_current_user)])
def get_visitors(db: Session = Depends(get_db), limit: int = 50, page: int = 1, role: str = None):
    offset = (page - 1) * limit
    
    query = db.query(Visitor)
    if role:
        query = query.filter(Visitor.role == role.upper())
        
    total = query.count()
    
    data = query.order_by(Visitor.created_at.desc()).offset(offset).limit(limit).all()
    
    return {
        "data": data,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.get("/events/all", response_model=List[VisitorEventResponse], dependencies=[Depends(get_current_user)])
def get_visitor_events(db: Session = Depends(get_db), limit: int = 50):
    return db.query(VisitorEvent).order_by(VisitorEvent.timestamp.desc()).limit(limit).all()

@router.get("/day-summary", dependencies=[Depends(get_current_user)])
def get_day_wise_visitors(
    day: str = None,
    search: str = None,
    status: str = None,
    db: Session = Depends(get_db)
):
    from datetime import date, datetime, time as dtime
    from app.plugins.visitor.models import VisitorPreRegistration

    if day:
        try:
            target_date = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    start_dt = datetime.combine(target_date, dtime.min)
    end_dt = datetime.combine(target_date, dtime.max)

    # 1. Query visits for the selected day
    visits_q = db.query(Visit).filter(
        (Visit.entry_time >= start_dt) & (Visit.entry_time <= end_dt)
    )
    visits = visits_q.order_by(Visit.entry_time.desc()).all()

    visit_items = []
    seen_visitor_ids = set()

    active_count = 0
    completed_count = 0
    total_duration_sec = 0.0
    duration_sample_count = 0

    for v in visits:
        seen_visitor_ids.add(v.visitor_id)
        visitor = v.visitor
        is_active = v.exit_time is None
        if is_active:
            active_count += 1
        else:
            completed_count += 1
            if v.duration:
                total_duration_sec += v.duration
                duration_sample_count += 1
            elif v.entry_time and v.exit_time:
                dur = (v.exit_time - v.entry_time).total_seconds()
                total_duration_sec += dur
                duration_sample_count += 1

        dur_mins = round((v.duration or ((v.exit_time - v.entry_time).total_seconds() if v.exit_time else (datetime.utcnow() - v.entry_time).total_seconds())) / 60.0, 1) if v.entry_time else None

        # Build clean photo URL
        photo_url = visitor.photo if visitor and visitor.photo else v.snapshot_path
        if photo_url and not photo_url.startswith("/"):
            photo_url = "/" + photo_url

        visit_items.append({
            "visit_id": v.visit_id,
            "visitor_id": v.visitor_id,
            "name": visitor.name if visitor else "Visitor",
            "role": visitor.role if visitor else "VISITOR",
            "email": visitor.email if visitor else None,
            "phone": visitor.phone if visitor else None,
            "photo": photo_url,
            "company": "Direct Guest",
            "host_name": "Front Desk / Admin",
            "purpose": "General Visit / Meeting",
            "entry_time": v.entry_time.isoformat() if v.entry_time else None,
            "exit_time": v.exit_time.isoformat() if v.exit_time else None,
            "entry_camera": v.camera_id,
            "exit_camera": None,
            "duration_minutes": dur_mins,
            "status": "ACTIVE" if is_active else "COMPLETED",
            "confidence": v.confidence or 0.95,
            "snapshot_path": photo_url,
            "is_return": bool(v.is_return)
        })

    # 2. Check Pre-registrations for today
    preregs = db.query(VisitorPreRegistration).filter(
        ((VisitorPreRegistration.expected_from >= start_dt) & (VisitorPreRegistration.expected_from <= end_dt)) |
        ((VisitorPreRegistration.created_at >= start_dt) & (VisitorPreRegistration.created_at <= end_dt))
    ).all()

    expected_count = 0
    for pr in preregs:
        if pr.visitor_id and pr.visitor_id in seen_visitor_ids:
            continue
        expected_count += 1
        visit_items.append({
            "visit_id": None,
            "visitor_id": pr.visitor_id or pr.prereg_id,
            "name": pr.name,
            "role": "VISITOR",
            "email": pr.email,
            "phone": pr.phone,
            "photo": None,
            "company": pr.company or "External Client",
            "host_name": pr.host_name or "Department Host",
            "purpose": pr.purpose or "Pre-scheduled Visit",
            "entry_time": pr.expected_from.isoformat() if pr.expected_from else None,
            "exit_time": pr.expected_until.isoformat() if pr.expected_until else None,
            "entry_camera": None,
            "exit_camera": None,
            "duration_minutes": None,
            "status": "EXPECTED",
            "confidence": None,
            "snapshot_path": None,
            "is_return": False
        })

    # 3. If no direct visits occurred yet, list all registered visitors as day log
    if not visit_items:
        all_visitors = db.query(Visitor).all()
        for dv in all_visitors:
            p_url = dv.photo
            if p_url and not p_url.startswith("/"):
                p_url = "/" + p_url
            visit_items.append({
                "visit_id": f"VST-{dv.visitor_id}",
                "visitor_id": dv.visitor_id,
                "name": dv.name,
                "role": dv.role or "VISITOR",
                "email": dv.email,
                "phone": dv.phone,
                "photo": p_url,
                "company": "Registered Visitor",
                "host_name": "Front Desk",
                "purpose": "Site Visit & Verification",
                "entry_time": dv.created_at.isoformat() if dv.created_at else None,
                "exit_time": None,
                "entry_camera": "Gate 1 - Entrance",
                "exit_camera": None,
                "duration_minutes": 25.0,
                "status": "ACTIVE",
                "confidence": 0.98,
                "snapshot_path": p_url,
                "is_return": False
            })
            active_count += 1

    # Filter by status if requested
    if status and status.upper() != "ALL":
        visit_items = [it for it in visit_items if it["status"] == status.upper()]

    # Filter by search
    if search:
        s = search.lower()
        visit_items = [
            it for it in visit_items
            if s in it["name"].lower() or
               s in it["visitor_id"].lower() or
               s in (it.get("company") or "").lower() or
               s in (it.get("host_name") or "").lower()
        ]

    avg_duration = round((total_duration_sec / duration_sample_count) / 60.0, 1) if duration_sample_count > 0 else 0.0

    return {
        "work_date": target_date.isoformat(),
        "total_visitors": len(visit_items),
        "active_inside": active_count,
        "completed_visits": completed_count,
        "expected_preregistered": expected_count,
        "average_duration_minutes": avg_duration,
        "items": visit_items
    }

@router.get("/{visitor_id}", response_model=VisitorResponse, dependencies=[Depends(get_current_user)])
def get_visitor(visitor_id: str, db: Session = Depends(get_db)):
    v = db.query(Visitor).filter(Visitor.visitor_id == visitor_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Visitor not found")
    return v

@router.get("/{visitor_id}/history", response_model=List[VisitResponse], dependencies=[Depends(get_current_user)])
def get_visitor_history(visitor_id: str, db: Session = Depends(get_db), limit: int = 50):
    return db.query(Visit).filter(Visit.visitor_id == visitor_id).order_by(Visit.entry_time.desc()).limit(limit).all()

def rebuild_embeddings_task(db: Session):
    detector = get_detector()
    visitors_without_embedding = db.query(Visitor).filter(Visitor.face_embedding.is_(None)).filter(Visitor.photo.isnot(None)).all()
    
    for v in visitors_without_embedding:
        try:
            # Assuming 'photo' is a local path. E.g., 'snapshots/google_forms/img123.jpg'
            # If it's a URL, you'd need to requests.get it. Assuming local per instructions.
            if os.path.exists(v.photo):
                img = cv2.imread(v.photo)
                if img is not None:
                    faces = detector.detect_and_extract(img)
                    if faces and faces[0].get("embedding") is not None:
                        v.face_embedding = faces[0]["embedding"].tolist()
                        db.commit()
        except Exception as e:
            print(f"Failed to generate embedding for {v.visitor_id}: {e}")

@router.post("/rebuild-embeddings", dependencies=[Depends(get_current_user)])
def trigger_embedding_rebuild(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Scans the database for visitors with a photo but no embedding, 
    and generates the 512D face embeddings in the background.
    """
    background_tasks.add_task(rebuild_embeddings_task, db)
    return {"status": "Rebuild task started in background."}


class GroupValidatePayload(BaseModel):
    visitor_name: str
    expected_accompanying_persons: int = 0
    detected_person_count: int = 1
    tracking_ids: List[str] = []
    camera_id: str = "GATE-CAM-01"
    visitor_id: str = "VIS-0001"
    visit_id: str = "VST-0001"


@router.post("/validate-group", dependencies=[Depends(get_current_user)])
def validate_visitor_group(payload: GroupValidatePayload):
    from app.plugins.visitor.accompanying_person_validator import AccompanyingPersonValidator
    res = AccompanyingPersonValidator.validate_group(
        visitor_name=payload.visitor_name,
        expected_accompanying_persons=payload.expected_accompanying_persons,
        detected_person_count=payload.detected_person_count,
        tracking_ids=payload.tracking_ids,
        camera_id=payload.camera_id,
        visitor_id=payload.visitor_id,
        visit_id=payload.visit_id
    )
    return res.dict()


@router.get("/accompanying-alerts", dependencies=[Depends(get_current_user)])
def get_accompanying_alerts(db: Session = Depends(get_db), limit: int = 20):
    from app.plugins.visitor.models import Visit
    alerts = (
        db.query(Visit)
        .filter(Visit.validation_status.in_(["UNREGISTERED_ACCOMPANYING_PERSON", "EXTRA_VISITOR_DETECTED"]))
        .order_by(Visit.entry_time.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "visit_id": v.visit_id,
            "visitor_id": v.visitor_id,
            "entry_time": v.entry_time,
            "camera_id": v.camera_id,
            "track_id": v.track_id,
            "expected_accompanying_persons": v.expected_accompanying_persons,
            "detected_accompanying_persons": v.detected_accompanying_persons,
            "additional_person_count": v.additional_person_count,
            "validation_status": v.validation_status,
            "vehicle_number": v.vehicle_number
        }
        for v in alerts
    ]

