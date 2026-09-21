import os
import yaml
from pathlib import Path
from collections import Counter

def inspect_fire_training():
    base_dir = Path(r"C:\Users\Praveen\Downloads\CVSOLUTION\DevaVisionAI\backend")
    runs_dir = base_dir / "runs_fire" / "train"
    dataset_dir = base_dir / "dataset_fire"

    print("=" * 80)
    print("FIRE MODEL TRAINING & DATASET INSPECTION")
    print("=" * 80)

    # 1. Inspect dataset YAML
    data_yaml_path = dataset_dir / "data.yaml"
    if not data_yaml_path.exists():
        data_yaml_path = Path(r"C:\Users\Praveen\Downloads\fire_dataset\data.yaml")

    if data_yaml_path.exists():
        print(f"\n1. DATASET CONFIGURATION ({data_yaml_path}):")
        with open(data_yaml_path, "r", encoding="utf-8") as f:
            data_cfg = yaml.safe_load(f)
        names = data_cfg.get("names", {})
        nc = data_cfg.get("nc", len(names))
        print(f"   - Number of classes (nc): {nc}")
        print("   - Class Mapping:")
        if isinstance(names, list):
            for i, n in enumerate(names):
                print(f"       Class {i}: '{n}'")
        elif isinstance(names, dict):
            for i, n in names.items():
                print(f"       Class {i}: '{n}'")
    else:
        print(f"\n1. DATASET CONFIGURATION: NOT FOUND at {data_yaml_path}")

    # 2. Inspect Training Args (args.yaml)
    args_yaml_path = runs_dir / "args.yaml"
    if args_yaml_path.exists():
        print(f"\n2. TRAINING HYPERPARAMETERS ({args_yaml_path}):")
        with open(args_yaml_path, "r", encoding="utf-8") as f:
            args_cfg = yaml.safe_load(f)
        print(f"   - Base Model: {args_cfg.get('model')}")
        print(f"   - Epochs: {args_cfg.get('epochs')}")
        print(f"   - Batch Size: {args_cfg.get('batch')}")
        print(f"   - Image Size (imgsz): {args_cfg.get('imgsz')}")
        print(f"   - Optimizer: {args_cfg.get('optimizer')}")
        print(f"   - Learning Rate (lr0): {args_cfg.get('lr0')}")
    else:
        print(f"\n2. TRAINING ARGS: NOT FOUND at {args_yaml_path}")

    # 3. Inspect Dataset Labels Distribution
    print("\n3. DATASET CLASS DISTRIBUTION:")
    splits = ["train", "valid", "test"]
    for split in splits:
        labels_dir = dataset_dir / split / "labels"
        if not labels_dir.exists():
            continue
        
        label_files = list(labels_dir.glob("*.txt"))
        counts = Counter()
        total_boxes = 0

        for lfile in label_files:
            with open(lfile, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        cls_id = int(parts[0])
                        counts[cls_id] += 1
                        total_boxes += 1

        print(f"   Split '{split}' ({len(label_files)} image files, {total_boxes} total bounding boxes):")
        for cls_id in sorted(counts.keys()):
            cls_name = names[cls_id] if isinstance(names, list) and cls_id < len(names) else str(cls_id)
            print(f"     - Class {cls_id} ('{cls_name}'): {counts[cls_id]} boxes ({counts[cls_id]/max(1, total_boxes)*100:.1f}%)")

    # 4. Verify Weights Existence
    best_pt = runs_dir / "weights" / "best.pt"
    last_pt = runs_dir / "weights" / "last.pt"
    print("\n4. MODEL WEIGHTS VERIFICATION:")
    print(f"   - best.pt exists: {best_pt.exists()} ({best_pt.stat().st_size / (1024*1024):.2f} MB)" if best_pt.exists() else f"   - best.pt exists: False ({best_pt})")
    print(f"   - last.pt exists: {last_pt.exists()} ({last_pt.stat().st_size / (1024*1024):.2f} MB)" if last_pt.exists() else f"   - last.pt exists: False ({last_pt})")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    inspect_fire_training()
