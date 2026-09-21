"""
Colour measurement, kit matching and calibration.

Kept apart from the plugin so the same code answers both questions: at
runtime, "what colour is this person wearing"; during setup, "what HSV range
describes the colour I just pointed at". If those two used different logic,
calibration would produce numbers that do not reproduce in production, which
is the usual reason colour-based PPE detection fails on a real site.
"""

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from app.plugins.ppe.models import BODY_REGIONS

# OpenCV packs hue into 0-179 (half of the 0-359 degrees) so it fits a byte.
HUE_MAX = 179


def region_slice(box: Sequence[float], region: str,
                 frame_shape: Tuple[int, int]) -> Optional[Tuple[int, int, int, int]]:
    """
    The pixel rectangle for a body region inside a person box.

    Narrows horizontally as well as vertically for HEAD: a person box is as
    wide as their shoulders, so the top band of it is mostly background, and
    background is exactly what must not be sampled as helmet colour.
    """
    x1, y1, x2, y2 = (int(v) for v in box[:4])
    h, w = frame_shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 - x1 < 4 or y2 - y1 < 8:
        return None

    lo, hi = BODY_REGIONS.get(region.upper(), BODY_REGIONS["FULL"])
    box_h = y2 - y1
    ry1 = y1 + int(box_h * lo)
    ry2 = y1 + int(box_h * hi)

    if region.upper() == "HEAD":
        box_w = x2 - x1
        inset = int(box_w * 0.22)
        rx1, rx2 = x1 + inset, x2 - inset
    else:
        rx1, rx2 = x1, x2

    if rx2 - rx1 < 2 or ry2 - ry1 < 2:
        return None
    return rx1, ry1, rx2, ry2


def mask_for_ranges(hsv: np.ndarray, ranges: Sequence[Sequence[Sequence[int]]]) -> np.ndarray:
    """
    Combined mask for a colour's HSV ranges.

    Several ranges are OR-ed, which is what lets red be expressed as two bands
    either side of the hue wrap-around; a single inRange cannot span it, so a
    red kit is otherwise unrepresentable.
    """
    out = None
    for pair in ranges or []:
        try:
            lo = np.array(pair[0][:3], dtype=np.uint8)
            hi = np.array(pair[1][:3], dtype=np.uint8)
        except (IndexError, TypeError, ValueError):
            continue
        m = cv2.inRange(hsv, lo, hi)
        out = m if out is None else cv2.bitwise_or(out, m)
    if out is None:
        return np.zeros(hsv.shape[:2], dtype=np.uint8)
    return out


def coverage(hsv_region: np.ndarray, ranges) -> float:
    """Fraction of a region's pixels carrying a colour, 0..1."""
    if hsv_region is None or hsv_region.size == 0:
        return 0.0
    total = hsv_region.shape[0] * hsv_region.shape[1]
    if total <= 0:
        return 0.0
    return float(cv2.countNonZero(mask_for_ranges(hsv_region, ranges))) / float(total)


def measure_person(hsv_frame: np.ndarray, box: Sequence[float],
                   colours: Dict[str, Sequence], regions: Sequence[str]) -> Dict[str, Dict[str, float]]:
    """
    Coverage of every catalogued colour in every requested body region.

    Returned as {region: {colour_id: coverage}}. Measuring once per region and
    scoring vendors from that costs one pass over the pixels regardless of how
    many vendors are in the catalogue — scoring vendor by vendor would re-mask
    the same pixels for every vendor that shares a colour.
    """
    out: Dict[str, Dict[str, float]] = {}
    for region in regions:
        rect = region_slice(box, region, hsv_frame.shape)
        if rect is None:
            out[region] = {}
            continue
        rx1, ry1, rx2, ry2 = rect
        patch = hsv_frame[ry1:ry2, rx1:rx2]
        out[region] = {cid: coverage(patch, ranges) for cid, ranges in colours.items()}
    return out


def score_kit(measured: Dict[str, Dict[str, float]], kit_items: Sequence[dict]) -> dict:
    """
    How well a person's measured colours match one vendor's kit.

    Required items dominate: a kit whose required helmet is absent is not that
    vendor, however well the vest matches. Optional items only raise
    confidence. The returned detail is what the violation record keeps, so a
    disputed identification can be inspected instead of argued about.
    """
    required_hits, required_total = 0, 0
    optional_hits, optional_total = 0, 0
    detail = []
    score = 0.0

    for item in kit_items:
        region = (item.get("body_region") or "TORSO").upper()
        colour_id = item.get("colour_id")
        needed = float(item.get("min_coverage") or 0.0)
        got = float(measured.get(region, {}).get(colour_id, 0.0))
        ok = got >= needed
        if item.get("is_required", True):
            required_total += 1
            required_hits += 1 if ok else 0
        else:
            optional_total += 1
            optional_hits += 1 if ok else 0
        if ok:
            # Credit how convincingly it matched, capped so one very saturated
            # item cannot carry a kit whose other items are absent.
            score += min(got / needed, 3.0) if needed > 0 else 1.0
        detail.append({
            "item_type": item.get("item_type"),
            "body_region": region,
            "colour_id": colour_id,
            "required": bool(item.get("is_required", True)),
            "needed": round(needed, 4),
            "measured": round(got, 4),
            "matched": ok,
        })

    complete = required_total > 0 and required_hits == required_total
    return {
        "score": round(score, 4),
        "required_hits": required_hits,
        "required_total": required_total,
        "optional_hits": optional_hits,
        "optional_total": optional_total,
        "complete": complete,
        # Partial means some but not all required items matched — the person
        # is probably this vendor's, wearing an incomplete kit. That is a
        # different violation from "not this vendor at all".
        "partial": required_total > 0 and 0 < required_hits < required_total,
        "detail": detail,
    }


def identify(measured: Dict[str, Dict[str, float]],
             vendors: Sequence[dict]) -> Tuple[Optional[dict], Optional[dict], List[dict]]:
    """
    Best vendor for a person, and whether their kit was complete.

    Returns (vendor, score, all_scores). A complete kit always beats a partial
    one regardless of raw score, so a fully-kitted Beta worker is never
    reported as a partially-kitted Acme worker just because Acme's vest colour
    happens to cover more pixels.
    """
    scored = []
    for vendor in vendors:
        s = score_kit(measured, vendor.get("kit_items") or [])
        scored.append({"vendor": vendor, "score": s})

    complete = [x for x in scored if x["score"]["complete"]]
    pool = complete or [x for x in scored if x["score"]["partial"]]
    if not pool:
        return None, None, scored

    best = max(pool, key=lambda x: (x["score"]["complete"], x["score"]["score"]))
    return best["vendor"], best["score"], scored


# --------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------- #
def calibrate(bgr_patch: np.ndarray, percentile: float = 8.0,
              min_saturation: int = 60, min_value: int = 50) -> Optional[dict]:
    """
    Derive HSV ranges from a real patch of a real garment.

    Takes the dominant hue cluster rather than the full spread, because a
    photograph of a vest includes shadow, glare and background at its edges,
    and a range wide enough to include all of them matches most of the site.
    Grey and near-black pixels are dropped first for the same reason: their
    hue is meaningless and would drag the cluster anywhere.

    Returns None when the patch has no coherent colour — which is a useful
    answer, not a failure: it means the operator selected shadow or wall.
    """
    if bgr_patch is None or getattr(bgr_patch, "size", 0) == 0:
        return None

    hsv = cv2.cvtColor(bgr_patch, cv2.COLOR_BGR2HSV)
    h = hsv[:, :, 0].astype(np.int32).ravel()
    s = hsv[:, :, 1].astype(np.int32).ravel()
    v = hsv[:, :, 2].astype(np.int32).ravel()

    keep = (s >= min_saturation) & (v >= min_value)
    if keep.sum() < max(20, 0.05 * h.size):
        return None
    h, s, v = h[keep], s[keep], v[keep]

    # Find the dominant hue on the circle. Averaging hues directly is wrong at
    # the wrap-around (a red garment's hues sit near 0 and near 179 and average
    # to cyan), so work with unit vectors and take the circular mean.
    ang = h.astype(np.float64) * (2.0 * np.pi / (HUE_MAX + 1))
    mean_ang = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())
    if mean_ang < 0:
        mean_ang += 2 * np.pi
    centre = mean_ang * (HUE_MAX + 1) / (2.0 * np.pi)

    # Distance of each pixel from the centre, measured the short way round.
    d = np.abs(h - centre)
    d = np.minimum(d, (HUE_MAX + 1) - d)
    spread = float(np.percentile(d, 100.0 - percentile))
    spread = max(4.0, min(spread, 25.0))     # never absurdly tight or wide

    lo_h = centre - spread
    hi_h = centre + spread
    s_lo = int(max(30, np.percentile(s, percentile)))
    v_lo = int(max(30, np.percentile(v, percentile)))

    # Split into two ranges when the band crosses the wrap-around, which is
    # the only way to express red.
    ranges = []
    if lo_h < 0:
        ranges.append([[int((lo_h + HUE_MAX + 1)) % (HUE_MAX + 1), s_lo, v_lo],
                       [HUE_MAX, 255, 255]])
        ranges.append([[0, s_lo, v_lo], [int(hi_h), 255, 255]])
    elif hi_h > HUE_MAX:
        ranges.append([[int(lo_h), s_lo, v_lo], [HUE_MAX, 255, 255]])
        ranges.append([[0, s_lo, v_lo], [int(hi_h - HUE_MAX - 1), 255, 255]])
    else:
        ranges.append([[int(lo_h), s_lo, v_lo], [int(hi_h), 255, 255]])

    # What the proposed range actually recovers from the patch it came from.
    recovered = coverage(hsv, ranges)
    bgr = cv2.cvtColor(
        np.uint8([[[int(centre) % (HUE_MAX + 1), int(np.median(s)), int(np.median(v))]]]),
        cv2.COLOR_HSV2BGR)[0][0]

    return {
        "hsv_ranges": ranges,
        "hue_centre": round(float(centre), 1),
        "hue_spread": round(float(spread), 1),
        "sample_pixels": int(h.size),
        "coverage_of_sample": round(float(recovered), 4),
        "wraps_hue": len(ranges) > 1,
        "display_hex": "#{:02x}{:02x}{:02x}".format(int(bgr[2]), int(bgr[1]), int(bgr[0])),
    }
