"""
Indian license-plate text reader (OCR) for ANPRPlugin.

WHAT THIS IS: a CRNN (CNN + BiLSTM + CTC) trained from scratch on 1649
real Indian plate crops (Google-scraped photos, video frames, and
state-wise OLX listings covering 36+ states/UTs — see
backend/scripts/merge_anpr_dataset.py and train_anpr_ocr.py).

RESULTS (166 held-out test crops, never seen in training):
    exact match:      17.5%
    char accuracy:    56.1%
  For comparison, generic Tesseract OCR on the same test crops scored
  12.9% exact / 47% char accuracy — this model reads Indian plates
  measurably better than an off-the-shelf general-purpose OCR engine, but
  is NOT yet a reliable standalone reader (over 4 in 5 plates still come
  out wrong somewhere). Given how small the training set is (1319 images)
  for a from-scratch OCR model, this should be treated as a starting point
  to improve with more data, not a production-ready replacement for
  whatever OCR engine (EasyOCR/PaddleOCR per requirements.txt) the ANPR
  plugin already uses — that engine is pretrained on vastly more text data
  and may well already outperform this. Compare both on the same test set
  (this module's test crops are in backend/dataset_anpr/test/, with
  ground truth in manifest.csv) before deciding which to use.

INPUT REQUIRED: a plate crop (BGR, as from cv2) — this does NOT detect
plates in a full frame; pair it with the project's existing plate
detector (indian_plate_yolo.pt / license_plate_yolov11n.pt) or the
ground-truth boxes in dataset_anpr/ for evaluation.
"""

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import tensorflow as tf
from tensorflow import keras

_MODEL_PATH = Path(__file__).resolve().parent / "anpr_ocr_model.keras"
IMG_H, IMG_W = 32, 128
CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
IDX_TO_CHAR = {i: c for i, c in enumerate(CHARSET)}


class PlateOCR:
    def __init__(self, model_path: Optional[Path] = None):
        path = model_path or _MODEL_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"anpr_ocr_model.keras not found at {path}. See "
                "backend/scripts/train_anpr_ocr.py to reproduce it."
            )
        self.model = keras.models.load_model(str(path))

    def read(self, plate_crop_bgr: np.ndarray) -> str:
        """plate_crop_bgr: a plate-region crop (any size, BGR as from cv2).
        Returns the predicted plate text (may be wrong or partially wrong —
        see accuracy figures in the module docstring above)."""
        gray = cv2.cvtColor(plate_crop_bgr, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (IMG_W, IMG_H))
        arr = resized.astype(np.float32) / 255.0
        arr = np.expand_dims(arr, axis=(0, -1))  # (1, H, W, 1)

        y_pred = self.model.predict(arr, verbose=0)
        input_len = np.array([y_pred.shape[1]])
        decoded, _ = tf.keras.backend.ctc_decode(y_pred, input_length=input_len, greedy=True)
        decoded = decoded[0].numpy()[0]
        chars = [IDX_TO_CHAR[i] for i in decoded if 0 <= i < len(CHARSET)]
        return "".join(chars)


# --- Integration sketch ---
#
#   from app.plugins.anpr.plate_ocr import PlateOCR
#
#   _plate_ocr = PlateOCR()  # load once
#
#   plate_box = existing_plate_detector.detect(frame)   # your current detector
#   crop = frame[y1:y2, x1:x2]
#   text = _plate_ocr.read(crop)
#   # Given the accuracy figures above, treat this as ONE candidate reading —
#   # compare against whatever OCR engine ANPRPlugin already runs, and only
#   # switch over if this genuinely scores better on YOUR camera footage,
#   # not just this dataset's photos.
