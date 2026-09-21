from fastapi import APIRouter, Depends
from app.auth.dependencies import get_current_user
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from loguru import logger

from core.state import LATEST_DATA, DATA_LOCK
from core.telemetry_cache import telemetry_cache
from services.event_service import EventService
from database.session import SessionLocal
from database.models.models import CameraEvent
from database.repositories.event_repository import EventRepository

router = APIRouter(tags=["System"])

@router.get("/telemetry", dependencies=[Depends(get_current_user)])
@router.get("/api/telemetry", dependencies=[Depends(get_current_user)])
def get_telemetry():
    """Returns the latest edge telemetry hardware stats."""
    return JSONResponse(content=telemetry_cache.get_all())

@router.get("/api/health")
def health_check():
    return {"status": "running", "active_cameras": list(LATEST_DATA.keys())}

@router.get("/api/debug/fire-state")
def debug_fire_state():
    cam_id = "10fba70c-7972-43f9-831c-6382396d4bba"
    data = LATEST_DATA.get(cam_id, {})
    return {
        "camera_id": cam_id,
        "data_keys": list(data.keys()),
        "events": data.get("events", {}),
        "cached_events": data.get("_cached_events", {}),
        "fps": data.get("fps"),
        "timestamp": data.get("timestamp")
    }

@router.get("/api/system/network-info")
def get_network_info():
    """Returns local LAN IP address so mobile devices can connect directly."""
    import socket
    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    return {"local_ip": ip, "default_url": f"http://{ip}:3000"}

@router.get("/events", dependencies=[Depends(get_current_user)])
def get_events(
    camera_id: str = None, 
    start_date: str = None, 
    end_date: str = None, 
    severity: str = None, 
    category: str = None
):
    """Returns the latest historical events from the database."""
    events = EventService.get_latest_events(
        camera_id=camera_id, 
        start_date=start_date, 
        end_date=end_date, 
        severity=severity, 
        category=category
    )
    return JSONResponse(content=events)

@router.get("/analytics/dashboard", dependencies=[Depends(get_current_user)])
def get_analytics_dashboard():
    stats = EventService.get_dashboard_stats(len(LATEST_DATA))
    return stats

class ManualEvent(BaseModel):
    camera_id: str
    event_type: str
    description: str
    
@router.post("/events/manual", dependencies=[Depends(get_current_user)])
def post_manual_event(event: ManualEvent):
    db = SessionLocal()
    try:
        repo = EventRepository(db)
        new_event = CameraEvent(
            camera_id=event.camera_id,
            events={
                "event_type": event.event_type,
                "description": event.description
            }
        )
        repo.add(new_event)
        return {"status": "success"}
    finally:
        db.close()

@router.get("/api/intrusions", dependencies=[Depends(get_current_user)])
def get_intrusions():
    """Returns historical intrusion events with snapshots from the DB."""
    db = SessionLocal()
    try:
        repo = EventRepository(db)
        events = repo.get_recent_events(limit=1000)
        
        intrusions = []
        for e in events:
            spatial_events = e.events.get("IntrusionDetectionPlugin", [])
            for event in spatial_events:
                if event.get("event_type") == "INTRUSION_DETECTED":
                    meta = event.get("metadata") or {}
                    # snapshot_path is always PRESENT but None on these events,
                    # so a dict .get() default never applies — "/" + None raised
                    # a TypeError and 500'd the whole endpoint.
                    snap = event.get("snapshot_path") or meta.get("snapshot_file")
                    intrusions.append({
                        "id": e.id,
                        "camera_id": e.camera_id,
                        "timestamp": e.timestamp.isoformat(),
                        "track_id": meta.get("track_id"),
                        "snapshot": ("/" + snap) if snap else None,
                        "zone": meta.get("zone"),
                        # Named zones and per-zone severity arrived with the
                        # restricted-zone module; /api/zones/events is the
                        # queryable log, this stays for existing callers.
                        "zone_id": meta.get("zone_id"),
                        "zone_name": meta.get("zone_name"),
                        "severity": meta.get("severity"),
                        "dwell_seconds": meta.get("dwell_seconds"),
                    })
                
        return {"intrusions": intrusions}
    finally:
        db.close()

@router.get("/report/pdf")
def get_report_pdf():
    # Dummy PDF endpoint
    return JSONResponse(content={"status": "not implemented"}, status_code=404)

@router.get("/api/system/ip", dependencies=[Depends(get_current_user)])
def get_system_ip():
    import socket
    try:
        # Create a dummy socket to determine the local IP used for outbound connections
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # We don't actually connect to 8.8.8.8, it just helps the OS determine the route
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        return {"ip": local_ip}
    except Exception as e:
        return {"ip": "127.0.0.1"}

# AI Agent Chat Endpoint
class ChatRequest(BaseModel):
    message: str
    camera_id: str = ""

@router.post("/api/chat", dependencies=[Depends(get_current_user)])
def chat_with_agent(req: ChatRequest):
    try:
        from agents.chat_agent import agent
        response = agent.chat(req.message, req.camera_id)
        return {"response": response}
    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return {"response": f"Sorry, I encountered an error: {str(e)}"}
