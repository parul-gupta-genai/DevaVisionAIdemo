import queue
import threading
import time
from datetime import datetime
from typing import List, Optional

import cv2
import numpy as np
from loguru import logger

from app.engine.base import BaseDetectionPlugin, DetectionEvent, FrameData, TrackerContext
from app.engine.snapshots import save_event_snapshot
from app.plugins.ppe.colour import identify, measure_person, region_slice
from app.plugins.ppe.repository import kit_catalogue

# --- ML helmet cross-check (added on top of the original colour-only logic) ---
#
# Colour matching alone has one systematic gap: a helmet in a colour that
# isn't in the vendor catalogue (or the two hardcoded legacy colours) is
# indistinguishable from no helmet at all — both measure as "no catalogued
# colour present". That conflates two very different safety states ("not
# wearing one" vs "wearing one we don't recognise the brand of"). This
# classifier (trained on the Kaggle Hard Hat Workers dataset — see
# backend/scripts/train_helmet_classifier.py) is only consulted at exactly
# that gap: when colour-matching has already failed to find a catalogued
# colour. It never overrides a successful colour match, so every camera
# that already works stays exactly as it was.
_helmet_classifier = None
_helmet_classifier_load_failed = False

# Below this no-helmet probability, treat the colour-unmatched head as
# "probably has a helmet, just not a catalogued colour" rather than
# "no helmet". Deliberately conservative (test-set precision/recall was
# 55%/84% at the model's own 0.5 threshold — see helmet_classifier.py) so a
# genuinely bare head close to the boundary still gets flagged, not waved
# through on a marginal classifier reading.
HELMET_CONFIRM_THRESHOLD = 0.35


def _get_helmet_classifier():
    """Lazy-load once per process; a missing/broken model must never take
    down the colour-based detection this plugin already relies on."""
    global _helmet_classifier, _helmet_classifier_load_failed
    if _helmet_classifier is not None or _helmet_classifier_load_failed:
        return _helmet_classifier
    try:
        from app.plugins.ppe.helmet_classifier import HelmetClassifier
        _helmet_classifier = HelmetClassifier()
        logger.info("PPE helmet ML classifier loaded")
    except Exception as exc:
        _helmet_classifier_load_failed = True
        logger.warning(
            f"PPE helmet ML classifier unavailable ({exc}); continuing with "
            "colour-only detection, unchanged from before this feature."
        )
    return _helmet_classifier


def _ml_head_has_helmet(frame, box, frame_shape) -> Optional[bool]:
    """Returns True/False if the classifier is available and the head crop
    is usable, else None (caller must treat None as "no opinion" and fall
    back to whatever colour-matching already decided)."""
    classifier = _get_helmet_classifier()
    if classifier is None:
        return None
    rect = region_slice(box, "HEAD", frame_shape)
    if rect is None:
        return None
    x1, y1, x2, y2 = rect
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    try:
        label, no_helmet_prob = classifier.predict(crop)
        return no_helmet_prob < HELMET_CONFIRM_THRESHOLD
    except Exception as exc:
        logger.warning(f"PPE helmet ML scoring failed: {exc}")
        return None

# The two colours this plugin recognised before the vendor catalogue existed.
# Kept, and used verbatim, whenever no catalogue has been configured: PPE is
# live on a dozen cameras, and installing this code must not change what any
# of them report until somebody actually defines a vendor.
LEGACY_YELLOW = (np.array([10, 100, 100], np.uint8), np.array([40, 255, 255], np.uint8))
LEGACY_BLUE = (np.array([100, 150, 0], np.uint8), np.array([140, 255, 255], np.uint8))
LEGACY_THRESHOLD = 0.02

# Regions worth measuring. Sampling only what some kit item asks for would be
# marginally cheaper, but measuring both lets the stats event explain a
# near-miss ("orange on the torso, nothing on the head"), which is exactly
# what calibrating on site needs.
MEASURED_REGIONS = ("HEAD", "TORSO")


class PPEDetectionPlugin(BaseDetectionPlugin):
    """
    PPE compliance and vendor identification from colour kits.

    With a catalogue configured, each person's head and torso colours are
    measured and scored against the vendor kits expected on that camera. That
    is what distinguishes "yellow helmet, blue vest" from "blue helmet, yellow
    vest" — two different agencies that a whole-body colour count cannot tell
    apart, because it only ever knew how much blue and how much yellow were
    present, not where.

    With no catalogue configured it behaves exactly as it did before.
    """

    # Reads raw pixels (per-person HSV colour masks + snapshot crops).
    needs_frame = True
    # Per-camera alert timers are keyed by camera_id; the catalogue snapshot is
    # replaced wholesale rather than mutated.
    thread_safe = True

    def __init__(self, app_config=None):
        super().__init__(app_config)
        self.last_alert_time = {}
        # (camera_id, violation_type) -> monotonic time of the last alert.
        self._last_violation = {}
        self._writes: "queue.Queue[dict]" = queue.Queue(maxsize=256)
        self._writer = threading.Thread(target=self._drain, name="ppe-writer", daemon=True)
        self._writer_started = False
        self._dropped = 0
        logger.info("Initialized PPEDetectionPlugin")

    @property
    def plugin_name(self) -> str:
        return "PPEDetectionPlugin"

    def get_required_classes(self) -> List[int]:
        return [0]  # Requires Person class

    # ------------------------------------------------------------------ #
    def _ensure_writer(self):
        if not self._writer_started:
            self._writer_started = True
            self._writer.start()

    def _submit(self, job: dict):
        try:
            self._writes.put_nowait(job)
        except queue.Full:
            self._dropped += 1
            if self._dropped in (1, 10) or self._dropped % 200 == 0:
                logger.warning(f"PPE violation queue full; dropped {self._dropped}")

    def _drain(self):
        from database.session import SessionLocal
        from app.plugins.ppe.repository import PPERepository

        while True:
            job = self._writes.get()
            db = None
            try:
                db = SessionLocal()
                PPERepository(db).log_violation(**job)
            except Exception as exc:
                logger.error(f"PPE violation write failed: {exc}")
            finally:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass
                self._writes.task_done()

    # ------------------------------------------------------------------ #
    def process_frame(self, frame_data: FrameData,
                      tracker_context: TrackerContext) -> List[DetectionEvent]:
        detections = frame_data.detections
        if not detections:
            return []

        if frame_data.frame is None:
            # Metadata-only pass: report how many people are present so the
            # dashboard tile does not go blank, and judge nobody.
            return [self._stats_event(
                frame_data, sum(1 for d in detections if d.class_id == 0),
                0, 0, [], {})]

        kit_catalogue.refresh()
        if kit_catalogue.configured:
            return self._process_with_catalogue(frame_data)
        return self._process_legacy(frame_data)

    # ------------------------------------------------------------------ #
    # Vendor colour-kit identification
    # ------------------------------------------------------------------ #
    def _process_with_catalogue(self, frame_data: FrameData) -> List[DetectionEvent]:
        events: List[DetectionEvent] = []
        camera_id = frame_data.camera_id
        frame = frame_data.frame
        timestamp = frame_data.timestamp
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        cfg = kit_catalogue.camera_config.get(camera_id, {})
        enforce = cfg.get("enforce", True)
        alert_on = set(cfg.get("alert_on") or ["NO_PPE", "WRONG_KIT"])
        severity = cfg.get("severity", "warning")
        cooldown = float(cfg.get("alert_cooldown_sec", 30.0))
        min_px = int(cfg.get("min_person_px", 80))

        expected_ids = {v["vendor_id"] for v in kit_catalogue.vendors_for(camera_id)}
        # Score against every vendor, not only the expected ones: spotting a
        # cleaning contractor in the switchyard is the point, and that needs
        # the vendor identified before it can be judged out of place.
        all_vendors = kit_catalogue.vendors

        drawings = []
        per_vendor = {}
        violations = []
        unknown = 0
        judged = 0

        for det in frame_data.detections:
            if det.class_id != 0:
                continue
            x1, y1, x2, y2 = (int(v) for v in det.bbox[:4])
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            if (y2 - y1) < min_px:
                # Too few pixels for colour to mean anything. Skipping is not a
                # compliance judgement, so it is not counted as a violation.
                drawings.append({"type": "rect", "coords": [x1, y1, x2, y2],
                                 "color": [120, 120, 120], "thickness": 1})
                continue

            judged += 1
            measured = measure_person(hsv, [x1, y1, x2, y2],
                                      kit_catalogue.colours, MEASURED_REGIONS)
            vendor, score, _ = identify(measured, all_vendors)

            if vendor is None:
                ml_has_helmet = _ml_head_has_helmet(frame, [x1, y1, x2, y2], frame.shape)
                if ml_has_helmet:
                    # Colour didn't match any catalogued vendor, but the ML
                    # classifier is reasonably confident a helmet IS present
                    # — an unrecognised-colour helmet, not a bare head. Kept
                    # as a distinct type rather than silently marking
                    # compliant: we still don't know which vendor, so this
                    # still deserves a human look, just not the same
                    # "missing PPE entirely" severity as NO_PPE.
                    unknown += 1
                    vtype, label, colour = "UNRECOGNIZED_KIT", "Helmet present (unrecognised colour)", [0, 200, 200]
                else:
                    unknown += 1
                    vtype, label, colour = "NO_PPE", "NO PPE", [0, 0, 255]
            elif vendor["vendor_id"] not in expected_ids:
                vtype = "WRONG_KIT"
                label = f"{vendor['name']} (not expected here)"
                colour = [0, 140, 255]
            elif not score["complete"]:
                vtype = "INCOMPLETE_KIT"
                missing = [d["item_type"] for d in score["detail"]
                           if d["required"] and not d["matched"]]
                label = f"{vendor['name']} - missing {', '.join(missing) or 'kit'}"
                colour = [0, 200, 255]
            else:
                vtype, label = None, vendor["name"]
                colour = _hex_to_bgr(vendor.get("display_hex")) or [0, 200, 0]
                per_vendor[vendor["name"]] = per_vendor.get(vendor["name"], 0) + 1

            drawings.append({"type": "rect", "coords": [x1, y1, x2, y2],
                             "color": colour, "thickness": 2})
            drawings.append({"type": "text", "text": label,
                             "coords": [x1, max(0, y1 - 5)],
                             "color": colour, "scale": 0.6})

            if vtype and enforce:
                violations.append({
                    "type": vtype,
                    "box": [x1, y1, x2, y2],
                    "vendor": vendor,
                    "track_id": det.track_id,
                    "evidence": {
                        "measured": {r: {k: round(v, 4) for k, v in vals.items() if v > 0.005}
                                     for r, vals in measured.items()},
                        "kit": score["detail"] if score else None,
                    },
                })

        events.append(self._stats_event(frame_data, judged, unknown,
                                        len(violations), drawings, per_vendor))

        # One alert per violation type per camera per cooldown, so a group of
        # people in the wrong kit does not produce one alert each.
        now = time.monotonic()
        by_type = {}
        for v in violations:
            by_type.setdefault(v["type"], []).append(v)

        for vtype, group in by_type.items():
            if vtype not in alert_on:
                continue
            key = (camera_id, vtype)
            last = self._last_violation.get(key)
            if last is not None and (now - last) < cooldown:
                continue
            self._last_violation[key] = now

            first = group[0]
            snapshot = self._crop_snapshot(frame, first["box"], camera_id)
            vendor = first.get("vendor")
            self._ensure_writer()
            self._submit({
                "camera_id": camera_id,
                "camera_name": frame_data.camera_url or camera_id,
                "violation_type": vtype,
                "severity": severity,
                "timestamp": datetime.utcnow(),
                "vendor_id": vendor["vendor_id"] if vendor else None,
                "vendor_name": vendor["name"] if vendor else None,
                "track_id": str(first.get("track_id")) if first.get("track_id") else None,
                "snapshot_path": snapshot,
                "evidence": first["evidence"],
            })
            logger.warning(
                f"PPE {vtype} on {camera_id}: {len(group)} person(s)"
                + (f" [{vendor['name']}]" if vendor else "")
            )
            events.append(DetectionEvent(
                plugin_name=self.plugin_name,
                # NO_PPE keeps the original event name so existing alert rules,
                # dashboards and the events feed keep firing unchanged.
                event_type="PPE_MISSING" if vtype == "NO_PPE" else "PPE_VIOLATION",
                camera_id=camera_id,
                timestamp=timestamp,
                confidence=1.0,
                metadata={
                    "violation_type": vtype,
                    "count": len(group),
                    "persons_without_ppe": [v["box"] for v in group],
                    "vendor_id": vendor["vendor_id"] if vendor else None,
                    "vendor_name": vendor["name"] if vendor else None,
                    "severity": severity,
                    "evidence": first["evidence"],
                    "drawings": drawings,
                    "snapshot_file": snapshot,
                    "active_alerts": [vtype] if severity in ("critical", "danger") else [],
                },
            ))
        return events

    # ------------------------------------------------------------------ #
    # Behaviour before the catalogue existed, preserved exactly
    # ------------------------------------------------------------------ #
    def _process_legacy(self, frame_data: FrameData) -> List[DetectionEvent]:
        events: List[DetectionEvent] = []
        camera_id = frame_data.camera_id
        timestamp = frame_data.timestamp
        frame = frame_data.frame
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        contractor_1_count = 0
        contractor_2_count = 0
        missing_ppe_count = 0
        persons_without_ppe = []
        drawings = []

        for det in frame_data.detections:
            if det.class_id != 0:
                continue
            x1, y1, x2, y2 = (int(v) for v in det.bbox[:4])
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            roi = hsv_frame[y1:y2, x1:x2]
            pixels_yellow = cv2.countNonZero(cv2.inRange(roi, *LEGACY_YELLOW))
            pixels_blue = cv2.countNonZero(cv2.inRange(roi, *LEGACY_BLUE))
            total = (x2 - x1) * (y2 - y1)
            ratio_yellow = pixels_yellow / float(total) if total > 0 else 0.0
            ratio_blue = pixels_blue / float(total) if total > 0 else 0.0

            is_c1 = ratio_blue >= LEGACY_THRESHOLD
            is_c2 = ratio_yellow >= LEGACY_THRESHOLD
            if is_c1 and is_c2:
                if ratio_blue > ratio_yellow:
                    is_c2 = False
                else:
                    is_c1 = False

            if is_c1:
                contractor_1_count += 1
                colour, label = [255, 0, 0], "Contractor 1"
            elif is_c2:
                contractor_2_count += 1
                colour, label = [0, 255, 255], "Contractor 2"
            else:
                ml_has_helmet = _ml_head_has_helmet(frame, [x1, y1, x2, y2], frame.shape)
                if ml_has_helmet:
                    # Same reasoning as the catalogue path above: a helmet in
                    # neither legacy colour is not the same thing as no
                    # helmet. Not counted as missing_ppe_count, so it neither
                    # inflates the alert nor appears in persons_without_ppe.
                    colour, label = [0, 200, 200], "Helmet (unrecognised colour)"
                else:
                    missing_ppe_count += 1
                    persons_without_ppe.append([x1, y1, x2, y2])
                    colour, label = [0, 0, 255], "NO PPE"

            drawings.append({"type": "rect", "coords": [x1, y1, x2, y2],
                             "color": colour, "thickness": 2})
            drawings.append({"type": "text", "text": label,
                             "coords": [x1, y1 - 5], "color": colour, "scale": 0.6})

        events.append(DetectionEvent(
            plugin_name=self.plugin_name,
            event_type="PPE_STATS",
            camera_id=camera_id,
            timestamp=timestamp,
            confidence=1.0,
            metadata={
                "contractor_1_count": contractor_1_count,
                "contractor_2_count": contractor_2_count,
                "missing_ppe_count": missing_ppe_count,
                "drawings": drawings,
            },
        ))

        last_time = self.last_alert_time.get(camera_id, 0)
        if persons_without_ppe and (timestamp - last_time >= 5.0):
            self.last_alert_time[camera_id] = timestamp
            logger.warning(
                f"⚠️ Missing PPE Detected on {camera_id}! Count: {len(persons_without_ppe)}")
            snapshot_path = self._crop_snapshot(frame, persons_without_ppe[0], camera_id)
            events.append(DetectionEvent(
                plugin_name=self.plugin_name,
                event_type="PPE_MISSING",
                camera_id=camera_id,
                timestamp=timestamp,
                confidence=1.0,
                metadata={
                    "persons_without_ppe": persons_without_ppe,
                    "drawings": drawings,
                    "snapshot_file": snapshot_path,
                },
            ))
        return events

    # ------------------------------------------------------------------ #
    def _stats_event(self, frame_data, judged, unknown, violations,
                     drawings, per_vendor) -> DetectionEvent:
        return DetectionEvent(
            plugin_name=self.plugin_name,
            event_type="PPE_STATS",
            camera_id=frame_data.camera_id,
            timestamp=frame_data.timestamp,
            confidence=1.0,
            metadata={
                "persons_judged": judged,
                "missing_ppe_count": unknown,
                "violation_count": violations,
                "by_vendor": per_vendor,
                # Kept so anything written against the old shape keeps working.
                "contractor_1_count": 0,
                "contractor_2_count": 0,
                "drawings": drawings,
            },
        )

    @staticmethod
    def _crop_snapshot(frame, box, camera_id):
        try:
            px1, py1, px2, py2 = (int(v) for v in box[:4])
            h, w = frame.shape[:2]
            pad_x = int((px2 - px1) * 0.2)
            pad_y = int((py2 - py1) * 0.2)
            cx1, cy1 = max(0, px1 - pad_x), max(0, py1 - pad_y)
            cx2, cy2 = min(w, px2 + pad_x), min(h, py2 + pad_y)
            if cx2 - cx1 > 10 and cy2 - cy1 > 10:
                return save_event_snapshot("ppe", camera_id,
                                           frame[cy1:cy2, cx1:cx2].copy())
        except Exception as exc:
            logger.error(f"Failed to save PPE snapshot: {exc}")
        return None


def _hex_to_bgr(value):
    """'#rrggbb' -> [b, g, r] for the overlay, or None."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lstrip("#")
    if len(v) != 6:
        return None
    try:
        r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
        return [b, g, r]
    except ValueError:
        return None
