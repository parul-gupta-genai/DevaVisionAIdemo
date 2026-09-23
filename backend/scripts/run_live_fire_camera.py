"""
Live Real-Time Fire, Smoke, and People Detection GUI Window.

Features:
- Real-time Human / Person Detection (High-Precision COCO YOLOv8) -> Green Bounding Box
- Real-time Fire Detection (Specialist Fire Detector with Flame Verification) -> Red Bounding Box
- Real-time Smoke Detection (Specialist Smoke Plume Detector) -> Cyan Bounding Box
- Live Dynamic Counter: Fire, Smoke, People, FPS, and Confidences on top banner.
"""

import sys
import time
import argparse
from pathlib import Path
import cv2
import numpy as np
from loguru import logger
from ultralytics import YOLO

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.plugins.fire.yolo_fire_detector import YoloFireDetector


def run_live_detection(source="0"):
    logger.info("Loading YOLO Models (Fire, Smoke & People Detectors)...")
    
    # 1. Fire and Smoke Specialist Detector
    fire_detector = YoloFireDetector()
    fire_detector.warm()

    # 2. High-Accuracy General Person Detector (COCO Pre-trained YOLOv8n)
    person_model = YOLO("yolov8n.pt")

    # Determine source (int for webcam, string for video/image)
    if source.isdigit():
        src = int(source)
        logger.info(f"Opening Live Webcam (Device {src})...")
    else:
        src = source
        logger.info(f"Opening Video/Media Source: {src}")

    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        logger.error(f"Cannot open video source: {source}")
        print(f"\n[ERROR] Camera / Video source '{source}' open nahi ho paya.\n")
        return

    window_name = "DevaVisionAI - Live AI Detector (Fire, Smoke & People)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1024, 680)

    fps_count = 0
    fps_start_time = time.time()
    fps_display = 0.0

    print("\n=======================================================")
    print(" 🚀 LIVE FIRE, SMOKE & PEOPLE DETECTION WINDOW STARTED")
    print("=======================================================")
    print(" 🟢 GREEN: Person Detected")
    print(" 🔴 RED:   Fire Detected")
    print(" 🔵 CYAN:  Smoke Detected")
    print("-------------------------------------------------------")
    print(" - Press 'q' to Quit window")
    print(" - Press 's' to Save annotated screenshot")
    print("=======================================================\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            if not str(source).isdigit():
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            else:
                break

        h, w = frame.shape[:2]

        # Calculate FPS
        fps_count += 1
        elapsed = time.time() - fps_start_time
        if elapsed >= 1.0:
            fps_display = fps_count / elapsed
            fps_count = 0
            fps_start_time = time.time()

        # 1. Detect Fire & Smoke
        fire_candidates = fire_detector.detect(frame)

        # 2. Detect People using High-Precision Person Detector
        person_results = person_model(frame, classes=[0], conf=0.40, verbose=False)
        person_boxes = []
        if person_results and person_results[0].boxes is not None:
            for b in person_results[0].boxes:
                conf = float(b.conf[0])
                coords = [int(v) for v in b.xyxy[0].tolist()]
                person_boxes.append((conf, coords))

        # Counters
        fire_count = 0
        smoke_count = 0
        people_count = len(person_boxes)

        # Draw People (Green)
        for conf, (x1, y1, x2, y2) in person_boxes:
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            color = (0, 255, 0)
            label = f"PERSON {conf:.0%}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame, (x1, max(0, y1 - 24)), (x1 + tw + 8, y1), color, -1)
            cv2.putText(frame, label, (x1 + 4, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

        # Draw Fire & Smoke
        for c in fire_candidates:
            if c.kind.lower() == "person":
                continue  # Handled by high-precision person detector above

            x1, y1, x2, y2 = c.bbox
            kind = c.kind.lower()
            conf = c.score

            if kind == "fire":
                fire_count += 1
                color = (0, 0, 255)      # Red for Fire
                label = f"FIRE {conf:.0%}"
            else:
                smoke_count += 1
                color = (255, 220, 0)    # Cyan for Smoke
                label = f"SMOKE {conf:.0%}"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            cv2.rectangle(frame, (x1, max(0, y1 - 26)), (x1 + tw + 10, y1), color, -1)
            cv2.putText(frame, label, (x1 + 5, y1 - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        # Top Overlay Banner
        banner_color = (0, 0, 180) if (fire_count > 0 or smoke_count > 0) else (35, 35, 35)
        cv2.rectangle(frame, (0, 0), (w, 42), banner_color, -1)

        status_text = f"DevaVisionAI Live | FPS: {fps_display:.1f} | People: {people_count} | Fire: {fire_count} | Smoke: {smoke_count}"
        cv2.putText(frame, status_text, (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        # Show frame
        cv2.imshow(window_name, frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:  # 'q' or ESC
            break
        elif key == ord('s'):
            filename = f"live_snapshot_{int(time.time())}.jpg"
            cv2.imwrite(filename, frame)
            logger.info(f"Saved snapshot to {filename}")

    cap.release()
    cv2.destroyAllWindows()
    logger.info("Live detection window closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live AI Detector (Fire, Smoke & People)")
    parser.add_argument("--source", "-s", type=str, default="0", help="Camera index (0) or path to video file/stream")
    args = parser.parse_args()

    run_live_detection(source=args.source)
