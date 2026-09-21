import os
import cv2
import uuid
import time
import numpy as np
from loguru import logger

def save_snapshot(image: np.ndarray, prefix: str = "anpr") -> str:
    """
    Saves an image snapshot to the snapshots directory.
    Returns the relative path for HTTP serving.
    """
    if image is None or not isinstance(image, np.ndarray) or image.size == 0:
        return None
    try:
        # Base backend dir
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        snapshots_dir = os.path.join(backend_dir, "snapshots")
        os.makedirs(snapshots_dir, exist_ok=True)
        filename = f"{prefix}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}.jpg"
        filepath = os.path.join(snapshots_dir, filename)
        cv2.imwrite(filepath, image)
        return f"snapshots/{filename}"
    except Exception as e:
        logger.error(f"Failed to save snapshot: {e}")
        return None

def enhance_plate_image(image: np.ndarray, clahe_clip: float = 2.0, denoise_h: float = 30.0) -> np.ndarray:
    """
    Applies image enhancement techniques to improve OCR accuracy.
    """
    if image is None or image.size == 0:
        return image
        
    try:
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Denoise
        denoised = cv2.fastNlMeansDenoising(gray, None, float(denoise_h), 7, 21)
        
        # Apply CLAHE
        clahe = cv2.createCLAHE(clipLimit=float(clahe_clip), tileGridSize=(8,8))
        enhanced = clahe.apply(denoised)
        
        # Sharpening
        kernel = np.array([[0, -1, 0], 
                           [-1, 5,-1], 
                           [0, -1, 0]])
        sharpened = cv2.filter2D(enhanced, -1, kernel)
        
        return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)
    except Exception as e:
        return image
