"""
YOLO-based fire and smoke detector.

Model strategy (in order of preference at runtime):
  1. backend/runs_fire/train/weights/best.pt  — your own fine-tuned weights
     (produced by train_fire_dataset.py; base model: yolo11n or yolo11s)
  2. backend/app/plugins/fire/fire_yolo.pt    — drop any fire YOLO .pt here
  3. backend/app/plugins/fire/fire_yolo_cached.pt — auto-download cache
  4. Auto-download yolov11-fire best.pt from GitHub (spacewalk01 model)
  5. Roboflow Serverless API fallback (if ROBOFLOW_API_KEY is set)

YOLO version guide:
  YOLO11n  — default base for fine-tuning (5.4 MB, +2% mAP vs v8n)
  YOLO11s  — recommended for GPU deployment (better accuracy, fast with FP16)
  YOLOv10n — NMS-free, lowest latency on TensorRT (set USE_YOLOV10=true)

Why not in DeepStream's primary inference (PGIE): the PGIE trunk is shared
across every camera and plugin. Swapping it to a fire model breaks PPE, ANPR,
intrusion, and people counting. Running YOLO here means it only executes for
cameras that have FireDetectionPlugin enabled.
"""

import os
from typing import List

from loguru import logger

from app.plugins.fire.detector import Candidate, FIRE, SMOKE

# Path to the primary trained fire YOLO model (produced by train_fire_dataset.py).
# Base model for training: yolo11n.pt or yolo11s.pt (set via --model flag).
_BEST_TRAINED_MODEL_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "runs_fire", "train", "weights", "best.pt")
)

# Path to place any custom fire YOLO .pt (checked second).
_LOCAL_MODEL_PATH = os.path.join(os.path.dirname(__file__), "fire_yolo.pt")

# Auto-download destination — written once, reused on every restart.
_CACHED_MODEL_PATH = os.path.join(os.path.dirname(__file__), "fire_yolo_cached.pt")

# Public fire+smoke YOLO11 model (spacewalk01, GitHub releases).
# 2 classes: fire=0, smoke=1.
_DOWNLOAD_URL = (
    "https://github.com/spacewalk01/yolov11-fire-detection"
    "/releases/download/v1.0/best.pt"
)

# Class names as they appear in the fire-specific model.
_CLASS_FIRE  = "fire"
_CLASS_SMOKE = "smoke"

# Calibrated confidence thresholds for live camera feeds
_CONFIDENCE_THRESHOLD = 0.45
_SMOKE_CONFIDENCE_THRESHOLD = 0.35

# Roboflow default model configuration
_DEFAULT_ROBOFLOW_MODEL = "fire-detection-for-khkt/3"

# Device for local inference (resolved once at import time via gpu_utils)
try:
    from gpu_utils import get_device, get_fp16_enabled
    _INFER_DEVICE = get_device()
    _USE_FP16 = get_fp16_enabled()
except Exception:
    _INFER_DEVICE = "cpu"
    _USE_FP16 = False

# YOLOv10 NMS-free mode — set USE_YOLOV10=true in .env for lowest latency
# on TensorRT GPU deployments. Requires: pip install ultralytics>=8.3
# YOLOv10 uses end-to-end inference (no NMS post-processing step) which
# reduces per-frame latency by ~5-10ms on GPU.
_USE_YOLOV10 = os.getenv("USE_YOLOV10", "false").lower() in ("true", "1", "yes")


class YoloFireDetector:
    """
    Fire/smoke detector supporting:
      1. Roboflow Serverless API (if ROBOFLOW_API_KEY is set)
      2. Local YOLO model — YOLO11n/YOLO11s (recommended) or YOLOv10n (NMS-free)
         Base model used for training: yolo11n.pt (set USE_YOLOV10=true for v10)
      3. Graceful fallback to CV2 HSV frame analyzer
    """

    def __init__(self) -> None:
        self._model = None
        self._model_has_fire_classes = False
        self._available = True
        
        # Roboflow config & rate-limiting (max 1 request per second to preserve API quota)
        self._roboflow_api_key = os.getenv("ROBOFLOW_API_KEY", "").strip()
        self._roboflow_model_id = os.getenv("ROBOFLOW_MODEL_ID", _DEFAULT_ROBOFLOW_MODEL).strip()
        self._roboflow_workspace = os.getenv("ROBOFLOW_WORKSPACE", "").strip()
        self._roboflow_workflow_id = os.getenv("ROBOFLOW_WORKFLOW_ID", "").strip()
        self._roboflow_client = None
        self._use_roboflow = False
        self._last_roboflow_call_time = 0.0
        self._last_roboflow_candidates: List[Candidate] = []
        self._roboflow_interval_sec = 1.0  # Throttle: 1 call/sec saves 97% API credits

    def warm(self) -> None:
        """Pre-load at plugin init so the first camera frame isn't slow."""
        if self._model is not None or self._use_roboflow or not self._available:
            return
        self._load()

    def _load(self) -> None:
        # Check Roboflow Serverless API option first
        if self._roboflow_api_key:
            self._use_roboflow = True
            mode_desc = (
                f"workflow '{self._roboflow_workspace}/{self._roboflow_workflow_id}'"
                if (self._roboflow_workspace and self._roboflow_workflow_id)
                else f"model '{self._roboflow_model_id}'"
            )
            logger.info(
                f"YoloFireDetector: using Roboflow Serverless API with {mode_desc} "
                f"(Rate limited to 1 call/sec)"
            )
            try:
                from inference_sdk import InferenceHTTPClient, InferenceConfiguration  # noqa: PLC0415
                self._roboflow_client = InferenceHTTPClient(
                    api_url="https://serverless.roboflow.com",
                    api_key=self._roboflow_api_key,
                ).configure(InferenceConfiguration(api_key_transport="header"))
                logger.info("YoloFireDetector: inference_sdk client initialized")
            except ImportError:
                logger.info(
                    "YoloFireDetector: inference_sdk not installed — "
                    "will use direct HTTP requests for Roboflow API"
                )
            return

        # Local Ultralytics PyTorch YOLO loading
        try:
            from ultralytics import YOLO  # noqa: PLC0415
        except ImportError:
            logger.warning(
                "YoloFireDetector: ultralytics not installed and ROBOFLOW_API_KEY not set — "
                "YOLO fire detection disabled. Set ROBOFLOW_API_KEY or run: pip install ultralytics"
            )
            self._available = False
            return

        model_path = self._resolve_model_path()
        if model_path is None:
            logger.error(
                "YoloFireDetector: no model available — "
                "YOLO fire detection disabled. "
                f"Place best.pt at {_BEST_TRAINED_MODEL_PATH} or set ROBOFLOW_API_KEY."
            )
            self._available = False
            return

        try:
            # YOLOv10 NMS-free mode (USE_YOLOV10=true in .env)
            if _USE_YOLOV10:
                try:
                    from ultralytics import YOLOv10  # noqa: PLC0415
                    logger.info(
                        "YoloFireDetector: YOLOv10 NMS-free mode enabled — "
                        "no post-processing NMS step, lower latency on TensorRT"
                    )
                    ModelClass = YOLOv10
                except ImportError:
                    logger.warning(
                        "YoloFireDetector: USE_YOLOV10=true but YOLOv10 class not found — "
                        "falling back to YOLO (upgrade ultralytics: pip install -U ultralytics)"
                    )
                    ModelClass = YOLO
            else:
                ModelClass = YOLO  # YOLO11n/YOLO11s (default)

            self._model = ModelClass(model_path)
            raw_names = self._model.names or {}
            names = [str(n).lower() for n in raw_names.values()]
            
            # DO NOT USE COCO 80-class models for fire detection
            if len(names) == 80 and "person" in names and "bicycle" in names:
                logger.error(
                    f"YoloFireDetector: Model at {model_path} is a COCO 80-class model! "
                    f"COCO models cannot be used for fire detection. "
                    f"Loading stopped. Ensure {_BEST_TRAINED_MODEL_PATH} is loaded."
                )
                self._model = None
                self._available = False
                return

            # Move model to the best available device (GPU/CPU)
            try:
                self._model.to(_INFER_DEVICE)
                if _USE_FP16 and _INFER_DEVICE != "cpu":
                    self._model.half()  # FP16 for ~2x GPU throughput
                    logger.info(
                        f"YoloFireDetector: inference on {_INFER_DEVICE} with FP16 enabled"
                    )
                else:
                    logger.info(
                        f"YoloFireDetector: inference on {_INFER_DEVICE} (FP32)"
                    )
            except Exception as dev_exc:
                logger.warning(
                    f"YoloFireDetector: could not move model to {_INFER_DEVICE} — {dev_exc}; "
                    "falling back to CPU"
                )

            self._model_has_fire_classes = any(
                n in (_CLASS_FIRE, _CLASS_SMOKE) or "fire" in n or "smoke" in n
                for n in names
            )
            if self._model_has_fire_classes:
                arch = "YOLOv10 (NMS-free)" if _USE_YOLOV10 else "YOLO11"
                # Format required startup log block
                class_mapping_txt = "\n".join(
                    f"{cid} -> {cname}" for cid, cname in raw_names.items()
                )
                init_banner = (
                    "\n========================================\n"
                    "FIRE MODEL INITIALIZATION\n"
                    "========================================\n\n"
                    f"Architecture:\n{arch}\n\n"
                    f"Model:\n{model_path}\n\n"
                    f"Device:\n{_INFER_DEVICE} (FP16={_USE_FP16})\n\n"
                    f"Classes:\n{class_mapping_txt}\n\n"
                    "Model loaded successfully: TRUE\n"
                    "========================================"
                )
                logger.info(init_banner)
            else:
                logger.warning(
                    f"YoloFireDetector: model at {model_path} has no fire/smoke "
                    f"classes — YOLO path disabled."
                )
                self._model = None
                self._available = False
        except Exception as exc:
            logger.error(f"YoloFireDetector: model load failed — {exc}")
            self._available = False

    def _resolve_model_path(self) -> str:
        """
        Returns the path of the best available local model, or None.
        Priority: fine-tuned best.pt (YOLO11) > fire_yolo.pt > cached download
        """
        if os.path.exists(_BEST_TRAINED_MODEL_PATH):
            logger.info(
                f"YoloFireDetector: using fine-tuned YOLO11 model: {_BEST_TRAINED_MODEL_PATH}"
            )
            return _BEST_TRAINED_MODEL_PATH

        if os.path.exists(_LOCAL_MODEL_PATH):
            logger.info(f"YoloFireDetector: using local model: {_LOCAL_MODEL_PATH}")
            return _LOCAL_MODEL_PATH

        if os.path.exists(_CACHED_MODEL_PATH):
            logger.info(f"YoloFireDetector: using cached model {_CACHED_MODEL_PATH}")
            return _CACHED_MODEL_PATH

        downloaded = self._try_download(_DOWNLOAD_URL, _CACHED_MODEL_PATH)
        if downloaded:
            return _CACHED_MODEL_PATH

        return None

    @staticmethod
    def _try_download(url: str, dest: str) -> bool:
        """Download a model file. Returns True on success."""
        try:
            import requests  # noqa: PLC0415
            logger.info(f"YoloFireDetector: downloading fire model from {url} ...")
            r = requests.get(url, timeout=60, allow_redirects=True, stream=True)
            if r.status_code != 200:
                logger.warning(
                    f"YoloFireDetector: download returned HTTP {r.status_code}"
                )
                return False
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
            size_kb = os.path.getsize(dest) // 1024
            logger.info(f"YoloFireDetector: downloaded {size_kb} KB to {dest}")
            return True
        except Exception as exc:
            logger.warning(f"YoloFireDetector: download failed — {exc}")
            if os.path.exists(dest):
                os.remove(dest)
            return False

    def detect(self, frame) -> List[Candidate]:
        """
        Run inference on one BGR frame. Returns Candidates matching the shape
        of FrameAnalyzer.analyze() so the adapter can merge both lists.
        Never raises.
        """
        if not self._available:
            return []

        if self._model is None and not self._use_roboflow:
            self._load()
            if self._model is None and not self._use_roboflow:
                return []

        try:
            if self._use_roboflow:
                return self._infer_roboflow(frame)
            return self._infer_local(frame)
        except Exception as exc:
            logger.error(f"YoloFireDetector.detect() failed: {exc}")
            return []

    def _infer_roboflow(self, frame) -> List[Candidate]:
        """Infer using Roboflow Serverless API (workflow or model) with rate limiting."""
        import time  # noqa: PLC0415

        now = time.time()
        # Rate limit check: reuse cached results if called within 1 second
        if now - self._last_roboflow_call_time < self._roboflow_interval_sec:
            return self._last_roboflow_candidates

        self._last_roboflow_call_time = now
        h, w = frame.shape[:2]
        frame_area = float(h * w) or 1.0
        candidates: List[Candidate] = []

        try:
            predictions = []
            if self._roboflow_client is not None:
                # Check if user specified a Roboflow Workflow
                if self._roboflow_workspace and self._roboflow_workflow_id:
                    result = self._roboflow_client.run_workflow(
                        workspace_name=self._roboflow_workspace,
                        workflow_id=self._roboflow_workflow_id,
                        images={"image": frame},
                        use_cache=True,
                    )
                    if isinstance(result, list) and len(result) > 0:
                        first = result[0]
                        p_data = first.get("predictions", {})
                        if isinstance(p_data, dict):
                            predictions = p_data.get("predictions", [])
                        elif isinstance(p_data, list):
                            predictions = p_data
                else:
                    result = self._roboflow_client.infer(frame, model_id=self._roboflow_model_id)
                    if isinstance(result, dict):
                        predictions = result.get("predictions", [])
            else:
                import base64  # noqa: PLC0415
                import cv2  # noqa: PLC0415
                import requests  # noqa: PLC0415

                _, buffer = cv2.imencode(".jpg", frame)
                img_b64 = base64.b64encode(buffer).decode("ascii")
                url = (
                    f"https://detect.roboflow.com/{self._roboflow_model_id}"
                    f"?api_key={self._roboflow_api_key}"
                    f"&confidence={int(min(_CONFIDENCE_THRESHOLD, _SMOKE_CONFIDENCE_THRESHOLD) * 100)}"
                )
                resp = requests.post(
                    url,
                    data=img_b64,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=5,
                )
                if resp.status_code == 200:
                    predictions = resp.json().get("predictions", [])
                else:
                    logger.warning(f"Roboflow API returned HTTP {resp.status_code}")

            for pred in predictions:
                conf = float(pred.get("confidence", 0.0))
                cls_name = str(pred.get("class", "")).lower()
                if _CLASS_FIRE not in cls_name and _CLASS_SMOKE not in cls_name:
                    continue

                min_conf = _SMOKE_CONFIDENCE_THRESHOLD if _CLASS_SMOKE in cls_name else _CONFIDENCE_THRESHOLD
                if conf < min_conf:
                    continue

                xc, yc = float(pred["x"]), float(pred["y"])
                bw, bh = float(pred["width"]), float(pred["height"])

                x1 = max(0, int(xc - bw / 2.0))
                y1 = max(0, int(yc - bh / 2.0))
                x2 = min(w, int(xc + bw / 2.0))
                y2 = min(h, int(yc + bh / 2.0))

                box_area = max(0.0, float((x2 - x1) * (y2 - y1)))
                area_frac = box_area / frame_area
                kind = FIRE if _CLASS_FIRE in cls_name else SMOKE

                candidates.append(
                    Candidate(
                        kind=kind,
                        bbox=[x1, y1, x2, y2],
                        area_frac=area_frac,
                        score=conf,
                    )
                )
        except Exception as exc:
            logger.error(f"Roboflow inference error: {exc}")

        self._last_roboflow_candidates = candidates
        return candidates

    def _infer_local(self, frame) -> List[Candidate]:
        """Infer using local Ultralytics PyTorch YOLO model."""
        # Run at the lower of the two per-class floors so a genuine smoke box
        # isn't discarded by ultralytics before we get a chance to apply
        # smoke's own (lower) threshold below.
        run_conf = min(_CONFIDENCE_THRESHOLD, _SMOKE_CONFIDENCE_THRESHOLD)
        results = self._model(
            frame, verbose=False, conf=run_conf,
            device=_INFER_DEVICE,
            half=(_USE_FP16 and _INFER_DEVICE != "cpu"),
        )
        if not results:
            return []

        h, w = frame.shape[:2]
        frame_area = float(h * w) or 1.0
        candidates: List[Candidate] = []

        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = (r.names or {}).get(cls_id, "").lower()

                # Model classes: fire(0), light(1), no-fire(2), smoke(3).
                # Exact name match is safer than substring for this 4-class model.
                is_fire = ("fire" in cls_name and cls_name != "no-fire") or "flame" in cls_name
                is_smoke = "smoke" in cls_name
                is_person = "person" in cls_name
                if not (is_fire or is_smoke or is_person):
                    continue

                # Thresholds
                if is_person:
                    min_conf = 0.35
                elif is_smoke:
                    min_conf = _SMOKE_CONFIDENCE_THRESHOLD
                else:
                    min_conf = _CONFIDENCE_THRESHOLD

                if conf < min_conf:
                    continue

                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                # Flame color confirmation to eliminate non-fire false positives on room objects
                if is_fire:
                    crop = frame[y1:y2, x1:x2]
                    if crop.size > 0:
                        import cv2
                        import numpy as np
                        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                        mask1 = cv2.inRange(hsv, (0, 50, 70), (35, 255, 255))
                        mask2 = cv2.inRange(hsv, (155, 50, 70), (180, 255, 255))
                        flame_pixels = int(np.count_nonzero(mask1) + np.count_nonzero(mask2))
                        if flame_pixels < max(12, int(0.015 * crop.shape[0] * crop.shape[1])):
                            # Reject false alarm
                            continue

                box_area = max(0.0, float((x2 - x1) * (y2 - y1)))
                area_frac = box_area / frame_area
                if is_fire:
                    kind = FIRE
                elif is_smoke:
                    kind = SMOKE
                else:
                    kind = "person"

                candidates.append(Candidate(
                    kind=kind,
                    bbox=[x1, y1, x2, y2],
                    area_frac=area_frac,
                    score=conf,
                ))

        return candidates

