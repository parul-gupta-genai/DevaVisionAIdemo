import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
import threading
import queue
import time
from loguru import logger

from config.config import config
try:
    from core.events.bus import RedisEventBus
except ImportError:
    class RedisEventBus:
        def __init__(self, *args, **kwargs):
            pass
        def publish(self, *args, **kwargs):
            pass
from api.server import app  # Required for uvicorn main:app

def ds_consumer(result_queue: queue.Queue):
    """Listens to DeepStream inference results via Redis."""
    import redis
    import json
    from app.engine.base import NormalizedDetection

    logger.info("Started DeepStream consumer loop.")
    while True:
        try:
            redis_client = redis.Redis.from_url(config.REDIS_URL)
            pubsub = redis_client.pubsub()
            pubsub.subscribe("inference_result_ds")

            for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        ds_data = json.loads(message["data"])
                        camera_id = ds_data.get("camera_id") or ds_data.get("sensor", {}).get("id", "camera1")
                        events = ds_data.get("events") or {}

                        raw_dets = ds_data.get("detections", [])
                        detections = [
                            NormalizedDetection(
                                class_id=int(d.get("class_id", 0)),
                                confidence=float(d.get("confidence", 1.0)),
                                bbox=[float(b) for b in d.get("bbox", [0, 0, 0, 0])],
                                track_id=int(d["track_id"]) if d.get("track_id") is not None else None
                            )
                            for d in raw_dets
                        ]

                        packet = {
                            "camera_id": camera_id,
                            "frame": None,
                            "detections": detections,
                            "events": events,
                            "fps": float(ds_data.get("fps", 30.0)),
                            "latency_ms": 0,
                            "timestamp": float(ds_data.get("timestamp", time.time()))
                        }
                        
                        if result_queue.full():
                            try:
                                result_queue.get_nowait()
                            except queue.Empty:
                                pass
                        result_queue.put_nowait(packet)
                    except Exception as e:
                        logger.error(f"Error parsing DeepStream message: {e}")
        except Exception as e:
            if "ConnectionError" in type(e).__name__ or "10061" in str(e):
                logger.debug(f"Redis offline for DeepStream consumer (retrying in 5s): {e}")
                time.sleep(5.0)
            else:
                logger.error(f"DeepStream consumer error: {e}")
                time.sleep(1.0)

def event_loop(result_queue: queue.Queue):
    """Pulls results from all cameras, updates API state, and forwards actionable events to Redis."""
    from core.state import update_global_state
    from fastapi.encoders import jsonable_encoder
    import json
    logger.info("Started global event loop (Redis Publisher).")
    
    # Single RedisEventBus instance — avoid creating a new connection per event
    event_bus = RedisEventBus(config.REDIS_URL)
    
    while True:
        try:
            packet = result_queue.get(timeout=1.0)
            
            # 1. Update API state
            update_global_state(packet)
            
            # 2. Forward to Database worker via Redis
            if packet.get("events"):
                ignored_redis_events = {None, "info", "PERSON_COUNT", "PARKING_STATS", "ATTENDANCE_STATE",
                                        "VISITOR_TRACK", "CARTON_TRACK", "CARTON_STATS", "ANPR_STATS",
                                        "LIVE_TRACKING", "FIRE_STATS", "FIGHT_STATS",
                                        "RESTRICTION_ZONE_DRAW", "RESTRICTION_INTRUDER_TRACK", "PPE_STATS", "FACE_STATS"}
                
                filtered_events = {}
                for plugin_name, plugin_events in packet["events"].items():
                    if isinstance(plugin_events, list):
                        valid_plugin_events = []
                        for e in plugin_events:
                            e_type = getattr(e, "event_type", None)
                            if e_type is None and isinstance(e, dict):
                                e_type = e.get("event_type")
                            if e_type not in ignored_redis_events:
                                e_dict = e if isinstance(e, dict) else (e.dict() if hasattr(e, "dict") else e.__dict__)
                                valid_plugin_events.append(e_dict)
                        if valid_plugin_events:
                            filtered_events[plugin_name] = valid_plugin_events
                        
                if filtered_events:
                    from core.utils import clean_numpy
                    cleaned_events = clean_numpy(filtered_events)
                    db_packet = jsonable_encoder({
                        "camera_id": packet["camera_id"],
                        "timestamp": packet["timestamp"],
                        "events": cleaned_events
                    })
                    
                    try:
                        event_bus.publish("devavisionai:events", db_packet)
                        logger.debug(f"Published event packet to Redis for camera {packet['camera_id']}")
                    except Exception:
                        pass
                
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Event loop error: {e}")

def telemetry_consumer():
    """Listens to Edge Telemetry via Redis and caches it."""
    import redis
    import json
    from config.config import config
    from core.telemetry_cache import telemetry_cache
    
    logger.info("Started Telemetry consumer loop.")
    while True:
        try:
            redis_client = redis.Redis.from_url(config.REDIS_URL)
            pubsub = redis_client.pubsub()
            pubsub.subscribe("devavisionai:telemetry")
            
            for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        edge_id = data.get("edge_id", "unknown")
                        telemetry_cache.update(edge_id, data)
                    except Exception as e:
                        logger.error(f"Error parsing telemetry message: {e}")
        except Exception as e:
            if "ConnectionError" in type(e).__name__ or "10061" in str(e):
                logger.debug(f"Redis offline for Telemetry consumer (retrying in 5s): {e}")
                time.sleep(5.0)
            else:
                logger.error(f"Telemetry consumer error: {e}")
                time.sleep(1.0)

def main():
    """Entry point — all initialization is handled by server.py startup event."""
    logger.info("Starting DevaVision AI CCTV Platform...")
    try:
        # Telemetry threads are started by the server lifespan (api/server.py)
        # so they also run under a bare `uvicorn main:app` launch.
        uvicorn.run("api.server:app", host="127.0.0.1", port=8000, log_level="error")
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        # Force an immediate clean exit to bypass macOS native library (OpenCV/Paddle/CoreAudio) destructor segfaults
        import os
        os._exit(0)

if __name__ == "__main__":
    main()
