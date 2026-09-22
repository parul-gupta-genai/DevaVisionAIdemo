import argparse
import glob
import random
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

CLASS_NAMES = ["tractor", "truck"]
CLASS_IDS = {
    "tractor": 0,
    "truck": 1,
    "car": 1,
    "bus": 1,
    "vehicle": 1,
    "van": 1,
    "heavy-vehicle": 1,
    "automobile": 1,
}
random.seed(42)


def extract_zips_if_any(raw_dir: Path, target_dir: Path):
    zip_files = list(raw_dir.rglob("*.zip"))
    if zip_files:
        print(f"Found {len(zip_files)} zip file(s) in {raw_dir}, extracting...")
        for zpath in zip_files:
            try:
                with zipfile.ZipFile(zpath, 'r') as z:
                    z.extractall(target_dir)
            except Exception as e:
                print(f"Warning: Failed to extract {zpath}: {e}")


def find_vehicle_images(search_dirs):
    images = {}
    for search_dir in search_dirs:
        p = Path(search_dir)
        if not p.exists() or "helmet_dataset" in str(p).lower() or "hard-hat" in str(p).lower():
            continue
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]:
            for f in p.rglob(ext):
                images[f.stem] = f
    return images


def find_annotations(search_dirs):
    annotations = {}
    for search_dir in search_dirs:
        p = Path(search_dir)
        if not p.exists() or "helmet_dataset" in str(p).lower() or "hard-hat" in str(p).lower():
            continue
        for ext in ["*.xml", "*.XML", "*.txt", "*.TXT"]:
            for f in p.rglob(ext):
                if f.name.lower() in ["data.yaml", "dataset.yaml", "requirements.txt", "classes.txt", "notes.json"]:
                    continue
                annotations[f.stem] = f
    return annotations


def convert(ann_path):
    if ann_path.suffix.lower() in [".txt"]:
        lines = []
        try:
            content = ann_path.read_text().strip().splitlines()
            for line in content:
                parts = line.strip().split()
                if len(parts) == 5:
                    cls, xc, yc, bw, bh = parts
                    try:
                        cls_idx = int(cls)
                        # map any class 0 or 1 or higher to valid tractor(0) or truck(1)
                        mapped_cls = 0 if cls_idx == 0 else 1
                        lines.append(f"{mapped_cls} {float(xc):.6f} {float(yc):.6f} {float(bw):.6f} {float(bh):.6f}")
                    except ValueError:
                        pass
        except Exception:
            pass
        return lines

    try:
        root = ET.parse(ann_path).getroot()
    except Exception:
        return []
    size = root.find("size")
    if size is None:
        return []
    w, h = float(size.find("width").text), float(size.find("height").text)
    if w <= 0 or h <= 0:
        return []
    lines = []
    for obj in root.findall("object"):
        name_node = obj.find("name")
        if name_node is None or not name_node.text:
            continue
        name = name_node.text.strip().lower()
        if name not in CLASS_IDS:
            continue
        cls = CLASS_IDS[name]
        box = obj.find("bndbox")
        if box is None:
            continue
        xmin = max(0, float(box.find("xmin").text))
        ymin = max(0, float(box.find("ymin").text))
        xmax = min(w, float(box.find("xmax").text))
        ymax = min(h, float(box.find("ymax").text))
        if xmax <= xmin or ymax <= ymin:
            continue
        xc, yc = (xmin + xmax) / 2 / w, (ymin + ymax) / 2 / h
        bw, bh = (xmax - xmin) / w, (ymax - ymin) / h
        lines.append(f"{cls} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
    return lines


def create_synthetic_dataset(out_dir):
    import cv2
    import numpy as np
    print("\nNo raw or Kaggle dataset found. Generating synthetic Vehicle dataset as fallback...")
    splits = {"train": 30, "val": 6, "test": 6}
    for split, count in splits.items():
        img_dir = out_dir / split / "images"
        lbl_dir = out_dir / split / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            img = np.full((640, 640, 3), random.randint(100, 200), dtype=np.uint8)
            boxes = []
            cls_id = random.choice([0, 1])
            xmin, ymin = random.randint(50, 200), random.randint(50, 200)
            w, h = random.randint(150, 300), random.randint(150, 300)
            color = (0, 255, 0) if cls_id == 0 else (0, 0, 255)
            cv2.rectangle(img, (xmin, ymin), (xmin + w, ymin + h), color, -1)
            cv2.putText(img, "Tractor" if cls_id == 0 else "Truck", (xmin + 10, ymin + 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            xc, yc = (xmin + w / 2) / 640.0, (ymin + h / 2) / 640.0
            bw, bh = w / 640.0, h / 640.0
            boxes.append(f"{cls_id} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")

            stem = f"synth_veh_{split}_{i:03d}"
            cv2.imwrite(str(img_dir / f"{stem}.jpg"), img)
            (lbl_dir / f"{stem}.txt").write_text("\n".join(boxes) + "\n")

    (out_dir / "data.yaml").write_text(
        f"path: {out_dir.as_posix()}\n"
        "train: train/images\nval: val/images\ntest: test/images\n\n"
        f"nc: {len(CLASS_NAMES)}\nnames: {CLASS_NAMES}\n"
    )
    print(f"Successfully generated synthetic vehicle dataset at {out_dir}")


def main():
    parser = argparse.ArgumentParser(description="Convert Vehicle (Tractor/Truck) dataset to YOLO format")
    parser.add_argument("--raw-dir", type=str, default=None, help="Path to raw dataset directory")
    parser.add_argument("--out-dir", type=str, default="./vehicle_dataset", help="Output directory for YOLO dataset")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    search_dirs = []
    if args.raw_dir:
        search_dirs.append(Path(args.raw_dir))

    search_dirs.extend([
        Path("/kaggle/input"),
        Path("./raw_training_data/vehicle"),
        Path("../raw_training_data/vehicle"),
        Path("/home/claude/vehicle_check"),
        Path("."),
    ])

    extracted_dir = out_dir / "extracted"
    for s_dir in search_dirs:
        if s_dir.exists():
            extract_zips_if_any(s_dir, extracted_dir)
    search_dirs.append(extracted_dir)

    images = find_vehicle_images(search_dirs)
    annotations = find_annotations(search_dirs)
    candidate_ids = sorted(set(images.keys()) & set(annotations.keys()))
    valid_ids = [stem for stem in candidate_ids if convert(annotations[stem])]
    print(f"Matched valid vehicle image+annotation pairs initially: {len(valid_ids)}")

    if not valid_ids:
        datasets_to_try = [
            "mhananasghar/vehicle-detection-yolo-version",
            "rohangupta/vehicle-detection",
            "haseebhsb/yolo-person-vehicle-detection-dataset-annotated",
            "mushafiq/vehicle-dataset-for-yolo",
            "pkdarabi/vehicle-detection-dataset",
            "vitaliypolyakov/vehicle-detection",
            "ahmetfurkandemir/vehicle-detection-dataset",
            "vijaykumar22/vehicle-detection-dataset"
        ]
        import kagglehub
        for ds in datasets_to_try:
            try:
                print(f"\nTrying to auto-download Vehicle dataset '{ds}' via kagglehub...")
                kh_path = Path(kagglehub.dataset_download(ds))
                print(f"Downloaded vehicle dataset to {kh_path}")
                search_dirs.append(kh_path)

                yaml_files = list(kh_path.rglob("data.yaml")) + list(kh_path.rglob("*.yaml"))
                if yaml_files:
                    print(f"Found existing YOLO data.yaml at {yaml_files[0]}")
                    out_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(yaml_files[0], out_dir / "data.yaml")
                    print(f"Successfully configured YOLO dataset at {out_dir}")
                    return

                images = find_vehicle_images(search_dirs)
                annotations = find_annotations(search_dirs)
                candidate_ids = sorted(set(images.keys()) & set(annotations.keys()))
                valid_ids = [stem for stem in candidate_ids if convert(annotations[stem])]
                if valid_ids:
                    print(f"Matched valid vehicle pairs after download: {len(valid_ids)}")
                    break
            except Exception as e:
                print(f"Attempt for '{ds}' failed: {e}")

    if not valid_ids:
        create_synthetic_dataset(out_dir)
        return

    random.shuffle(valid_ids)
    ids = valid_ids
    n = len(ids)
    n_train, n_val = int(n * 0.8), int(n * 0.1)
    splits = {"train": ids[:n_train], "val": ids[n_train:n_train + n_val], "test": ids[n_train + n_val:]}

    for split, split_ids in splits.items():
        img_out = out_dir / split / "images"
        lbl_out = out_dir / split / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)
        n_boxes = 0
        for stem in split_ids:
            lines = convert(annotations[stem])
            if not lines:
                continue
            src_img = images[stem]
            shutil.copy(src_img, img_out / src_img.name)
            (lbl_out / f"{stem}.txt").write_text("\n".join(lines) + "\n")
            n_boxes += len(lines)
        print(f"{split}: {len(split_ids)} images, {n_boxes} boxes")

    (out_dir / "data.yaml").write_text(
        f"path: {out_dir.as_posix()}\n"
        "train: train/images\nval: val/images\ntest: test/images\n\n"
        f"nc: {len(CLASS_NAMES)}\nnames: {CLASS_NAMES}\n"
    )
    print(f"\nSaved vehicle dataset to {out_dir}")


if __name__ == "__main__":
    main()

