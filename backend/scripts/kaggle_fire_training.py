"""
DevaVisionAI — Fire & Smoke YOLO11s Training Notebook
=======================================================
Kaggle GPU (T4/P100) pe directly run karo.

STEPS:
  1. Kaggle notebook mein "New Notebook" create karo
  2. Accelerator: GPU T4 x2 enable karo (Settings > Accelerator)
  3. Is sara code ek cell mein paste karo
  4. Run karo — ~20-30 minutes mein training complete hogi
  5. best.pt download karo aur fire_yolo.pt ke naam se project mein rakh do

Dataset: Roboflow Fire+Smoke+Person (3 classes)
Model:   YOLO11s (19MB, 47.0 mAP) — best GPU choice
"""

# ============================================================
# CELL 1 — Install dependencies
# ============================================================
import subprocess
subprocess.run(["pip", "install", "-q", "ultralytics", "roboflow"], check=True)

import os
from pathlib import Path

print("Ultralytics version:")
subprocess.run(["yolo", "version"])

import torch
print(f"\nGPU available : {torch.cuda.is_available()}")
print(f"GPU name      : {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None'}")
print(f"VRAM          : {torch.cuda.get_device_properties(0).total_memory // (1024**2)} MB"
      if torch.cuda.is_available() else "")


# ============================================================
# CELL 2 — Download dataset from Roboflow
# (Aapke paas dataset pehle se hai — ZIP upload karo ya Roboflow use karo)
# ============================================================

# Option A: Roboflow se download (API key chahiye — free account pe milta hai)
# roboflow.com par account banao -> workspace -> fire dataset -> Export -> YOLO v8
ROBOFLOW_API_KEY = ""  # <- apna API key yahan paste karo (optional)

DATASET_DIR = Path("/kaggle/working/dataset_fire")

if ROBOFLOW_API_KEY:
    from roboflow import Roboflow
    rf = Roboflow(api_key=ROBOFLOW_API_KEY)
    # Publicly available fire+smoke dataset
    project = rf.workspace("roboflow-universe-projects").project("fire-detection-mwnkh")
    dataset = project.version(2).download("yolov8", location=str(DATASET_DIR))
    DATA_YAML = str(DATASET_DIR / "data.yaml")
    print(f"Dataset downloaded to: {DATASET_DIR}")
else:
    # Option B: Apna dataset ZIP Kaggle pe upload karo
    # Kaggle > + Add Data > Upload > fire_smoke_dataset.zip
    # Phir path set karo:
    UPLOADED_ZIP = "/kaggle/input/fire-smoke-dataset/fire_smoke_dataset.zip"  # <- apna path

    if Path(UPLOADED_ZIP).exists():
        import zipfile
        DATASET_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(UPLOADED_ZIP, "r") as z:
            z.extractall(DATASET_DIR)
        print(f"Dataset extracted to: {DATASET_DIR}")

        # data.yaml mein path fix karo
        import yaml
        yaml_path = DATASET_DIR / "data.yaml"
        if yaml_path.exists():
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
            data["path"] = str(DATASET_DIR)
            data["train"] = "train/images"
            data["val"]   = "valid/images"
            data["test"]  = "test/images"
            with open(yaml_path, "w") as f:
                yaml.safe_dump(data, f)
            DATA_YAML = str(yaml_path)
            print(f"data.yaml updated: {data}")
    else:
        # Option C: Direct Kaggle dataset use karo
        # https://www.kaggle.com/datasets/atulyakumar98/fire-and-smoke-dataset
        print("No dataset found. Use Roboflow API key or upload your ZIP.")
        print("Alternatively, add a Kaggle dataset via + Add Data")

        # Fallback: create a minimal data.yaml pointing to a Kaggle dataset
        # (replace with your actual Kaggle dataset path)
        DATA_YAML = "/kaggle/input/fire-smoke-yolo/data.yaml"


# ============================================================
# CELL 3 — Train YOLO11s on GPU
# ============================================================
from ultralytics import YOLO

# YOLO11s — sabse sahi choice Kaggle T4 GPU ke liye
# 47.0 mAP, 19MB, ~4ms inference on GPU
MODEL_BASE = "yolo11s.pt"

print(f"\n{'='*50}")
print(f"Training Config:")
print(f"  Base model : {MODEL_BASE}")
print(f"  Dataset    : {DATA_YAML}")
print(f"  Device     : {'cuda:0' if torch.cuda.is_available() else 'cpu'}")
print(f"  Epochs     : 50")
print(f"  Image size : 640")
print(f"{'='*50}\n")

model = YOLO(MODEL_BASE)

results = model.train(
    data=DATA_YAML,
    epochs=50,           # Kaggle T4 pe ~25-30 minutes
    imgsz=640,           # YOLO11 optimal
    batch=16,            # T4 16GB ke liye safe
    device=0,            # GPU
    workers=2,
    project="/kaggle/working/runs_fire",
    name="yolo11s_fire",
    exist_ok=True,
    verbose=True,
    # Augmentation (better generalization):
    mosaic=1.0,          # Mosaic augmentation
    mixup=0.1,           # Mixup augmentation
    degrees=10.0,        # Rotation
    fliplr=0.5,          # Horizontal flip
    hsv_h=0.015,         # HSV hue augmentation
    hsv_s=0.7,
    hsv_v=0.4,
    patience=15,         # Early stopping
)


# ============================================================
# CELL 4 — Validate and show results
# ============================================================
BEST_PT = Path("/kaggle/working/runs_fire/yolo11s_fire/weights/best.pt")

if BEST_PT.exists():
    print(f"\nTraining complete!")
    print(f"Best model: {BEST_PT}")
    print(f"Size: {BEST_PT.stat().st_size / (1024*1024):.1f} MB")

    # Validate on test set
    val_model = YOLO(str(BEST_PT))
    metrics = val_model.val(data=DATA_YAML, device=0)
    print(f"\nValidation Results:")
    print(f"  mAP50    : {metrics.box.map50:.3f}")
    print(f"  mAP50-95 : {metrics.box.map:.3f}")
    print(f"  Precision: {metrics.box.mp:.3f}")
    print(f"  Recall   : {metrics.box.mr:.3f}")
else:
    print("Training failed — best.pt not found")


# ============================================================
# CELL 5 — Download instructions
# ============================================================
print(f"""
{'='*55}
TRAINING COMPLETE — Download karo:
{'='*55}

Kaggle notebook mein:
  File browser > /kaggle/working/runs_fire/yolo11s_fire/weights/best.pt
  Right-click > Download

Apne project mein rakh do:
  backend/app/plugins/fire/fire_yolo.pt
  (Existing file replace ho jayega)

Phir backend restart karo — automatically use hoga!
Log mein dikhega:
  YoloFireDetector: using local model: ...fire_yolo.pt
{'='*55}
""")


# ============================================================
# CELL 6 — (Optional) Export to TensorRT on Kaggle GPU
# ============================================================
DO_TRT_EXPORT = False  # True karo agar TensorRT engine bhi chahiye

if DO_TRT_EXPORT and BEST_PT.exists():
    trt_model = YOLO(str(BEST_PT))
    engine_path = trt_model.export(
        format="engine",
        half=True,      # FP16
        imgsz=640,
        batch=1,
        workspace=4,
        device=0,
    )
    print(f"TensorRT engine exported: {engine_path}")
    print("Download fire.engine aur .env mein set karo:")
    print("  USE_TENSORRT=true")
    print("  TRT_ENGINE_FIRE=/path/to/fire.engine")
