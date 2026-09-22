"""
Unified Video AI Test Tool for DevaVisionAI.
Features Hybrid Detection (YOLO AI + HSV Temporal Smoke/Fire Analyzer).
"""

import sys
import argparse
from pathlib import Path
import cv2
import time
import numpy as np

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.plugins.fire.detector import FrameAnalyzer, FIRE, SMOKE

def draw_custom_box(img, box, label, score, color=(0, 0, 255)):
    x1, y1, x2, y2 = [int(v) for v in box]
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
    
    text = f"{label.upper()} {score:.0%}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(img, (x1, max(0, y1 - 25)), (x1 + tw + 10, max(0, y1)), color, -1)
    cv2.putText(img, text, (x1 + 5, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

def run_video_ai(video_source, task="fire", output_path=None, show_window=True, conf_threshold=0.15):
    from ultralytics import YOLO
    
    model_paths = {
        "fire": backend_dir / "app" / "plugins" / "fire" / "smoke_finetuned.pt",
        "smoke": backend_dir / "app" / "plugins" / "fire" / "smoke_finetuned.pt",
        "fight": backend_dir / "app" / "plugins" / "fight" / "fight_classifier_best.pt",
        "anpr": backend_dir / "indian_plate_yolo.pt",
        "yolo": backend_dir / "yolov8n.pt",
        "yolo11": backend_dir / "yolo11n.pt"
    }

    selected_model_path = model_paths.get(task.lower(), model_paths["fire"])
    if not selected_model_path.exists():
        selected_model_path = backend_dir / "app" / "plugins" / "fire" / "fire_yolo.pt"
        if not selected_model_path.exists():
            selected_model_path = model_paths["yolo"]

    print(f"\n==========================================")
    print(f"🚀 Loading AI Engine: {selected_model_path.name} for [{task.upper()}]")
    print(f"📹 Video Source: {video_source}")
    print(f"🎯 Detection Sensitivity: {conf_threshold:.2f} (Hybrid Mode: YOLO + HSV Temporal)")
    print(f"==========================================\n")

    model = YOLO(str(selected_model_path))
    hsv_analyzer = FrameAnalyzer() if task in ["fire", "smoke"] else None

    src = int(video_source) if str(video_source).isdigit() else str(video_source)
    cap = cv2.VideoCapture(src)

    if not cap.isOpened():
        print(f"❌ Error: Cannot open video source '{video_source}'")
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    out_writer = None
    if output_path:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        print(f"💾 Saving output to: {output_path}")

    frame_idx = 0
    t_start = time.time()
    total_alerts = 0

    print("▶ Processing video... Press 'q' in the video window to stop.\n")
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1
            display_frame = frame.copy()
            detected_items = []

            # 1. HSV / Temporal Smoke & Fire Analysis (for early/soft smoke and flame)
            if hsv_analyzer is not None:
                hsv_candidates = hsv_analyzer.analyze(frame)
                for c in hsv_candidates:
                    if c.score >= 0.25:
                        c_color = (0, 165, 255) if c.kind.lower() == "smoke" else (0, 0, 255)
                        draw_custom_box(display_frame, c.bbox, f"EARLY {c.kind}", c.score, c_color)
                        detected_items.append((c.kind, c.score))

            # 2. YOLO AI Model Prediction
            results = model.predict(frame, conf=conf_threshold, verbose=False)
            if len(results) > 0 and results[0].boxes is not None:
                boxes = results[0].boxes
                for i in range(len(boxes)):
                    cls_id = int(boxes.cls[i].item())
                    score = float(boxes.conf[i].item())
                    cls_name = model.names.get(cls_id, str(cls_id)).lower()
                    xyxy = boxes.xyxy[i].cpu().numpy()

                    if cls_name in ["no-fire", "no fire", "nofire", "light", "background"]:
                        continue

                    if "fire" in cls_name or "flame" in cls_name:
                        color = (0, 0, 255) # Red
                    elif "smoke" in cls_name:
                        color = (0, 165, 255) # Orange
                    elif "fight" in cls_name:
                        color = (255, 0, 128) # Magenta
                    elif "plate" in cls_name or "license" in cls_name:
                        color = (0, 255, 0) # Green
                    else:
                        color = (255, 200, 0)

                    draw_custom_box(display_frame, xyxy, cls_name, score, color)
                    detected_items.append((cls_name, score))

            # HUD Overlay
            fps_live = frame_idx / (time.time() - t_start + 1e-5)
            cv2.rectangle(display_frame, (10, 10), (450, 50), (30, 30, 30), -1)
            hud = f"DevaVisionAI [{task.upper()}] | Frame: {frame_idx} | FPS: {fps_live:.1f}"
            cv2.putText(display_frame, hud, (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

            # Alert Banner
            if detected_items:
                total_alerts += 1
                top_threat = detected_items[0]
                alert_text = f"ALERT: {top_threat[0].upper()} ({top_threat[1]:.0%})"
                cv2.rectangle(display_frame, (10, 60), (380, 100), (0, 0, 200), -1)
                cv2.putText(display_frame, f"⚠️ {alert_text}", (20, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            if out_writer:
                out_writer.write(display_frame)

            if show_window:
                cv2.imshow(f"DevaVisionAI - {task.upper()}", display_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    print("⏹ Stopped by user.")
                    break

    finally:
        cap.release()
        if out_writer:
            out_writer.release()
        cv2.destroyAllWindows()
        total_time = time.time() - t_start
        print(f"\n✅ Finished {frame_idx} frames in {total_time:.2f}s ({frame_idx/(total_time+1e-5):.1f} FPS)")
        print(f"📊 Total Alert Frames: {total_alerts}")
        if output_path:
            print(f"🎉 Output video saved: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DevaVisionAI Video Tester")
    parser.add_argument("--source", type=str, default="0", help="Path to video file (.mp4/.avi) or '0' for webcam")
    parser.add_argument("--task", type=str, default="fire", choices=["fire", "smoke", "fight", "anpr", "yolo", "yolo11"], help="AI task/model to test")
    parser.add_argument("--output", type=str, default=None, help="Path to save annotated output video")
    parser.add_argument("--no-show", action="store_true", help="Do not display live window (headless mode)")
    parser.add_argument("--conf", type=float, default=0.12, help="Confidence threshold (default 0.12 for maximum sensitivity)")

    args = parser.parse_args()
    run_video_ai(
        video_source=args.source,
        task=args.task,
        output_path=args.output,
        show_window=not args.no_show,
        conf_threshold=args.conf
    )
