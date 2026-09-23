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

# Auto-discovery logic for Kaggle inputs & datasets
DATASET_DIR = Path("/kaggle/working/dataset_fire")
DATA_YAML = None

# Step 1: Check if Roboflow API key provided
if ROBOFLOW_API_KEY:
    try:
        from roboflow import Roboflow
        rf = Roboflow(api_key=ROBOFLOW_API_KEY)
        project = rf.workspace("roboflow-universe-projects").project("fire-detection-mwnkh")
        dataset = project.version(2).download("yolov8", location=str(DATASET_DIR))
        DATA_YAML = str(DATASET_DIR / "data.yaml")
        print(f"Dataset downloaded via Roboflow API: {DATASET_DIR}")
    except Exception as e:
        print(f"Roboflow download failed: {e}")

# Step 2: Auto-find any data.yaml anywhere under /kaggle/input/
if not DATA_YAML:
    kaggle_input = Path("/kaggle/input")
    if kaggle_input.exists():
        found_yamls = list(kaggle_input.rglob("data.yaml")) + list(kaggle_input.rglob("*.yaml"))
        # Filter for actual YOLO data yamls (containing train and val keys)
        for ypath in found_yamls:
            try:
                import yaml
                with open(ypath, "r") as f:
                    content = yaml.safe_load(f)
                if isinstance(content, dict) and ("train" in content or "names" in content):
                    DATA_YAML = str(ypath)
                    print(f"✅ Auto-discovered dataset data.yaml at: {DATA_YAML}")
                    break
            except Exception:
                continue

# Step 3: Auto-find any .zip file in /kaggle/input/ and extract
if not DATA_YAML and kaggle_input.exists():
    found_zips = list(kaggle_input.rglob("*.zip"))
    if found_zips:
        zip_path = found_zips[0]
        print(f"Found zip in Kaggle input: {zip_path}, extracting...")
        import zipfile
        DATASET_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(DATASET_DIR)
        
        yamls = list(DATASET_DIR.rglob("data.yaml"))
        if yamls:
            DATA_YAML = str(yamls[0])
            print(f"Extracted dataset data.yaml at: {DATA_YAML}")

# Step 4: Fallback — Auto-download public open-source Fire & Smoke dataset
if not DATA_YAML:
    print("🌐 No local/Kaggle dataset found. Downloading public Fire & Smoke YOLO dataset...")
    zip_dest = Path("/kaggle/working/fire_dataset_public.zip")
    
    # Direct dataset download URLs (with User-Agent bypass)
    urls = [
        "https://universe.roboflow.com/ds/Z043w0T7uH?key=O526N3R88x",
        "https://github.com/roboflow/notebooks/raw/main/assets/fire-smoke-dataset.zip"
    ]
    
    for url in urls:
        print(f"Downloading dataset from: {url} ...")
        try:
            cmd = ["curl", "-sSL", "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "-o", str(zip_dest), url]
            subprocess.run(cmd, check=True)
            
            if zip_dest.exists() and zip_dest.stat().st_size > 1000:
                import zipfile
                DATASET_DIR.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(zip_dest, "r") as z:
                    z.extractall(DATASET_DIR)
                yamls = list(DATASET_DIR.rglob("data.yaml"))
                if yamls:
                    DATA_YAML = str(yamls[0])
                    print(f"✅ Public dataset extracted and ready at: {DATA_YAML}")
                    break
        except Exception as err:
            print(f"Download attempt failed: {err}")

if not DATA_YAML:
    raise FileNotFoundError("Could not find or download any dataset. Please add a Kaggle dataset via '+ Add Data' or upload a dataset ZIP.")


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
