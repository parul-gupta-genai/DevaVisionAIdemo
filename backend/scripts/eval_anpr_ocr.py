import csv
import re
import subprocess
import tempfile
from pathlib import Path

import cv2

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "dataset_anpr"
if not DATASET_DIR.exists():
    for fallback in [Path("/home/claude/anpr_dataset"), Path("/kaggle/input/anpr_dataset")]:
        if fallback.exists():
            DATASET_DIR = fallback
            break
SPLIT = "test"


def read_plate_tesseract(crop_bgr):
    """OCR a plate crop with Tesseract, restricted to alphanumeric characters."""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    scale = max(1, 200 // max(gray.shape[0], 1))
    if scale > 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    try:
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            cv2.imwrite(f.name, gray)
            result = subprocess.run(
                ["tesseract", f.name, "stdout", "--psm", "7",
                 "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"],
                capture_output=True, text=True, timeout=5,
            )
        text = result.stdout.strip().upper()
        res = re.sub(r"[^A-Z0-9]", "", text)
        if res:
            return res
    except Exception:
        pass

    try:
        import easyocr
        if not hasattr(read_plate_tesseract, "easy_reader"):
            read_plate_tesseract.easy_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        results = read_plate_tesseract.easy_reader.readtext(crop_bgr)
        if results:
            text = "".join([r[1] for r in results]).upper()
            return re.sub(r"[^A-Z0-9]", "", text)
    except Exception:
        pass

    return ""


def char_accuracy(pred, truth):
    if not truth:
        return 0.0
    matches = sum(1 for a, b in zip(pred, truth) if a == b)
    return matches / max(len(truth), len(pred))


def main():
    manifest = DATASET_DIR / "manifest.csv"
    if not manifest.exists():
        print(f"ANPR manifest.csv not found at {manifest}")
        return
    rows = list(csv.DictReader(open(manifest)))
    test_rows = [r for r in rows if r.get("split") == SPLIT]
    print(f"Evaluating OCR on {len(test_rows)} test-set plates...")

    exact_matches = 0
    char_acc_sum = 0.0
    n = 0
    failures = []

    for row in test_rows:
        img_path = DATASET_DIR / SPLIT / "images" / row["image"]
        lbl_path = DATASET_DIR / SPLIT / "labels" / (Path(row["image"]).stem + ".txt")
        if not img_path.exists() or not lbl_path.exists():
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        cls, xc, yc, bw, bh = map(float, lbl_path.read_text().split())
        x1 = int((xc - bw / 2) * w)
        y1 = int((yc - bh / 2) * h)
        x2 = int((xc + bw / 2) * w)
        y2 = int((yc + bh / 2) * h)
        crop = img[max(0, y1):y2, max(0, x1):x2]
        if crop.size == 0:
            continue

        truth = row["plate_text"].strip().upper()
        pred = read_plate_tesseract(crop)

        n += 1
        is_exact = pred == truth
        exact_matches += is_exact
        ca = char_accuracy(pred, truth)
        char_acc_sum += ca
        if not is_exact and len(failures) < 15:
            failures.append((row["image"], truth, pred, round(ca, 2)))

    if n == 0:
        print("\n=== OCR (Tesseract) RESULTS on 0 held-out test plates ===")
        print("No valid plate OCR results obtained. Tesseract CLI binary is not installed in this environment.")
        print("To run Tesseract OCR evaluation, install tesseract-ocr: !apt-get update && !apt-get install -y tesseract-ocr")
        return

    print(f"\n=== OCR (Tesseract) RESULTS on {n} held-out test plates ===")
    print(f"Exact string match:        {exact_matches}/{n} = {exact_matches/n*100:.1f}%")
    print(f"Avg character accuracy:    {char_acc_sum/n*100:.1f}%")

    print("\nSample failures (truth vs predicted):")
    for img, truth, pred, ca in failures:
        print(f"  {img:50s} truth={truth:12s} pred={pred:12s} char_acc={ca}")


if __name__ == "__main__":
    main()
