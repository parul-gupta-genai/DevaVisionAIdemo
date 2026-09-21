from database.session import SessionLocal
from database.repositories.camera_repository import CameraRepository

db = SessionLocal()
repo = CameraRepository(db)

cam = repo.get_by_name("Carton Counting")
if cam:
    cam.source = "../332263_medium.mp4"
    cam.rtsp_url = "../332263_medium.mp4"
    db.commit()
    print("Fixed source path for Carton Counting to ../332263_medium.mp4")
else:
    print("Camera not found!")
