import glob
import hashlib
import os
import random
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

# Every source folder we've received across all uploads. Old and new
# batches often reused the same folder NAME (e.g. "google_images1") for
# genuinely different photo sets, or the same photos re-exported — content
# hashing below (not filename) is what actually decides what's a duplicate.
SOURCES = {
    "gi_a": "/home/claude/anpr_check/gi/google_images",
    "gi1_a": "/home/claude/anpr_check/gi1/google_images1",
    "vi_a": "/home/claude/anpr_check/vi/video_images",
    "vi1_a": "/home/claude/anpr_check/vi1/video_images1",
    "gi_b": "/home/claude/anpr_check_v2/gi/google_images",
    "gi1_b": "/home/claude/anpr_check_v2/gi1/google_images1",
    "gi2_b": "/home/claude/anpr_check_v2/gi2/google_images2",
    "gi3_b": "/home/claude/anpr_check_v2/gi3/google_images3",
    "vi_b": "/home/claude/anpr_check_v2/vi/video_images",
    "vi1_b": "/home/claude/anpr_check_v2/vi1/video_images1",
    "vi2_b": "/home/claude/anpr_check_v2/vi2/vide_images2",
    "vi3_b": "/home/claude/anpr_check_v2/vi3/video_images3",
}
OLX_ROOTS = [
    "/home/claude/anpr_check/olx/State-wise_OLX",
    "/home/claude/anpr_check_v2/olx/State-wise_OLX",
]

OUT_DIR = Path("/home/claude/anpr_dataset_v2")
IMG_EXTS = (".jpg", ".jpeg", ".png", ".JPG")
random.seed(42)


def find_image_for(xml_path: str):
    base = xml_path[:-4]
    for ext in IMG_EXTS:
        if os.path.exists(base + ext):
            return base + ext
    return None


def file_hash(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def collect_pairs():
    pairs = []
    for tag, d in SOURCES.items():
        for xml_path in glob.glob(f"{d}/**/*.xml", recursive=True):
            img = find_image_for(xml_path)
            if img:
                pairs.append((img, xml_path, tag))
    for root in OLX_ROOTS:
        for state_dir in Path(root).iterdir():
            if not state_dir.is_dir():
                continue
            for xml_path in glob.glob(f"{state_dir}/*.xml"):
                img = find_image_for(xml_path)
                if img:
                    pairs.append((img, xml_path, f"olx_{state_dir.name}"))
    return pairs


def convert_box(xml_path: str):
    root = ET.parse(xml_path).getroot()
    size = root.find("size")
    w, h = int(size.find("width").text), int(size.find("height").text)
    obj = root.find("object")
    if obj is None:
        return None, None
    plate_text = obj.find("name").text.strip()
    box = obj.find("bndbox")
    xmin, ymin = float(box.find("xmin").text), float(box.find("ymin").text)
    xmax, ymax = float(box.find("xmax").text), float(box.find("ymax").text)
    xmin, xmax = max(0, xmin), min(w, xmax)
    ymin, ymax = max(0, ymin), min(h, ymax)
    if xmax <= xmin or ymax <= ymin:
        return None, plate_text
    xc, yc = (xmin + xmax) / 2 / w, (ymin + ymax) / 2 / h
    bw, bh = (xmax - xmin) / w, (ymax - ymin) / h
    return f"0 {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}", plate_text


def main():
    all_pairs = collect_pairs()
    print(f"Total (image, xml) pairs found across all sources: {len(all_pairs)}")

    seen_hashes = set()
    deduped = []
    for img_path, xml_path, tag in all_pairs:
        try:
            h = file_hash(img_path)
        except Exception:
            continue
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        deduped.append((img_path, xml_path, tag))

    print(f"After content-hash deduplication: {len(deduped)} unique images "
          f"({len(all_pairs) - len(deduped)} duplicates removed)")

    random.shuffle(deduped)
    n = len(deduped)
    n_train, n_val = int(n * 0.8), int(n * 0.1)
    splits = {
        "train": deduped[:n_train],
        "val": deduped[n_train:n_train + n_val],
        "test": deduped[n_train + n_val:],
    }

    manifest_lines = ["image,split,plate_text,source"]
    for split, split_pairs in splits.items():
        img_out = OUT_DIR / split / "images"
        lbl_out = OUT_DIR / split / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        n_ok = 0
        for img_path, xml_path, tag in split_pairs:
            yolo_line, plate_text = convert_box(xml_path)
            if yolo_line is None or not plate_text:
                continue
            stem = f"{tag}_{Path(img_path).stem}".replace(" ", "_")
            ext = Path(img_path).suffix
            shutil.copy(img_path, img_out / f"{stem}{ext}")
            (lbl_out / f"{stem}.txt").write_text(yolo_line + "\n")
            manifest_lines.append(f"{stem}{ext},{split},{plate_text},{tag}")
            n_ok += 1
        print(f"{split}: {n_ok} images")

    (OUT_DIR / "data.yaml").write_text(
        "train: train/images\nval: val/images\ntest: test/images\n\n"
        "nc: 1\nnames: ['license_plate']\n"
    )
    (OUT_DIR / "manifest.csv").write_text("\n".join(manifest_lines) + "\n")
    print(f"\nSaved to {OUT_DIR}")


if __name__ == "__main__":
    main()
