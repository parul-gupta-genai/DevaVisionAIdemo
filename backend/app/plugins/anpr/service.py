import asyncio
from typing import Dict, Any
from loguru import logger
from database.session import SessionLocal
from app.plugins.anpr.repository import ANPRRepository

class ANPRService:
    def __init__(self):
        self.queue = asyncio.Queue(maxsize=1000)
        self.worker_task = None
        
    async def start(self):
        if not self.worker_task:
            self.worker_task = asyncio.create_task(self._process_queue())
            logger.info("ANPR Service worker started.")

    async def stop(self):
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            logger.info("ANPR Service worker stopped.")

    async def enqueue_finalized_track(self, track_data: Dict[str, Any]):
        try:
            await self.queue.put(track_data)
        except asyncio.QueueFull:
            logger.error("ANPR Service queue is full. Dropping track data.")

    async def _process_queue(self):
        while True:
            try:
                track_data = await self.queue.get()
                # Run the blocking DB and I/O operations in a thread pool
                await asyncio.to_thread(self._handle_track, track_data)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing ANPR track data: {e}")

    def _handle_track(self, track_data: Dict[str, Any]):
        from app.plugins.anpr.utils import save_snapshot
        import numpy as np
        
        track_info = track_data["track_info"]
        
        # Save images sequentially in this background thread
        veh_crop = track_info.get("vehicle_snapshot")
        if isinstance(veh_crop, np.ndarray):
            track_info["vehicle_snapshot"] = save_snapshot(veh_crop, prefix="veh")
            
        plate_crop = track_info.get("plate_snapshot")
        if isinstance(plate_crop, np.ndarray):
            track_info["plate_snapshot"] = save_snapshot(plate_crop, prefix="plate")

        # These travel with the track but are not columns on it; pop them
        # before the row is built, or ANPRVehicleTrack(**track_info) raises.
        had_watchlist_key = "watchlist_id" in track_info
        watchlist_id = track_info.pop("watchlist_id", None)
        match_kind = track_info.pop("watchlist_match_kind", None)

        db = SessionLocal()
        try:
            repo = ANPRRepository(db)

            # Log the track
            repo.create_vehicle_track(track_info)
            
            best_plate = track_info.get("best_plate")
            if best_plate:
                # Log to plate history
                history_data = {
                    "plate_number": best_plate,
                    "confidence": track_info.get("plate_confidence", 0.0),
                    "timestamp": track_info["start_time"],
                    "camera_id": track_info["camera_id"],
                    "track_id": track_info["track_id"],
                    "vehicle_snapshot": track_info.get("vehicle_snapshot"),
                    "plate_snapshot": track_info.get("plate_snapshot"),
                }
                repo.log_plate_history(history_data)
                
                # The plugin already resolved the list match against the
                # cached index (tolerating OCR confusions and honouring
                # expiry), so re-running an exact-equality lookup here would
                # disagree with the alert the operator just saw. Fall back to
                # matching only when the plugin did not run this path.
                from app.plugins.anpr.watchlist import (
                    is_blacklist, is_whitelist, plate_watchlist,
                )

                entry = None
                if watchlist_id:
                    entry = repo.get_watchlist_by_id(watchlist_id)
                elif not had_watchlist_key:
                    cached, match_kind = plate_watchlist.match(best_plate)
                    if cached:
                        entry = repo.get_watchlist_by_id(cached["id"])

                if entry:
                    kind = ("BLACKLIST" if is_blacklist(entry.list_type)
                            else "WHITELIST" if is_whitelist(entry.list_type)
                            else (entry.list_type or "WATCHLIST").upper())
                    logger.warning(
                        f"{kind} MATCH: {best_plate} listed as {entry.plate_number} "
                        f"({entry.list_type}, matched {match_kind or 'exact'})"
                    )
                    repo.create_event({
                        "event_type": f"{kind}_MATCH",
                        "plate_number": best_plate,
                        "confidence": track_info.get("plate_confidence", 0.0),
                        "timestamp": track_info["start_time"],
                        "camera_id": track_info["camera_id"],
                        "track_id": track_info["track_id"],
                        "metadata_json": {
                            "listed_plate": entry.plate_number,
                            "list_type": entry.list_type,
                            "match_kind": match_kind or "exact",
                            "reason": entry.reason,
                            "priority": entry.priority,
                        },
                    })
        except Exception as e:
            logger.error(f"DB Error handling ANPR track: {e}")
        finally:
            db.close()

anpr_service = ANPRService()
