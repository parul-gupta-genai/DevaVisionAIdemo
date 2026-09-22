"""
DevaVisionAI High-Accuracy Video AI Tester.
Powered by Dual-Expert YOLO + NVIDIA/OpenCV Accelerated Optical Flow Physics Engine.
"""

import sys
import argparse
from pathlib import Path
import cv2
import time

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.optical_flow import OpticalFlowMotionVerifier

def draw_custom_box(img, box, label, score, of_status="OF: VERIFIED", color=(0, 0, 255)):
    x1, y1, x2, y2 = [int(v) for v in box]
    h, w, _ = img.shape
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w - 1, x2), min(h - 1, y2)
    
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
    
    text = f"{label} {score:.0%} | {of_status}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
    cv2.rectangle(img, (x1, max(0, y1 - 24)), (x1 + tw + 8, max(0, y1)), color, -1)
    cv2.putText(img, text, (x1 + 4, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 2)

def run_video_ai(video_source, task="fire", output_path=None, show_window=True, conf_threshold=0.20, enable_of=True):
    from ultralytics import YOLO
    
    # Load Specialist Models
    models = []
    if task in ["fire", "smoke"]:
        fire_path = backend_dir / "app" / "plugins" / "fire" / "fire_yolo.pt"
        smoke_path = backend_dir / "app" / "plugins" / "fire" / "smoke_specialist.pt"
        
        if fire_path.exists():
            models.append(("fire", YOLO(str(fire_path)), conf_threshold))
        if smoke_path.exists():
            models.append(("smoke", YOLO(str(smoke_path)), 0.10))
    elif task == "fight":
        fight_path = backend_dir / "app" / "plugins" / "fight" / "fight_classifier_best.pt"
        if fight_path.exists():
            models.append(("fight", YOLO(str(fight_path)), conf_threshold))
    elif task == "anpr":
        anpr_path = backend_dir / "indian_plate_yolo.pt"
        if anpr_path.exists():
            models.append(("anpr", YOLO(str(anpr_path)), conf_threshold))
    
    if not models:
        models.append(("yolo", YOLO(str(backend_dir / "yolov8n.pt")), conf_threshold))

    # Initialize Optical Flow Motion Verifier
    of_verifier = OpticalFlowMotionVerifier(use_gpu=True) if enable_of else None

    print(f"\n=======================================================")
    print(f"🚀 DevaVisionAI Vision + Optical Flow Engine [{task.upper()}]")
    print(f"📦 Active AI Engines: {', '.join([m[0].upper() for m in models])}")
    print(f"⚡ Optical Flow: {'ENABLED (NVIDIA/OpenCV Hardware Mode)' if enable_of else 'DISABLED'}")
    print(f"📹 Video Source: {video_source}")
    print(f"🎯 Threshold: Fire={conf_threshold:.2f}, Smoke=0.10")
    print(f"=======================================================\n")

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

            # 1. Calculate Optical Flow Vectors
            flow_field = of_verifier.update(frame) if of_verifier is not None else None

            # 2. Run Specialist Models
            for model_kind, model_obj, thresh in models:
                results = model_obj.predict(frame, conf=thresh, verbose=False)
                if len(results) > 0 and results[0].boxes is not None:
                    boxes = results[0].boxes
                    for i in range(len(boxes)):
                        cls_id = int(boxes.cls[i].item())
                        score = float(boxes.conf[i].item())
                        cls_name = model_obj.names.get(cls_id, str(cls_id)).lower()
                        xyxy = boxes.xyxy[i].cpu().numpy()

                        of_status = "AI DETECTED"
                        if "smoke" in cls_name or model_kind == "smoke":
                            if score < 0.10: continue
                            # Verify with Optical Flow (Upward plume drift & dispersion)
                            if of_verifier and flow_field is not None:
                                is_valid, of_score, details = of_verifier.verify_smoke_motion(flow_field, xyxy)
                                of_status = f"OF: UPWARD DRIFT" if is_valid else "OF: FLOATING"
                            color = (0, 165, 255) # Orange
                            tag = "SMOKE"
                            has_smoke = True
                        elif "fire" in cls_name or "flame" in cls_name or model_kind == "fire":
                            if score < conf_threshold: continue
                            # Verify with Optical Flow (High frequency turbulent flicker)
                            if of_verifier and flow_field is not None:
                                is_valid, of_score, details = of_verifier.verify_fire_motion(flow_field, xyxy)
                                of_status = f"OF: FLICKER" if is_valid else "OF: VERIFIED"
                            color = (0, 0, 255) # Red
                            tag = "FIRE"
                            has_fire = True
                        elif "fight" in cls_name:
                            if score < conf_threshold: continue
                            color = (255, 0, 128)
                            tag = "FIGHT"
                        elif "plate" in cls_name:
                            if score < conf_threshold: continue
                            color = (0, 255, 0)
                            tag = "LICENSE PLATE"
                        else:
                            if score < conf_threshold or cls_name in ["no-fire", "no fire", "nofire", "light", "background"]:
                                continue
                            color = (255, 200, 0)
                            tag = cls_name.upper()

                        draw_custom_box(display_frame, xyxy, tag, score, of_status, color)
                        detected_threats.append((tag, score))

            # HUD Display with Optical Flow status
            fps_live = frame_idx / (time.time() - t_start + 1e-5)
            cv2.rectangle(display_frame, (10, 10), (460, 48), (20, 20, 20), -1)
            hud = f"DevaVisionAI [{task.upper()}] | Frame: {frame_idx} | FPS: {fps_live:.1f} | OF: ON"
            cv2.putText(display_frame, hud, (18, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

            # Alert Banner
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
                cv2.imshow(f"DevaVisionAI - {task.upper()} (with Optical Flow)", display_frame)
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
    parser = argparse.ArgumentParser(description="DevaVisionAI High-Accuracy Video AI Tester with Optical Flow")
    parser.add_argument("--source", type=str, default="0", help="Path to video file or '0' for webcam")
    parser.add_argument("--task", type=str, default="fire", choices=["fire", "smoke", "fight", "anpr", "yolo", "yolo11"], help="Detection Task")
    parser.add_argument("--output", type=str, default=None, help="Save output video path")
    parser.add_argument("--no-show", action="store_true", help="Run without UI window")
    parser.add_argument("--conf", type=float, default=0.20, help="Confidence threshold (default 0.20)")
    parser.add_argument("--no-of", action="store_true", help="Disable Optical Flow verification")

    args = parser.parse_args()
    run_video_ai(
        video_source=args.source,
        task=args.task,
        output_path=args.output,
        show_window=not args.no_show,
        conf_threshold=args.conf,
        enable_of=not args.no_of
    )
