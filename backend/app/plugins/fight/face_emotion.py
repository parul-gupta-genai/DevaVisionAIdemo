"""
Facial-expression aggression signal for FightDetectionPlugin.

WHAT THIS IS: a pretrained facial-emotion classifier (Emotion-FERPlus, from
the ONNX Model Zoo — https://github.com/onnx/models/tree/main/validated/
vision/body_analysis/emotion_ferplus). Given a face crop, it scores 8
emotions: neutral, happiness, surprise, sadness, anger, disgust, fear,
contempt. This module turns that into a single "aggression_score" (anger +
disgust, the two most associated with visible violent intent) per detected
face, using OpenCV's face detector already shipped in this project
(face_detection_yunet_2023mar.onnx under backend/detection/).

No training was needed for this one — it's a ready-made, well-established
model (trained on the FER+ dataset), not something built for this project
specifically. Runs via cv2.dnn — no PyTorch/CUDA, ~35MB, fast on CPU.

IMPORTANT — READ BEFORE WIRING THIS IN AS A PRIMARY SIGNAL:
  Face-expression recognition needs a reasonably sized, in-focus,
  front/near-frontal face. That's realistic for entrance/reception/
  checkpoint-style cameras, but during an actual physical scuffle on a
  typical wide-angle CCTV camera, faces are usually small, motion-blurred,
  turned away, or occluded — exactly when you'd most want the signal. In
  quick testing against the uploaded RLVS violence clips (wide, low-res,
  fast-moving altercations), YuNet detected essentially no usable faces at
  all in a 40-clip sample. That doesn't mean this is useless — it means it
  is a much better fit as a SEPARATE early-warning signal for cameras with
  clear, closer faces (e.g. flagging visibly angry/aggressive expressions
  before or around a confrontation, at an entrance or a queue), not as a
  drop-in replacement or even a reliable co-signal for the motion-based
  ml_classifier.py during an actual wide-shot scuffle. Treat it as a third,
  independent, lower-confidence signal — validate its false-positive rate
  (anger/disgust from someone just talking loudly, laughing hard, etc.) on
  real camera footage before alerting on it alone.
"""

from pathlib import Path
from typing import List, Optional, TypedDict

import cv2
import numpy as np

_EMOTION_MODEL_PATH = Path(__file__).resolve().parent / "models" / "emotion-ferplus-8.onnx"
_FACE_MODEL_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "detection" / "face_detection_yunet_2023mar.onnx"
)

EMOTION_LABELS = ["neutral", "happiness", "surprise", "sadness", "anger", "disgust", "fear", "contempt"]
# Anger + disgust are the two most reliably associated with visible
# aggression/hostility in the FER+ taxonomy. Fear is deliberately excluded —
# a victim's fearful expression is not itself a sign of aggression and
# including it would conflate "someone is scared" with "someone is being
# aggressive", which are opposite roles in the same incident.
AGGRESSION_EMOTIONS = ["anger", "disgust"]


class FaceEmotionResult(TypedDict):
    bbox: List[float]  # [x, y, w, h]
    emotion: str        # highest-scoring label
    scores: dict         # label -> probability
    aggression_score: float  # anger + disgust probability, in [0, 1]


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()


class FaceEmotionClassifier:
    def __init__(self, emotion_model_path: Optional[Path] = None, face_model_path: Optional[Path] = None,
                 face_score_threshold: float = 0.6):
        e_path = emotion_model_path or _EMOTION_MODEL_PATH
        f_path = face_model_path or _FACE_MODEL_PATH
        if not e_path.exists():
            raise FileNotFoundError(f"Emotion model not found at {e_path}")
        if not f_path.exists():
            raise FileNotFoundError(f"Face detector model not found at {f_path}")

        self.emotion_net = cv2.dnn.readNetFromONNX(str(e_path))
        self._face_detector_path = str(f_path)
        self._face_score_threshold = face_score_threshold
        self._face_detector = None  # created lazily once we know frame size
        self._face_detector_size = None

    def _get_face_detector(self, w: int, h: int):
        if self._face_detector is None or self._face_detector_size != (w, h):
            self._face_detector = cv2.FaceDetectorYN.create(
                self._face_detector_path, "", (w, h),
                score_threshold=self._face_score_threshold,
            )
            self._face_detector_size = (w, h)
        return self._face_detector

    def _classify_face(self, face_crop_bgr: np.ndarray) -> dict:
        gray = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (64, 64))
        blob = gray.astype(np.float32).reshape(1, 1, 64, 64)
        self.emotion_net.setInput(blob)
        logits = self.emotion_net.forward().flatten()
        probs = _softmax(logits)
        return {label: float(p) for label, p in zip(EMOTION_LABELS, probs)}

    def analyze(self, frame_bgr: np.ndarray) -> List[FaceEmotionResult]:
        """Detect faces in a frame and score each one's emotions."""
        h, w = frame_bgr.shape[:2]
        detector = self._get_face_detector(w, h)
        _, faces = detector.detect(frame_bgr)
        if faces is None:
            return []

        results: List[FaceEmotionResult] = []
        for f in faces:
            x, y, fw, fh = [max(0, int(v)) for v in f[:4]]
            fw, fh = min(fw, w - x), min(fh, h - y)
            if fw <= 0 or fh <= 0:
                continue
            crop = frame_bgr[y:y + fh, x:x + fw]
            if crop.size == 0:
                continue
            scores = self._classify_face(crop)
            top_emotion = max(scores, key=scores.get)
            aggression = sum(scores[e] for e in AGGRESSION_EMOTIONS)
            results.append({
                "bbox": [float(x), float(y), float(fw), float(fh)],
                "emotion": top_emotion,
                "scores": scores,
                "aggression_score": float(aggression),
            })
        return results


# --- Integration sketch (as a THIRD, independent signal alongside the
# heuristic in adapter.py and the motion classifier in ml_classifier.py —
# see that file's module docstring for how those two already combine) ---
#
#   _face_emotion = FaceEmotionClassifier()   # load once
#
#   results = _face_emotion.analyze(latest_frame)
#   max_aggression = max((r["aggression_score"] for r in results), default=0.0)
#   # e.g.: only let this ADD confidence to an already-flagged heuristic hit,
#   # never trigger an event on its own — see the module docstring above for
#   # why (unreliable on wide-shot scuffle footage, better suited to
#   # close-up cameras as an early-warning signal instead).
