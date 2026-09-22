import argparse
import glob
import random
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

CLASS_NAMES = ["tractor", "truck"]
CLASS_IDS = {"tractor": 0, "truck": 1}
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
        if not p.exists():
            continue
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]:
            for f in p.rglob(ext):
                name_lower = f.stem.lower()
                parent_lower = str(f.parent).lower()
                # Determine class from path or filename
                label = None
                if "tractor" in name_lower or "tractor" in parent_lower:
                    label = "tractor"
                elif "truck" in name_lower or "truck" in parent_lower:
                    label = "truck"
                if label:
                    images[f.stem] = (f, label)
    return images


def find_annotations(search_dirs):
    annotations = {}
    for search_dir in search_dirs:
        p = Path(search_dir)
        if not p.exists():
            continue
        for ext in ["*.xml", "*.XML"]:
            for f in p.rglob(ext):
                annotations[f.stem] = f
    return annotations


def convert(xml_path):
    try:
        root = ET.parse(xml_path).getroot()
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
    ids = sorted(set(images.keys()) & set(annotations.keys()))
    print(f"Matched vehicle image+annotation pairs: {len(ids)}")

    if not ids:
        print("\nWARNING: No vehicle image+annotation pairs found!")
        print("Please ensure your raw vehicle dataset (tractor/truck images + XML annotations) is placed in /kaggle/input or raw_training_data.")
        return

    random.shuffle(ids)
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
            src_img, _ = images[stem]
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
