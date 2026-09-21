import cv2
from pathlib import Path

DATASET_DIR = Path("/home/claude/helmet_dataset")
CROPS_DIR = Path("/home/claude/helmet_crops")
CLASS_NAMES = ["helmet", "no-helmet"]
PAD_FRAC = 0.15  # small padding around each box so the crop isn't razor-tight


def extract_split(split: str):
    img_dir = DATASET_DIR / split / "images"
    lbl_dir = DATASET_DIR / split / "labels"
    counts = {c: 0 for c in CLASS_NAMES}

    for img_path in img_dir.iterdir():
        lbl_path = lbl_dir / f"{img_path.stem}.txt"
        if not lbl_path.exists():
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]

        for i, line in enumerate(lbl_path.read_text().strip().splitlines()):
            parts = line.split()
            if len(parts) != 5:
                continue
            cls_id, xc, yc, bw, bh = int(parts[0]), *map(float, parts[1:])
            cls_name = CLASS_NAMES[cls_id]

            xc, yc, bw, bh = xc * w, yc * h, bw * w, bh * h
            bw *= (1 + PAD_FRAC)
            bh *= (1 + PAD_FRAC)
            x1 = max(0, int(xc - bw / 2))
            y1 = max(0, int(yc - bh / 2))
            x2 = min(w, int(xc + bw / 2))
            y2 = min(h, int(yc + bh / 2))
            if x2 <= x1 or y2 <= y1:
                continue

            crop = img[y1:y2, x1:x2]
            out_dir = CROPS_DIR / split / cls_name
            out_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out_dir / f"{img_path.stem}_{i}.png"), crop)
            counts[cls_name] += 1

    return counts


if __name__ == "__main__":
    for split in ("train", "val", "test"):
        counts = extract_split(split)
        print(f"{split}: {counts}")
