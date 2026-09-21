import cv2
import numpy as np
from pathlib import Path
from skimage.feature import hog

CROPS_DIR = Path("/home/claude/vehicle_crops")
RESIZE = (128, 128)


def extract_features(img_path):
    img = cv2.imread(str(img_path))
    if img is None:
        return None
    img = cv2.resize(img, RESIZE)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    feats = {}

    # --- aspect ratio + size of the original crop (before resize) — tractors
    # tend to be narrower/taller relative to trucks' boxy rectangular cargo
    # bodies, and this is lost once we force-resize to a square ---
    orig = cv2.imread(str(img_path))
    h, w = orig.shape[:2]
    feats["aspect_ratio"] = w / h
    feats["log_area"] = np.log(max(w * h, 1))

    # --- colour histogram (HSV) — trucks in this dataset are often cargo
    # containers/cabs with more uniform colour blocks; tractors show more
    # exposed metal/engine + tire (darker, less saturated) ---
    for i, ch in enumerate(["h", "s", "v"]):
        hist = cv2.calcHist([hsv], [i], None, [8], [0, 256]).flatten()
        hist = hist / (hist.sum() + 1e-6)
        for j, v in enumerate(hist):
            feats[f"hsv_{ch}_{j}"] = float(v)

    # --- edge density (Canny) — proxy for structural complexity; a tractor's
    # exposed chassis/engine/large rear tire tends to produce a busier edge
    # map than a truck's flatter cargo-box panels ---
    edges = cv2.Canny(gray, 100, 200)
    feats["edge_density"] = float(edges.mean() / 255.0)

    # --- HOG (Histogram of Oriented Gradients) — captures overall shape/
    # silhouette, summarized to a small number of stats rather than the full
    # HOG vector to keep the feature count sane for ~260 training examples ---
    hog_feat = hog(gray, orientations=6, pixels_per_cell=(32, 32),
                    cells_per_block=(2, 2), feature_vector=True)
    feats["hog_mean"] = float(hog_feat.mean())
    feats["hog_std"] = float(hog_feat.std())
    feats["hog_max"] = float(hog_feat.max())

    # --- vertical profile — trucks' cargo boxes tend to have a flatter top
    # silhouette than a tractor's irregular cab/engine/exhaust-stack outline ---
    top_row_dark = (gray[:10, :] < 128).mean()
    feats["top_dark_fraction"] = float(top_row_dark)

    return feats


def build_split(split):
    rows, labels, paths = [], [], []
    for label_idx, cls in enumerate(["tractor", "truck"]):
        cls_dir = CROPS_DIR / split / cls
        if not cls_dir.exists():
            continue
        for f in sorted(cls_dir.iterdir()):
            feats = extract_features(f)
            if feats is None:
                continue
            rows.append(feats)
            labels.append(label_idx)
            paths.append(str(f))
    return rows, labels, paths


if __name__ == "__main__":
    import json
    out = {}
    for split in ("train", "val", "test"):
        rows, labels, paths = build_split(split)
        out[split] = {"rows": rows, "labels": labels, "paths": paths}
        print(f"{split}: {len(rows)} crops, {sum(labels)} truck / {len(labels)-sum(labels)} tractor")
    json.dump(out, open("/home/claude/vehicle_features.json", "w"))
    print("Saved to /home/claude/vehicle_features.json")
