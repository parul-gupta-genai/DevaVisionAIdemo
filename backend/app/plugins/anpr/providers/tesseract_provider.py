import time
import numpy as np
from typing import Dict, Any, List
from loguru import logger
from app.plugins.anpr.interfaces import IOCR

class TesseractOCRProvider(IOCR):
    """
    Standard generic Tesseract OCR provider.
    Optimized for ARM64 Edge Devices (CPU).
    """
    def __init__(self, lang: str = "eng"):
        self.lang = lang
        
        try:
            import pytesseract
            self.pytesseract = pytesseract
            # Test if tesseract is available in system PATH
            tess_version = self.pytesseract.get_tesseract_version()
            self.TESSERACT_AVAILABLE = True
            logger.info(f"Initialized TesseractOCRProvider (v{tess_version}) for lang={self.lang}")
        except Exception as e:
            self.pytesseract = None
            self.TESSERACT_AVAILABLE = False
            logger.warning(f"Tesseract OCR is not installed or accessible: {e}")

    def recognize(self, image_crop: np.ndarray) -> List[Dict[str, Any]]:
        start_time = time.time()
        h, w = image_crop.shape[:2]
        
        if not getattr(self, 'TESSERACT_AVAILABLE', False) or self.pytesseract is None:
            # Fallback mock for testing if library missing
            time.sleep(0.02)
            return [{
                "text": "TESS-OFFLINE",
                "confidence": 0.0,
                "bbox": [[0, 0], [w, 0], [w, h], [0, h]],
                "char_confidences": [0.0],
                "recognition_time_ms": (time.time() - start_time) * 1000
            }]

        extracted = []
        try:
            # For license plates, PSM 7 (Treat the image as a single text line) is usually best.
            # config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
            # Let's use simple data-to-dict for now.
            data = self.pytesseract.image_to_data(image_crop, lang=self.lang, output_type=self.pytesseract.Output.DICT)
            
            # Combine words into a single string for license plate
            text_parts = []
            avg_conf = 0.0
            word_count = 0
            
            for i in range(len(data['text'])):
                word = data['text'][i].strip()
                if word:
                    conf = float(data['conf'][i])
                    if conf > 0: # Tesseract gives -1 for empty strings sometimes
                        text_parts.append(word)
                        avg_conf += conf
                        word_count += 1
                        
            if text_parts:
                final_text = "".join(text_parts).replace(" ", "")
                # Tesseract confidence is 0-100, we need 0.0-1.0
                normalized_conf = (avg_conf / word_count) / 100.0 if word_count > 0 else 0.0
                
                extracted.append({
                    "text": final_text,
                    "confidence": normalized_conf,
                    "bbox": [[0, 0], [w, 0], [w, h], [0, h]], # Tesseract bbox can be complex, just use full crop
                    "char_confidences": [normalized_conf] * len(final_text),
                    "recognition_time_ms": (time.time() - start_time) * 1000
                })
                
        except Exception as e:
            logger.error(f"Tesseract OCR Error: {e}")
            
        return extracted
