"""
Train a real YOLO detector for tractor / truck — the upgrade path from
vehicle_classifier.py's crop-based Random Forest (only 60% accuracy — the
weakest of all the models in this project, because it was trained from
just 326 images) to a proper detector.

WHY THIS WASN'T DONE IN THE SANDBOX: same reason as the helmet detector —
PyTorch/ultralytics needs CUDA libraries this sandbox's disk couldn't fit.
Run this on your own GPU machine.

BEFORE RUNNING:
  1. python convert_vehicle_dataset.py
     (reads from raw_training_data's Tractor/Tractor1/Truck/Truck1/
     Annotations zips — see that script's IMG_DIRS/ANN_ROOT for the exact
     folder layout it expects)
     Produces /home/claude/vehicle_dataset/{train,val,test}.

  2. pip install ultralytics

USAGE:
    python train_vehicle_yolo.py --epochs 150

IMPORTANT — MANAGE EXPECTATIONS: this dataset is genuinely small (326
images, only 96 of them tractor). A YOLO detector will very likely still
outperform the 60%-accuracy Random Forest classifier (YOLO's convolutional
features generalize better than handcrafted HOG/colour features even on
modest data, and it gets the advantage of locating vehicles itself rather
than depending on a separate detector for crops) — but with this little
data, don't expect a highly reliable detector either. More tractor images
specifically (currently the bottleneck class) would help more than any
amount of further tuning on these same 326 photos.
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Train YOLO tractor/truck detector")
    parser.add_argument("--data-yaml", type=str, default="./vehicle_dataset/data.yaml")
    parser.add_argument("--model", type=str, default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=150,
                         help="More than helmet's default — small datasets benefit from more "
                              "passes since each epoch sees far fewer images")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8,
                         help="Smaller default than helmet's — 260 train images means fewer "
                              "batches per epoch either way, and a smaller batch adds useful "
                              "gradient noise that can help generalization on tiny datasets")
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument("--project", type=str, default="./runs_vehicle_yolo")
    args = parser.parse_args()

    data_yaml = Path(args.data_yaml)
    if not data_yaml.exists():
        raise FileNotFoundError(
            f"{data_yaml} not found. Run convert_vehicle_dataset.py first."
        )

    import torch
    from ultralytics import YOLO

    device = args.device
    if device is not None and device != "cpu" and not torch.cuda.is_available():
        print(f"WARNING: Device '{device}' requested, but CUDA is not available in PyTorch. Auto-falling back to CPU.")
        device = "cpu"

    model = YOLO(args.model)
    kwargs = dict(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name="train",
        exist_ok=True,
        patience=30,  # generous — small-dataset training is noisier epoch to epoch
        # Heavier augmentation than ultralytics' defaults, since 260 training
        # images need all the help they can get to avoid overfitting:
        degrees=10.0,
        translate=0.15,
        scale=0.3,
        fliplr=0.5,
        mosaic=1.0,
    )
    if device is not None:
        kwargs["device"] = device

    results = model.train(**kwargs)

    print(f"\nTraining complete. Best weights: {args.project}/train/weights/best.pt")
    print("Validate with:")
    print(f"  yolo val model={args.project}/train/weights/best.pt data={data_yaml}")
    print("\nCompare its precision/recall per class against the Random Forest's "
          "60% accuracy / 40% tractor recall / 70% truck recall before switching over — "
          "on a dataset this small, results can vary a fair bit by random seed.")


if __name__ == "__main__":
    main()
