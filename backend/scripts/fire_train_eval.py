"""
Fire Detection YOLOv8 - Train, Validate, Test, Predict

Dataset: fire set.v5i.yolov8  (nc=1, class=fire)
  Train:  13,590 images
  Valid:   1,159 images
  Test:      667 images

Steps:
1. Train YOLOv8n (nano) on train split for 30 epochs
2. Validate on val split  -> mAP50, mAP50-95, P, R
3. Evaluate on test split -> same metrics
4. Predict on 5 random test images for visual check
"""

import os
import glob
import random
from pathlib import Path
from ultralytics import YOLO
import torch

DATA_YAML  = r"C:\Users\Praveen\Downloads\fire_dataset\data.yaml"
OUTPUT_DIR = r"C:\Users\Praveen\Downloads\fire_training"
EPOCHS     = 5           # CPU pe 5 epochs, fraction=0.2 = ~15-20 min
IMG_SIZE   = 320         # 320 instead of 640 = 16x faster on CPU
BATCH      = 16          # higher batch is fine at 320px
FRACTION   = 0.2         # 20% of 13590 = ~2700 images — enough to get real metrics fast
MODEL_BASE = "yolov8n.pt"
DEVICE     = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"Training device: {DEVICE} | imgsz={IMG_SIZE} | fraction={FRACTION} | epochs={EPOCHS}")


def train() -> Path:
    print("\n" + "="*60)
    print("STEP 1 - TRAINING")
    print("="*60)
    model = YOLO(MODEL_BASE)
    results = model.train(
        data=DATA_YAML,
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        batch=BATCH,
        fraction=FRACTION,
        project=OUTPUT_DIR,
        name="fire_yolov8n_cpu",
        exist_ok=True,
        patience=3,
        device=DEVICE,
        workers=0,         # 0 workers = no multiprocessing overhead on Windows CPU
        verbose=True,
        cache=True,        # cache images in RAM to avoid slow disk reads
    )
    best_pt = Path(OUTPUT_DIR) / "fire_yolov8n_cpu" / "weights" / "best.pt"
    print(f"\nTraining done. Best weights: {best_pt}")
    return best_pt


def validate(best_pt: Path) -> None:
    print("\n" + "="*60)
    print("STEP 2 - VALIDATION (val split)")
    print("="*60)
    model = YOLO(str(best_pt))
    metrics = model.val(
        data=DATA_YAML,
        imgsz=IMG_SIZE,
        batch=BATCH,
        split="val",
        project=OUTPUT_DIR,
        name="val_results",
        exist_ok=True,
        workers=0,
        verbose=True,
    )
    _print_metrics("Validation", metrics)


def test(best_pt: Path) -> None:
    print("\n" + "="*60)
    print("STEP 3 - TEST (held-out test split)")
    print("="*60)
    model = YOLO(str(best_pt))
    metrics = model.val(
        data=DATA_YAML,
        imgsz=IMG_SIZE,
        batch=BATCH,
        split="test",
        project=OUTPUT_DIR,
        name="test_results",
        exist_ok=True,
        workers=0,
        verbose=True,
    )
    _print_metrics("Test", metrics)


def predict_samples(best_pt: Path, n: int = 5) -> None:
    print("\n" + "="*60)
    print(f"STEP 4 - PREDICT on {n} random test images")
    print("="*60)
    test_images_dir = r"C:\Users\Praveen\Downloads\fire_dataset\test\images"
    images = glob.glob(os.path.join(test_images_dir, "*.jpg"))
    sample = random.sample(images, min(n, len(images)))

    model = YOLO(str(best_pt))
    results = model.predict(
        source=sample,
        imgsz=IMG_SIZE,
        conf=0.25,
        project=OUTPUT_DIR,
        name="predict_samples",
        save=True,
        exist_ok=True,
        verbose=False,
    )

    print(f"\n{'Image':<60} {'Detections':<12} {'Max Conf'}")
    print("-" * 85)
    for r in results:
        n_dets = len(r.boxes) if r.boxes is not None else 0
        max_conf = float(r.boxes.conf.max()) if n_dets > 0 else 0.0
        print(f"{Path(r.path).name:<60} {n_dets:<12} {max_conf:.2f}")

    save_dir = Path(OUTPUT_DIR) / "predict_samples"
    print(f"\nAnnotated images saved to: {save_dir}")


def _print_metrics(label: str, metrics) -> None:
    try:
        box = metrics.box
        print(f"\n{'-'*50}")
        print(f"  {label} Results (fire class)")
        print(f"{'-'*50}")
        print(f"  mAP@0.5       : {box.map50:.4f}  ({box.map50*100:.1f}%)")
        print(f"  mAP@0.5:0.95  : {box.map:.4f}  ({box.map*100:.1f}%)")
        print(f"  Precision (P) : {box.mp:.4f}  ({box.mp*100:.1f}%)")
        print(f"  Recall    (R) : {box.mr:.4f}  ({box.mr*100:.1f}%)")
        print(f"{'-'*50}")
        grade = _grade(box.map50)
        print(f"  mAP50 grade   : {grade}")
    except Exception as exc:
        print(f"  Could not parse metrics: {exc}")
        print(f"  Raw: {metrics}")


def _grade(map50: float) -> str:
    if map50 >= 0.90: return f"Excellent  ({map50*100:.1f}%)"
    if map50 >= 0.75: return f"Good       ({map50*100:.1f}%)"
    if map50 >= 0.60: return f"Acceptable ({map50*100:.1f}%)"
    return f"Needs improvement ({map50*100:.1f}%)"


if __name__ == "__main__":
    best_weights = train()
    validate(best_weights)
    test(best_weights)
    predict_samples(best_weights, n=5)

    print("\n" + "="*60)
    print("ALL DONE")
    print(f"Results saved to: {OUTPUT_DIR}")
    print("="*60)
