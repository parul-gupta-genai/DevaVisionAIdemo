import os
import cv2
import numpy as np
from typing import List, Optional, Tuple
from loguru import logger
from app.plugins.anpr.interfaces import IPlateDetector
from app.plugins.anpr.config_parser import anpr_app_config

try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False

# Fraction of plate box size added on each side before cropping; slight
# context around the plate measurably improves OCR accuracy.
PLATE_CROP_PADDING = 0.06


def _resolve_model_path(model_path: str) -> Optional[str]:
    """
    Resolves a plate-model path regardless of which process CWD we run under
    (backend uvicorn runs from backend/, DeepStream runs from deepstream_pyds/).
    """
    if os.path.isabs(model_path):
        return model_path if os.path.exists(model_path) else None

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.abspath(os.path.join(plugin_dir, "..", "..", ".."))
    candidates = [
        os.path.join(backend_dir, "detection", model_path),
        os.path.join(backend_dir, model_path),
        os.path.join(plugin_dir, model_path),
        model_path,
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


class GenericYOLOPlateDetector(IPlateDetector):
    """
    Detects license plates within a larger vehicle crop or full frame using a YOLO model.
    """
    def __init__(self, model_path: str = "plate_yolo.pt", conf_threshold: float = 0.5):
        self.conf_threshold = conf_threshold
        self.model = None
        if not ULTRALYTICS_AVAILABLE:
            logger.error("ultralytics is not installed — plate detection falls back to a heuristic crop.")
            return

        resolved = _resolve_model_path(model_path)
        if resolved is None:
            logger.error(
                f"Plate detection model '{model_path}' not found on disk — "
                f"falling back to heuristic crop. OCR accuracy will be poor."
            )
            return
        try:
            self.model = YOLO(resolved)
            logger.info(f"Loaded plate detection model: {resolved}")
        except Exception as e:
            logger.error(f"Failed to load YOLO plate detector '{resolved}': {e}")
            self.model = None

    def detect_plates(self, image: np.ndarray) -> List[Tuple[np.ndarray, float, List[int]]]:
        if image is None or image.size == 0:
            return []
        h, w = image.shape[:2]

        if self.model is None:
            # Heuristic fallback: assume the plate sits in the lower-center of
            # the vehicle crop. Low confidence so fused results reflect doubt.
            y1, y2 = int(h * 0.60), h
            x1, x2 = int(w * 0.10), int(w * 0.90)
            bbox = [x1, y1, x2, y2]
            if y2 > y1 and x2 > x1:
                crop = image[y1:y2, x1:x2]
            else:
                crop = image
                bbox = [0, 0, w, h]
            return [(self.conditionally_enhance_plate(crop), 0.30, bbox)]

        plates = []
        results = self.model(image, conf=self.conf_threshold, verbose=False)
        if not results:
            return plates

        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])

            pad_x = int((x2 - x1) * PLATE_CROP_PADDING)
            pad_y = int((y2 - y1) * PLATE_CROP_PADDING)
            px1, py1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
            px2, py2 = min(w, x2 + pad_x), min(h, y2 + pad_y)

            crop = image[py1:py2, px1:px2]
            if crop.size > 0:
                crop = self.conditionally_enhance_plate(crop)
                plates.append((crop, conf, [x1, y1, x2, y2]))

        return plates

    def conditionally_enhance_plate(self, plate_img: np.ndarray) -> np.ndarray:
        """Applies enhancement ONLY when quality score is below threshold."""
        gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)

        # Calculate blur metric (variance of Laplacian)
        quality_score = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Normalize quality score (approximate thresholding, > 100 is usually sharp)
        # We will use the config quality_threshold as a scaled threshold
        threshold_value = anpr_app_config.enhancement.quality_threshold * 100.0

        if quality_score < threshold_value:
            return self.enhance_plate(plate_img)
        return plate_img

    def enhance_plate(self, plate_img: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        h_param = anpr_app_config.enhancement.denoise_h
        clip_limit = anpr_app_config.enhancement.clahe_clip_limit

        denoised = cv2.fastNlMeansDenoising(gray, h=h_param)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
        cl1 = clahe.apply(denoised)

        kernel = np.array([[0, -1, 0],
                           [-1, 5, -1],
                           [0, -1, 0]])
        sharpened = cv2.filter2D(cl1, -1, kernel)
        enhanced_bgr = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)
        return enhanced_bgr


class IndianYOLOPlateDetector(GenericYOLOPlateDetector):
    """
    Optimized for Indian plates: HSRP, Single Line, Double Line, Night, Rain, Blur, Tilt.
    """
    def __init__(self, model_path: str = "license_plate_yolov11n.pt", conf_threshold: float = 0.5):
        super().__init__(model_path=model_path, conf_threshold=conf_threshold)
        logger.info(f"Initialized IndianYOLOPlateDetector with model: {model_path}")
