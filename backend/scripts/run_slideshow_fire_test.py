"""
Live Interactive Visual Test Window for Dataset Images & Videos.

Displays test images with real-time bounding boxes (FIRE in RED, SMOKE in CYAN) in an OpenCV window.
Press SPACEBAR or RIGHT ARROW to advance to the next image, 'q' to quit.
"""

import sys
import time
from pathlib import Path
import cv2
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.plugins.fire.yolo_fire_detector import YoloFireDetector


def run_visual_test():
    logger.info("Initializing YOLO Fire & Smoke Detector...")
    detector = YoloFireDetector()
    detector.warm()

    dataset_path = Path(r"C:\Users\Praveen\Downloads\Fire and Smoke detection-yolov8.v1i.yolov8\test\images")
    if not dataset_path.exists():
        dataset_path = BASE_DIR / "dataset_fire_smoke_combined" / "test" / "images"

    images = list(dataset_path.glob("*.jpg")) + list(dataset_path.glob("*.png"))
    if not images:
        print(f"No test images found in {dataset_path}")
        return

    window_name = "DevaVisionAI - Fire & Smoke Visual Test (SPACE: Next Image, 'q': Quit)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1024, 720)

    print("\n=======================================================")
    print(" 🎯 VISUAL FIRE & SMOKE TEST WINDOW")
    print("=======================================================")
    print(f" Total test images loaded: {len(images)}")
    print(" - Press 'SPACEBAR' or 'RIGHT ARROW' to see next image")
    print(" - Press 'q' to Quit window")
    print("=======================================================\n")

    current_idx = 0
    while True:
        img_path = images[current_idx % len(images)]
        frame = cv2.imread(str(img_path))
        if frame is None:
            current_idx += 1
            continue

        # Detect
        candidates = detector.detect(frame)

        fire_count = 0
        smoke_count = 0

        for c in candidates:
            x1, y1, x2, y2 = c.bbox
            kind = c.kind.lower()
            conf = c.score

            if kind == "fire":
                fire_count += 1
                color = (0, 0, 255)      # Red for Fire
                label = f"FIRE {conf:.0%}"
            else:
                smoke_count += 1
                color = (255, 200, 0)    # Cyan/Yellow-blue for Smoke
                label = f"SMOKE {conf:.0%}"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(frame, (x1, max(0, y1 - 26)), (x1 + w + 10, y1), color, -1)
            cv2.putText(frame, label, (x1 + 5, y1 - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Header bar
        h, w = frame.shape[:2]
        banner_color = (0, 0, 180) if (fire_count > 0 or smoke_count > 0) else (30, 30, 30)
        cv2.rectangle(frame, (0, 0), (w, 45), banner_color, -1)

        status_text = f"[{current_idx+1}/{len(images)}] {img_path.name[:25]} | Fire: {fire_count} | Smoke: {smoke_count}"
        cv2.putText(frame, status_text, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        cv2.imshow(window_name, frame)

        key = cv2.waitKey(0) & 0xFF
        if key == ord('q') or key == 27:
            break
        elif key == 32 or key == ord('d') or key == ord('n') or key == 83:  # Space, 'd', 'n', Right arrow
            current_idx += 1
        elif key == ord('a') or key == ord('p') or key == 81:  # 'a', 'p', Left arrow
            current_idx = max(0, current_idx - 1)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_visual_test()
