import sys
import os
import uuid

# Add backend to path so we can import DB modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.session import SessionLocal
from database.models.models import Camera

def add_camera():
    db = SessionLocal()
    try:
        existing = db.query(Camera).filter(Camera.name == "Parking Live").first()
        if existing:
            print("Camera already exists!")
            return
            
        new_cam = Camera(
            id=str(uuid.uuid4()),
            name="Parking Live",
            rtsp_url="/home/user/DevaVisionAI/PARKING.mp4",
            source="/home/user/DevaVisionAI/PARKING.mp4",
            source_type="file",
            active=True
        )
        db.add(new_cam)
        db.commit()
        print(f"Added camera: {new_cam.name} with ID: {new_cam.id}")
    finally:
        db.close()

if __name__ == "__main__":
    add_camera()
