import csv
import re
from pathlib import Path

import cv2
import numpy as np

DATASET_DIR = Path("/home/claude/anpr_dataset_v2")
OUT_DIR = Path("/home/claude/anpr_ocr_crops_v2")
IMG_H, IMG_W = 32, 128

CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CHAR_TO_IDX = {c: i for i, c in enumerate(CHARSET)}
MAX_LABEL_LEN = 13  # longest real Indian plate text is well under this


def clean_text(t: str) -> str:
    t = t.strip().upper()
    return re.sub(f"[^{CHARSET}]", "", t)


def crop_and_resize(img, box, w, h):
    xc, yc, bw, bh = box
    x1 = max(0, int((xc - bw / 2) * w))
    y1 = max(0, int((yc - bh / 2) * h))
    x2 = min(w, int((xc + bw / 2) * w))
    y2 = min(h, int((yc + bh / 2) * h))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = img[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (IMG_W, IMG_H))
    return resized


def process_split(split):
    rows = [r for r in csv.DictReader(open(DATASET_DIR / "manifest.csv")) if r["split"] == split]
    out_img_dir = OUT_DIR / split
    out_img_dir.mkdir(parents=True, exist_ok=True)

    kept = []
    skipped_too_long = 0
    skipped_bad_char = 0
    skipped_read_fail = 0

    for row in rows:
        text = clean_text(row["plate_text"])
        if not text:
            skipped_bad_char += 1
            continue
        if len(text) > MAX_LABEL_LEN:
            skipped_too_long += 1
            continue

        img_path = DATASET_DIR / split / "images" / row["image"]
        lbl_path = DATASET_DIR / split / "labels" / (Path(row["image"]).stem + ".txt")
        img = cv2.imread(str(img_path))
        if img is None or not lbl_path.exists():
            skipped_read_fail += 1
            continue
        h, w = img.shape[:2]
        cls, xc, yc, bw, bh = map(float, lbl_path.read_text().split())
        crop = crop_and_resize(img, (xc, yc, bw, bh), w, h)
        if crop is None:
            skipped_read_fail += 1
            continue

        stem = Path(row["image"]).stem
        out_path = out_img_dir / f"{stem}.png"
        cv2.imwrite(str(out_path), crop)
        kept.append((str(out_path), text))

    print(f"{split}: kept={len(kept)}  skipped(too_long={skipped_too_long}, "
          f"bad_chars={skipped_bad_char}, read_fail={skipped_read_fail})")
    return kept


if __name__ == "__main__":
    manifest = {}
    for split in ("train", "val", "test"):
        manifest[split] = process_split(split)

    import json
    with open(OUT_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f)
    print(f"\nCharset ({len(CHARSET)} chars): {CHARSET}")
    print(f"Saved crop manifest to {OUT_DIR / 'manifest.json'}")
