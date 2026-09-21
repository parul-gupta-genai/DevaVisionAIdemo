import csv
import re
import subprocess
import tempfile
from pathlib import Path

import cv2

DATASET_DIR = Path("/home/claude/anpr_dataset")
SPLIT = "test"


def read_plate_tesseract(crop_bgr):
    """OCR a plate crop with Tesseract, restricted to the alphanumeric
    charset Indian plates actually use (cuts down on stray punctuation/
    misreads Tesseract's general-purpose mode would otherwise produce)."""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    # upscale small crops — Tesseract needs real pixel height to work with,
    # and plate crops here are often under 40px tall
    scale = max(1, 200 // max(gray.shape[0], 1))
    if scale > 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        cv2.imwrite(f.name, gray)
        result = subprocess.run(
            ["tesseract", f.name, "stdout", "--psm", "7",
             "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"],
            capture_output=True, text=True,
        )
    text = result.stdout.strip().upper()
    return re.sub(r"[^A-Z0-9]", "", text)


def char_accuracy(pred, truth):
    """Fraction of truth's characters correctly matched at the same
    position, length-normalized against the longer string (so a 4-char
    pred against an 10-char truth doesn't score 100% on those 4)."""
    if not truth:
        return 0.0
    matches = sum(1 for a, b in zip(pred, truth) if a == b)
    return matches / max(len(truth), len(pred))


def main():
    rows = list(csv.DictReader(open(DATASET_DIR / "manifest.csv")))
    test_rows = [r for r in rows if r["split"] == SPLIT]
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

    print(f"\n=== OCR (Tesseract) RESULTS on {n} held-out test plates ===")
    print(f"Exact string match:        {exact_matches}/{n} = {exact_matches/n*100:.1f}%")
    print(f"Avg character accuracy:    {char_acc_sum/n*100:.1f}%")

    print("\nSample failures (truth vs predicted):")
    for img, truth, pred, ca in failures:
        print(f"  {img:50s} truth={truth:12s} pred={pred:12s} char_acc={ca}")


if __name__ == "__main__":
    main()
