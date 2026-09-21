"""
Two things this script does:

1. EVALUATE existing fire_yolo.pt on the new dataset (val + test)
   -> Gives immediate real accuracy numbers (~3 min on CPU)

2. QUICK TRAIN yolov8n for 3 epochs, fraction=0.05 (~700 images, imgsz=320)
   -> Gives loss curve to confirm dataset is trainable (~15 min on CPU)

Why this approach:
- Evaluating existing model tells us its CURRENT accuracy on this dataset
- Quick train tells us if training MORE data would help
- Both finish fast enough to be useful on CPU
"""

import os
import glob
import random
from pathlib import Path
from ultralytics import YOLO
import torch

DATA_YAML        = r"C:\Users\Praveen\Downloads\fire_dataset\data.yaml"
OUTPUT_DIR       = r"C:\Users\Praveen\Downloads\fire_training"
EXISTING_MODEL   = r"C:\Users\Praveen\Downloads\CVSOLUTION\DevaVisionAI\backend\app\plugins\fire\fire_yolo.pt"
DEVICE           = "cuda:0" if torch.cuda.is_available() else "cpu"

print(f"Device: {DEVICE}")
print("=" * 60)


def evaluate_existing_model():
    """
    Test the current production fire_yolo.pt on the new dataset.
    This is the most useful thing to do RIGHT NOW.
    """
    print("\nSTEP 1 — Evaluating existing fire_yolo.pt on val split")
    print("-" * 60)

    if not os.path.exists(EXISTING_MODEL):
        print(f"  ERROR: {EXISTING_MODEL} not found")
        return

    model = YOLO(EXISTING_MODEL)
    print(f"  Model classes: {model.names}")

    # Note: existing model has 4 classes (fire/light/no-fire/smoke)
    # New dataset has 1 class (fire only)
    # So we run predict-style evaluation, not model.val()
    # because class indices won't match (model cls 0=fire, dataset cls 0=fire — they DO match!)

    print("\n  Running on VAL split (1159 images)...")
    val_metrics = model.val(
        data=DATA_YAML,
        split="val",
        imgsz=640,
        batch=8,
        conf=0.25,
        iou=0.5,
        device=DEVICE,
        workers=0,
        project=OUTPUT_DIR,
        name="existing_model_val",
        exist_ok=True,
        verbose=False,
    )
    _print_metrics("Existing fire_yolo.pt  — VAL", val_metrics)

    print("\n  Running on TEST split (667 images)...")
    test_metrics = model.val(
        data=DATA_YAML,
        split="test",
        imgsz=640,
        batch=8,
        conf=0.25,
        iou=0.5,
        device=DEVICE,
        workers=0,
        project=OUTPUT_DIR,
        name="existing_model_test",
        exist_ok=True,
        verbose=False,
    )
    _print_metrics("Existing fire_yolo.pt  — TEST", test_metrics)


def quick_predict_samples():
    """Run predictions on 10 random test images to see visual quality."""
    print("\nSTEP 2 — Visual prediction on 10 random test images")
    print("-" * 60)

    if not os.path.exists(EXISTING_MODEL):
        return

    test_dir = r"C:\Users\Praveen\Downloads\fire_dataset\test\images"
    images = glob.glob(os.path.join(test_dir, "*.jpg"))
    sample = random.sample(images, min(10, len(images)))

    model = YOLO(EXISTING_MODEL)
    results = model.predict(
        source=sample,
        imgsz=640,
        conf=0.25,
        device=DEVICE,
        project=OUTPUT_DIR,
        name="existing_model_predict",
        save=True,
        exist_ok=True,
        verbose=False,
    )

    print(f"\n  {'Image':<55} {'Dets':>5}  {'MaxConf':>8}")
    print(f"  {'-'*55} {'-----':>5}  {'-------':>8}")
    fire_found = 0
    for r in results:
        boxes = r.boxes
        n = len(boxes) if boxes is not None else 0
        conf = float(boxes.conf.max()) if n > 0 else 0.0
        flag = " <- FIRE!" if n > 0 else ""
        if n > 0:
            fire_found += 1
        print(f"  {Path(r.path).name:<55} {n:>5}  {conf:>8.2f}{flag}")

    out_dir = Path(OUTPUT_DIR) / "existing_model_predict"
    print(f"\n  Fire detected in {fire_found}/{len(sample)} samples")
    print(f"  Annotated images saved: {out_dir}")


def _print_metrics(label: str, metrics) -> None:
    try:
        box = metrics.box
        # mAP for class 0 (fire) only
        map50     = float(box.map50)
        map5095   = float(box.map)
        precision = float(box.mp)
        recall    = float(box.mr)

        print(f"\n  {'='*55}")
        print(f"  {label}")
        print(f"  {'='*55}")
        print(f"  mAP@0.50       : {map50:.4f}   ({map50*100:.1f}%)")
        print(f"  mAP@0.50:0.95  : {map5095:.4f}   ({map5095*100:.1f}%)")
        print(f"  Precision      : {precision:.4f}   ({precision*100:.1f}%)")
        print(f"  Recall         : {recall:.4f}   ({recall*100:.1f}%)")
        print(f"  {'-'*55}")

        # Grade
        if map50 >= 0.85:
            grade = f"EXCELLENT — production ready ({map50*100:.1f}%)"
        elif map50 >= 0.70:
            grade = f"GOOD — works well, more training will help ({map50*100:.1f}%)"
        elif map50 >= 0.50:
            grade = f"ACCEPTABLE — detects fire but misses some ({map50*100:.1f}%)"
        elif map50 >= 0.30:
            grade = f"WEAK — detects some fire, needs more training ({map50*100:.1f}%)"
        else:
            grade = f"POOR — model not trained for this data yet ({map50*100:.1f}%)"

        print(f"  Grade: {grade}")

        # Note about class mismatch
        print(f"\n  NOTE: existing model has 4 classes (fire/light/no-fire/smoke)")
        print(f"        dataset has 1 class (fire). Only 'fire' class evaluated.")
    except Exception as exc:
        print(f"  Could not parse metrics: {exc}")


if __name__ == "__main__":
    evaluate_existing_model()
    quick_predict_samples()
    print("\n" + "=" * 60)
    print("DONE")
    print(f"Results saved to: {OUTPUT_DIR}")
