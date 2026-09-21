from fastapi import APIRouter, Depends
from app.auth.dependencies import get_current_user
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database.session import SessionLocal
from typing import List, Dict, Any
from database.models.models import CameraEvent

attendance_router = APIRouter(prefix="/api/attendance", tags=["Attendance Analytics"], dependencies=[Depends(get_current_user)])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@attendance_router.get("/stats")
def get_attendance_stats(db: Session = Depends(get_db)):
    events = db.query(CameraEvent).filter(
        CameraEvent.events.op("->")("AttendanceDetectionPlugin") != None
    ).order_by(desc(CameraEvent.timestamp)).limit(50).all()
    
    logs_by_cam = {}
    for e in events:
        if e.camera_id not in logs_by_cam:
            logs_by_cam[e.camera_id] = []
        plugin_events = e.events.get("AttendanceDetectionPlugin", [])
        for pe in plugin_events:
            if pe.get("event_type") in ["CHECK_IN", "CHECK_OUT"]:
                logs_by_cam[e.camera_id].append({
                    "time": e.timestamp.timestamp(),
                    "action": pe.get("metadata", {}).get("action", pe.get("event_type")),
                    "employee": pe.get("metadata", {}).get("person_name") or (f"Emp {pe['metadata']['employee_id']}" if pe.get("metadata", {}).get("employee_id") is not None else "Unknown Person")
                })
    
    # We rely on WebSocket for live state, this just provides recent logs per camera
    # We will format it to match the expected schema but leave live arrays empty.
    result = {}
    for cam, logs in logs_by_cam.items():
        result[cam] = {
            "authorized_employees_in_frame": [], # Handled by WebSocket on frontend
            "unauthorized_count": 0,             # Handled by WebSocket on frontend
            "attendance_logs": logs[:10]
        }
    return {"current": result}
