import xml.etree.ElementTree as ET
import shutil
import random
from pathlib import Path

IMG_DIRS = [
    "/home/claude/ppe_check/images/images",
    "/home/claude/ppe_check/images2/images2",
    "/home/claude/ppe_check/images4/images4",
    "/home/claude/ppe_check/image3/image3",
]
ANN_DIRS = [
    "/home/claude/ppe_check/ann/annotations",
    "/home/claude/ppe_check/ann1/annotations1",
    "/home/claude/ppe_check/ann2/annotations2",
    "/home/claude/ppe_check/ann3/annotation3",
]
OUT_DIR = Path("/home/claude/helmet_dataset")

# Only these two classes matter for "helmet vs no-helmet". "person" (751
# boxes, a different/rarer annotation style in this dataset covering whole
# people rather than head-region state) is dropped — it doesn't say
# helmet-or-not and would just add label noise for this specific task.
CLASS_MAP = {"helmet": 0, "head": 1}  # head = bare head = "no-helmet"
CLASS_NAMES = ["helmet", "no-helmet"]

random.seed(42)


def find_all(dirs, ext):
    out = {}
    for d in dirs:
        for f in Path(d).glob(f"*{ext}"):
            out[f.stem] = f
    return out


def convert_one(xml_path: Path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    size = root.find("size")
    w = int(size.find("width").text)
    h = int(size.find("height").text)

    lines = []
    for obj in root.findall("object"):
        name = obj.find("name").text.strip().lower()
        if name not in CLASS_MAP:
            continue
        cls = CLASS_MAP[name]
        box = obj.find("bndbox")
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
    images = find_all(IMG_DIRS, ".png")
    annotations = find_all(ANN_DIRS, ".xml")
    ids = sorted(set(images) & set(annotations))
    print(f"Matched image+annotation pairs: {len(ids)}")

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
        img_out = OUT_DIR / split / "images"
        lbl_out = OUT_DIR / split / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        n_boxes = 0
        n_empty = 0
        n_skipped_no_box = 0
        for stem in split_ids:
            lines = convert_one(annotations[stem])
            if not lines:
                n_skipped_no_box += 1
                continue  # image has zero helmet/head boxes — skip, not useful for this task
            shutil.copy(images[stem], img_out / f"{stem}.png")
            (lbl_out / f"{stem}.txt").write_text("\n".join(lines) + "\n")
            n_boxes += len(lines)

        stats[split] = {
            "images": len(list(img_out.iterdir())),
            "boxes": n_boxes,
            "skipped_no_relevant_box": n_skipped_no_box,
        }

    (OUT_DIR / "data.yaml").write_text(
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
