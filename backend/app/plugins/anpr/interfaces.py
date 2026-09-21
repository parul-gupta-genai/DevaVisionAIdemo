from abc import ABC, abstractmethod
import numpy as np
from typing import List, Tuple, Dict, Any

class IPlateDetector(ABC):
    """
    Abstract interface for Plate Detection models.
    """
    @abstractmethod
    def detect_plates(self, image: np.ndarray) -> List[Tuple[np.ndarray, float, List[int]]]:
        """
        Returns a list of (cropped_plate_image, confidence, bbox).
        """
        pass

    @abstractmethod
    def enhance_plate(self, plate_img: np.ndarray) -> np.ndarray:
        """
        Applies image enhancement.
        """
        pass

class IOCR(ABC):
    """
    Abstract interface for OCR wrappers.
    """
    @abstractmethod
    def recognize(self, image_crop: np.ndarray) -> List[Dict[str, Any]]:
        """
        Returns a list of detected texts with their confidences and bounding boxes.
        Schema:
        {
            "text": str,
            "confidence": float,
            "bbox": List[List[float]],
            "char_confidences": List[float],
            "recognition_time_ms": float
        }
        """
        pass
