from fastapi import APIRouter, Depends
from app.auth.dependencies import get_current_user
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database.session import SessionLocal
from typing import List, Dict, Any
from database.models.models import CameraEvent

parking_router = APIRouter(prefix="/api/parking", tags=["Parking Analytics"], dependencies=[Depends(get_current_user)])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@parking_router.get("/stats")
def get_parking_stats(db: Session = Depends(get_db)):
    events = db.query(CameraEvent).filter(
        CameraEvent.events.op("->")("ParkingAnalyticsPlugin") != None
    ).order_by(desc(CameraEvent.timestamp)).limit(50).all()
    
    # Just return empty/initial structure because WebSockets handles the real-time update
    result = {}
    for e in events:
        if e.camera_id not in result:
            plugin_events = e.events.get("ParkingAnalyticsPlugin", [])
            for pe in plugin_events:
                if pe.get("event_type") == "PARKING_STATS":
                    result[e.camera_id] = {
                        "timestamp": e.timestamp.isoformat() + "Z",
                        "total_spots": pe.get("metadata", {}).get("total_spots", 0),
                        "occupied_spots": pe.get("metadata", {}).get("occupied_spots", 0),
                        "available_spots": pe.get("metadata", {}).get("available_spots", 0),
                        "spot_status": pe.get("metadata", {}).get("spot_status", []),
                        "vehicle_count": pe.get("metadata", {}).get("vehicle_count", 0)
                    }
                    break
                    
    return {"current": result}
