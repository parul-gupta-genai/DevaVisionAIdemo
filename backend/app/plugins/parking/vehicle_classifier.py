"""
Tractor / Truck classifier — a complementary signal for the parking/
counting/zones plugins, which currently rely only on the shared COCO
detector (which has no "tractor" class at all, and Indian-truck appearance
sometimes differs from COCO's training distribution).

WHAT THIS IS: a classical-features + Gradient Boosting classifier (color
histogram, HOG shape descriptor, edge density, aspect ratio) trained on
326 real tractor/truck photos. NOT a from-scratch CNN — two CNN attempts on
this dataset collapsed to predicting only the majority class ("truck") for
every input, which is a known failure mode when a from-scratch network has
too little data (344 training crops, only 96 of them tractor) to learn real
features before it finds the trivial "always guess majority" shortcut.
Classical, low-parameter-count features generalize far better at this data
scale — see backend/scripts/train_vehicle_ml.py for both attempts.

HONEST ACCURACY (45 held-out test crops, never seen in training):
    accuracy:         60%
    tractor recall:   40%   (catches 6 of 15 real tractors)
    tractor precision: 40%
    truck recall:     70%
    truck precision:  70%
  This is a WEAK classifier, not a reliable one — treat its output as one
  low-confidence vote, never as a standalone decision. The tractor class
  especially is data-starved (only 96 training crops across all sources);
  more tractor photos would likely help more than any further tuning of
  this same 326-image dataset. 100% accuracy was asked for at the start of
  this task — that is not realistic for any real-world visual classifier,
  and reporting it would mean the numbers were made up.

INPUT REQUIRED: a vehicle-region crop (BGR, as from cv2) — pair with the
shared COCO detector's "truck"/"car" boxes (or any vehicle-shaped candidate
region) as the source of that crop; this module does not detect vehicles in
a full frame on its own.
"""

from pathlib import Path
from typing import Optional, Tuple

import cv2
import joblib
import numpy as np
from skimage.feature import hog

_MODEL_PATH = Path(__file__).resolve().parent / "vehicle_classifier.joblib"
RESIZE = (128, 128)


class VehicleClassifier:
    def __init__(self, model_path: Optional[Path] = None):
        path = model_path or _MODEL_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"vehicle_classifier.joblib not found at {path}. See "
                "backend/scripts/train_vehicle_ml.py to reproduce it."
            )
        bundle = joblib.load(path)
        self.model = bundle["model"]
        self.scaler = bundle["scaler"]
        self.feature_names = bundle["feature_names"]
        self.classes = bundle["classes"]  # ["tractor", "truck"]
        self.test_accuracy = bundle.get("test_accuracy")

    def _extract_features(self, crop_bgr: np.ndarray, orig_w: int, orig_h: int) -> dict:
        img = cv2.resize(crop_bgr, RESIZE)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        feats = {"aspect_ratio": orig_w / max(orig_h, 1), "log_area": float(np.log(max(orig_w * orig_h, 1)))}

        for i, ch in enumerate(["h", "s", "v"]):
            hist = cv2.calcHist([hsv], [i], None, [8], [0, 256]).flatten()
            hist = hist / (hist.sum() + 1e-6)
            for j, v in enumerate(hist):
                feats[f"hsv_{ch}_{j}"] = float(v)

        edges = cv2.Canny(gray, 100, 200)
        feats["edge_density"] = float(edges.mean() / 255.0)

        hog_feat = hog(gray, orientations=6, pixels_per_cell=(32, 32),
                        cells_per_block=(2, 2), feature_vector=True)
        feats["hog_mean"] = float(hog_feat.mean())
        feats["hog_std"] = float(hog_feat.std())
        feats["hog_max"] = float(hog_feat.max())

        feats["top_dark_fraction"] = float((gray[:10, :] < 128).mean())
        return feats

    def predict(self, crop_bgr: np.ndarray) -> Tuple[str, float]:
        """crop_bgr: a vehicle-region crop (any size, BGR as from cv2).
        Returns (label, confidence) — label is 'tractor' or 'truck'."""
        h, w = crop_bgr.shape[:2]
        feats = self._extract_features(crop_bgr, w, h)
        x = np.array([[feats[name] for name in self.feature_names]])
        x_scaled = self.scaler.transform(x)
        proba = self.model.predict_proba(x_scaled)[0]
        idx = int(np.argmax(proba))
        return self.classes[idx], float(proba[idx])


# --- Integration sketch ---
#
#   from app.plugins.counting.vehicle_classifier import VehicleClassifier
#
#   _vehicle_clf = VehicleClassifier()  # load once
#
#   for det in coco_detections:
#       if det.class_name in ("truck", "car"):  # candidate vehicle box
#           crop = frame[y1:y2, x1:x2]
#           label, conf = _vehicle_clf.predict(crop)
#           # Given ~60% accuracy, treat this as a hint, not ground truth —
#           # e.g. only relabel a "truck" detection as "tractor" when conf is
#           # reasonably high (>0.65), and log/monitor how often it disagrees
#           # with what a human reviewing footage would call it before
#           # trusting it for anything automated (alerts, counts, billing).
