"""
NVIDIA / OpenCV Accelerated Optical Flow Analysis Engine for DevaVisionAI.
Analyzes physical pixel motion dynamics (Upward Plume Drift, Dispersion, Flame Flicker)
to verify genuine Smoke & Fire and eliminate false positives.
"""

import cv2
import numpy as np
from typing import Tuple, Dict, Any, Optional

class OpticalFlowMotionVerifier:
    """
    High-Performance Optical Flow Engine with NVIDIA GPU acceleration support
    and automatic vectorized fallback.
    """

    def __init__(self, use_gpu: bool = True, downscale_factor: float = 0.5):
        self.downscale = downscale_factor
        self.prev_gray: Optional[np.ndarray] = None
        self.gpu_available = False
        self.cuda_flow = None

        # Attempt to initialize OpenCV CUDA / NVIDIA Optical Flow if available
        if use_gpu:
            try:
                if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                    self.cuda_flow = cv2.cuda_FarnebackOpticalFlow.create(
                        numLevels=3, pyrScale=0.5, fastPyramids=False, winSize=15,
                        numIters=3, polyN=5, polySigma=1.2, flags=0
                    )
                    self.gpu_available = True
                    print("⚡ NVIDIA CUDA Optical Flow Engine Initialized successfully!")
            except Exception:
                self.gpu_available = False

        if not self.gpu_available:
            print("🚀 Using Fast Vectorized Optical Flow Engine (CPU/SIMD mode)")

    def update(self, frame_bgr: np.ndarray) -> Optional[np.ndarray]:
        """
        Computes the dense optical flow field (dx, dy) for the current frame.
        Returns: (H, W, 2) array containing flow vectors in full-frame coordinates.
        """
        # Downscale for ultra-high FPS motion calculation
        h, w = frame_bgr.shape[:2]
        small_w = int(w * self.downscale)
        small_h = int(h * self.downscale)
        small = cv2.resize(frame_bgr, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
        curr_gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        if self.prev_gray is None:
            self.prev_gray = curr_gray
            return None

        # Compute Flow Field
        if self.gpu_available and self.cuda_flow is not None:
            try:
                gpu_prev = cv2.cuda_GpuMat()
                gpu_curr = cv2.cuda_GpuMat()
                gpu_prev.upload(self.prev_gray)
                gpu_curr.upload(self.curr_gray)
                gpu_flow = self.cuda_flow.calc(gpu_prev, gpu_curr, None)
                flow_small = gpu_flow.download()
            except Exception:
                flow_small = cv2.calcOpticalFlowFarneback(
                    self.prev_gray, curr_gray, None,
                    pyr_scale=0.5, levels=3, winsize=15, iterations=3, poly_n=5, poly_sigma=1.2, flags=0
                )
        else:
            flow_small = cv2.calcOpticalFlowFarneback(
                self.prev_gray, curr_gray, None,
                pyr_scale=0.5, levels=3, winsize=15, iterations=3, poly_n=5, poly_sigma=1.2, flags=0
            )

        self.prev_gray = curr_gray

        # Scale flow vectors back to original resolution
        flow = cv2.resize(flow_small, (w, h), interpolation=cv2.INTER_LINEAR)
        flow[:, :, 0] /= self.downscale
        flow[:, :, 1] /= self.downscale
        return flow

    def verify_smoke_motion(self, flow: np.ndarray, bbox: list) -> Tuple[bool, float, Dict[str, Any]]:
        """
        Verifies if the bounding box exhibits physical smoke motion dynamics:
        1. Vertical Upward Flow (vy < 0 in image coords)
        2. Spatial Volumetric Dispersion / Expansion
        3. Plume Turbulence (non-rigid motion)
        """
        if flow is None:
            return True, 0.5, {"reason": "initial_frame"}

        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = flow.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w - 1, x2), min(h - 1, y2)

        if (x2 - x1) < 10 or (y2 - y1) < 10:
            return False, 0.0, {"reason": "box_too_small"}

        roi_flow = flow[y1:y2, x1:x2]
        u = roi_flow[:, :, 0] # Horizontal flow (dx)
        v = roi_flow[:, :, 1] # Vertical flow (dy, negative is UPWARDS)

        # 1. Upward Motion Magnitude
        # Smoke particles typically move upward (dy < 0)
        upward_mask = v < -0.15
        upward_ratio = float(np.mean(upward_mask))
        mean_vy = float(np.mean(v))

        # 2. Total Motion Energy (magnitude)
        mag = np.hypot(u, v)
        mean_mag = float(np.mean(mag))
        
        # 3. Turbulent Non-Rigid Variance (rigid objects have low variance)
        u_var = float(np.var(u))
        v_var = float(np.var(v))
        turbulence_score = min(1.0, (u_var + v_var) / 4.0)

        # Smoke Verification Score Formulation
        smoke_score = 0.0
        if mean_vy < 0.05: # moving upward or floating
            smoke_score += 0.40
        if upward_ratio > 0.20: # at least 20% pixels rising
            smoke_score += 0.35
        if turbulence_score > 0.05: # turbulent diffuse dispersion
            smoke_score += 0.25

        is_verified = (smoke_score >= 0.35) or (mean_mag > 0.25 and mean_vy <= 0.2)
        
        details = {
            "upward_ratio": round(upward_ratio, 2),
            "mean_vy": round(mean_vy, 2),
            "mean_mag": round(mean_mag, 2),
            "turbulence": round(turbulence_score, 2),
            "score": round(smoke_score, 2)
        }
        return is_verified, smoke_score, details

    def verify_fire_motion(self, flow: np.ndarray, bbox: list) -> Tuple[bool, float, Dict[str, Any]]:
        """
        Verifies if the bounding box exhibits physical fire motion dynamics:
        1. High-frequency flicker & churn
        2. High velocity gradient / vorticity
        """
        if flow is None:
            return True, 0.5, {"reason": "initial_frame"}

        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = flow.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w - 1, x2), min(h - 1, y2)

        if (x2 - x1) < 6 or (y2 - y1) < 6:
            return False, 0.0, {"reason": "box_too_small"}

        roi_flow = flow[y1:y2, x1:x2]
        u = roi_flow[:, :, 0]
        v = roi_flow[:, :, 1]
        mag = np.hypot(u, v)
        
        mean_mag = float(np.mean(mag))
        std_mag = float(np.std(mag))
        flicker_score = min(1.0, std_mag / (mean_mag + 1e-4))

        is_verified = (mean_mag > 0.10) or (flicker_score > 0.20)
        details = {
            "mean_mag": round(mean_mag, 2),
            "flicker": round(flicker_score, 2)
        }
        return is_verified, flicker_score, details
