import argparse
import random
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

# Only these two classes matter for "helmet vs no-helmet".
CLASS_MAP = {"helmet": 0, "head": 1}  # head = bare head = "no-helmet"
CLASS_NAMES = ["helmet", "no-helmet"]

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


def find_all_files(search_paths, extensions):
    out = {}
    for p in search_paths:
        p = Path(p)
        if not p.exists():
            continue
        for ext in extensions:
            for f in p.rglob(f"*{ext}"):
                out[f.stem] = f
    return out


def convert_one(xml_path: Path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    size = root.find("size")
    if size is None:
        return []
    w = int(float(size.find("width").text))
    h = int(float(size.find("height").text))
    if w <= 0 or h <= 0:
        return []

    lines = []
    for obj in root.findall("object"):
        name_node = obj.find("name")
        if name_node is None or not name_node.text:
            continue
        name = name_node.text.strip().lower()
        if name not in CLASS_MAP:
            continue
        cls = CLASS_MAP[name]
        box = obj.find("bndbox")
        if box is None:
            continue
        xmin = float(box.find("xmin").text)
        ymin = float(box.find("ymin").text)
        xmax = float(box.find("xmax").text)
        ymax = float(box.find("ymax").text)

        xmin, xmax = max(0, xmin), min(w, xmax)
        ymin, ymax = max(0, ymin), min(h, ymax)
        if xmax <= xmin or ymax <= ymin:
            continue

        xc = (xmin + xmax) / 2 / w
        yc = (ymin + ymax) / 2 / h
        bw = (xmax - xmin) / w
        bh = (ymax - ymin) / h
        lines.append(f"{cls} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
    return lines


def main():
    parser = argparse.ArgumentParser(description="Convert Hard-Hat dataset to YOLO format")
    parser.add_argument("--raw-dir", type=str, default=None, help="Directory containing raw zips, images, and annotations")
    parser.add_argument("--out-dir", type=str, default="./helmet_dataset", help="Output directory for YOLO dataset")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()

    search_dirs = []
    if args.raw_dir:
        search_dirs.append(Path(args.raw_dir))

    # Add standard fallback search locations (Kaggle input, workspace raw_training_data, etc.)
    search_dirs.extend([
        Path("/kaggle/input"),
        Path("./raw_training_data/helmet"),
        Path("../raw_training_data/helmet"),
        Path("/home/claude/ppe_check"),
        Path("./raw_dataset"),
        Path("."),
    ])

    # Extract any zip files found in raw directories to out_dir / "extracted"
    extracted_dir = out_dir / "extracted"
    for s_dir in search_dirs:
        if s_dir.exists():
            extract_zips_if_any(s_dir, extracted_dir)

    search_dirs.append(extracted_dir)

    images = find_all_files(search_dirs, [".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"])
    annotations = find_all_files(search_dirs, [".xml", ".XML"])
    ids = sorted(set(images) & set(annotations))
    print(f"Matched image+annotation pairs initially: {len(ids)}")

    if not ids:
        try:
            import kagglehub
            print("\nNo local dataset found. Auto-downloading Hard-Hat dataset via kagglehub...")
            kh_path = kagglehub.dataset_download("andrewmvd/hard-hat-detection")
            print(f"Downloaded dataset to {kh_path}")
            search_dirs.append(Path(kh_path))
            images = find_all_files(search_dirs, [".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"])
            annotations = find_all_files(search_dirs, [".xml", ".XML"])
            ids = sorted(set(images) & set(annotations))
            print(f"Matched image+annotation pairs after download: {len(ids)}")
        except Exception as e:
            print(f"kagglehub auto-download failed: {e}")

    if not ids:
        print("\nWARNING: No image+annotation pairs found!")
        print("Please ensure your raw helmet dataset (images + VOC XML annotations) is placed in one of:")
        print("  - /kaggle/input/<dataset-name>")
        print("  - ./raw_training_data/helmet/")
        print("Or specify custom path using: python convert_helmet_dataset.py --raw-dir <path_to_raw_dataset>")
        return

    random.shuffle(ids)
    n = len(ids)
    n_train = int(n * 0.8)
    n_val = int(n * 0.1)
    splits = {
        "train": ids[:n_train],
        "val": ids[n_train:n_train + n_val],
        "test": ids[n_train + n_val:],
    }

    stats = {}
    for split, split_ids in splits.items():
        img_out = out_dir / split / "images"
        lbl_out = out_dir / split / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        n_boxes = 0
        n_skipped_no_box = 0
        for stem in split_ids:
            lines = convert_one(annotations[stem])
            if not lines:
                n_skipped_no_box += 1
                continue
            src_img = images[stem]
            dst_img = img_out / src_img.name
            shutil.copy(src_img, dst_img)
            (lbl_out / f"{stem}.txt").write_text("\n".join(lines) + "\n")
            n_boxes += len(lines)

        stats[split] = {
            "images": len(list(img_out.iterdir())),
            "boxes": n_boxes,
            "skipped_no_relevant_box": n_skipped_no_box,
        }

    (out_dir / "data.yaml").write_text(
        f"path: {out_dir.as_posix()}\n"
        "train: train/images\n"
        "val: val/images\n"
        "test: test/images\n\n"
        f"nc: {len(CLASS_NAMES)}\n"
        f"names: {CLASS_NAMES}\n"
    )

    for split, s in stats.items():
        print(f"{split}: {s}")


if __name__ == "__main__":
    main()
