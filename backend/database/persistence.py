import threading
import queue
import time
from typing import Optional
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone, timedelta

from database.session import SessionLocal, engine, Base
from database.models.models import CameraEvent
import app.plugins.visitor.models # Ensure visitor tables are registered
import app.plugins.anpr.models # Ensure ANPR tables are registered
try:
    from core.alert_engine import AlertEngine
except ImportError:
    AlertEngine = None

class DatabaseWorker:
    """
    Background worker thread dedicated to writing events to PostgreSQL/TimescaleDB.
    
    It reads from the global result queue, drops the heavy video frame, 
    and performs bulk inserts to maximize throughput without blocking AI.
    """
    def __init__(self):
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self.batch_size = 50
        self.flush_interval = 1.0  # Force a DB write every 1 second minimum (optimized)
        self.prune_interval = 3600.0 # Prune old records every hour
        
        self.alert_engine = AlertEngine() if AlertEngine is not None else None
        
        from core.events.bus import RedisEventBus
        from config.config import config
        self.event_bus = RedisEventBus(config.REDIS_URL)
        self.stream_name = "devavisionai:events"
        self.group_name = "db_writers"
        
        # Ensure consumer group exists
        try:
            self.event_bus.client.xgroup_create(self.stream_name, self.group_name, id='0', mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                logger.warning(f"Error creating Redis consumer group (may already exist): {e}")

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        
        # Ensure extensions exist (we rely on Alembic for prod, but this is a failsafe)
        with engine.connect() as conn:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                # Attempt to enable TimescaleDB and create hypertable for enterprise scaling
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
                conn.commit()
                
                # Check if it's already a hypertable, if not, convert it
                conn.execute(text("SELECT create_hypertable('camera_events', 'timestamp', if_not_exists => TRUE);"))
                conn.commit()
                logger.info("TimescaleDB optimizations applied successfully.")
            except Exception as e:
                logger.debug(f"TimescaleDB not available or already configured: {e}")
                conn.commit()

        self._thread = threading.Thread(target=self._run, daemon=True, name="DatabaseWorker")
        self._thread.start()
        logger.info("Started Database Worker thread.")

    def stop(self):
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("Stopped Database Worker thread.")

    def _is_actionable(self, events: dict) -> bool:
        """Determine if a frame has any actionable events worth saving to the DB."""
        if not events:
            return False
            
        # Keep in step with main.py's ignored_redis_events. The *_STATS / *_DRAW / *_TRACK families are live-overlay twins: they are
        # re-emitted on EVERY processed frame so boxes and banners stay lit.
        # Recording them wrote a DB row per frame per camera, which both
        # amplified writes enormously and — because the feed reads only the
        # latest 20 rows per camera — pushed every real alert out of the
        # window. Overlays reach the UI through update_global_state, not
        # through this stream, so dropping them here costs nothing visible.
        ignored_events = {None, "info", "PERSON_COUNT", "PARKING_STATS", "ATTENDANCE_STATE", "VISITOR_TRACK",
                          "CARTON_TRACK", "CARTON_STATS", "ANPR_STATS", "LIVE_TRACKING", "FIRE_STATS", "FIGHT_STATS",
                          "RESTRICTION_ZONE_DRAW", "RESTRICTION_INTRUDER_TRACK", "PPE_STATS", "FACE_STATS"}
            
        if isinstance(events, list):
            for event in events:
                if event.get("active_alerts") or event.get("event_type") not in ignored_events:
                    return True
        elif isinstance(events, dict):
            for plugin_name, data in events.items():
                if isinstance(data, dict):
                    if data.get("active_alerts") or data.get("event_type") not in ignored_events:
                        return True
                elif isinstance(data, list):
                    for event in data:
                        if event.get("event_type") not in ignored_events:
                            return True
        return False

    def _run(self):
        logger.info("Database Worker active and listening for events...")
        
        batch = []
        last_flush = time.time()
        last_prune = time.time()
        
        import json
        while self.is_running:
            try:
                # Read from Redis stream (block for 100ms)
                messages = self.event_bus.subscribe_group(self.group_name, "db_worker_1", self.stream_name, count=10, block=100)
                
                for msg in messages:
                    try:
                        msg_id = msg["id"]
                        packet = msg["data"]
                        
                        # Only write to DB if the event is actionable
                        if self._is_actionable(packet["events"]):
                            db_event = CameraEvent(
                                camera_id=packet["camera_id"],
                                timestamp=datetime.fromtimestamp(packet["timestamp"], timezone.utc),
                                events=packet["events"]
                            )
                            batch.append(db_event)
                            
                            # Dispatch critical external alerts (SMS/Email) asynchronously
                            self.alert_engine.process_events(packet["camera_id"], packet["events"])
                            
                        # Acknowledge the message
                        self.event_bus.ack(self.stream_name, self.group_name, msg_id)
                    except Exception as e:
                        logger.error(f"Error parsing redis message: {e}")
                
            except Exception as e:
                if "ConnectionError" in type(e).__name__ or "10061" in str(e):
                    logger.debug(f"Redis offline for DB worker (retrying in 5s): {e}")
                    time.sleep(5.0)
                else:
                    logger.error(f"Error processing event from Redis for DB: {e}")
                    time.sleep(0.5)
                
            # Flush conditions
            if len(batch) >= self.batch_size or (time.time() - last_flush) > self.flush_interval:
                if batch:
                    self._flush(batch)
                    batch = []
                last_flush = time.time()
                
            # Prune conditions (hourly)
            if (time.time() - last_prune) > self.prune_interval:
                self._prune_old_events()
                last_prune = time.time()
                
        # Final flush on graceful shutdown
        if batch:
            self._flush(batch)

    def _flush(self, batch):
        db = None
        try:
            db: Session = SessionLocal()
            db.add_all(batch)
            db.commit()
            logger.debug(f"Flushed {len(batch)} events to Database.")
        except SQLAlchemyError as e:
            logger.error(f"Database error during bulk insert: {e}")
            if db:
                db.rollback()
        except Exception as e:
            logger.error(f"Failed to bulk insert to database: {e}")
            if db:
                db.rollback()
        finally:
            if db:
                db.close()
            
    def _prune_old_events(self):
        db = None
        try:
            db: Session = SessionLocal()
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            # Use raw query for speed
            result = db.execute(text("DELETE FROM camera_events WHERE timestamp < :limit"), {"limit": thirty_days_ago})
            db.commit()
            if result.rowcount > 0:
                logger.info(f"Pruned {result.rowcount} old events from database.")
        except SQLAlchemyError as e:
            logger.error(f"Database error during prune: {e}")
            if db:
                db.rollback()
        except Exception as e:
            logger.error(f"Failed to prune database: {e}")
            if db:
                db.rollback()
        finally:
            if db:
                db.close()
