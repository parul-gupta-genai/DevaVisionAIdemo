from database.session import SessionLocal
from database.repositories.camera_repository import CameraRepository
from database.models.models import Camera

db = SessionLocal()
repo = CameraRepository(db)

import uuid

cam = repo.get_by_url("332263_medium.mp4")
if not cam:
    new_cam = Camera(
        id=f"CAM-{uuid.uuid4().hex[:8].upper()}",
        name="Carton Counting",
        rtsp_url="332263_medium.mp4",
        source="332263_medium.mp4",
        source_type="file",
        active=True
    )
    repo.add(new_cam)
    print("Added Carton Counting camera to database!")
else:
    print("Carton Counting camera already exists in database.")
