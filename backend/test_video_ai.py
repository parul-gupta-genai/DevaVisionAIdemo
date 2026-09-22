"""
Unified Video AI Test Tool for DevaVisionAI.
Run AI models (Fire, Smoke, Fight, ANPR, YOLO) directly on any video file or live webcam.
"""

import sys
import argparse
from pathlib import Path
import cv2
import time

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

def run_video_ai(video_source, task="yolo", output_path=None, show_window=True, conf_threshold=0.35):
    from ultralytics import YOLO
    
    # Select Model based on task
    model_paths = {
        "fire": backend_dir / "app" / "plugins" / "fire" / "fire_yolo.pt",
        "smoke": backend_dir / "app" / "plugins" / "fire" / "smoke_finetuned.pt",
        "fight": backend_dir / "app" / "plugins" / "fight" / "fight_classifier_best.pt",
        "anpr": backend_dir / "indian_plate_yolo.pt",
        "yolo": backend_dir / "yolov8n.pt",
        "yolo11": backend_dir / "yolo11n.pt"
    }

    selected_model_path = model_paths.get(task.lower(), model_paths["yolo"])
    if not selected_model_path.exists():
        selected_model_path = model_paths["yolo"]

    print(f"\n==========================================")
    print(f"🚀 Loading Model: {selected_model_path.name} for [{task.upper()}]")
    print(f"📹 Video Source: {video_source}")
    print(f"==========================================\n")

    model = YOLO(str(selected_model_path))

    # Open Video Source
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

    print("▶ Processing video... Press 'q' in the video window to stop.\n")
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1
            
            # AI Inference
            results = model.predict(frame, conf=conf_threshold, verbose=False)
            annotated_frame = results[0].plot()

            # Add HUD / info overlay
            fps_live = frame_idx / (time.time() - t_start + 1e-5)
            hud = f"DevaVisionAI [{task.upper()}] | Frame: {frame_idx} | FPS: {fps_live:.1f}"
            cv2.putText(annotated_frame, hud, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)

            if out_writer:
                out_writer.write(annotated_frame)

            if show_window:
                cv2.imshow(f"DevaVisionAI - {task.upper()}", annotated_frame)
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
        if output_path:
            print(f"🎉 Output video saved: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DevaVisionAI Video Tester")
    parser.add_argument("--source", type=str, default="0", help="Path to video file (.mp4/.avi) or '0' for webcam")
    parser.add_argument("--task", type=str, default="yolo", choices=["fire", "smoke", "fight", "anpr", "yolo", "yolo11"], help="AI task/model to test")
    parser.add_argument("--output", type=str, default=None, help="Path to save annotated output video")
    parser.add_argument("--no-show", action="store_true", help="Do not display live window (headless mode)")
    parser.add_argument("--conf", type=float, default=0.35, help="Confidence threshold (0.0 to 1.0)")

    args = parser.parse_args()
    run_video_ai(
        video_source=args.source,
        task=args.task,
        output_path=args.output,
        show_window=not args.no_show,
        conf_threshold=args.conf
    )
