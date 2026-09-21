import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from database.session import SessionLocal
from database.models.models import Camera

def clean_paths():
    db = SessionLocal()
    try:
        cams = db.query(Camera).all()
        for c in cams:
            if c.source:
                c.source = c.source.strip('\"\'')
            if c.rtsp_url:
                c.rtsp_url = c.rtsp_url.strip('\"\'')
            c.source_type = "video_file" if c.source and not c.source.startswith(("rtsp://", "http://")) else "rtsp"
            print(f"Cleaned Camera: {c.name} -> {c.source} (type: {c.source_type})")
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    clean_paths()
