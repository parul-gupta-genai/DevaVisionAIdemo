import time
import cv2
import numpy as np
from typing import Dict, Any, List
from loguru import logger
from app.plugins.anpr.interfaces import IOCR

class EasyOCRProvider(IOCR):
    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu
        try:
            import easyocr
            self.reader = easyocr.Reader(["en"], gpu=use_gpu)
            logger.info(f"Initialized EasyOCRProvider (gpu={self.use_gpu})")
        except Exception as e:
            self.reader = None
            logger.error(f"Failed to initialize EasyOCR: {e}")

    def recognize(self, image_crop: np.ndarray) -> List[Dict[str, Any]]:
        start_time = time.time()
        extracted = []

        if self.reader is None or image_crop is None or not isinstance(image_crop, np.ndarray) or image_crop.size == 0:
            return extracted

        try:
            # High-accuracy bicubic upscaling to height 120px for clear text recognition
            h, w = image_crop.shape[:2]
            scale = 120.0 / max(1, h)
            target_w = max(100, int(w * scale))
            upscaled = cv2.resize(image_crop, (target_w, 120), interpolation=cv2.INTER_CUBIC)

            results = self.reader.readtext(upscaled, detail=1, allowlist="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-")

            segments = []
            for (bbox, text, prob) in results:
                cleaned = text.replace(" ", "").replace("-", "").upper()
                if len(cleaned) < 2:
                    continue
                ys = [p[1] for p in bbox]
                xs = [p[0] for p in bbox]
                segments.append({
                    "text": cleaned,
                    "confidence": float(prob),
                    "bbox": bbox,
                    "y_center": (min(ys) + max(ys)) / 2.0,
                    "x_min": min(xs),
                    "height": max(ys) - min(ys),
                })

            elapsed_ms = (time.time() - start_time) * 1000

            # Indian plates are frequently two-line (bikes, trucks, HSRP).
            # EasyOCR returns each line separately; merge lines top-to-bottom
            # (and left-to-right within a line) into one combined candidate.
            if len(segments) > 1:
                segments.sort(key=lambda s: s["y_center"])
                rows: List[List[dict]] = [[segments[0]]]
                for seg in segments[1:]:
                    row_y = sum(s["y_center"] for s in rows[-1]) / len(rows[-1])
                    row_h = max(s["height"] for s in rows[-1])
                    if abs(seg["y_center"] - row_y) < row_h * 0.6:
                        rows[-1].append(seg)
                    else:
                        rows.append([seg])
                ordered = []
                for row in rows:
                    row.sort(key=lambda s: s["x_min"])
                    ordered.extend(row)

                combined_text = "".join(s["text"] for s in ordered)
                total_chars = sum(len(s["text"]) for s in ordered)
                combined_conf = (
                    sum(s["confidence"] * len(s["text"]) for s in ordered) / total_chars
                    if total_chars else 0.0
                )
                extracted.append({
                    "text": combined_text,
                    "confidence": combined_conf,
                    "bbox": [],
                    "char_confidences": [combined_conf] * len(combined_text),
                    "recognition_time_ms": elapsed_ms,
                })

            for seg in segments:
                extracted.append({
                    "text": seg["text"],
                    "confidence": seg["confidence"],
                    "bbox": seg["bbox"],
                    "char_confidences": [seg["confidence"]] * len(seg["text"]),
                    "recognition_time_ms": elapsed_ms,
                })
        except Exception as e:
            logger.error(f"EasyOCR Error: {e}")

        return extracted
