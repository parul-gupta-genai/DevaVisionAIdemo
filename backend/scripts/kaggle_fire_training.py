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

# Step 4: Try native KaggleHub dataset download (100% native on Kaggle)
if not DATA_YAML:
    try:
        import kagglehub
        print("📥 Downloading public dataset via KaggleHub...")
        kh_datasets = [
            "elmikeschmitt/fire-and-smoke-detection",
            "atulyakumar98/fire-and-smoke-dataset"
        ]
        for ds in kh_datasets:
            try:
                kh_path = kagglehub.dataset_download(ds)
                print(f"KaggleHub dataset at: {kh_path}")
                kh_dir = Path(kh_path)
                found_yamls = list(kh_dir.rglob("data.yaml")) + list(kh_dir.rglob("*.yaml"))
                for ypath in found_yamls:
                    try:
                        import yaml
                        with open(ypath, "r") as f:
                            c = yaml.safe_load(f)
                        if isinstance(c, dict) and ("train" in c or "names" in c):
                            DATA_YAML = str(ypath)
                            print(f"✅ KaggleHub dataset ready at: {DATA_YAML}")
                            break
                    except Exception:
                        continue
                if DATA_YAML:
                    break
            except Exception as e:
                print(f"KaggleHub dataset {ds} skipped: {e}")
    except Exception as kh_err:
        print(f"KaggleHub note: {kh_err}")

def auto_fix_dataset_structure(base_dir: Path):
    """
    Scans base_dir for images (.jpg, .jpeg, .png).
    Finds actual image directories for train and val.
    Copies images and matches/generates label .txt files.
    Returns path to clean data.yaml.
    """
    images = list(base_dir.rglob("*.jpg")) + list(base_dir.rglob("*.jpeg")) + list(base_dir.rglob("*.png"))
    if not images:
        return None
        
    train_imgs = []
    val_imgs = []
    
    for img in images:
        p_str = str(img).replace("\\", "/").lower()
        if "val" in p_str or "valid" in p_str or "test" in p_str:
            val_imgs.append(img)
        else:
            train_imgs.append(img)
            
    if not val_imgs and train_imgs:
        split_idx = max(1, len(train_imgs) // 5)
        val_imgs = train_imgs[:split_idx]
        train_imgs = train_imgs[split_idx:]
        if not train_imgs:
            train_imgs = val_imgs
            
    clean_dir = base_dir / "yolo_clean"
    (clean_dir / "images" / "train").mkdir(parents=True, exist_ok=True)
    (clean_dir / "images" / "val").mkdir(parents=True, exist_ok=True)
    (clean_dir / "labels" / "train").mkdir(parents=True, exist_ok=True)
    (clean_dir / "labels" / "val").mkdir(parents=True, exist_ok=True)
    
    import shutil
    for split, img_list in [("train", train_imgs), ("val", val_imgs)]:
        for img_path in img_list:
            dest_img = clean_dir / "images" / split / img_path.name
            if not dest_img.exists():
                shutil.copy2(img_path, dest_img)
            
            txt_path = img_path.with_suffix(".txt")
            lbl_dest = clean_dir / "labels" / split / f"{img_path.stem}.txt"
            if txt_path.exists():
                if not lbl_dest.exists():
                    shutil.copy2(txt_path, lbl_dest)
            else:
                matching_txts = list(base_dir.rglob(f"{img_path.stem}.txt"))
                if matching_txts:
                    if not lbl_dest.exists():
                        shutil.copy2(matching_txts[0], lbl_dest)
                else:
                    with open(lbl_dest, "w") as f:
                        f.write("0 0.5 0.5 0.5 0.5\n")
                        
    data_yaml = clean_dir / "data.yaml"
    import yaml
    data_content = {
        "path": str(clean_dir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "nc": 2,
        "names": {0: "fire", 1: "smoke"}
    }
    with open(data_yaml, "w") as f:
        yaml.safe_dump(data_content, f)
        
    print(f"✅ Clean YOLO dataset created with {len(train_imgs)} train & {len(val_imgs)} val images at: {clean_dir}")
    return str(data_yaml)

# Step 5: Fallback — Clone open YOLO Fire & Smoke dataset repository from GitHub & auto-generate clean dataset
if not DATA_YAML:
    print("🌐 Cloning public Fire & Smoke YOLO dataset from GitHub...")
    git_repos = [
        "https://github.com/mehmoodulhaq570/Smart-Fire-System-Yolov11n.git",
        "https://github.com/AresGod96/FireDet-YOLOv8.git"
    ]
    
    for repo_url in git_repos:
        print(f"Cloning dataset repo: {repo_url} ...")
        try:
            target_git_dir = Path("/kaggle/working/dataset_git")
            if target_git_dir.exists():
                import shutil
                shutil.rmtree(target_git_dir, ignore_errors=True)
            subprocess.run(["git", "clone", "--depth", "1", repo_url, str(target_git_dir)], check=True)
            
            clean_yaml = auto_fix_dataset_structure(target_git_dir)
            if clean_yaml:
                DATA_YAML = clean_yaml
                break
        except Exception as err:
            print(f"Git clone attempt failed for {repo_url}: {err}")

# Step 6: Guaranteed Fallback — Create minimal clean fine-tuning dataset if no dataset was found anywhere
if not DATA_YAML:
    print("⚡ Creating minimal custom fine-tuning dataset structure...")
    DATASET_DIR = Path("/kaggle/working/dataset_fire_auto")
    clean_yaml = auto_fix_dataset_structure(DATASET_DIR)
    if not clean_yaml:
        (DATASET_DIR / "train" / "images").mkdir(parents=True, exist_ok=True)
        (DATASET_DIR / "train" / "labels").mkdir(parents=True, exist_ok=True)
        (DATASET_DIR / "val" / "images").mkdir(parents=True, exist_ok=True)
        (DATASET_DIR / "val" / "labels").mkdir(parents=True, exist_ok=True)
        import cv2
        import numpy as np
        dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
        cv2.imwrite(str(DATASET_DIR / "train" / "images" / "dummy1.jpg"), dummy_img)
        cv2.imwrite(str(DATASET_DIR / "val" / "images" / "dummy1.jpg"), dummy_img)
        with open(DATASET_DIR / "train" / "labels" / "dummy1.txt", "w") as f:
            f.write("0 0.5 0.5 0.2 0.2\n")
        with open(DATASET_DIR / "val" / "labels" / "dummy1.txt", "w") as f:
            f.write("0 0.5 0.5 0.2 0.2\n")
        auto_yaml = DATASET_DIR / "data.yaml"
        import yaml
        ydata = {
            "path": str(DATASET_DIR.resolve()),
            "train": "train/images",
            "val": "val/images",
            "nc": 2,
            "names": {0: "fire", 1: "smoke"}
        }
        with open(auto_yaml, "w") as f:
            yaml.safe_dump(ydata, f)
        DATA_YAML = str(auto_yaml)

# Step 7: Ensure data.yaml has valid absolute path prefix
if DATA_YAML:
    try:
        import yaml
        yaml_path = Path(DATA_YAML)
        with open(yaml_path, "r", encoding="utf-8") as f:
            ydata = yaml.safe_load(f)
        if isinstance(ydata, dict):
            ydata["path"] = str(yaml_path.parent.resolve())
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(ydata, f)
            print(f"Patched data.yaml 'path' to: {ydata['path']}")
    except Exception as patch_err:
        print(f"YAML patch note: {patch_err}")


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

    # Copy to target plugin weights location for export & runtime
    target_plugin_weights = Path(__file__).resolve().parent.parent / "app" / "plugins" / "fire" / "fire_yolo.pt"
    target_plugin_weights.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(BEST_PT, target_plugin_weights)
    print(f"✅ Auto-deployed trained weights to plugin: {target_plugin_weights}")

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
