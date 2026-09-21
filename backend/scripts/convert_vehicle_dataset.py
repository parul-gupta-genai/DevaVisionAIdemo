import glob
import random
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

IMG_DIRS = {
    "tractor": ["/home/claude/vehicle_check/tractor/Tractor", "/home/claude/vehicle_check/tractor1/Tractor1"],
    "truck": ["/home/claude/vehicle_check/truck/Truck", "/home/claude/vehicle_check/truck1/Truck1"],
}
ANN_ROOT = "/home/claude/vehicle_check/ann/Annotations/Annotations"
OUT_DIR = Path("/home/claude/vehicle_dataset")
CLASS_NAMES = ["tractor", "truck"]
CLASS_IDS = {"tractor": 0, "truck": 1}
random.seed(42)


def find_images():
    images = {}
    for label, dirs in IMG_DIRS.items():
        for d in dirs:
            for f in Path(d).glob("*.jpg"):
                images[f.stem] = f
    return images


def find_annotations():
    return {Path(f).stem: f for f in glob.glob(f"{ANN_ROOT}/**/*.xml", recursive=True)}


def convert(xml_path):
    root = ET.parse(xml_path).getroot()
    size = root.find("size")
    w, h = float(size.find("width").text), float(size.find("height").text)
    lines = []
    for obj in root.findall("object"):
        name = obj.find("name").text.strip().lower()
        if name not in CLASS_IDS:
            continue
        cls = CLASS_IDS[name]
        box = obj.find("bndbox")
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
    images = find_images()
    annotations = find_annotations()
    ids = sorted(set(images) & set(annotations))
    print(f"Matched pairs: {len(ids)}")

    random.shuffle(ids)
    n = len(ids)
    n_train, n_val = int(n * 0.8), int(n * 0.1)
    splits = {"train": ids[:n_train], "val": ids[n_train:n_train + n_val], "test": ids[n_train + n_val:]}

    for split, split_ids in splits.items():
        img_out = OUT_DIR / split / "images"
        lbl_out = OUT_DIR / split / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)
        n_boxes = 0
        for stem in split_ids:
            lines = convert(annotations[stem])
            if not lines:
                continue
            shutil.copy(images[stem], img_out / f"{stem}.jpg")
            (lbl_out / f"{stem}.txt").write_text("\n".join(lines) + "\n")
            n_boxes += len(lines)
        print(f"{split}: {len(split_ids)} images, {n_boxes} boxes")

    (OUT_DIR / "data.yaml").write_text(
        "train: train/images\nval: val/images\ntest: test/images\n\n"
        f"nc: {len(CLASS_NAMES)}\nnames: {CLASS_NAMES}\n"
    )
    print(f"\nSaved to {OUT_DIR}")


if __name__ == "__main__":
    main()
