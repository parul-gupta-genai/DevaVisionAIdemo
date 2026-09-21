from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
import asyncio
import json

router = APIRouter(tags=["WebSockets"])

# Global state for connected websockets
connected_websockets = set()
_broadcaster_task = None

async def telemetry_broadcaster():
    """Background task to broadcast telemetry to all connected clients once per tick."""
    from core.state import LATEST_DATA, DATA_LOCK
    from fastapi.encoders import jsonable_encoder
    from core.utils import clean_numpy

    while True:
        try:
            if connected_websockets:
                with DATA_LOCK:
                    clean_data = {}
                    for cam, data in LATEST_DATA.items():
                        raw_dets = data.get("detections", [])
                        clean_dets = []
                        for d in raw_dets:
                            if hasattr(d, "bbox"):
                                clean_dets.append({
                                    "class_id": int(getattr(d, "class_id", 0)),
                                    "confidence": float(getattr(d, "confidence", 1.0)),
                                    "bbox": [float(b) for b in getattr(d, "bbox", [0,0,0,0])],
                                    "track_id": int(d.track_id) if getattr(d, "track_id", None) is not None else None
                                })
                            elif isinstance(d, dict):
                                clean_dets.append(d)

                        clean_data[cam] = {
                            "camera_id": data["camera_id"],
                            "timestamp": data["timestamp"],
                            "fps": data.get("fps", 0),
                            "latency_ms": data.get("latency_ms", 0),
                            "events": data.get("events", {}),
                            "detections": clean_dets
                        }

                safe_data = clean_numpy(clean_data)
                payload = json.dumps(jsonable_encoder({"type": "telemetry", "states": safe_data}))

                # Broadcast to all clients
                disconnected = set()
                for ws in connected_websockets:
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        disconnected.add(ws)

                for ws in disconnected:
                    connected_websockets.discard(ws)

            await asyncio.sleep(0.1)  # 10Hz tick
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in telemetry broadcaster: {e}")
            await asyncio.sleep(1)

def ensure_broadcaster_running():
    global _broadcaster_task
    if _broadcaster_task is None or _broadcaster_task.done():
        try:
            loop = asyncio.get_running_loop()
            _broadcaster_task = loop.create_task(telemetry_broadcaster())
            logger.info("Started WebSocket telemetry broadcaster task (10Hz).")
        except Exception as e:
            logger.error(f"Failed to start telemetry broadcaster: {e}")

@router.on_event("startup")
async def startup_event():
    ensure_broadcaster_running()

@router.on_event("shutdown")
async def shutdown_event():
    if _broadcaster_task:
        _broadcaster_task.cancel()

@router.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    """
    Push telemetry (fps, latency, events) to the frontend at 10Hz.
    Requires a valid access token passed as ?token=<jwt>.
    """
    from app.auth.security import decode_access_token

    if not token or decode_access_token(token) is None:
        # Policy violation per RFC 6455; browser clients will retry after re-login.
        await websocket.close(code=1008, reason="Invalid or missing token")
        return

    await websocket.accept()
    ensure_broadcaster_running()
    connected_websockets.add(websocket)
    logger.info(f"WebSocket Client Connected: {websocket.client}")

    try:
        while True:
            await websocket.receive_text() # keep alive
    except WebSocketDisconnect:
        logger.info(f"WebSocket Client Disconnected: {websocket.client}")
    except Exception as e:
        if "Cannot call" not in str(e):
            logger.error(f"WebSocket Error: {e}")
    finally:
        connected_websockets.discard(websocket)
