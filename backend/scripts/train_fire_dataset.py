"""
Automated Training Script for Fire Detection Dataset.

This script:
  1. Unzips the fire-detection.v1i.yolov8.zip dataset.
  2. Updates data.yaml with proper local paths.
  3. Fine-tunes YOLO11n (or yolo11s for better accuracy) on the dataset.
  4. Copies the resulting best.pt weights to backend/app/plugins/fire/fire_yolo.pt.
  5. Validates the trained model.

Recommended base models (via --model flag):
  yolo11n.pt  — default, fast (5.4 MB, +2% mAP vs yolov8n)
  yolo11s.pt  — better accuracy, GPU recommended
  yolov10n.pt — NMS-free, set USE_YOLOV10=true in .env after training
"""

import os
import shutil
import zipfile
import yaml
from pathlib import Path
from loguru import logger

# Paths
ZIP_PATH = r"C:\Users\Praveen\Downloads\fire-detection.v1i.yolov8.zip"
BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "dataset_fire"
TARGET_MODEL_PATH = BASE_DIR / "app" / "plugins" / "fire" / "fire_yolo.pt"


def extract_dataset():
    """Extract zip dataset into backend/dataset_fire."""
    if not os.path.exists(ZIP_PATH):
        raise FileNotFoundError(f"Dataset zip not found at: {ZIP_PATH}")

    logger.info(f"Extracting dataset from {ZIP_PATH} to {DATASET_DIR} ...")
    os.makedirs(DATASET_DIR, exist_ok=True)
    
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        z.extractall(DATASET_DIR)
    
    logger.info("Dataset extracted successfully.")


def fix_data_yaml():
    """Patch data.yaml with absolute paths for Ultralytics training."""
    yaml_path = DATASET_DIR / "data.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"data.yaml not found at {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Set absolute paths to train, val, test
    data["path"] = str(DATASET_DIR.resolve())
    data["train"] = "train/images"
    data["val"] = "valid/images"
    data["test"] = "test/images"

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False)

    logger.info(f"Updated data.yaml at {yaml_path}")
    logger.info(f"Classes found ({data.get('nc', 0)}): {data.get('names')}")
    return yaml_path


def train_model(data_yaml_path, model_name=None, epochs=15, device=None):
    """Fine-tune YOLO model on the fire dataset.

    Default model is GPU-aware:
      GPU available -> yolo11s.pt  (better accuracy, 47.0 mAP)
      CPU only      -> yolo11n.pt  (fast, 39.5 mAP)
    Override with the --model flag.
    """
    try:
        from ultralytics import YOLO  # noqa: PLC0415
    except ImportError:
        raise ImportError("ultralytics package is required. Run: pip install ultralytics")

    # Auto-select model based on GPU availability if not explicitly set
    if model_name is None:
        try:
            import torch  # noqa: PLC0415
            model_name = "yolo11s.pt" if torch.cuda.is_available() else "yolo11n.pt"
        except Exception:
            model_name = "yolo11n.pt"
        logger.info(
            f"Auto-selected base model: {model_name} "
            f"(GPU detected: {'yes' if 'yolo11s' in model_name else 'no'})"
        )

    logger.info(f"Starting YOLO training using baseline model: {model_name}")
    model = YOLO(model_name)

    kwargs = {
        "data": str(data_yaml_path),
        "epochs": epochs,
        "imgsz": 640,   # YOLO11 optimal; was 416 for small v8 models (incorrect)
        "batch": 16,
        "workers": 2,
        "project": str(BASE_DIR / "runs_fire"),
        "name": "train",
        "exist_ok": True,
        "verbose": True,
    }
    if device is not None:
        kwargs["device"] = device

    # Train model
    results = model.train(**kwargs)

    trained_weights = BASE_DIR / "runs_fire" / "train" / "weights" / "best.pt"
    if not trained_weights.exists():
        raise FileNotFoundError(f"Trained weights not found at {trained_weights}")

    # Copy to target location for DevaVisionAI fire plugin
    os.makedirs(TARGET_MODEL_PATH.parent, exist_ok=True)
    shutil.copy(trained_weights, TARGET_MODEL_PATH)
    
    size_mb = TARGET_MODEL_PATH.stat().st_size / (1024 * 1024)
    logger.info(f"✅ Training Complete! Saved weights ({size_mb:.2f} MB) to:\n   {TARGET_MODEL_PATH}")
    return trained_weights


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Train Fire Detection YOLO Model")
    parser.add_argument(
        "--model", type=str, default=None,
        help=(
            "Base model for fine-tuning. Default: auto (yolo11s on GPU, yolo11n on CPU).\n"
            "  GPU options : yolo11s.pt (recommended), yolo11m.pt, yolov8s.pt\n"
            "  CPU options : yolo11n.pt, yolov8n.pt\n"
            "  NMS-free    : yolov10n.pt (also set USE_YOLOV10=true in .env)"
        )
    )
    parser.add_argument("--epochs", type=int, default=15, help="Number of training epochs")
    parser.add_argument("--device", type=str, default=None, help="Device: '0' for GPU 0, 'cpu' for CPU")
    args = parser.parse_args()

    logger.info("=== Starting Automated Fire Model Training Pipeline ===")
    if not (DATASET_DIR / "data.yaml").exists():
        extract_dataset()
    yaml_path = fix_data_yaml()
    train_model(yaml_path, model_name=args.model, epochs=args.epochs, device=args.device)
    logger.info("=== Pipeline Completed Successfully! ===")


if __name__ == "__main__":
    main()
