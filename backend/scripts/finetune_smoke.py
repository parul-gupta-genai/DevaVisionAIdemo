"""
Fine-tune the existing fire/smoke model (fire_yolo.pt) on additional smoke
data, without retraining from scratch and without forgetting the fire /
light / no-fire classes.

WHY THIS SCRIPT (not train_fire_dataset.py) FOR THE NEW SMOKE DATA:
  - train_fire_dataset.py starts from a blank yolov8n.pt and trains only on
    whatever single dataset you point it at. If you ran it on the new
    smoke-only data as-is, the model would learn ONLY "smoke" and forget
    fire/light/no-fire entirely (catastrophic forgetting) — every image in
    that dataset has zero fire/light/no-fire boxes, so the loss pushes the
    model to stop predicting them.
  - This script instead RESUMES from your current, already-trained
    fire_yolo.pt, freezes the backbone (early feature-extraction layers),
    and fine-tunes only the head with a low learning rate for a small
    number of epochs. That keeps fire/light/no-fire recognition intact
    while improving smoke recall.

BEFORE YOU RUN THIS (important):
  1. This only teaches the model MORE about smoke. It cannot verify fire/
     light/no-fire didn't regress, because backend/dataset_smoke_v2 has NO
     fire/light/no-fire images. If you still have the original dataset
     used for fire_yolo.pt (fire-detection.v1i.yolov8.zip, referenced in
     train_fire_dataset.py), the safest approach is to MERGE that dataset's
     train/valid/test images+labels with backend/dataset_smoke_v2's before
     running this script, so every epoch sees all 4 classes together. This
     script will use whichever it finds — see merge_datasets() below.
  2. Requires a GPU machine with `ultralytics` installed
     (`pip install ultralytics`). Not meant to run on a CPU-only sandbox —
     even a few epochs over ~750 images will be very slow on CPU.
  3. Always validate afterwards on a few real fire clips from camera 1/2
     (the cameras this model already serves) to confirm fire detection
     didn't regress, not just the new smoke set.

USAGE:
    python finetune_smoke.py --epochs 8
    python finetune_smoke.py --original-dataset "C:\\path\\to\\fire-detection.v1i.yolov8" --epochs 8
"""

import argparse
import shutil
from pathlib import Path

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
CURRENT_MODEL = BASE_DIR / "app" / "plugins" / "fire" / "fire_yolo.pt"
NEW_SMOKE_DATASET = BASE_DIR / "dataset_smoke_v2"
MERGED_DATASET = BASE_DIR / "dataset_fire_smoke_merged"
TARGET_MODEL_PATH = CURRENT_MODEL  # overwritten only after validation prompt


def merge_datasets(original_dataset: Path | None) -> Path:
    """
    Build a merged dataset directory combining the new smoke-only data with
    the original fire/light/no-fire/smoke dataset, if provided. If no
    original dataset is given (or not found), fine-tunes on the new smoke
    data alone (backbone-frozen, low-LR — see module docstring for why
    that's still safe-ish, just less thorough than a proper merge).
    """
    if original_dataset is None or not original_dataset.exists():
        logger.warning(
            "No original fire dataset given/found — fine-tuning on the new "
            "smoke data alone. Backbone will be frozen and LR kept low to "
            "limit forgetting, but a real merge (see docstring) is safer."
        )
        return NEW_SMOKE_DATASET

    logger.info(f"Merging {original_dataset} with {NEW_SMOKE_DATASET} ...")
    for split in ("train", "valid", "test"):
        for kind in ("images", "labels"):
            dst = MERGED_DATASET / split / kind
            dst.mkdir(parents=True, exist_ok=True)
            for src_root in (original_dataset, NEW_SMOKE_DATASET):
                src = src_root / split / kind
                if not src.exists():
                    continue
                for f in src.iterdir():
                    if f.is_file():
                        # Prefix by source to avoid filename collisions
                        # between the two datasets.
                        shutil.copy(f, dst / f"{src_root.name}__{f.name}")

    (MERGED_DATASET / "data.yaml").write_text(
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n\n"
        "nc: 4\n"
        "names: ['fire', 'light', 'no-fire', 'smoke']\n"
    )
    logger.info(f"Merged dataset ready at {MERGED_DATASET}")
    return MERGED_DATASET


def finetune(dataset_dir: Path, epochs: int, freeze: int, lr0: float, device: str | None):
    try:
        from ultralytics import YOLO
    except ImportError:
        raise ImportError("ultralytics package is required. Run: pip install ultralytics")

    if not CURRENT_MODEL.exists():
        raise FileNotFoundError(
            f"Expected existing model at {CURRENT_MODEL} to fine-tune from. "
            "This script continues training from it — it does not start fresh."
        )

    logger.info(f"Resuming training from existing model: {CURRENT_MODEL}")
    model = YOLO(str(CURRENT_MODEL))

    kwargs = {
        "data": str(dataset_dir / "data.yaml"),
        "epochs": epochs,
        "imgsz": 416,
        "batch": 16,
        "workers": 2,
        "lr0": lr0,          # low LR: nudge, don't overwrite, existing weights
        "freeze": freeze,    # freeze first N layers (backbone) of the backbone
        "project": str(BASE_DIR / "runs_smoke_finetune"),
        "name": "train",
        "exist_ok": True,
        "verbose": True,
    }
    if device is not None:
        kwargs["device"] = device

    results = model.train(**kwargs)

    trained_weights = BASE_DIR / "runs_smoke_finetune" / "train" / "weights" / "best.pt"
    if not trained_weights.exists():
        raise FileNotFoundError(f"Trained weights not found at {trained_weights}")

    logger.info(
        f"Fine-tuning complete. New weights at: {trained_weights}\n"
        f"They are NOT auto-copied over {CURRENT_MODEL}. Validate them first:\n"
        f"  yolo val model={trained_weights} data={dataset_dir / 'data.yaml'}\n"
        "and spot-check a few real fire clips before replacing fire_yolo.pt."
    )
    return trained_weights


def main():
    parser = argparse.ArgumentParser(description="Fine-tune fire_yolo.pt on additional smoke data")
    parser.add_argument(
        "--original-dataset", type=str, default=None,
        help="Path to the original fire-detection.v1i.yolov8 dataset folder (train/valid/test), "
             "if you still have it. Strongly recommended — see module docstring.",
    )
    parser.add_argument("--epochs", type=int, default=8, help="Fine-tune epochs (keep this small)")
    parser.add_argument("--freeze", type=int, default=10, help="Number of leading layers to freeze")
    parser.add_argument("--lr0", type=float, default=0.001, help="Initial learning rate (kept low)")
    parser.add_argument("--device", type=str, default=None, help="'0' for GPU 0, 'cpu' for CPU")
    args = parser.parse_args()

    original = Path(args.original_dataset) if args.original_dataset else None
    dataset_dir = merge_datasets(original)
    finetune(dataset_dir, epochs=args.epochs, freeze=args.freeze, lr0=args.lr0, device=args.device)


if __name__ == "__main__":
    main()
