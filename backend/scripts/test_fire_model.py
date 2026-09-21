import argparse
import os
import sys
from pathlib import Path
import cv2
import numpy as np

def run_fire_model_test():
    parser = argparse.ArgumentParser(description="Standalone Fire Model Test (best.pt)")
    parser.add_argument("--source", type=str, default="fire_test_output.jpg", help="Path to input image or video")
    parser.add_argument("--model", type=str, default=r"C:\Users\Praveen\Downloads\CVSOLUTION\DevaVisionAI\backend\runs_fire\train\weights\best.pt", help="Path to best.pt weights")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--diag", action="store_true", help="Print raw diagnostic predictions for all classes")
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print("Error: ultralytics package is required.")
        sys.exit(1)

    model_path = Path(args.model)
    if not model_path.exists():
        print(f"Error: Model not found at {model_path}")
        sys.exit(1)

    print("=" * 80)
    print("========================================")
    print("FIRE MODEL INITIALIZATION")
    print("========================================")
    print(f"Model:\n{model_path}\n")

    model = YOLO(str(model_path))
    names = model.names or {}
    print("Classes:")
    for cid, cname in names.items():
        print(f"{cid} -> {cname}")
    print(f"\nModel loaded successfully: TRUE")
    print("========================================\n")

    source_path = Path(args.source)
    if not source_path.exists():
        # Fallback search
        base_dir = Path(r"C:\Users\Praveen\Downloads\CVSOLUTION\DevaVisionAI")
        if (base_dir / args.source).exists():
            source_path = base_dir / args.source
        elif (base_dir / "backend" / args.source).exists():
            source_path = base_dir / "backend" / args.source
        else:
            print(f"Error: Input source file not found at {args.source}")
            sys.exit(1)

    print(f"Testing input source: {source_path}")

    # Check if video or image
    is_video = source_path.suffix.lower() in [".mp4", ".avi", ".mov", ".mkv"]

    if not is_video:
        frame = cv2.imread(str(source_path))
        if frame is None:
            print(f"Error: Failed to read image file {source_path}")
            sys.exit(1)

        print("\n--- MULTI-THRESHOLD DIAGNOSTIC EVALUATION ---")
        thresholds = [0.50, 0.40, 0.30, 0.25, 0.20, 0.15, 0.10]
        for t in thresholds:
            r = model(frame, verbose=False, conf=t)
            fire_det = False
            smoke_det = False
            top_fire_conf = 0.0
            top_smoke_conf = 0.0

            if r and len(r) > 0 and r[0].boxes is not None:
                for box in r[0].boxes:
                    c_id = int(box.cls[0])
                    c_name = names.get(c_id, "").lower()
                    c_score = float(box.conf[0])
                    if "fire" in c_name and c_name != "no-fire":
                        fire_det = True
                        top_fire_conf = max(top_fire_conf, c_score)
                    elif "smoke" in c_name:
                        smoke_det = True
                        top_smoke_conf = max(top_smoke_conf, c_score)

            status_str = []
            if fire_det:
                status_str.append(f"Fire: DETECTED ({top_fire_conf:.1%})")
            else:
                status_str.append("Fire: NOT DETECTED")
            if smoke_det:
                status_str.append(f"Smoke: DETECTED ({top_smoke_conf:.1%})")
            else:
                status_str.append("Smoke: NOT DETECTED")

            print(f"Threshold {t:.2f}: | {' | '.join(status_str)}")

        # Raw class probability inspection (conf=0.01)
        raw_res = model(frame, verbose=False, conf=0.01)
        raw_scores = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}
        if raw_res and len(raw_res) > 0 and raw_res[0].boxes is not None:
            for box in raw_res[0].boxes:
                c_id = int(box.cls[0])
                c_score = float(box.conf[0])
                if c_id in raw_scores:
                    raw_scores[c_id] = max(raw_scores[c_id], c_score)

        print("\n--- RAW PREDICTIONS (ALL 4 CLASSES, CONF >= 0.01) ---")
        for cid, cname in names.items():
            score_val = raw_scores.get(cid, 0.0)
            print(f"  Class {cid} ({cname:<8}): Max Confidence = {score_val:.4f} ({score_val:.2%})")

        print("\n--- TARGET INFERENCE AT CONFIDENCE = {:.2f} ---".format(args.conf))
        results = model(frame, verbose=False, conf=args.conf)
        annotated = frame.copy()

        detected_summary = {"fire": (False, 0.0), "smoke": (False, 0.0), "light": (False, 0.0), "no-fire": (False, 0.0)}

        if results and len(results) > 0:
            boxes = results[0].boxes
            if boxes is not None:
                for box in boxes:
                    c_id = int(box.cls[0])
                    c_name = names.get(c_id, "").lower()
                    c_score = float(box.conf[0])
                    x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())

                    if "fire" in c_name and c_name != "no-fire":
                        detected_summary["fire"] = (True, max(detected_summary["fire"][1], c_score))
                        color = (0, 0, 255) # Red
                    elif "smoke" in c_name:
                        detected_summary["smoke"] = (True, max(detected_summary["smoke"][1], c_score))
                        color = (128, 128, 128) # Gray
                    elif "light" in c_name:
                        detected_summary["light"] = (True, max(detected_summary["light"][1], c_score))
                        color = (0, 255, 255) # Yellow
                    else:
                        detected_summary["no-fire"] = (True, max(detected_summary["no-fire"][1], c_score))
                        color = (0, 255, 0) # Green

                    label = f"{c_name.upper()}: {c_score:.1%}"
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(annotated, label, (x1, max(25, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        print(f"\nMODEL: best.pt\n")
        for cls_k in ["fire", "smoke", "light", "no-fire"]:
            det_bool, det_score = detected_summary[cls_k]
            status_txt = f"YES (Confidence: {det_score:.1%})" if det_bool else "NO"
            print(f"{cls_k.upper():<8}: Detected: {status_txt}")

        output_img_path = "fire_test_result.jpg"
        cv2.imwrite(output_img_path, annotated)
        print(f"\nSaved annotated test output to: {os.path.abspath(output_img_path)}")

    else:
        # Process Video
        cap = cv2.VideoCapture(str(source_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        out_video_path = "fire_test_result.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_video_path, fourcc, fps, (width, height))

        frame_idx = 0
        total_fire = 0
        total_smoke = 0

        print(f"Processing video {source_path} ({width}x{height} @ {fps:.1f} FPS)...")
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1
            results = model(frame, verbose=False, conf=args.conf)
            annotated = frame.copy()

            if results and len(results) > 0 and results[0].boxes is not None:
                for box in results[0].boxes:
                    c_id = int(box.cls[0])
                    c_name = names.get(c_id, "").lower()
                    c_score = float(box.conf[0])
                    x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())

                    if "fire" in c_name and c_name != "no-fire":
                        total_fire += 1
                        color = (0, 0, 255)
                    elif "smoke" in c_name:
                        total_smoke += 1
                        color = (128, 128, 128)
                    else:
                        color = (0, 255, 255)

                    label = f"{c_name.upper()}: {c_score:.1%}"
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(annotated, label, (x1, max(25, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            writer.write(annotated)

        cap.release()
        writer.release()
        print(f"\nProcessed {frame_idx} video frames. Fire detections: {total_fire} | Smoke detections: {total_smoke}")
        print(f"Saved annotated video to: {os.path.abspath(out_video_path)}")

if __name__ == "__main__":
    run_fire_model_test()
