import os
from pydantic import BaseModel, Field

class ANPRConfig(BaseModel):
    # OCR settings
    ocr_lang: str = "en"
    ocr_use_gpu: bool = os.getenv("ANPR_OCR_USE_GPU", "False").lower() in ("true", "1")
    
    # Detector settings
    detector_model_path: str = os.getenv("ANPR_DETECTOR_MODEL", "plate_yolo.pt")
    detector_conf_threshold: float = float(os.getenv("ANPR_DETECTOR_CONF", "0.45"))
    
    # Tracker settings
    track_timeout_seconds: float = float(os.getenv("ANPR_TRACK_TIMEOUT", "2.0"))
    
    # Logic
    min_ocr_confidence: float = 0.80

anpr_config = ANPRConfig()
