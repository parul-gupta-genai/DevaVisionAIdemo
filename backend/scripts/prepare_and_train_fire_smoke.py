"""
Comprehensive Pipeline for Merging Fire & Smoke Datasets, Training YOLOv8, and Integrating with DevaVisionAI.

Steps:
1. Load YOLO annotations from 'Fire and Smoke detection-yolov8.v1i.yolov8' and remap to:
   - 0: fire
   - 1: smoke
2. Incorporate 'archive/fire_dataset':
   - 'non_fire_images': Background negatives (empty labels) to eliminate false positives.
   - 'fire_images': High-volume fire images to augment fire detection.
3. Build structured dataset at 'backend/dataset_fire_smoke_combined'.
4. Train YOLOv8 model.
5. Deploy 'best.pt' weights to:
   - backend/app/plugins/fire/fire_yolo.pt
   - backend/runs_fire/train/weights/best.pt
6. Verify inference with YoloFireDetector.
"""

import os
import shutil
import random
from pathlib import Path
import yaml
import cv2
from loguru import logger

# Paths configuration
BASE_DIR = Path(__file__).resolve().parent.parent
SRC_ROBOFLOW_DATASET = Path(r"C:\Users\Praveen\Downloads\Fire and Smoke detection-yolov8.v1i.yolov8")
SRC_ARCHIVE_DATASET = Path(r"C:\Users\Praveen\Downloads\archive\fire_dataset")

OUTPUT_DATASET_DIR = BASE_DIR / "dataset_fire_smoke_combined"
TARGET_PLUGIN_WEIGHTS = BASE_DIR / "app" / "plugins" / "fire" / "fire_yolo.pt"
TARGET_RUNS_WEIGHTS = BASE_DIR / "runs_fire" / "train" / "weights" / "best.pt"


def create_combined_dataset():
    logger.info("=== STEP 1: Building Combined Dataset ===")
    
    # Destination directories
    for split in ["train", "valid", "test"]:
        (OUTPUT_DATASET_DIR / split / "images").mkdir(parents=True, exist_ok=True)
        (OUTPUT_DATASET_DIR / split / "labels").mkdir(parents=True, exist_ok=True)

    # 1. Process Roboflow dataset
    # Roboflow classes: 0: Fire, 1: Person, 2: Smoke
    # Target classes: 0: fire, 1: smoke
    class_remap = {
        0: 0,  # Fire -> fire
        2: 1,  # Smoke -> smoke
    }
    
    total_roboflow_copied = 0
    if SRC_ROBOFLOW_DATASET.exists():
        logger.info(f"Processing annotated dataset from: {SRC_ROBOFLOW_DATASET}")
        for split in ["train", "valid", "test"]:
            img_src = SRC_ROBOFLOW_DATASET / split / "images"
            lbl_src = SRC_ROBOFLOW_DATASET / split / "labels"
            
            if not img_src.exists():
                continue
                
            img_dest = OUTPUT_DATASET_DIR / split / "images"
            lbl_dest = OUTPUT_DATASET_DIR / split / "labels"
            
            for img_file in img_src.iterdir():
                if img_file.suffix.lower() not in [".jpg", ".jpeg", ".png"]:
                    continue
                
                # Copy image
                shutil.copy(img_file, img_dest / img_file.name)
                
                # Process matching label
                lbl_file = lbl_src / (img_file.stem + ".txt")
                new_lbl_lines = []
                if lbl_file.exists():
                    with open(lbl_file, "r") as f:
                        for line in f:
                            parts = line.strip().split()
                            if not parts:
                                continue
                            cls_id = int(parts[0])
                            if cls_id in class_remap:
                                new_cls_id = class_remap[cls_id]
                                new_lbl_lines.append(f"{new_cls_id} " + " ".join(parts[1:]) + "\n")
                
                with open(lbl_dest / (img_file.stem + ".txt"), "w") as f:
                    f.writelines(new_lbl_lines)
                total_roboflow_copied += 1
        logger.info(f"Copied {total_roboflow_copied} labeled images from Roboflow dataset.")
    else:
        logger.warning(f"Roboflow dataset path not found at {SRC_ROBOFLOW_DATASET}")

    # 2. Process Archive dataset
    if SRC_ARCHIVE_DATASET.exists():
        logger.info(f"Processing archive dataset from: {SRC_ARCHIVE_DATASET}")
        
        # A) Non-fire images (background negatives to prevent false positives)
        non_fire_dir = SRC_ARCHIVE_DATASET / "non_fire_images"
        if non_fire_dir.exists():
            non_fire_files = [f for f in non_fire_dir.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png"]]
            random.seed(42)
            random.shuffle(non_fire_files)
            
            # Split: 80% train, 20% valid
            split_idx = int(0.8 * len(non_fire_files))
            train_negatives = non_fire_files[:split_idx]
            val_negatives = non_fire_files[split_idx:]
            
            for f in train_negatives:
                dest_name = f"neg_{f.name}"
                shutil.copy(f, OUTPUT_DATASET_DIR / "train" / "images" / dest_name)
                # Empty label file for background negative
                (OUTPUT_DATASET_DIR / "train" / "labels" / f"{Path(dest_name).stem}.txt").write_text("")
                
            for f in val_negatives:
                dest_name = f"neg_{f.name}"
                shutil.copy(f, OUTPUT_DATASET_DIR / "valid" / "images" / dest_name)
                (OUTPUT_DATASET_DIR / "valid" / "labels" / f"{Path(dest_name).stem}.txt").write_text("")
                
            logger.info(f"Added {len(non_fire_files)} non-fire background negative samples (Train: {len(train_negatives)}, Val: {len(val_negatives)}).")

        # B) Fire images (Full-frame fire images labeled with standard fire box)
        fire_dir = SRC_ARCHIVE_DATASET / "fire_images"
        if fire_dir.exists():
            fire_files = [f for f in fire_dir.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png"]]
            random.seed(42)
            random.shuffle(fire_files)
            
            # Use top 200 high-quality fire images to balance the dataset
            selected_fire = fire_files[:200]
            split_idx = int(0.8 * len(selected_fire))
            train_fire = selected_fire[:split_idx]
            val_fire = selected_fire[split_idx:]
            
            # Fire class index 0, center bounding box covering central region
            box_label = "0 0.500000 0.500000 0.850000 0.850000\n"
            
            for f in train_fire:
                dest_name = f"arch_fire_{f.name}"
                shutil.copy(f, OUTPUT_DATASET_DIR / "train" / "images" / dest_name)
                (OUTPUT_DATASET_DIR / "train" / "labels" / f"{Path(dest_name).stem}.txt").write_text(box_label)
                
            for f in val_fire:
                dest_name = f"arch_fire_{f.name}"
                shutil.copy(f, OUTPUT_DATASET_DIR / "valid" / "images" / dest_name)
                (OUTPUT_DATASET_DIR / "valid" / "labels" / f"{Path(dest_name).stem}.txt").write_text(box_label)
                
            logger.info(f"Added {len(selected_fire)} archive fire samples (Train: {len(train_fire)}, Val: {len(val_fire)}).")
    else:
        logger.warning(f"Archive dataset not found at {SRC_ARCHIVE_DATASET}")

    # 3. Write data.yaml
    yaml_data = {
        "path": str(OUTPUT_DATASET_DIR.resolve()).replace("\\", "/"),
        "train": "train/images",
        "val": "valid/images",
        "test": "test/images",
        "nc": 2,
        "names": ["fire", "smoke"]
    }
    
    yaml_path = OUTPUT_DATASET_DIR / "data.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(yaml_data, f, default_flow_style=False)
        
    logger.info(f"Generated standardized data.yaml at {yaml_path}")
    return yaml_path


def train_yolo_model(yaml_path: Path, epochs=25, base_model="yolov8n.pt"):
    logger.info(f"=== STEP 2: Training YOLOv8 Model ({base_model}, {epochs} epochs) ===")
    from ultralytics import YOLO
    
    model = YOLO(base_model)
    
    project_dir = BASE_DIR / "runs_fire"
    results = model.train(
        data=str(yaml_path),
        epochs=epochs,
        imgsz=416,
        batch=16,
        workers=2,
        project=str(project_dir),
        name="train",
        exist_ok=True,
        verbose=True,
        lr0=0.01,
        lrf=0.01,
        cos_lr=True,
        flipud=0.2,
        fliplr=0.5,
    )
    
    best_weights = project_dir / "train" / "weights" / "best.pt"
    if not best_weights.exists():
        raise FileNotFoundError(f"Training failed to produce weights at {best_weights}")
    
    logger.info(f"Training successfully completed! Best weights saved at: {best_weights}")
    return best_weights


def integrate_and_validate(trained_weights: Path):
    logger.info("=== STEP 3: Integrating Weights with DevaVisionAI ===")
    
    # 1. Deploy to backend/app/plugins/fire/fire_yolo.pt
    TARGET_PLUGIN_WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(trained_weights, TARGET_PLUGIN_WEIGHTS)
    
    # 2. Deploy to backend/runs_fire/train/weights/best.pt
    TARGET_RUNS_WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
    if TARGET_RUNS_WEIGHTS.resolve() != trained_weights.resolve():
        shutil.copy(trained_weights, TARGET_RUNS_WEIGHTS)
        
    size_mb = TARGET_PLUGIN_WEIGHTS.stat().st_size / (1024 * 1024)
    logger.info(f"✅ Successfully deployed weights ({size_mb:.2f} MB) to:\n  - {TARGET_PLUGIN_WEIGHTS}\n  - {TARGET_RUNS_WEIGHTS}")

    # 3. Validate loading through YoloFireDetector
    logger.info("=== STEP 4: Validating YoloFireDetector Integration ===")
    import sys
    sys.path.insert(0, str(BASE_DIR))
    
    from app.plugins.fire.yolo_fire_detector import YoloFireDetector
    detector = YoloFireDetector()
    detector.warm()
    
    # Run inference on a test frame or sample image
    test_img_dir = OUTPUT_DATASET_DIR / "test" / "images"
    sample_images = list(test_img_dir.glob("*.jpg")) + list(test_img_dir.glob("*.png"))
    if not sample_images:
        sample_images = list((OUTPUT_DATASET_DIR / "valid" / "images").glob("*.jpg"))
        
    if sample_images:
        sample_path = sample_images[0]
        logger.info(f"Testing inference on sample image: {sample_path.name}")
        frame = cv2.imread(str(sample_path))
        if frame is not None:
            candidates = detector.detect(frame)
            logger.info(f"Detection results: {len(candidates)} candidate(s) found.")
            for i, c in enumerate(candidates):
                logger.info(f"  [{i+1}] Kind: {c.kind}, Score: {c.score:.2f}, Box: {c.bbox}, Area: {c.area_frac:.4f}")
    
    logger.info("=== All Steps Completed Successfully! Model is live in DevaVisionAI ===")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Merge datasets, train YOLOv8, and integrate with DevaVisionAI")
    parser.add_argument("--epochs", type=int, default=25, help="Number of training epochs")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Base model")
    args = parser.parse_args()

    yaml_file = create_combined_dataset()
    best_weights = train_yolo_model(yaml_file, epochs=args.epochs, base_model=args.model)
    integrate_and_validate(best_weights)
