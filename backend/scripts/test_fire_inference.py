"""
Standalone Test Script for Fire & Smoke Detection Inference on Images & Videos.

1. Why this file exists:
   Allows testing YOLO fire/smoke detection (`fire_yolo.pt`) and hybrid candidate evaluation
   on sample images, video files (e.g. bucket11.mp4), or webcam/stream sources.

2. Why this approach was chosen:
   Uses `cv2.VideoCapture` to handle both static images and video files. Evaluates frames
   sequentially with `FrameAnalyzer` and `YoloFireDetector` so temporal state (churn, background EMA)
   settles realistically as it does on a live camera stream.

3. Alternative approaches & tradeoffs:
   - Single static frame test: Does not simulate background learning or temporal churn over video frames.
   - Full video sequence test: Accurately reflects real-time multi-frame camera detection.

4. Expected output:
   - Detailed logs for detected fire/smoke bounding boxes, scores, and frame counts across the video.
   - Saves annotated output image or video (`fire_test_output.mp4` / `fire_test_output.jpg`).
"""

import sys
import argparse
from pathlib import Path
import cv2
import numpy as np
from loguru import logger

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.plugins.fire.yolo_fire_detector import YoloFireDetector
from app.plugins.fire.detector import FrameAnalyzer, FIRE, SMOKE


def create_synthetic_fire_image() -> np.ndarray:
    """Create a synthetic test image with a warm fire-like glowing area for testing."""
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = (20, 20, 20)
    cv2.ellipse(img, (320, 240), (80, 120), 0, 0, 360, (0, 140, 255), -1)
    cv2.ellipse(img, (320, 230), (50, 80), 0, 0, 360, (0, 215, 255), -1)
    cv2.ellipse(img, (320, 210), (25, 45), 0, 0, 360, (200, 255, 255), -1)
    return img


def test_fire_inference(source_path: str = None, output_path: str = "fire_test_output.mp4"):
    logger.info("Initializing YoloFireDetector & FrameAnalyzer...")
    yolo_detector = YoloFireDetector()
    yolo_detector.warm()
    hsv_analyzer = FrameAnalyzer()

    # Determine if source is video file, image, or synthetic
    is_video = False
    cap = None
    frames_list = []

    if source_path and Path(source_path).exists():
        ext = Path(source_path).suffix.lower()
        if ext in [".mp4", ".avi", ".mov", ".mkv", ".h264"]:
            is_video = True
            cap = cv2.VideoCapture(source_path)
            logger.info(f"Loaded video file: {source_path} ({int(cap.get(cv2.CAP_PROP_FRAME_COUNT))} frames)")
        else:
            img = cv2.imread(source_path)
            if img is not None:
                frames_list.append(img)
                logger.info(f"Loaded static image: {source_path}")
            else:
                logger.error(f"Failed to read image: {source_path}")
                return
    else:
        logger.info("No valid source path provided. Using synthetic fire image.")
        frames_list.append(create_synthetic_fire_image())

    total_yolo_detections = 0
    total_hsv_detections = 0
    frame_idx = 0

    if is_video and cap is not None:
        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        out_writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            frame_idx += 1

            yolo_candidates = yolo_detector.detect(frame)
            hsv_candidates = hsv_analyzer.analyze(frame)

            total_yolo_detections += len(yolo_candidates)
            total_hsv_detections += len(hsv_candidates)

            if len(yolo_candidates) > 0 or len(hsv_candidates) > 0:
                logger.info(f"[Frame {frame_idx}] Detections -> YOLO: {len(yolo_candidates)} | HSV: {len(hsv_candidates)}")
                for c in yolo_candidates:
                    logger.info(f"   🔥 YOLO: {c.kind} | BBox: {c.bbox} | Score: {c.score:.2%}")
                for c in hsv_candidates:
                    logger.info(f"   💨 HSV:  {c.kind} | BBox: {c.bbox} | Score: {c.score:.2%}")

            # Draw annotations
            annotated = frame.copy()
            for c in hsv_candidates:
                if c.score >= 0.40:
                    x1, y1, x2, y2 = c.bbox
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)
                    cv2.putText(annotated, f"HSV:{c.kind} {c.score:.0%}", (x1, max(15, y1 - 5)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

            for c in yolo_candidates:
                if c.score >= 0.25:
                    x1, y1, x2, y2 = c.bbox
                    color = (0, 0, 255) if c.kind.lower() == FIRE else (255, 255, 0)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
                    cv2.putText(annotated, f"YOLO:{c.kind} {c.score:.0%}", (x1, max(30, y1 - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            out_writer.write(annotated)

        cap.release()
        out_writer.release()
        logger.info(f"=== Video Processing Finished ===")
        logger.info(f"Total Frames: {frame_idx} | YOLO Detections: {total_yolo_detections} | HSV Detections: {total_hsv_detections}")
        logger.info(f"Annotated output saved to: {Path(output_path).resolve()}")

    else:
        # Static image / synthetic frame processing
        frame = frames_list[0]
        yolo_candidates = yolo_detector.detect(frame)
        hsv_candidates = hsv_analyzer.analyze(frame)

        logger.info(f"Single Frame Detections -> YOLO: {len(yolo_candidates)} | HSV: {len(hsv_candidates)}")
        for c in yolo_candidates:
            logger.info(f"  🔥 YOLO: {c.kind} | BBox: {c.bbox} | Score: {c.score:.2%}")
        for c in hsv_candidates:
            logger.info(f"  💨 HSV:  {c.kind} | BBox: {c.bbox} | Score: {c.score:.2%}")

        annotated = frame.copy()
        for c in hsv_candidates:
            x1, y1, x2, y2 = c.bbox
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.putText(annotated, f"HSV:{c.kind} {c.score:.0%}", (x1, max(15, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        for c in yolo_candidates:
            x1, y1, x2, y2 = c.bbox
            color = (0, 0, 255) if c.kind.lower() == FIRE else (255, 255, 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
            cv2.putText(annotated, f"YOLO:{c.kind} {c.score:.0%}", (x1, max(30, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        out_img_path = output_path if output_path.endswith((".jpg", ".png")) else "fire_test_output.jpg"
        cv2.imwrite(out_img_path, annotated)
        logger.info(f"Annotated image saved to: {Path(out_img_path).resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Fire Detection Inference")
    parser.add_argument("--image", type=str, help="Path to input image or video file", default=None)
    parser.add_argument("--output", type=str, help="Path to save annotated output file", default="fire_test_output.mp4")
    args = parser.parse_args()

    test_fire_inference(source_path=args.image, output_path=args.output)
