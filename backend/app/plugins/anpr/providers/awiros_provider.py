import os
import time
import numpy as np
from typing import Dict, Any, List
from loguru import logger
from app.plugins.anpr.interfaces import IOCR
from app.plugins.anpr.config_parser import anpr_app_config

try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False

try:
    from huggingface_hub import hf_hub_download
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

class AwirosOCRProvider(IOCR):
    """
    Official Awiros ANPR OCR integration using PaddlePaddle.
    Downloads the model from Hugging Face once and uses it locally.
    """
    def __init__(self, local_model_path: str = "models/awiros", download_if_missing: bool = True, use_gpu: bool = False):
        self.use_gpu = use_gpu
        self.local_model_path = local_model_path
        self.repo_id = "Awiros/anpr-ocr"
        self.ocr = None
        
        self.safetensors_path = os.path.join(self.local_model_path, "model.safetensors")
        self.dict_path = os.path.join(self.local_model_path, "en_dict.txt")
        
        # Verify and Download
        if not self._verify_files():
            if download_if_missing:
                logger.info(f"Downloading Awiros model to {self.local_model_path}")
                self._download_model()
            else:
                raise FileNotFoundError(f"Awiros model files missing in {self.local_model_path} and download_if_missing=False")
        
        if not PADDLE_AVAILABLE:
            raise ImportError("PaddleOCR is required to run the Awiros model.")
            
        try:
            logger.info("Initializing Awiros PP-OCRv5 Model...")
            # We initialize PaddleOCR pointing to our local directory
            # For PaddleOCR 3.7+, we use text_recognition_model_dir
            self.ocr = PaddleOCR(
                text_recognition_model_dir=self.local_model_path,
                lang="en"
            )
            logger.info("Awiros PP-OCRv5 initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Awiros PaddleOCR: {e}")
            raise e

    def _verify_files(self) -> bool:
        return os.path.exists(self.safetensors_path) and os.path.exists(self.dict_path)

    def _download_model(self):
        if not HF_AVAILABLE:
            raise ImportError("huggingface_hub is required to download the model.")
        try:
            os.makedirs(self.local_model_path, exist_ok=True)
            hf_hub_download(repo_id=self.repo_id, filename="model.safetensors", local_dir=self.local_model_path)
            hf_hub_download(repo_id=self.repo_id, filename="en_dict.txt", local_dir=self.local_model_path)
            logger.info("Awiros model download complete.")
        except Exception as e:
            logger.error(f"Failed to download Awiros model from Hugging Face: {e}")
            raise e

    def recognize(self, image_crop: np.ndarray) -> List[Dict[str, Any]]:
        start_time = time.time()
        
        if self.ocr is None:
            raise RuntimeError("Awiros OCR is not initialized.")
            
        results = self.ocr.ocr(image_crop, cls=False)
        
        extracted = []
        if results and results[0]:
            for line in results[0]:
                bbox = line[0] 
                text = line[1][0]
                confidence = line[1][1]
                
                extracted.append({
                    "text": text,
                    "confidence": float(confidence),
                    "bbox": bbox,
                    "char_confidences": [float(confidence)] * len(text),
                    "recognition_time_ms": (time.time() - start_time) * 1000
                })
                
        return extracted
