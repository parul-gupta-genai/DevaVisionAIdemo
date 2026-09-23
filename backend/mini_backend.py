import os
import time
import json
import uuid
import asyncio
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

# Initialize FastAPI App
app = FastAPI(title="DevaVisionAI Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared In-Memory Camera and Event State
CAMERAS_DB: Dict[str, dict] = {}

EVENTS_LOG: List[dict] = []

ADMIN_USER = {
    "id": 1,
    "email": "gauriirajpoot@gmail.com",
    "name": "Admin User",
    "role": "super_admin",
    "roles": ["super_admin", "admin"],
    "permissions": ["*", "settings:read", "settings:write", "users:read", "users:write",
                    "cameras:read", "cameras:write", "analytics:read", "plugins:read",
                    "plugins:write", "system:admin"],
    "is_active": True,
    "is_superuser": True,
    "is_admin": True
}


# Schemas
class LoginRequest(BaseModel):
    email: str
    password: str

class CameraCreateRequest(BaseModel):
    name: str
    rtsp_url: Optional[str] = "0"
    source: Optional[str] = "0"
    source_type: Optional[str] = "webcam"
    active: Optional[bool] = True
    plugins: Optional[List[str]] = ["fire", "smoke"]


# Authentication Routes
@app.post("/auth/login")
def login(req: LoginRequest):
    return {"access_token": "demo-admin-token", "token_type": "bearer", "user": ADMIN_USER}

@app.get("/auth/me")
def me(): return ADMIN_USER

@app.get("/users/me")
def users_me(): return ADMIN_USER

@app.get("/users")
def users(): return [ADMIN_USER]

@app.get("/roles")
def roles(): return [{"id": 1, "name": "super_admin", "permissions": ["*"]}]


# Telemetry Endpoints
@app.get("/telemetry")
@app.get("/api/telemetry")
def get_telemetry():
    return JSONResponse(content={
        "cpu_usage": 18.5,
        "memory_usage": 42.1,
        "gpu_usage": 0.0,
        "temperature": 45.0,
        "fps": 29.8,
        "active_cameras": len(CAMERAS_DB),
        "timestamp": time.time()
    })

@app.get("/api/health")
def health_check():
    return {"status": "running", "active_cameras": list(CAMERAS_DB.keys())}


# Cameras CRUD & Status
@app.get("/api/cameras")
@app.get("/cameras")
def get_cameras():
    cams = list(CAMERAS_DB.values())
    return {
        "status": "success",
        "cameras": cams,
        "total": len(cams)
    }

@app.post("/api/cameras")
@app.post("/cameras")
def create_camera(req: CameraCreateRequest):
    cam_id = f"cam-{str(uuid.uuid4())[:8]}"
    cam_data = {
        "id": cam_id,
        "name": req.name,
        "rtsp_url": req.rtsp_url or req.source or "0",
        "source": req.source or req.rtsp_url or "0",
        "source_type": req.source_type or "webcam",
        "active": req.active if req.active is not None else True,
        "status": "RUNNING",
        "fps": 30,
        "plugins": req.plugins or ["fire", "smoke"]
    }
    CAMERAS_DB[cam_id] = cam_data
    return {
        **cam_data,
        "status": "success",
        "camera_id": cam_id,
        "state": "RUNNING"
    }

@app.put("/api/cameras/{camera_id}")
@app.put("/cameras/{camera_id}")
def update_camera(camera_id: str, req: CameraCreateRequest):
    if camera_id in CAMERAS_DB:
        CAMERAS_DB[camera_id].update({
            "name": req.name,
            "rtsp_url": req.rtsp_url or req.source or CAMERAS_DB[camera_id].get("rtsp_url"),
            "source": req.source or req.rtsp_url or CAMERAS_DB[camera_id].get("source"),
            "source_type": req.source_type or CAMERAS_DB[camera_id].get("source_type", "webcam"),
        })
        return {"status": "success", "camera": CAMERAS_DB[camera_id]}
    raise HTTPException(status_code=404, detail="Camera not found")

@app.post("/api/cameras/start")
@app.post("/cameras/start")
def start_camera(payload: dict):
    cam_id = payload.get("camera_id")
    if cam_id in CAMERAS_DB:
        CAMERAS_DB[cam_id]["status"] = "RUNNING"
        CAMERAS_DB[cam_id]["active"] = True
        return {"status": "success", "state": "RUNNING"}
    return {"status": "success"}

@app.post("/api/cameras/stop")
@app.post("/cameras/stop")
def stop_camera(payload: dict):
    cam_id = payload.get("camera_id")
    if cam_id in CAMERAS_DB:
        CAMERAS_DB[cam_id]["status"] = "STOPPED"
        CAMERAS_DB[cam_id]["active"] = False
        return {"status": "success", "state": "STOPPED"}
    return {"status": "success"}

@app.post("/api/cameras/start-all")
@app.post("/cameras/start-all")
def start_all_cameras():
    for c in CAMERAS_DB.values():
        c["status"] = "RUNNING"
        c["active"] = True
    return {"status": "success"}

@app.post("/api/cameras/stop-all")
@app.post("/cameras/stop-all")
def stop_all_cameras():
    for c in CAMERAS_DB.values():
        c["status"] = "STOPPED"
        c["active"] = False
    return {"status": "success"}

@app.post("/api/cameras/upload")
@app.post("/cameras/upload")
async def upload_camera_file(request: Request):
    from fastapi import UploadFile
    form = await request.form()
    file = form.get("file")
    upload_dir = Path(__file__).resolve().parent / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    if hasattr(file, "filename") and hasattr(file, "read"):
        file_path = upload_dir / file.filename
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        return {"status": "success", "file_path": str(file_path)}
    return {"status": "success", "file_path": "0"}

@app.get("/api/cameras/active")
@app.get("/cameras/active")
def active_cameras():
    return [c for c in CAMERAS_DB.values() if c.get("active", True)]

@app.get("/api/cameras/status")
@app.get("/cameras/status")
def cameras_status():
    return {cid: c.get("status", "RUNNING") for cid, c in CAMERAS_DB.items()}

@app.delete("/api/cameras/{camera_id}")
@app.delete("/cameras/{camera_id}")
def delete_camera(camera_id: str):
    if camera_id in CAMERAS_DB:
        del CAMERAS_DB[camera_id]
        return {"status": "deleted", "id": camera_id}
    raise HTTPException(status_code=404, detail="Camera not found")

def generate_camera_frames(camera_id: str):
    import cv2
    cam = CAMERAS_DB.get(camera_id, {})
    src = cam.get("source") or cam.get("rtsp_url") or "0"
    if str(src).isdigit():
        src = int(src)
    
    # Auto-fallback to local test video if path not found
    if isinstance(src, str) and not os.path.exists(src):
        for candidate in [r"C:\Users\Praveen\Downloads\anpr.mp4", r"C:\Users\Praveen\Downloads\fight.mp4", r"C:\Users\Praveen\Downloads\ppe.mp4"]:
            if os.path.exists(candidate):
                src = candidate
                break
                
    cap = cv2.VideoCapture(src)
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1)
                    continue
            
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.033)
    finally:
        cap.release()

@app.get("/api/cameras/{camera_id}/stream")
@app.get("/cameras/{camera_id}/stream")
def camera_mjpeg_stream(camera_id: str):
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        generate_camera_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/api/cameras/{camera_id}/snapshot")
@app.get("/cameras/{camera_id}/snapshot")
def camera_snapshot(camera_id: str):
    import cv2
    from fastapi import Response
    cam = CAMERAS_DB.get(camera_id, {})
    src = cam.get("source") or cam.get("rtsp_url") or "0"
    if str(src).isdigit(): src = int(src)
    cap = cv2.VideoCapture(src)
    ret, frame = cap.read()
    cap.release()
    if ret:
        _, buffer = cv2.imencode('.jpg', frame)
        return Response(content=buffer.tobytes(), media_type="image/jpeg")
    return Response(status_code=404)

ZONES_DB: Dict[str, dict] = {}
CONFIG_DB: Dict[str, Any] = {"COUNTING_LINES": {}}

# Zones & ROI Endpoints
@app.get("/api/zones")
@app.get("/zones")
def get_zones(camera_id: Optional[str] = None):
    items = list(ZONES_DB.values())
    if camera_id:
        items = [z for z in items if z.get("camera_id") == camera_id]
    return items

@app.post("/api/zones")
@app.post("/zones")
def create_zone(payload: dict):
    zone_id = payload.get("zone_id") or f"zone-{str(uuid.uuid4())[:8]}"
    zone_data = {
        "zone_id": zone_id,
        "camera_id": payload.get("camera_id", "cam-1"),
        "name": payload.get("name", "Restricted Area"),
        "points": payload.get("points", []),
        "is_active": payload.get("is_active", True),
        "object_classes": payload.get("object_classes", [0]),
        "class_names": payload.get("class_names", ["person"]),
        "min_confidence": payload.get("min_confidence", 0.5),
        "anchor": payload.get("anchor", "bottom_center"),
        "min_box_px": payload.get("min_box_px", 30),
        "schedule": payload.get("schedule", None),
        "schedule_text": payload.get("schedule_text", "Always armed"),
        "armed_now": True,
        "min_dwell_sec": payload.get("min_dwell_sec", 0),
        "loiter_sec": payload.get("loiter_sec", None),
        "exit_grace_sec": payload.get("exit_grace_sec", 2),
        "alert_cooldown_sec": payload.get("alert_cooldown_sec", 15),
        "severity": payload.get("severity", "critical"),
        "notes": payload.get("notes", "")
    }
    ZONES_DB[zone_id] = zone_data
    return zone_data

@app.put("/api/zones/{zone_id}")
@app.put("/zones/{zone_id}")
def update_zone(zone_id: str, payload: dict):
    if zone_id in ZONES_DB:
        ZONES_DB[zone_id].update(payload)
        return ZONES_DB[zone_id]
    raise HTTPException(status_code=404, detail="Zone not found")

@app.delete("/api/zones/{zone_id}")
@app.delete("/zones/{zone_id}")
def delete_zone(zone_id: str):
    if zone_id in ZONES_DB:
        del ZONES_DB[zone_id]
        return {"status": "deleted", "zone_id": zone_id}
    raise HTTPException(status_code=404, detail="Zone not found")

@app.get("/api/zones/events")
@app.get("/zones/events")
def get_zone_events(camera_id: Optional[str] = None):
    return {"items": [], "total": 0}

@app.get("/api/zones/coverage")
@app.get("/zones/coverage")
def get_zone_coverage():
    return {
        "cameras_with_plugin": len(CAMERAS_DB),
        "cameras_with_zones": len(set(z.get("camera_id") for z in ZONES_DB.values())),
        "cameras_missing_zones": [],
        "total_zones": len(ZONES_DB),
        "armed_now": len([z for z in ZONES_DB.values() if z.get("is_active", True)]),
        "legacy_config_cameras": []
    }

@app.post("/api/config")
@app.post("/config")
def save_config(payload: dict):
    updates = payload.get("updates", {})
    if "COUNTING_LINES" in updates:
        for cid, lines in updates["COUNTING_LINES"].items():
            CONFIG_DB["COUNTING_LINES"][cid] = lines
    return {"status": "success", "message": "Configuration saved successfully"}


# Events & Analytics
@app.get("/api/events")
@app.get("/events")
def get_events():
    return {"items": EVENTS_LOG, "total": len(EVENTS_LOG)}

@app.get("/analytics/summary")
def analytics_summary():
    return {
        "total_events": len(EVENTS_LOG),
        "active_cameras": len(CAMERAS_DB),
        "alerts_today": sum(1 for e in EVENTS_LOG if e.get("severity") in ["HIGH", "CRITICAL"])
    }

@app.get("/api/plugins")
def get_plugins():
    return [
        {"id": "fire", "name": "Fire & Smoke Detection", "active": True, "model": "fire_yolo.pt", "status": "loaded"},
        {"id": "anpr", "name": "ANPR & Vehicle OCR", "active": True, "model": "anpr_yolo.pt", "status": "loaded"},
        {"id": "fight", "name": "Fight Detection", "active": False, "status": "standby"},
        {"id": "ppe", "name": "PPE & Helmet Detection", "active": True, "status": "loaded"}
    ]

@app.get("/api/settings")
@app.get("/api/config")
@app.get("/config")
def get_settings():
    return {
        "theme": "dark",
        "notifications_enabled": True,
        "alert_email": "admin@devavision.ai",
        "ai_engine": "DevaVisionAI Edge",
        "telemetry_interval_sec": 2.0,
        "COUNTING_LINES": CONFIG_DB.get("COUNTING_LINES", {}),
        "plugins": {
            "fire": {"enabled": True, "model": "fire_yolo.pt", "confidence": 0.25},
            "smoke": {"enabled": True, "model": "fire_yolo.pt", "confidence": 0.18}
        }
    }

@app.get("/favicon.ico")
def favicon():
    return JSONResponse(content={})

@app.get("/api/system/info")
def system_info():
    return {"version": "2.0.0", "status": "running", "engine": "DevaVisionAI Edge Engine"}

@app.get("/api/system/network-info")
def network_info():
    return {"local_ip": "127.0.0.1", "default_url": "http://127.0.0.1:8000"}


# WebRTC / WHEP Stream Handlers
@app.options("/webrtc-stream/{path:path}")
async def whep_options(path: str):
    from fastapi import Response
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS, PATCH, DELETE",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Expose-Headers": "Location",
            "Accept-Post": "application/sdp"
        }
    )

@app.post("/webrtc-stream/{path:path}")
@app.patch("/webrtc-stream/{path:path}")
@app.delete("/webrtc-stream/{path:path}")
async def whep_proxy(path: str, request: Request):
    from fastapi import Response
    import urllib.request
    
    # Try proxying to local MediaMTX WebRTC server (port 8889)
    body = await request.body()
    mediamtx_url = f"http://127.0.0.1:8889/{path}"
    try:
        req = urllib.request.Request(
            mediamtx_url,
            data=body if request.method in ["POST", "PATCH"] else None,
            headers={k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]},
            method=request.method
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            resp_body = resp.read()
            resp_headers = dict(resp.headers)
            resp_headers["Access-Control-Allow-Origin"] = "*"
            return Response(
                content=resp_body,
                status_code=resp.status,
                headers=resp_headers,
                media_type=resp.headers.get("content-type", "application/sdp")
            )
    except Exception:
        # MediaMTX not publishing this stream yet — return clean status without 405
        return Response(
            content=b"",
            status_code=404,
            headers={"Access-Control-Allow-Origin": "*", "Content-Type": "text/plain"}
        )


# WebSocket Connections Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()


@app.websocket("/ws")
@app.websocket("/ws/{client_id}")
@app.websocket("/api/ws")
@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket, client_id: Optional[str] = None):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Broadcast telemetry & ping updates
            telemetry_payload = {
                "type": "telemetry",
                "cpu_usage": 18.5,
                "memory_usage": 42.1,
                "active_cameras": len(CAMERAS_DB),
                "timestamp": time.time()
            }
            await websocket.send_json(telemetry_payload)
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# Frontend Static Files Mount
dist_candidates = [
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"),
    os.path.join(os.path.dirname(__file__), "frontend", "dist"),
    os.path.abspath("frontend/dist"),
    os.path.abspath("../frontend/dist")
]

mounted = False
for candidate in dist_candidates:
    if os.path.exists(candidate) and os.path.isdir(candidate):
        app.mount("/", StaticFiles(directory=candidate, html=True), name="static")
        print(f"Mounted frontend dist from: {candidate}")
        mounted = True
        break

if not mounted:
    @app.get("/")
    def index():
        return {"status": "DevaVisionAI Backend Running", "message": "Frontend build not detected in frontend/dist"}
