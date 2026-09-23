"""
Train a real YOLO detector for helmet / no-helmet — the upgrade path from
helmet_classifier.py's crop-based CNN (79% accuracy, needs a person/head
detector to feed it crops) to a single-stage detector that finds AND
classifies heads directly in a full frame.

WHY THIS WASN'T DONE IN THE SANDBOX: PyTorch (which ultralytics needs) is
the CUDA-enabled build by default on PyPI — even for CPU-only use it tries
to load several GB of CUDA libraries at import time, which didn't fit this
environment's disk budget. Run this on your own GPU machine instead.

BEFORE RUNNING:
  1. Get the dataset into YOLO format first (bounding boxes, not crops):
       python convert_helmet_dataset.py
     This reads from the raw Kaggle "Hard Hat Workers" images+XML
     (see raw_training_data/helmet/ in your backup zip — extract those 8
     zips into the folder structure convert_helmet_dataset.py expects, or
     edit its IMG_DIRS/ANN_DIRS paths to point at wherever you put them).
     Produces /home/claude/helmet_dataset/{train,val,test} — copy that to
     wherever you run this script from, or edit DATA_YAML below.

  2. pip install ultralytics

USAGE:
    python train_helmet_yolo.py --epochs 100
    python train_helmet_yolo.py --epochs 100 --model yolo11s.pt --device 0

Recommended base models:
  yolo11n.pt  — default, fast (5.4 MB, +2% mAP vs yolov8n)
  yolo11s.pt  — better accuracy with GPU
  yolov10n.pt — NMS-free option

WHAT TO EXPECT: with ~3900 images (the full Hard Hat Workers dataset) this
should comfortably beat the 79%-accuracy crop classifier, and — unlike that
classifier — will locate heads in a full frame on its own rather than
needing a separate person detector to hand it crops first. Still validate
on real camera footage before trusting it unsupervised; the training data
here is general construction-site photos, not this project's specific
camera angles/lighting.
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Train YOLO helmet/no-helmet detector")
    parser.add_argument("--data-yaml", type=str, default="./helmet_dataset/data.yaml",
                         help="Path to the YOLO-format data.yaml (from convert_helmet_dataset.py)")
    parser.add_argument(
        "--model", type=str, default=None,
        help=(
            "Base model. Default: auto (yolo11s on GPU, yolo11n on CPU).\n"
            "  GPU: yolo11s.pt (recommended), yolo11m.pt, yolov8s.pt\n"
            "  CPU: yolo11n.pt, yolov8n.pt"
        )
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", type=str, default=None, help="'0' for GPU 0, 'cpu' for CPU")
    parser.add_argument("--project", type=str, default="./runs_helmet_yolo")
    args = parser.parse_args()

    data_yaml = Path(args.data_yaml)
    if not data_yaml.exists():
        raise FileNotFoundError(
            f"{data_yaml} not found. Run convert_helmet_dataset.py first — "
            "see the module docstring above for where the raw dataset comes from."
        )

    import torch
    from ultralytics import YOLO

    device = args.device
    if device is not None and device != "cpu" and not torch.cuda.is_available():
        print(f"WARNING: Device '{device}' requested, but CUDA is not available. Falling back to CPU.")
        device = "cpu"

    # Auto-select model based on GPU availability
    model_name = args.model
    if model_name is None:
        model_name = "yolo11s.pt" if torch.cuda.is_available() else "yolo11n.pt"
        print(f"Auto-selected base model: {model_name} (GPU: {torch.cuda.is_available()})")

    model = YOLO(model_name)
    kwargs = dict(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name="train",
        exist_ok=True,
        patience=20,  # early stop if val mAP doesn't improve for 20 epochs
    )
    if device is not None:
        kwargs["device"] = device

    results = model.train(**kwargs)

    print(f"\nTraining complete. Best weights: {args.project}/train/weights/best.pt")
    print("Validate with:")
    print(f"  yolo val model={args.project}/train/weights/best.pt data={data_yaml}")
    print("\nTo deploy: replace backend/app/plugins/ppe/helmet_classifier.keras usage with this "
          "detector directly (it locates heads itself — no separate person/head-crop step needed).")


if __name__ == "__main__":
    main()
