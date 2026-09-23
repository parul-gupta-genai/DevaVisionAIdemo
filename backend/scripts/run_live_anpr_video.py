"""
High-Performance ANPR & Vehicle Counting with Instant Responsive Display & Smart Plate Stabilization.

Features:
- Instant Real-Time License Plate Detection & OCR Display (No delay/strict lag)
- Smart Anti-Flicker Vehicle Plate Locking: Displays the best recognized plate per vehicle and upgrades automatically when a clearer read is captured.
- Indian Number Plate Formatting (Clean spacing, removes IND prefixes, standardizes State codes e.g. 'UP 14 DT 2891', 'UP 32 DC 4597')
- Multi-Class Vehicle Tracking (Car, Bike, Bus, Truck) using YOLO11
- Virtual Roadway Counting Line (Tripwire) with real-time class counters
- High-Contrast On-Screen Badges with Status
- Keyboard Controls:
    - [SPACE] : Pause / Resume
    - [r]     : Reset Counters & Restart Video
    - [s]     : Save Screenshot
    - [q]     : Quit Window
"""

import sys
import os
import time
import re
import argparse
import threading
from collections import defaultdict
from pathlib import Path
import cv2
import numpy as np
from loguru import logger
from ultralytics import YOLO

# Setup backend directory
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Initialize EasyOCR
try:
    import easyocr
    logger.info("Initializing EasyOCR Engine for License Plates...")
    ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    logger.info("EasyOCR Engine initialized successfully.")
except Exception as e:
    logger.warning(f"EasyOCR loading warning: {e}")
    ocr_reader = None

# Known Indian State Codes
INDIAN_STATES = {
    "DL", "UP", "MH", "KA", "HR", "GJ", "RJ", "MP", "PB", "TN",
    "AP", "TS", "WB", "KL", "BR", "UK", "CH", "JK", "OD", "AS",
    "HP", "GA", "TR", "PY", "CG", "JH", "MN", "ML", "MZ", "NL"
}

STATE_FIX = {
    "0L": "DL", "D1": "DL", "OL": "DL", "1L": "DL",
    "WJ": "UP", "WP": "UP", "UJ": "UP", "PJ": "UP",
    "U9": "UP", "U1": "UP", "U3": "UP", "VP": "UP", "OP": "UP", "JP": "UP",
    "M8": "MH", "MR": "MH", "MI": "MH",
    "H8": "HR", "HA": "HR",
    "R1": "RJ", "R0": "RJ",
    "K4": "KA", "KT": "KA",
    "W8": "WB", "P8": "PB",
    "C6": "CG", "M9": "MP", "T1": "TN"
}

# OCR character disambiguation
LETTER_TO_DIGIT = {
    'O': '0', 'D': '0', 'Q': '0', 'U': '0',
    'I': '1', '|': '1',
    'Z': '2',
    'J': '3', 'E': '3',
    'A': '4',
    'S': '5',
    'G': '6', 'b': '6',
    'T': '7', 'Y': '7',
    'B': '8',
    'g': '9', 'q': '9'
}

DIGIT_TO_LETTER = {
    '0': 'D', '1': 'I', '2': 'Z', '3': 'J', '5': 'S', '8': 'B'
}


def clean_and_format_plate(raw_text: str) -> str:
    """Format and standardize Indian license plate strings cleanly."""
    if not raw_text:
        return ""
    
    # 1. Clean noise & non-alphanumeric characters
    s = re.sub(r'[^A-Za-z0-9]', '', raw_text).upper()

    # 2. Remove common HSRP security sticker prefixes like "IND", "HND", "INDIA"
    for prefix in ["INDIA", "HSRP", "IND", "HND", "NDI", "MND", "AND"]:
        if s.startswith(prefix) and len(s) > len(prefix) + 3:
            s = s[len(prefix):]
            break

    # Strip single-letter stray logo bar before state code (e.g. FUP -> UP)
    if len(s) >= 6 and s[0] in "FHEKCTI" and (s[1:3] in INDIAN_STATES or s[1:3] in STATE_FIX):
        s = s[1:]

    if len(s) < 4:
        return s if len(s) >= 3 else ""

    # 3. Correct State code prefix
    st = s[:2]
    if st in STATE_FIX:
        s = STATE_FIX[st] + s[2:]
        st = s[:2]

    # 4. Standard Indian Format Spacing: [State 2] [District 2] [Series 1-2] [Number 4]
    if st in INDIAN_STATES:
        rest = s[2:]
        if len(rest) >= 4:
            # Fix district code digits (pos 0, 1 of rest)
            d1 = LETTER_TO_DIGIT.get(rest[0], rest[0])
            d2 = LETTER_TO_DIGIT.get(rest[1], rest[1])
            district = d1 + d2
            tail = rest[2:]

            if len(tail) >= 4:
                series_raw = tail[:-4]
                num_raw = tail[-4:]
                
                # Fix series characters to letters
                series = "".join(DIGIT_TO_LETTER.get(c, c) for c in series_raw)
                # Fix number characters to digits
                if num_raw[0] == 'L':
                    num_raw = '4' + num_raw[1:]
                num = "".join(LETTER_TO_DIGIT.get(c, c) for c in num_raw)
                
                if series:
                    return f"{st} {district} {series} {num}".strip()
                else:
                    return f"{st} {district} {num}".strip()
            elif len(tail) >= 1:
                return f"{st} {district} {tail}".strip()
            return f"{st} {district}"

    elif len(s) >= 8:
        return f"{s[:2]} {s[2:4]} {s[4:-4]} {s[-4:]}".replace("  ", " ").strip()
    elif len(s) >= 6:
        return f"{s[:2]} {s[2:4]} {s[4:]}".strip()

    return s


class InstantStabilizedTracker:
    """Instantly displays detected plates and stabilizes them without lag or flickering."""
    def __init__(self, reader):
        self.reader = reader
        self.plates = {}  # track_id -> best_plate_str
        self.scores = {}  # track_id -> best_score
        self.lock = threading.Lock()
        self.busy = False

    def get_plate(self, track_id: int, crop: np.ndarray) -> str:
        with self.lock:
            cached = self.plates.get(track_id, "")

        if self.reader is None or self.busy or crop is None or crop.size == 0:
            return cached

        # Run async OCR
        self.busy = True
        threading.Thread(target=self._ocr_worker, args=(track_id, crop.copy()), daemon=True).start()

        with self.lock:
            return self.plates.get(track_id, "")

    def _ocr_worker(self, track_id: int, crop: np.ndarray):
        try:
            h, w = crop.shape[:2]
            # Resize for crisp text reading
            scale = 80.0 / max(1, h)
            resized = cv2.resize(crop, (int(w * scale), 80), interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            
            # Read OCR
            results = self.reader.readtext(gray, detail=0, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
            if not results:
                results = self.reader.readtext(crop, detail=0, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')

            raw = "".join(results)
            cleaned = clean_and_format_plate(raw)

            if cleaned and len(cleaned) >= 4:
                # Score based on completeness & state matching
                score = len(cleaned) * 10
                if any(cleaned.startswith(st) for st in INDIAN_STATES):
                    score += 50
                if len(cleaned) >= 8:
                    score += 30

                with self.lock:
                    prev_score = self.scores.get(track_id, 0)
                    if score >= prev_score or track_id not in self.plates:
                        self.plates[track_id] = cleaned
                        self.scores[track_id] = score
        except Exception:
            pass
        finally:
            self.busy = False


def run_anpr_counting_video(video_source=None):
    if video_source is None:
        video_source = r"C:\Users\Praveen\Downloads\anpr.mp4"

    video_path = Path(video_source)
    if not video_path.exists() and not str(video_source).isdigit():
        print(f"[ERROR] Video file not found: {video_source}")
        return

    logger.info(f"Opening Video Source: {video_source}")
    src = int(video_source) if str(video_source).isdigit() else str(video_source)
    cap = cv2.VideoCapture(src)

    if not cap.isOpened():
        print(f"[ERROR] Cannot open video: {video_source}")
        return

    logger.info("Loading YOLO Models (Vehicle Tracking & License Plate Detector)...")
    veh_model = YOLO("yolo11n.pt")
    
    plate_model_path = BASE_DIR / "indian_plate_yolo.pt"
    plate_model = YOLO(str(plate_model_path))

    plate_tracker = InstantStabilizedTracker(ocr_reader)

    window_name = "DevaVisionAI - Instant ANPR & Vehicle Counting (SPACE: Pause, 'r': Reset, 's': Snapshot, 'q': Quit)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

    fps_count = 0
    fps_start_time = time.time()
    fps_display = 0.0
    is_paused = False

    # Vehicle Counting State
    counted_vehicle_ids = set()
    counts_by_type = {"CAR": 0, "BIKE": 0, "BUS": 0, "TRUCK": 0}
    total_vehicles_counted = 0
    track_history = {}
    last_detected_plate = "Scanning..."
    all_captured_plates = set()

    veh_class_names = {2: "CAR", 3: "BIKE", 5: "BUS", 7: "TRUCK"}

    print("\n=======================================================")
    print(" 🚘 INSTANT ANPR & VEHICLE COUNTING SYSTEM")
    print("=======================================================")
    print(" 🟢 GREEN: Detected License Plate & Vehicle Number")
    print(" 🔵 CYAN:  Vehicle Detection & Active Track ID")
    print(" 🟡 LINE:  Tripwire Counting Line")
    print("-------------------------------------------------------")
    print(" - Press 'SPACE' to Pause / Resume")
    print(" - Press 'r' to Reset Counts & Restart Video")
    print(" - Press 's' to Save Screenshot")
    print(" - Press 'q' to Quit")
    print("=======================================================\n")

    while True:
        if not is_paused:
            ret, frame = cap.read()
            if not ret:
                if not str(video_source).isdigit():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    break

            h, w = frame.shape[:2]
            line_y = int(h * 0.58)  # Virtual counting line

            # Calculate FPS
            fps_count += 1
            elapsed = time.time() - fps_start_time
            if elapsed >= 1.0:
                fps_display = fps_count / elapsed
                fps_count = 0
                fps_start_time = time.time()

            # 1. Multi-Object Vehicle Tracking
            v_results = veh_model.track(frame, classes=[2, 3, 5, 7], conf=0.30, persist=True, verbose=False)
            vehicle_tracks = []

            if v_results and v_results[0].boxes is not None:
                for b in v_results[0].boxes:
                    cls_id = int(b.cls[0])
                    conf = float(b.conf[0])
                    coords = [int(v) for v in b.xyxy[0].tolist()]
                    track_id = int(b.id[0]) if b.id is not None else None
                    v_type = veh_class_names.get(cls_id, "VEHICLE")

                    # Centroid
                    cx = (coords[0] + coords[2]) // 2
                    cy = (coords[1] + coords[3]) // 2

                    if track_id is not None:
                        if track_id not in track_history:
                            track_history[track_id] = []
                        track_history[track_id].append((cx, cy))
                        if len(track_history[track_id]) > 30:
                            track_history[track_id].pop(0)

                        # Counting Line Check
                        if track_id not in counted_vehicle_ids:
                            if len(track_history[track_id]) >= 2:
                                prev_cy = track_history[track_id][-2][1]
                                curr_cy = cy
                                if (prev_cy < line_y <= curr_cy) or (prev_cy > line_y >= curr_cy) or (abs(curr_cy - line_y) < 16):
                                    counted_vehicle_ids.add(track_id)
                                    total_vehicles_counted += 1
                                    if v_type in counts_by_type:
                                        counts_by_type[v_type] += 1
                                    logger.info(f"🚗 COUNTED {v_type} #{track_id} | Total: {total_vehicles_counted}")

                    vehicle_tracks.append((v_type, conf, coords, track_id))

            # 2. Detect Number Plates (Sensitive conf=0.18 for instant detection)
            p_results = plate_model(frame, conf=0.18, verbose=False)
            plate_boxes = []
            if p_results and p_results[0].boxes is not None:
                for b in p_results[0].boxes:
                    conf = float(b.conf[0])
                    coords = [int(v) for v in b.xyxy[0].tolist()]
                    plate_boxes.append((conf, coords))

            # Draw Virtual Counting Line (Yellow Glow Line)
            cv2.line(frame, (0, line_y), (w, line_y), (0, 215, 255), 3)
            cv2.putText(frame, "--- VEHICLE COUNTING LINE ---", (w // 2 - 170, line_y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 215, 255), 2)

            # Process and Draw Each Vehicle + Stabilized Plate
            for v_name, conf, (vx1, vy1, vx2, vy2), tid in vehicle_tracks:
                vx1, vy1 = max(0, vx1), max(0, vy1)
                vx2, vy2 = min(w, vx2), min(h, vy2)
                vw, vh = vx2 - vx1, vy2 - vy1

                # Find matching plate within this vehicle's bounding box
                plate_crop = None
                matched_plate_box = None
                for p_conf, (px1, py1, px2, py2) in plate_boxes:
                    if px1 >= vx1 - 15 and px2 <= vx2 + 15 and py1 >= vy1 - 15 and py2 <= vy2 + 15:
                        matched_plate_box = [px1, py1, px2, py2]
                        plate_crop = frame[max(0, py1 - 4):min(h, py2 + 4), max(0, px1 - 4):min(w, px2 + 4)]
                        break

                # Fallback to lower bumper crop if vehicle is large
                if plate_crop is None and vw >= 150 and vh >= 100:
                    bx1, bx2 = int(vx1 + 0.16 * vw), int(vx2 - 0.16 * vw)
                    by1, by2 = int(vy1 + 0.55 * vh), int(vy2 - 0.04 * vh)
                    matched_plate_box = [bx1, by1, bx2, by2]
                    plate_crop = frame[by1:by2, bx1:bx2]

                # Get stabilized plate string
                plate_str = ""
                if tid is not None:
                    plate_str = plate_tracker.get_plate(tid, plate_crop)

                if plate_str:
                    last_detected_plate = plate_str
                    all_captured_plates.add(plate_str)

                # Draw Vehicle Bounding Box
                color = (255, 200, 0)
                cv2.rectangle(frame, (vx1, vy1), (vx2, vy2), color, 2)
                
                # Top Vehicle Badge
                tid_str = f" #{tid}" if tid is not None else ""
                plate_disp = f" | {plate_str}" if plate_str else ""
                v_label = f"{v_name}{tid_str}{plate_disp}"
                (tw, th), _ = cv2.getTextSize(v_label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                cv2.rectangle(frame, (vx1, max(0, vy1 - 24)), (vx1 + tw + 8, vy1), color, -1)
                cv2.putText(frame, v_label, (vx1 + 4, vy1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

                # Draw Plate & Plate Text Badge
                if matched_plate_box is not None:
                    px1, py1, px2, py2 = matched_plate_box
                    p_color = (0, 255, 0)
                    cv2.rectangle(frame, (px1, py1), (px2, py2), p_color, 2)

                    if plate_str:
                        plate_badge = f"{plate_str}"
                        (ptw, pth), _ = cv2.getTextSize(plate_badge, cv2.FONT_HERSHEY_SIMPLEX, 0.72, 2)
                        
                        badge_y1 = max(0, py1 - 30)
                        cv2.rectangle(frame, (px1, badge_y1), (px1 + ptw + 12, py1), (15, 15, 15), -1)
                        cv2.rectangle(frame, (px1, badge_y1), (px1 + ptw + 12, py1), p_color, 2)
                        cv2.putText(frame, plate_badge, (px1 + 6, py1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.72, p_color, 2)

                # Draw track trail
                if tid is not None and tid in track_history:
                    pts = track_history[tid]
                    for i in range(1, len(pts)):
                        cv2.line(frame, pts[i - 1], pts[i], (0, 255, 255), 2)

            # Top Dashboard Banner
            cv2.rectangle(frame, (0, 0), (w, 58), (20, 20, 20), -1)
            cv2.line(frame, (0, 58), (w, 58), (0, 215, 255), 2)

            line1 = f"DevaVisionAI ANPR | FPS: {fps_display:.1f} | TOTAL COUNTED: {total_vehicles_counted} (Cars: {counts_by_type['CAR']} | Bikes: {counts_by_type['BIKE']} | Heavy: {counts_by_type['TRUCK'] + counts_by_type['BUS']})"
            line2 = f"Active Vehicles: {len(vehicle_tracks)} | Best Plate: {last_detected_plate} | Unique Plates: {len(all_captured_plates)}"
            cv2.putText(frame, line1, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (0, 255, 255), 2)
            cv2.putText(frame, line2, (12, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 220, 220), 1)

            display_frame = frame.copy()

        cv2.imshow(window_name, display_frame)

        key = cv2.waitKey(25) & 0xFF
        if key == ord('q') or key == 27:
            break
        elif key == 32:  # SPACE to pause
            is_paused = not is_paused
        elif key == ord('r'):  # Reset counters & restart
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            counted_vehicle_ids.clear()
            counts_by_type = {"CAR": 0, "BIKE": 0, "BUS": 0, "TRUCK": 0}
            total_vehicles_counted = 0
            track_history.clear()
            all_captured_plates.clear()
            last_detected_plate = "Scanning..."
            plate_tracker.plates.clear()
            plate_tracker.scores.clear()
            logger.info("Counters & Plates reset to 0.")
        elif key == ord('s'):
            fn = f"traffic_snapshot_{int(time.time())}.jpg"
            cv2.imwrite(fn, display_frame)
            logger.info(f"Saved snapshot to {fn}")

    cap.release()
    cv2.destroyAllWindows()
    logger.info("ANPR & Vehicle Counting player closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live ANPR & Vehicle Counting System")
    parser.add_argument("--source", "-s", type=str, default=r"C:\Users\Praveen\Downloads\anpr.mp4", help="Path to video file or camera stream")
    args = parser.parse_args()

    run_anpr_counting_video(video_source=args.source)
