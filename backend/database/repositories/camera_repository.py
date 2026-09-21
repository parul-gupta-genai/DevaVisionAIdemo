from typing import List, Optional
from sqlalchemy.orm import Session
from database.models.models import Camera

class CameraRepository:
    def __init__(self, db: Session):
        self.db = db
        
    def get_active_cameras(self) -> List[Camera]:
        return self.db.query(Camera).filter(Camera.active == True).all()
        
    def get_by_url(self, rtsp_url: str) -> Optional[Camera]:
        return self.db.query(Camera).filter(Camera.rtsp_url == rtsp_url).first()

    def get_by_name(self, name: str) -> Optional[Camera]:
        return self.db.query(Camera).filter(Camera.name == name).first()
        
    def get_by_id(self, cam_id: str) -> Optional[Camera]:
        return self.db.query(Camera).filter(Camera.id == cam_id).first()
        
    def add(self, camera: Camera) -> Camera:
        self.db.add(camera)
        self.db.commit()
        self.db.refresh(camera)
        return camera
