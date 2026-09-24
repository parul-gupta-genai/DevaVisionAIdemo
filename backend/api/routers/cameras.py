from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse, Response
from pydantic import BaseModel
import shutil
import os
import json
import time
import asyncio

from database.session import SessionLocal
from database.models.models import Camera
from database.repositories.camera_repository import CameraRepository
from config.config import redis_client, config
from app.auth.dependencies import get_current_user
# Still import camera_manager for legacy local pipelines if needed, but we prefer Redis now.
from core.camera_manager import camera_manager
from core.ffmpeg_manager import ffmpeg_manager

router = APIRouter(prefix="/api/cameras", tags=["Cameras"], dependencies=[Depends(get_current_user)])

class CameraInfo(BaseModel):
    name: str
    rtsp_url: str = None
    source_type: str = "rtsp"
    source: str = None
    edge_id: str = "edge-01"

class CameraControl(BaseModel):
    camera_id: str

class ViewerReport(BaseModel):
    """What the dashboard currently has on screen."""
    focused: list[str] = []   # expanded/selected camera — needs full framerate
    watched: list[str] = []   # visible grid tiles — reduced framerate is fine

def publish_redis_command(command: str, camera_id: str, edge_id: str, url: str = None):
    # Map command format to what DeepStreamMessageBroker expects
    action_map = {
        "start_camera": "start",
        "stop_camera": "stop"
    }
    payload = {
        "action": action_map.get(command, command),
        "camera_id": camera_id,
        "edge_id": edge_id
    }
    if url:
        payload["url"] = url
    redis_client.publish("camera_commands", json.dumps(payload))

# NOTE: Do NOT URL-encode RTSP credentials here.
# GStreamer's rtspsrc handles special characters (like @ in passwords) internally.
# Encoding them causes double-encoding and authentication failures.


def needs_ffmpeg_relay(source: str, source_type: str) -> bool:
    """
    True only for local video files, which are looped into MediaMTX by the
    ffmpeg relay. Live RTSP/HTTP sources are ingested directly by DeepStream —
    wrapping those in a relay breaks remote/tunneled cameras. Single source of
    truth so /start and /start-all can never drift apart again.
    """
    if not source:
        return False
    if source_type == 'video_file':
        return True
    return not source.startswith(('rtsp://', 'rtsps://', 'http://', 'https://'))


@router.get("")
@router.get("/")
def get_cameras():
    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        cameras = repo.get_all()
        result = []
        for cam in cameras:
            result.append({
                "id": cam.id,
                "name": cam.name,
                "rtsp_url": getattr(cam, 'rtsp_url', None) or getattr(cam, 'source', None),
                "source": getattr(cam, 'source', None) or getattr(cam, 'rtsp_url', None),
                "source_type": getattr(cam, 'source_type', 'rtsp'),
                "state": getattr(cam, 'state', 'STOPPED'),
                "edge_id": getattr(cam, 'edge_id', 'edge-01'),
                "active": getattr(cam, 'active', True)
            })
        return {"status": "success", "cameras": result}
    finally:
        db.close()

@router.post("")
def post_camera(camera: CameraInfo, background_tasks: BackgroundTasks):
    import uuid
    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        cam_id = str(uuid.uuid4())
        
        actual_source = camera.source if camera.source else camera.rtsp_url
        
        existing = repo.get_by_name(camera.name)
        if existing:
            cam_id = existing.id
            existing.rtsp_url = actual_source
            existing.source_type = camera.source_type
            existing.source = actual_source
            existing.edge_id = camera.edge_id
            db.commit()
        else:
            new_cam = Camera(
                id=cam_id,
                name=camera.name,
                rtsp_url=actual_source,
                source_type=camera.source_type,
                source=actual_source,
                active=True
            )
            new_cam.state = "STOPPED"
            new_cam.edge_id = camera.edge_id
            repo.add(new_cam)
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        db.close()
    cam_dict = camera.model_dump()
    cam_dict["id"] = cam_id
    return {"status": "success", "camera_id": cam_id, "camera": cam_dict}

@router.put("/{cam_id}")
def update_camera(cam_id: str, camera: CameraInfo, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        existing = repo.get_by_id(cam_id)
        if not existing:
            return JSONResponse(status_code=404, content={"status": "error", "message": "Camera not found"})
        
        actual_source = camera.source if camera.source else camera.rtsp_url
        
        existing.name = camera.name
        existing.rtsp_url = actual_source
        existing.source_type = camera.source_type
        existing.source = actual_source
        existing.edge_id = camera.edge_id
        db.commit()
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        db.close()
        
    return {"status": "success", "message": "Camera updated"}

@router.post("/start")
def start_camera(control: CameraControl, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        target_cam = repo.get_by_id(control.camera_id)
        if target_cam:
            # Idempotency check, but only trust the DB when the live pipeline
            # agrees — after a relay/pipeline crash the DB still says running
            # and an early return here makes the Start button a no-op.
            if getattr(target_cam, 'state', 'STOPPED') in ["Connecting/Offline", "Connected", "RUNNING"]:
                live_state = None
                try:
                    live_state = redis_client.get(f"camera_state:{target_cam.id}")
                except Exception:
                    pass
                if live_state == "Connected":
                    return {"status": "success", "message": "Camera is already starting or running."}

            target_cam.state = "Connecting/Offline"
            db.commit()
            
            source = getattr(target_cam, 'source', target_cam.rtsp_url)
            source_type = getattr(target_cam, 'source_type', 'rtsp')
            edge_id = getattr(target_cam, 'edge_id', 'edge-01')

            if needs_ffmpeg_relay(source, source_type):
                source = ffmpeg_manager.start_stream(target_cam.id, source)
                target_cam.state = "Running"
                try:
                    redis_client.set(f"camera_state:{target_cam.id}", "Running")
                except Exception:
                    pass
            else:
                target_cam.state = "Running"
                try:
                    redis_client.set(f"camera_state:{target_cam.id}", "Running")
                except Exception:
                    pass

            db.commit()
            publish_redis_command("start_camera", target_cam.id, edge_id, source)
            
            return {"status": "success", "message": "Camera start initiated on edge."}
        return JSONResponse(status_code=404, content={"status": "error", "message": "Camera not found"})
    finally:
        db.close()

@router.post("/stop")
def stop_camera(control: CameraControl, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        target_cam = repo.get_by_id(control.camera_id)
        if target_cam:
            target_cam.state = "STOPPED"
            db.commit()
            
            try:
                redis_client.set(f"camera_state:{target_cam.id}", "STOPPED")
            except Exception:
                pass
            
            ffmpeg_manager.stop_stream(target_cam.id)
            camera_manager.stop_camera_pipeline(target_cam.id)
                
            edge_id = getattr(target_cam, 'edge_id', 'edge-01')
            publish_redis_command("stop_camera", target_cam.id, edge_id)
            
            return {"status": "success", "message": "Camera stopped successfully."}
        return JSONResponse(status_code=404, content={"status": "error", "message": "Camera not found"})
    finally:
        db.close()

@router.delete("/{cam_id}")
def delete_camera(cam_id: str, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        target_cam = repo.get_by_id(cam_id)
        if target_cam:
            # Send stop command if running
            if getattr(target_cam, 'state', 'STOPPED') != "STOPPED":
                edge_id = getattr(target_cam, 'edge_id', 'edge-01')
                publish_redis_command("stop_camera", target_cam.id, edge_id)
            
            ffmpeg_manager.stop_stream(target_cam.id)
                
            db.delete(target_cam)
            db.commit()
            return {"status": "success", "message": "Camera deleted successfully."}
        return JSONResponse(status_code=404, content={"status": "error", "message": "Camera not found"})
    finally:
        db.close()

async def _batch_start_cameras(cameras):
    """
    Controlled concurrency logic to prevent blasting Redis simultaneously.

    Takes plain dicts, never ORM objects: this runs as a BackgroundTask after
    the request's session has committed (expiring every attribute) and closed
    (detaching the instances), so touching cam.source here would raise
    DetachedInstanceError.
    """
    for cam in cameras:
        source = cam["source"]
        source_type = cam["source_type"]

        if needs_ffmpeg_relay(source, source_type):
            source = ffmpeg_manager.start_stream(cam["id"], source)

        try:
            redis_client.set(f"camera_state:{cam['id']}", "Running")
        except Exception:
            pass

        publish_redis_command("start_camera", cam["id"], cam["edge_id"], source)
        await asyncio.sleep(0.05)  # 50ms pacing

@router.post("/start-all")
def start_all_cameras(background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        cameras = repo.get_active_cameras()
        
        starting = []
        for cam in cameras:
            cam.state = "Running"
            starting.append({
                "id": cam.id,
                "source": getattr(cam, 'source', None) or cam.rtsp_url,
                "source_type": getattr(cam, 'source_type', 'rtsp'),
                "edge_id": getattr(cam, 'edge_id', 'edge-01'),
            })

        db.commit()
        
        if starting:
            # Place in async queue to pace redis commands
            background_tasks.add_task(_batch_start_cameras, starting)
            
        return {"status": "success", "message": f"Start initiated for {len(starting)} cameras"}
    finally:
        db.close()

@router.post("/stop-all")
def stop_all_cameras(background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        cameras = repo.get_active_cameras()
        for cam in cameras:
            cam.state = "STOPPED"
            try:
                redis_client.set(f"camera_state:{cam.id}", "STOPPED")
            except Exception:
                pass
            
            ffmpeg_manager.stop_stream(cam.id)
            camera_manager.stop_camera_pipeline(cam.id)
                
            edge_id = getattr(cam, 'edge_id', 'edge-01')
            publish_redis_command("stop_camera", cam.id, edge_id)
        db.commit()
        return {"status": "success", "message": "Stop initiated for all cameras"}
    finally:
        db.close()

@router.post("/upload")
def upload_camera_video(file: UploadFile = File(...)):
    allowed_extensions = {".mp4", ".avi", ".mov", ".mkv"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Invalid file type. Only video files are allowed.")
    
    safe_filename = os.path.basename(file.filename)
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "videos")
    os.makedirs(upload_dir, exist_ok=True)
    target_path = os.path.join(upload_dir, safe_filename)
    
    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"status": "success", "file_path": target_path}

@router.get("")
def get_cameras():
    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        cameras = repo.get_active_cameras()
        return {
            "status": "success", 
            "cameras": [
                {
                    "id": c.id, 
                    "name": c.name, 
                    "rtsp_url": c.rtsp_url,
                    "source_type": getattr(c, 'source_type', 'rtsp'),
                    "source": getattr(c, 'source', c.rtsp_url),
                    "state": getattr(c, 'state', 'STOPPED'),
                    "edge_id": getattr(c, 'edge_id', 'edge-01')
                } for c in cameras
            ]
        }
    finally:
        db.close()

@router.post("/viewing")
def report_viewing(report: ViewerReport):
    payload = {
        "focused": [str(c) for c in report.focused][:64],
        "watched": [str(c) for c in report.watched][:64],
        "ts": time.time(),
    }
    try:
        redis_client.set("devavisionai:viewers", json.dumps(payload), ex=60)
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "message": str(e)})
    return {"status": "success", "focused": len(payload["focused"]), "watched": len(payload["watched"])}

@router.get("/status")
def get_cameras_status():
    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        cameras = repo.get_active_cameras()
        status = {}

        # Check MediaMTX active streams
        mediamtx_ready = set()
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:9997/v3/paths/list", headers={"User-Agent": "DevaVisionAI"})
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                data = json.loads(resp.read().decode())
                for item in data.get("items", []):
                    if item.get("ready"):
                        mediamtx_ready.add(item.get("name"))
        except Exception:
            pass

        for c in cameras:
            redis_state = None
            try:
                redis_state = redis_client.get(f"camera_state:{c.id}")
            except Exception:
                pass

            if redis_state:
                parsed = redis_state.decode() if isinstance(redis_state, bytes) else str(redis_state)
                if parsed.upper() == "STOPPED":
                    status[c.id] = "STOPPED"
                    continue

            if c.id in ffmpeg_manager.processes and ffmpeg_manager.processes[c.id]["process"].poll() is None:
                status[c.id] = "Running"
                continue

            if f"raw_{c.id}" in mediamtx_ready or c.id in mediamtx_ready:
                status[c.id] = "Running"
                continue

            if redis_state:
                status[c.id] = redis_state.decode() if isinstance(redis_state, bytes) else str(redis_state)
            else:
                status[c.id] = getattr(c, 'state', 'STOPPED')
        return status
    finally:
        db.close()


def _generate_mjpeg_frames(camera_id: str):
    import cv2

    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        cam = repo.get_by_id(camera_id)
        if not cam:
            return
        src = getattr(cam, 'source', None) or getattr(cam, 'rtsp_url', None) or "0"
    finally:
        db.close()

    if str(src).isdigit():
        src = int(src)
    elif isinstance(src, str):
        src = src.strip("\"'")
        if src.startswith("file://"):
            src = src[7:]
        if not src.startswith("http://") and not src.startswith("https://") and not src.startswith("rtsp://"):
            if not os.path.exists(src):
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                candidates = [
                    os.path.join(base_dir, "sample_videos", os.path.basename(src)),
                    os.path.join(base_dir, "sample_videos", "bucket11.mp4"),
                    os.path.join(base_dir, "backend", "uploads", os.path.basename(src)),
                ]
                for cand in candidates:
                    if os.path.exists(cand):
                        src = cand
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

@router.get("/{cam_id}/stream")
def get_camera_stream(cam_id: str):
    return StreamingResponse(
        _generate_mjpeg_frames(cam_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@router.get("/{cam_id}/snapshot")
def get_camera_snapshot(cam_id: str):
    import cv2

    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        cam = repo.get_by_id(cam_id)
        if not cam:
            return Response(status_code=404)
        src = getattr(cam, 'source', None) or getattr(cam, 'rtsp_url', None) or "0"
    finally:
        db.close()

    if str(src).isdigit():
        src = int(src)
    elif isinstance(src, str):
        src = src.strip("\"'")
        if src.startswith("file://"):
            src = src[7:]
        if not src.startswith("http://") and not src.startswith("https://") and not src.startswith("rtsp://"):
            if not os.path.exists(src):
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                candidates = [
                    os.path.join(base_dir, "sample_videos", os.path.basename(src)),
                    os.path.join(base_dir, "sample_videos", "bucket11.mp4"),
                ]
                for cand in candidates:
                    if os.path.exists(cand):
                        src = cand
                        break

    cap = cv2.VideoCapture(src)
    ret, frame = cap.read()
    cap.release()
    if ret:
        _, buffer = cv2.imencode('.jpg', frame)
        return Response(content=buffer.tobytes(), media_type="image/jpeg")
    return Response(status_code=404)


