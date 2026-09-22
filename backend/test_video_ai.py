"""
DevaVisionAI High-Accuracy Video AI Tester.
Distinct real-time Fire & Smoke detection with calibrated per-class sensitivity.
"""

import sys
import argparse
from pathlib import Path
import cv2
import time

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

def draw_custom_box(img, box, label, score, color=(0, 0, 255)):
    x1, y1, x2, y2 = [int(v) for v in box]
    h, w, _ = img.shape
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w - 1, x2), min(h - 1, y2)
    
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
    
    text = f"{label} {score:.0%}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    cv2.rectangle(img, (x1, max(0, y1 - 24)), (x1 + tw + 8, max(0, y1)), color, -1)
    cv2.putText(img, text, (x1 + 4, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

def run_video_ai(video_source, task="fire", output_path=None, show_window=True, conf_threshold=0.20):
    from ultralytics import YOLO
    
    model_paths = {
        "fire": backend_dir / "app" / "plugins" / "fire" / "fire_yolo.pt",
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
            selected_model_path = backend_dir / "yolov8n.pt"

    print(f"\n=======================================================")
    print(f"🚀 DevaVisionAI Smart Detection [{task.upper()}]")
    print(f"📦 Model: {selected_model_path.name}")
    print(f"📹 Video: {video_source}")
    print(f"🎯 Threshold: Fire={conf_threshold:.2f}, Smoke=0.08")
    print(f"=======================================================\n")

    model = YOLO(str(selected_model_path))

    src = int(video_source) if str(video_source).isdigit() else str(video_source)
    cap = cv2.VideoCapture(src)

    if not cap.isOpened():
        print(f"❌ Error: Could not open video '{video_source}'.")
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    out_writer = None
    if output_path:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        print(f"💾 Saving recording to: {output_path}")

    frame_idx = 0
    t_start = time.time()
    total_threat_frames = 0

    # Smoke is visually softer/lower contrast than bright flames, so we use conf=0.08 for smoke
    smoke_conf_floor = 0.08
    base_predict_conf = min(conf_threshold, smoke_conf_floor)

    print("▶ Running Detection... Press 'q' on the video window to stop.\n")
    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            frame_idx += 1
            display_frame = frame.copy()
            detected_threats = []
            has_fire = False
            has_smoke = False

            # YOLO AI Inference at lower base floor to catch soft smoke
            results = model.predict(frame, conf=base_predict_conf, verbose=False)
            if len(results) > 0 and results[0].boxes is not None:
                boxes = results[0].boxes
                for i in range(len(boxes)):
                    cls_id = int(boxes.cls[i].item())
                    score = float(boxes.conf[i].item())
                    cls_name = model.names.get(cls_id, str(cls_id)).lower()
                    xyxy = boxes.xyxy[i].cpu().numpy()

                    # Class filtering & per-class confidence threshold
                    if "smoke" in cls_name:
                        if score < smoke_conf_floor:
                            continue
                        color = (0, 165, 255) # Orange
                        tag = "SMOKE"
                        has_smoke = True
                    elif "fire" in cls_name or "flame" in cls_name:
                        if score < conf_threshold:
                            continue
                        color = (0, 0, 255) # Red
                        tag = "FIRE"
                        has_fire = True
                    elif "fight" in cls_name:
                        if score < conf_threshold:
                            continue
                        color = (255, 0, 128)
                        tag = "FIGHT"
                    elif "plate" in cls_name:
                        if score < conf_threshold:
                            continue
                        color = (0, 255, 0)
                        tag = "LICENSE PLATE"
                    else:
                        if score < conf_threshold or cls_name in ["no-fire", "no fire", "nofire", "light", "background"]:
                            continue
                        color = (255, 200, 0)
                        tag = cls_name.upper()

                    draw_custom_box(display_frame, xyxy, tag, score, color)
                    detected_threats.append((tag, score))

            # HUD Display
            fps_live = frame_idx / (time.time() - t_start + 1e-5)
            cv2.rectangle(display_frame, (10, 10), (420, 48), (20, 20, 20), -1)
            hud = f"DevaVisionAI [{task.upper()}] | Frame: {frame_idx} | FPS: {fps_live:.1f}"
            cv2.putText(display_frame, hud, (18, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # Contextual Alert Banner
            if detected_threats:
                total_threat_frames += 1
                if has_fire and has_smoke:
                    alert_title = "FIRE & SMOKE DETECTED"
                    banner_color = (0, 0, 220)
                elif has_fire:
                    alert_title = "FIRE DETECTED"
                    banner_color = (0, 0, 220)
                elif has_smoke:
                    alert_title = "SMOKE DETECTED"
                    banner_color = (0, 140, 255)
                else:
                    alert_title = f"{detected_threats[0][0]} DETECTED"
                    banner_color = (0, 0, 220)

                cv2.rectangle(display_frame, (10, 56), (420, 94), banner_color, -1)
                cv2.putText(display_frame, f"ALERT: {alert_title}", (18, 83), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

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
        print(f"\n=======================================================")
        print(f"✅ Completed: {frame_idx} frames in {total_time:.2f}s ({frame_idx/(total_time+1e-5):.1f} FPS)")
        print(f"🚨 Total Alert Frames: {total_threat_frames}")
        if output_path:
            print(f"📁 Output Video Saved: {output_path}")
        print(f"=======================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DevaVisionAI High-Accuracy Video AI Tester")
    parser.add_argument("--source", type=str, default="0", help="Path to video file or '0' for webcam")
    parser.add_argument("--task", type=str, default="fire", choices=["fire", "smoke", "fight", "anpr", "yolo", "yolo11"], help="Detection Task")
    parser.add_argument("--output", type=str, default=None, help="Save output video path")
    parser.add_argument("--no-show", action="store_true", help="Run without UI window")
    parser.add_argument("--conf", type=float, default=0.20, help="Confidence threshold (default 0.20)")

    args = parser.parse_args()
    run_video_ai(
        video_source=args.source,
        task=args.task,
        output_path=args.output,
        show_window=not args.no_show,
        conf_threshold=args.conf
    )
