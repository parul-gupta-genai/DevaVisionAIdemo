import time
import numpy as np
from typing import Dict, Any, List
from loguru import logger
from app.plugins.anpr.interfaces import IOCR


class FastPlateOCRProvider(IOCR):
    """
    Plate-specialized OCR using fast-plate-ocr (ONNX CCT models trained on
    global license plates, including Indian formats). Far more accurate than
    generic scene-text OCR on plate crops, and fast enough for CPU on Jetson.
    """

    def __init__(self, model_name: str = "cct-s-v1-global-model", use_gpu: bool = False):
        self.model_name = model_name
        self.recognizer = None
        self.device = None

        try:
            from fast_plate_ocr import LicensePlateRecognizer
        except Exception as e:
            logger.error(f"fast-plate-ocr is not importable: {e}")
            return

        # Try the GPU only if asked, and ALWAYS fall back to CPU on failure.
        # A GPU that fails to initialise must never cost us this provider:
        # the factory's fallback is EasyOCR, which is markedly worse on plate
        # crops, so a cuDNN error would silently degrade ANPR accuracy.
        attempts = (["auto"] if use_gpu else []) + ["cpu"]
        for device in attempts:
            try:
                self.recognizer = LicensePlateRecognizer(model_name, device=device)
                self.device = device
                logger.info(
                    f"Initialized FastPlateOCRProvider ({model_name}, device={device})"
                )
                return
            except Exception as e:
                logger.warning(
                    f"fast-plate-ocr could not start on device={device}: "
                    f"{str(e)[:160]}"
                )

        logger.error(
            "Failed to initialize fast-plate-ocr on any device; "
            "ANPR will fall back to the generic OCR provider."
        )

    def recognize(self, image_crop: np.ndarray) -> List[Dict[str, Any]]:
        start_time = time.time()
        extracted = []

        if (
            self.recognizer is None
            or image_crop is None
            or not isinstance(image_crop, np.ndarray)
            or image_crop.size == 0
        ):
            return extracted

        try:
            results = self.recognizer.run(image_crop, return_confidence=True)
            for pred in results:
                # PlatePrediction(plate=str, char_probs=ndarray); '_' is padding
                raw = pred.plate
                probs = np.asarray(pred.char_probs, dtype=float).ravel()
                chars = []
                char_confs = []
                for i, ch in enumerate(raw):
                    if ch == "_":
                        continue
                    chars.append(ch)
                    if i < len(probs):
                        char_confs.append(float(probs[i]))
                text = "".join(chars).upper()
                if len(text) < 4:
                    continue
                confidence = float(np.mean(char_confs)) if char_confs else 0.0
                extracted.append({
                    "text": text,
                    "confidence": confidence,
                    "bbox": [],
                    "char_confidences": char_confs,
                    "recognition_time_ms": (time.time() - start_time) * 1000,
                })
        except Exception as e:
            logger.error(f"FastPlateOCR error: {e}")

        return extracted
