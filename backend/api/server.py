import os
import threading
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from api.limiter import limiter
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool
import time
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
from cache import get_cached_response, set_cached_response
from gpu_utils import get_backend, get_status

from app.plugins.parking.router import parking_router
from app.plugins.attendance.router import attendance_router
from app.plugins.fire.router import fire_router
from app.plugins.fight.router import fight_router
from app.plugins.visitor.router import router as visitor_router
from app.plugins.anpr.router import router as anpr_router
from app.plugins.face.router import face_router
from app.plugins.ppe.router import ppe_router
from app.plugins.material.router import material_router
from app.plugins.zones.router import zones_router
from app.plugins.visitor.vms_router import vms_router
from app.auth.routes import router as auth_router
from app.auth.admin_routes import admin_router
from app.config_routes import config_router
from app.tts_routes import router as tts_router
from app.alert_routes import alerts_router
from app.provider_routes import router as provider_router, customer_router
from voice.api.routes import voice_router


# Import our new focused routers
from api.routers.cameras import router as cameras_router
from api.routers.websockets import router as websockets_router
from api.routers.system import router as system_router

# Seconds between successive camera start commands on resume. Tunable via
# env because the safe value scales with how heavy each camera's pipeline is.
RESUME_STAGGER_SEC = float(os.getenv("RESUME_STAGGER_SEC", "1.5"))

# Serialises resume runs. Startup and the ds_status listener can both call
# this, and two concurrent staggers interleave — landing two adds at once and
# reproducing the very burst the stagger exists to prevent.
_resume_lock = threading.Lock()


def resume_active_cameras():
    """(Re-)publishes start commands for all active cameras in the database.

    Called at startup and again whenever DeepStream announces itself ready on
    devavisionai:ds_status — the pipeline process may start listening after our
    startup publishes, which would otherwise silently drop every camera.
    """
    from loguru import logger
    from database.session import SessionLocal
    from database.repositories.camera_repository import CameraRepository
    from core.ffmpeg_manager import ffmpeg_manager
    from api.routers.cameras import publish_redis_command, needs_ffmpeg_relay

    if not _resume_lock.acquire(blocking=False):
        logger.info("Camera resume already in progress; skipping this request.")
        return
    db = SessionLocal()
    try:
        repo = CameraRepository(db)
        cameras = repo.get_active_cameras()
        logger.info(f"Resuming {len(cameras)} active cameras from database.")

        for cam in cameras:
            if getattr(cam, 'active', True) and getattr(cam, 'state', 'STOPPED') in ['Running', 'RUNNING']:
                logger.info(f"Auto-resuming active camera stream: {cam.name} ({cam.id})")
                source = getattr(cam, 'source', cam.rtsp_url)
                source_type = getattr(cam, 'source_type', 'rtsp')
                edge_id = getattr(cam, 'edge_id', 'edge-01')

                # Same rule as /start and /start-all — a third divergent copy
                # of this test is how RTSP cameras ended up wrongly relayed.
                if needs_ffmpeg_relay(source, source_type):
                    if source.startswith("/home/use/"):
                        source = source.replace("/home/use/", "/home/user/")
                    clean_path = source.replace("file://", "").strip("\"'")
                    if not os.path.exists(clean_path):
                        logger.warning(f"Skipping camera '{cam.name}' ({cam.id}): video file does not exist at '{clean_path}'")
                        cam.state = "STOPPED"
                        continue
                    source = ffmpeg_manager.start_stream(cam.id, source)

                cam.state = "Running"
                try:
                    import redis
                    r = redis.Redis.from_url(redis_url)
                    r.set(f"camera_state:{cam.id}", "Running")
                except Exception:
                    pass
                publish_redis_command("start_camera", cam.id, edge_id, source)
                # Pace the resume.
                time.sleep(RESUME_STAGGER_SEC)
            else:
                cam.state = "STOPPED"

        db.commit()
    except Exception as e:
        from loguru import logger
        logger.error(f"Failed to resume cameras: {e}")
    finally:
        db.close()
        _resume_lock.release()


def ds_ready_listener():
    """Blocks on devavisionai:ds_status; re-syncs cameras each time DS restarts."""
    import redis
    from loguru import logger
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    while True:
        try:
            r = redis.Redis.from_url(redis_url)
            pubsub = r.pubsub()
            pubsub.subscribe("devavisionai:ds_status")
            for message in pubsub.listen():
                if message.get("type") == "message":
                    logger.info("DeepStream announced ready — re-syncing active cameras.")
                    resume_active_cameras()
        except Exception as e:
            if "ConnectionError" in type(e).__name__ or "10061" in str(e):
                logger.debug(f"Redis offline for DS ready listener (retrying in 5s): {e}")
                time.sleep(5.0)
            else:
                logger.error(f"DS ready listener failed: {e}")
                time.sleep(1.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import threading
    from loguru import logger
    from core.camera_manager import camera_manager
    from config.config import config
    from database.persistence import DatabaseWorker
    from main import event_loop
    
    logger.info("Starting up FastAPI application and Camera Manager...")
    
    # 0. Ensure Database Tables exist
    try:
        from database.session import engine, Base
        import database.models.models
        import database.models.auth
        import app.plugins.visitor.models
        import app.plugins.anpr.models
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema verified and created.")
    except Exception as exc:
        logger.warning(f"Database schema auto-creation note: {exc}")

    # 1. Start Database Worker
    db_worker = DatabaseWorker()
    db_worker.start()
    
    # 2. Start global event loop thread
    import queue
    result_queue = queue.Queue(maxsize=100)
    loop_thread = threading.Thread(target=event_loop, args=(result_queue,), daemon=True, name="EventLoop")
    loop_thread.start()
    
    # 2.5 Start DeepStream Consumer thread
    from main import ds_consumer
    ds_thread = threading.Thread(target=ds_consumer, args=(result_queue,), daemon=True, name="DSConsumer")
    ds_thread.start()

    # 2.6 Start edge telemetry (publisher + consumer). Started here, not in
    # main.py's __main__ block, because production launches via `uvicorn main:app`.
    from main import telemetry_consumer
    from core.telemetry_publisher import start_telemetry_publisher
    threading.Thread(target=telemetry_consumer, daemon=True, name="TelemetryConsumer").start()
    start_telemetry_publisher()
    
    # 3. Start Camera Manager Command Listener & Global Workers
    camera_manager.start_command_listener(result_queue)
    camera_manager.start_global_workers()
    camera_manager.start_all_active_cameras()

    # 3.1 Start WebSocket telemetry broadcaster task
    from api.routers.websockets import ensure_broadcaster_running
    ensure_broadcaster_running()

    # 3.5 Seed the face module's RBAC scopes. The permission tables existed
    # but nothing outside the tests ever populated them, so require_permissions
    # had nothing to check and every role was equivalent. Idempotent.
    try:
        from database.session import SessionLocal as _Session
        from app.plugins.face.permissions import seed_permissions
        from app.plugins.anpr.permissions import seed_permissions as seed_anpr
        _s = _Session()
        try:
            # Face first: it creates the roles the ANPR scopes attach to.
            seed_permissions(_s)
            seed_anpr(_s)
            from app.plugins.ppe.permissions import seed_permissions as seed_ppe
            seed_ppe(_s)
            from app.plugins.zones.permissions import seed_permissions as seed_zones
            seed_zones(_s)
            from app.plugins.fire.permissions import seed_permissions as seed_fire
            seed_fire(_s)
            from app.plugins.fight.permissions import seed_permissions as seed_fight
            seed_fight(_s)

            # Say out loud how many cameras have restricted-zone monitoring
            # switched on but no zone drawn. Those cameras watch nothing, and
            # the previous behaviour — a built-in polygon across the middle of
            # every frame — hid that by alerting on all of them. Silence is
            # the correct outcome now, but it must not be a silent one.
            try:
                from app.plugins.zones.repository import ZoneRepository
                covered = set(ZoneRepository(_s).cameras_with_zones())
                enabled = [
                    cam for cam, plugins in (config.CAMERA_PLUGINS or {}).items()
                    if any(p in (plugins or []) for p in
                           ("IntrusionDetectionPlugin", "RestrictionZonePlugin"))
                ]
                missing = [c for c in enabled if c not in covered]
                if missing:
                    logger.warning(
                        f"Restricted zones: {len(missing)} of {len(enabled)} "
                        f"zone-enabled cameras have no zone defined and are "
                        f"monitoring nothing. Draw zones in Live Cameras, or "
                        f"see GET /api/zones/coverage."
                    )
                else:
                    logger.info(
                        f"Restricted zones: {len(covered)} camera(s) covered.")
            except Exception as exc:
                logger.warning(f"Could not report zone coverage: {exc}")

            # The mirror image for fire. A fire-enabled camera with no zone
            # drawn is NOT unwatched — it watches its whole frame, because
            # fire is meaningful wherever it appears — so this reports what
            # is being watched rather than what is being missed. It is worth
            # saying out loud either way: whole-frame monitoring is the state
            # most likely to raise a false alarm from a welding bay or a
            # sodium lamp, and an exclusion zone is the fix.
            try:
                from app.plugins.fire.repository import FireZoneRepository
                zoned = set(FireZoneRepository(_s).cameras_with_zones())
                fire_on = [
                    cam for cam, plugins in (config.CAMERA_PLUGINS or {}).items()
                    if "FireDetectionPlugin" in (plugins or [])
                ]
                whole = [c for c in fire_on if c not in zoned]
                if fire_on:
                    logger.info(
                        f"Fire & smoke: {len(fire_on)} camera(s) enabled — "
                        f"{len(zoned & set(fire_on))} with zones, {len(whole)} "
                        f"watching the whole frame. See GET /api/fire/coverage."
                    )
                    logger.info(
                        "Fire & smoke detection is an AI visual early-warning "
                        "aid and does not replace statutory fire detection, "
                        "alarm or suppression systems."
                    )
            except Exception as exc:
                logger.warning(f"Could not report fire coverage: {exc}")

            # SOW 2.7 requires the Contractor to communicate clearly that
            # fight detection is an aid. Saying it once at startup, in the
            # log an integrator actually reads, is part of that.
            try:
                from app.plugins.fight.repository import FightZoneRepository
                zoned = set(FightZoneRepository(_s).cameras_with_zones())
                on = [cam for cam, plugins in (config.CAMERA_PLUGINS or {}).items()
                      if "FightDetectionPlugin" in (plugins or [])]
                if on:
                    logger.info(
                        f"Fight/quarrel analytics: {len(on)} camera(s) enabled — "
                        f"{len(zoned & set(on))} with zones, "
                        f"{len([c for c in on if c not in zoned])} watching the "
                        f"whole frame. See GET /api/fight/coverage."
                    )
                    logger.info(
                        "Fight/quarrel detection is an automated visual "
                        "analytics aid. Indications require human verification "
                        "and do not replace human security intervention."
                    )
            except Exception as exc:
                logger.warning(f"Could not report fight coverage: {exc}")
        finally:
            _s.close()
    except Exception as exc:
        logger.warning(f"Face permission seeding skipped: {exc}")

    # 4. Load active cameras from Database (and re-sync whenever DeepStream
    # (re)starts and announces itself ready)
    # Off the event loop: resume_active_cameras staggers its start commands
    # with time.sleep, so calling it inline held the lifespan coroutine for
    # cameras x RESUME_STAGGER_SEC (27s at 18 cameras, 37s at 25) during which
    # uvicorn accepted no connections at all — no health check, no login, no
    # websocket — and the DB session held an uncommitted transaction the whole
    # time. The listener is started FIRST so a ds_status announcement arriving
    # during the stagger is not missed.
    ds_listener_thread = threading.Thread(target=ds_ready_listener, daemon=True, name="DSReadyListener")
    ds_listener_thread.start()
    threading.Thread(target=resume_active_cameras, daemon=True, name="ResumeCameras").start()

    yield
    
    logger.info("Initiating graceful shutdown of all camera pipelines...")
    
    # Get all active camera IDs
    active_cameras = list(camera_manager.running_cameras.keys())
    for cam_id in active_cameras:
        logger.info(f"Stopping pipeline for {cam_id} during shutdown...")
        camera_manager.stop_camera_pipeline(cam_id)
        
    logger.info("All pipelines stopped. Releasing global resources...")
    camera_manager.stop_global_workers()
    logger.info("Shutdown complete.")

app = FastAPI(title="DevaVision AI Enterprise API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from api.routers.command_center import router as command_center_router

# Core system routes
app.include_router(system_router)
app.include_router(cameras_router)
app.include_router(websockets_router)
app.include_router(command_center_router)

# Auth and config routes
app.include_router(auth_router)
app.include_router(auth_router, prefix="/api")
app.include_router(admin_router)
app.include_router(config_router)
app.include_router(alerts_router)

# Plugin routes
app.include_router(parking_router)
app.include_router(attendance_router)
app.include_router(fire_router)
app.include_router(fight_router)
app.include_router(visitor_router, prefix="/api/plugins")
app.include_router(anpr_router, prefix="/api/plugins")
app.include_router(face_router)
app.include_router(ppe_router)
app.include_router(material_router)
app.include_router(vms_router)
app.include_router(zones_router)
app.include_router(voice_router)
app.include_router(tts_router)
app.include_router(provider_router)
app.include_router(customer_router)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

snapshots_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "snapshots"))
os.makedirs(snapshots_dir, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=snapshots_dir), name="snapshots")

uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

videos_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "videos"))
os.makedirs(videos_dir, exist_ok=True)
app.mount("/videos", StaticFiles(directory=videos_dir), name="videos")

# WebRTC / WHEP Stream Handlers
@app.options("/webrtc-stream/{path:path}")
async def whep_options(path: str):
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
    import urllib.request
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
        return Response(status_code=503, content=b"MediaMTX stream unavailable")

frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
else:
    print(f"Warning: Frontend dist directory not found at {frontend_dist}. UI will not be served natively.")

