import glob
import os
import random
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

SOURCES = {
    "google_images": "/home/claude/anpr_check/gi/google_images",
    "google_images1": "/home/claude/anpr_check/gi1/google_images1",
    "video_images": "/home/claude/anpr_check/vi/video_images",
    "video_images1": "/home/claude/anpr_check/vi1/video_images1",
}
# OLX is nested one level deeper (per-state subfolders)
OLX_ROOT = "/home/claude/anpr_check/olx/State-wise_OLX"

OUT_DIR = Path("/home/claude/anpr_dataset")
IMG_EXTS = (".jpg", ".jpeg", ".png", ".JPG")
random.seed(42)


def find_image_for(xml_path: str):
    base = xml_path[:-4]
    for ext in IMG_EXTS:
        if os.path.exists(base + ext):
            return base + ext
    return None


def collect_pairs():
    pairs = []  # (image_path, xml_path, plate_text, source_tag)
    for tag, d in SOURCES.items():
        for xml_path in glob.glob(f"{d}/**/*.xml", recursive=True):
            img = find_image_for(xml_path)
            if img:
                pairs.append((img, xml_path, tag))
    for state_dir in Path(OLX_ROOT).iterdir():
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
    pairs = collect_pairs()
    print(f"Total matched image+annotation pairs: {len(pairs)}")

    random.shuffle(pairs)
    n = len(pairs)
    n_train, n_val = int(n * 0.8), int(n * 0.1)
    splits = {
        "train": pairs[:n_train],
        "val": pairs[n_train:n_train + n_val],
        "test": pairs[n_train + n_val:],
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
            if yolo_line is None:
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
    print(f"\nGround-truth plate texts preserved in {OUT_DIR / 'manifest.csv'} "
          "(not used for detection training, but needed for OCR evaluation).")


if __name__ == "__main__":
    main()
