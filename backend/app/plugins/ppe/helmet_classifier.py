"""
Helmet / No-Helmet classifier for PPEDetectionPlugin.

WHAT THIS IS: a small CNN (trained from scratch, ~250K params) that
classifies a head-region crop as "helmet" or "no-helmet". Trained on the
Kaggle "Hard Hat Workers" dataset (5000 construction-site images, VOC XML
annotations) merged down to just the helmet/head boxes relevant here.

Test-set results (390 held-out images, 1897 boxes, never seen in training):
    accuracy:  79.4%
    precision: 55.4%  (of crops flagged "no-helmet", ~55% truly are)
    recall:    84.3%  (catches ~84% of real no-helmet cases)
  Recall > precision is the safer direction for a safety-compliance signal —
  missing a real violation is worse than an extra false alarm a human then
  dismisses. Validate on your own camera footage before relying on it
  unsupervised; construction-site conditions here (dust, welding glare,
  cropped/blurry heads) will differ from this dataset's.

WHY A CLASSIFIER, NOT A YOLO DETECTOR: full object detection (YOLOv7/v8,
which the dataset descriptions reference) needs PyTorch or a from-scratch
anchor/NMS implementation. PyTorch's default PyPI wheel hard-requires
several GB of CUDA libraries just to import — even for CPU-only use — which
didn't fit this environment's disk budget. TensorFlow-CPU installs cleanly
without that problem, so this is a classifier: it labels a crop you hand
it, but does NOT find head regions in a full frame on its own.

HOW TO GET FROM "full camera frame" TO "head crop" (needed to use this):
Pair it with a detector that finds people/heads first — this project
already ships two options in backend/detection/:
  - The shared COCO person detector (class_id 0) → crop the top ~25-30% of
    each person's bounding box as an approximate head region, or
  - face_detection_yunet_2023mar.onnx (already used by face_emotion.py in
    the fight plugin) → gives a tighter head-region box directly when a
    face is visible/frontal enough.
Either way: get a box, crop it from the frame, pass the crop to
HelmetClassifier.predict() below. This mirrors exactly how
fight/face_emotion.py pairs YuNet with its own classifier — same pattern,
new model.

INTEGRATION SKETCH (into ppe/plugin.py or a new ppe/ml_classifier.py):
  This project's actual PPEDetectionPlugin currently decides helmet/vest
  presence with a colour-zone heuristic (ppe/colour.py) — no ML model.
  This classifier is a drop-in candidate to REPLACE that heuristic for the
  helmet half of the decision (vest still has no equivalent dataset/model
  yet): call it once per detected person, on a head-region crop, instead of
  sampling colours in that region. It does not touch vest logic.
"""

from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from tensorflow import keras

_MODEL_PATH = Path(__file__).resolve().parent / "helmet_classifier.keras"
IMG_SIZE = (96, 96)


class HelmetClassifier:
    def __init__(self, model_path: Optional[Path] = None):
        path = model_path or _MODEL_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"helmet_classifier.keras not found at {path}. See "
                "backend/scripts/train_helmet_classifier.py to reproduce it."
            )
        self.model = keras.models.load_model(str(path))

    def predict(self, head_crop_bgr: np.ndarray) -> Tuple[str, float]:
        """head_crop_bgr: a head-region crop (any size, BGR as from cv2).
        Returns (label, no_helmet_probability) — label is 'helmet' or
        'no-helmet'; the probability is always P(no-helmet), so callers can
        apply their own threshold (default 0.5) if 79%/55%/84% isn't the
        right operating point for their false-alarm tolerance.
        """
        import cv2
        rgb = cv2.cvtColor(head_crop_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, IMG_SIZE)
        arr = resized.astype(np.float32) / 255.0
        pred = self.model.predict(np.expand_dims(arr, 0), verbose=0)[0][0]
        label = "no-helmet" if pred > 0.5 else "helmet"
        return label, float(pred)


# --- Integration sketch ---
#
#   from app.plugins.ppe.helmet_classifier import HelmetClassifier
#
#   _helmet_clf = HelmetClassifier()  # load once
#
#   for person_box in detected_people:
#       x1, y1, x2, y2 = person_box
#       head_h = int((y2 - y1) * 0.3)          # top ~30% of the person box
#       head_crop = frame[y1:y1 + head_h, x1:x2]
#       if head_crop.size:
#           label, no_helmet_prob = _helmet_clf.predict(head_crop)
#           # combine with (or replace) ppe/colour.py's verdict for this person
