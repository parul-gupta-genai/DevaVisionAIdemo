from typing import List, Tuple, Any
from sqlalchemy.orm import Session
from database.models.models import CameraEvent

class EventRepository:
    def __init__(self, db: Session):
        self.db = db
        
    def add(self, event: CameraEvent) -> CameraEvent:
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def get_recent_events(self, limit: int = 1000) -> List[CameraEvent]:
        return self.db.query(CameraEvent).order_by(CameraEvent.timestamp.desc()).limit(limit).all()
        
    def get_distinct_camera_ids(self) -> List[Any]:
        return self.db.query(CameraEvent.camera_id).distinct().all()
        
    def get_recent_events_by_camera(self, camera_id: str, limit: int = 20) -> List[CameraEvent]:
        return self.db.query(CameraEvent).filter(
            CameraEvent.camera_id == camera_id
        ).order_by(CameraEvent.timestamp.desc()).limit(limit).all()

    def get_filtered_events(
        self, 
        camera_id: str = None, 
        start_date: str = None, 
        end_date: str = None, 
        limit: int = 100
    ) -> List[CameraEvent]:
        from datetime import datetime
        query = self.db.query(CameraEvent)
        
        if camera_id:
            query = query.filter(CameraEvent.camera_id == camera_id)
            
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                query = query.filter(CameraEvent.timestamp >= start_dt)
            except ValueError:
                pass
                
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                query = query.filter(CameraEvent.timestamp <= end_dt)
            except ValueError:
                pass
                
        return query.order_by(CameraEvent.timestamp.desc()).limit(limit).all()
