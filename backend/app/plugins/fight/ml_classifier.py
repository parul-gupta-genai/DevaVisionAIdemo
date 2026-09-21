"""
ML-based violence classifier for FightDetectionPlugin, trained on the
RLVS-style (Violence/NonViolence) dataset — see backend/scripts/ for the
feature-extraction/training scripts this model came from.

WHAT THIS DOES: given a short buffer of recent raw video frames (BGR,
as read by cv2.VideoCapture / whatever the camera pipeline hands you),
computes the same motion-energy + optical-flow features used at training
time and returns a violence probability in [0, 1].

WHY A SEPARATE MODULE (not baked into dynamics.py/rules.py): those files
work purely on person bounding boxes/tracks — they never see raw pixels.
This classifier needs actual frames (it looks at optical flow across the
whole scene, not just tracked person boxes), so it's a second, independent
signal computed from a short rolling frame buffer.

HOW TO WIRE IT IN (see integration note at the bottom of this file):
  - Don't let this fully replace the existing evaluate()/agitation logic
    on day one. Combine both signals — e.g. only raise FIGHT_DETECTED when
    BOTH the motion-heuristic (existing) AND this classifier agree, or use
    this score to veto a heuristic trigger when the classifier is very
    confident it's NOT violence (score < 0.2), and to confirm/escalate when
    it agrees (score > 0.6). Tune the exact combination against real
    footage from your cameras before trusting it standalone.

ACCURACY (on held-out test split, 200 clips, 50/50 balanced):
    accuracy: 85%   |   violence recall: 94%   |   violence precision: 80%
  i.e. it rarely misses a real fight, but has some false alarms — treat a
  positive score as "worth a closer look / corroborate with the motion
  heuristic", not as an automatic, unconditional alert on its own.
"""

from pathlib import Path
from typing import List, Optional

import cv2
import joblib
import numpy as np

_MODEL_PATH = Path(__file__).resolve().parent / "fight_classifier.joblib"

N_SAMPLE_FRAMES = 20
RESIZE_DIM = (160, 120)  # (w, h) — must match training (extract_fight_features.py)


class FightMLClassifier:
    """Loads once (e.g. at plugin init) and reused across calls."""

    def __init__(self, model_path: Optional[Path] = None):
        path = model_path or _MODEL_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"fight_classifier.joblib not found at {path}. Run "
                "backend/scripts/extract_fight_features.py + train_fight_ml.py "
                "(or the equivalent training pipeline) to produce it first."
            )
        bundle = joblib.load(path)
        self.model = bundle["model"]
        self.scaler = bundle["scaler"]
        self.feature_names = bundle["feature_names"]
        self.classes = bundle["classes"]  # ["NonViolence", "Violence"]
        self.test_accuracy = bundle.get("test_accuracy")

    def _extract_features(self, frames: List[np.ndarray]) -> Optional[dict]:
        """frames: list of BGR frames (any resolution, any count >= 2)."""
        if len(frames) < 2:
            return None

        # uniformly subsample to N_SAMPLE_FRAMES if we were given more
        if len(frames) > N_SAMPLE_FRAMES:
            idxs = np.linspace(0, len(frames) - 1, N_SAMPLE_FRAMES).astype(int)
            frames = [frames[i] for i in idxs]

        grays = [cv2.cvtColor(cv2.resize(f, RESIZE_DIM), cv2.COLOR_BGR2GRAY) for f in frames]

        diffs = np.array([
            cv2.absdiff(a, b).astype(np.float32).mean()
            for a, b in zip(grays[:-1], grays[1:])
        ])

        flow_mags, angle_hist_sum = [], np.zeros(8)
        for a, b in zip(grays[:-1], grays[1:]):
            flow = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 2, 12, 2, 5, 1.1, 0)
            mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            flow_mags.append(mag)
            hist, _ = np.histogram(ang, bins=8, range=(0, 2 * np.pi), weights=mag)
            angle_hist_sum += hist

        all_mag = np.concatenate([m.flatten() for m in flow_mags])
        per_frame_mean_mag = np.array([m.mean() for m in flow_mags])
        per_frame_max_mag = np.array([m.max() for m in flow_mags])
        angle_hist_norm = angle_hist_sum / (angle_hist_sum.sum() + 1e-6)

        feats = {
            "motion_energy_mean": diffs.mean(),
            "motion_energy_std": diffs.std(),
            "motion_energy_max": diffs.max(),
            "flow_mag_mean": all_mag.mean(),
            "flow_mag_std": all_mag.std(),
            "flow_mag_p95": np.percentile(all_mag, 95),
            "flow_mag_max": all_mag.max(),
            "per_frame_mean_mag_std": per_frame_mean_mag.std(),
            "per_frame_max_mag_mean": per_frame_max_mag.mean(),
            "high_motion_frame_fraction": float(
                (per_frame_mean_mag > np.percentile(per_frame_mean_mag, 50)).mean()
            ),
        }
        for i, v in enumerate(angle_hist_norm):
            feats[f"angle_hist_{i}"] = v
        return {k: float(v) for k, v in feats.items()}

    def score(self, frames: List[np.ndarray]) -> Optional[float]:
        """Returns violence probability in [0,1], or None if not enough frames."""
        feats = self._extract_features(frames)
        if feats is None:
            return None
        x = np.array([[feats[name] for name in self.feature_names]])
        x_scaled = self.scaler.transform(x)
        proba = self.model.predict_proba(x_scaled)[0]
        violence_idx = self.classes.index("Violence")
        return float(proba[violence_idx])


# --- Integration sketch (adapt to how frames actually flow through your
# per-camera pipeline in deepstream_pyds/main.py or camera_manager.py) ---
#
#   from collections import deque
#   from app.plugins.fight.ml_classifier import FightMLClassifier
#
#   _classifier = FightMLClassifier()               # load once
#   _frame_buffers: dict[str, deque] = {}            # per camera_id
#
#   def on_frame(camera_id: str, frame_bgr):
#       buf = _frame_buffers.setdefault(camera_id, deque(maxlen=20))
#       buf.append(frame_bgr)
#       if len(buf) == buf.maxlen:                   # every ~time window
#           ml_score = _classifier.score(list(buf))
#           # combine with the existing evaluate()/agitation signal, e.g.:
#           #   if heuristic_flagged and ml_score is not None and ml_score > 0.5:
#           #       raise FIGHT_DETECTED
#           #   elif heuristic_flagged and ml_score is not None and ml_score < 0.2:
#           #       suppress (likely false positive from the heuristic alone)
