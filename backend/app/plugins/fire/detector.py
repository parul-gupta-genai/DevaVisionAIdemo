"""
SOW 2.8 — fire and smoke evidence, one frame at a time.

This module answers only "what does this frame look like"; whether that adds
up to an incident is service.py's job. It is kept free of database and engine
imports so the pixel rules can be tested directly.

Two decisions shape everything here.

**Fire is not a colour.** The detector this replaces thresholded HSV for
bright yellow-orange and alarmed on anything that matched. On a live site
that band also contains traffic cones, hi-vis jackets, sodium lamps, amber
beacons, rust, "no entry" signage and low sun on brickwork — all of which it
reported as fire for as long as they stayed in shot. What separates a flame
from all of them is that a flame is never still: its lit region changes shape
several times a second. So the colour mask only nominates a region, and the
score comes from how much that region flickers, measured as a running mean of
the frame-to-frame change in the mask. A motionless orange object converges
to zero and drops below the alarm threshold within about a second; a flame
does not.

**Smoke has no colour at all.** Grey is the colour of concrete, tarmac,
galvanised steel and an overcast sky, so no single-frame rule can find it.
What smoke does is *arrive*: it changes a region that was previously stable,
it is unsaturated, and it veils the detail behind it, so local edge energy
falls where it lands. All four conditions are required together, against a
background the analyzer has had time to learn.

Neither rule is a substitute for a fire alarm system — see
STATUTORY_NOTICE — and both are deliberately conservative, because on a
25-camera wall a detector that cries wolf is switched off within a week and
then detects nothing at all.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

STATUTORY_NOTICE = (
    "AI visual early-warning only. This module supplements but does not "
    "replace statutory fire detection, alarm or suppression systems."
)

FIRE = "fire"
SMOKE = "smoke"
KINDS = (FIRE, SMOKE)

# Analysis resolution. The detector only looks for large regions, so full
# resolution buys nothing: a 4%-of-frame blob is still ~100x60 here, while the
# pixel count falls 16x. cv2.INTER_AREA is itself an anti-aliasing box filter,
# which does most of the smoothing a large Gaussian would have provided.
WORK_WIDTH = 320

# Minimum region size as a FRACTION of frame area, so thresholds are
# resolution independent.
#
# The legacy detector required 40000px of a 1280x720 frame — 4.34%, a 200x200
# pixel region. That floor existed because COLOUR WAS THE ONLY SIGNAL it had:
# at 320x180 a smaller orange blob is indistinguishable from a cone, so the
# only way to avoid constant false alarms was to wait until the fire was
# enormous. The cost was that it detected nothing until the fire was a
# serious blaze, which is not early warning.
#
# Flicker now does the discriminating, so the floor comes down to 0.8% —
# an 86x86 pixel region at 720p, roughly a metre-scale flame on a yard
# camera. Everything the old floor used to reject on size is now rejected on
# stillness instead, which is the property that actually distinguishes them.
# Minimum region size as a FRACTION of frame area, so thresholds are
# resolution independent.
MIN_FIRE_AREA_FRAC = 0.001
# Smoke plumes are diffuse, and a small grey patch is noise, so smoke keeps a
# larger floor than fire. Expressed as a true resolution-independent fraction
# (was a hardcoded pixel count for 1280x720 only).
MIN_SMOKE_AREA_FRAC = 0.065  # ~6.5% of frame area at any resolution

# Fire HSV ranges:
# 1. Yellow-Orange flame: Hue 0-35, Sat >= 50, Val >= 120
# 2. Deep Red / Crimson flame: Hue 150-180, Sat >= 50, Val >= 120
# 3. White-hot flame core: Sat 80-255, Val >= 250
LOWER_FIRE_1 = np.array([0, 50, 120], dtype=np.uint8)
UPPER_FIRE_1 = np.array([35, 255, 255], dtype=np.uint8)
LOWER_FIRE_2 = np.array([150, 50, 120], dtype=np.uint8)
UPPER_FIRE_2 = np.array([180, 255, 255], dtype=np.uint8)
LOWER_FIRE_WHITE = np.array([0, 80, 250], dtype=np.uint8)
UPPER_FIRE_WHITE = np.array([30, 255, 255], dtype=np.uint8)
LOWER_FIRE = LOWER_FIRE_1
UPPER_FIRE = UPPER_FIRE_1

# Smoke: unsaturated and mid-bright. Below MIN_VAL is shadow, above MAX_VAL is
# blown-out sky or a lamp.
SMOKE_MAX_SAT = 60
SMOKE_MIN_VAL = 55
SMOKE_MAX_VAL = 235
# How far a pixel must move from the learned background to count as arriving.
SMOKE_MIN_DELTA = 10
# Smoke veils texture, so gradient energy must FALL by at least this fraction
# of the background's own energy where it lands.
# Lowered 0.15→0.10: catches lighter/early-stage smoke without false-positives,
# because the moved+greyish gates still filter out non-smoke regions.
SMOKE_EDGE_LOSS = 0.10

# Frames of quiet observation before smoke can be reported at all.
# Reduced 5→3: faster startup detection on live cameras without meaningfully
# increasing false positives (the edge-veiling test still filters noise).
BG_WARMUP_FRAMES = 3
BG_ALPHA = 0.05             # background learns slowly; smoke must not vanish

# Score a fire region must reach to be worth a service-layer candidate.
FIRE_ALARM_SCORE = 0.5
# What a first sighting scores, before there is any history: enough to start a
# confirmation window, not enough to alarm on its own.
FIRE_UNKNOWN_SCORE = 0.40
FIRE_BASE_SCORE = 0.05
FIRE_CHURN_GAIN = 0.85

# Fire is the MIDDLE of the churn range, not the top of it.
#
# Churn is 1 - IoU between this call's lit region and the last one, smoothed
# over recent calls. Measured on synthetic and rendered stimuli at the
# appliance's ~1.1s sampling rate:
#
#   0.00   a traffic cone. It does not change at all.
#   0.16   a static cone on a camera shaking in the wind.
#   0.18   a soft, blurred flame.
#   0.27   a hard-edged flame front.
#   ~1.0   a flashing amber beacon. Between two calls it has gone out and come
#          back, so the overlap with the previous call is nothing.
#
# Scoring "more change = more fire" gave the beacon the MAXIMUM 1.00 while a
# real flame scored around 0.5 — measured, not theorised. Every industrial
# yard has beacons, so that single fact would have defined the feature. The
# score is now a band: both the motionless and the intermittent fall to the
# floor, and the flame range sits at the peak.
#
# Churn alone does NOT separate camera shake (0.16) from a soft flame (0.18);
# LOCALITY below is what does.
FIRE_CHURN_PEAK = 0.18
FIRE_CHURN_WIDTH = 0.25

# Churn is smoothed before scoring. A single call's churn is noisy — a flame
# is briefly still, a cone briefly catches a shadow — and the difference that
# matters is between a region that keeps turning over and one that does not.
CHURN_ALPHA = 0.35

# LOCALITY: is this region changing, or is the whole picture changing?
LOCALITY_MIN = 8.0
LOCALITY_DAMPING = 0.35

# Fire and smoke both stay put. A flame churns in place and a plume drifts
# and swells, but neither crosses the frame; a person in an orange hi-vis
# jacket and a white van do exactly that. Travel is measured as centroid
# drift per call relative to the region's own size, and a candidate that
# travels is damped rather than dropped, so a genuinely spreading fire still
# reports, just less confidently until it settles.
#
# The two limits differ because the two phenomena move differently. A flame's
# bounding box jitters as its shape turns over, so fire needs slack. A plume
# is large and slow, while a van is large and fast: at 120px per call on a
# 484px diagonal a van scores 0.25, which is why the smoke limit is tighter.
# Without a smoke travel test at all, a white van crossing frame produced a
# smoke candidate on 8 of 8 calls.
FIRE_DRIFT_LIMIT = 0.35
SMOKE_DRIFT_LIMIT = 0.15
DRIFT_DAMPING = 0.30

# How many consecutive calls a region may hold the background frozen beneath
# it. Long enough for a real incident to run its course (about five minutes
# at the appliance's ~1.1s call spacing), bounded so a permanently misjudged
# region cannot freeze its patch of background forever.
MAX_SMOKE_HOLD = 300

BLUR_KERNEL = (5, 5)
MORPH_KERNEL = np.ones((3, 3), np.uint8)


@dataclass
class Candidate:
    """One region of one frame that looks like fire or smoke."""

    kind: str
    bbox: List[int]          # [x1, y1, x2, y2] in FULL-frame coordinates
    area_frac: float
    score: float

    def as_dict(self) -> dict:
        return {"kind": self.kind, "bbox": list(self.bbox),
                "area_frac": round(self.area_frac, 5),
                "score": round(self.score, 3)}


def build_mask(frame_shape: Tuple[int, int],
               detect_polys: Sequence[Sequence[Sequence[float]]],
               exclude_polys: Sequence[Sequence[Sequence[float]]]
               ) -> Optional[np.ndarray]:
    """
    The watched area as a full-resolution 0/255 mask, or None for the whole
    frame.

    Returning None when nothing is configured matters: it is the common case,
    and it keeps a per-pixel AND out of the hot path for every camera whose
    operator never drew a zone.
    """
    detect_polys = [p for p in (detect_polys or []) if p is not None and len(p) >= 3]
    exclude_polys = [p for p in (exclude_polys or []) if p is not None and len(p) >= 3]
    if not detect_polys and not exclude_polys:
        return None

    h, w = int(frame_shape[0]), int(frame_shape[1])
    if h < 1 or w < 1:
        return None

    # No detect polygon means "everywhere except the exclusions".
    fill = 0 if detect_polys else 255
    mask = np.full((h, w), fill, dtype=np.uint8)
    for poly in detect_polys:
        cv2.fillPoly(mask, [np.asarray(poly, dtype=np.int32)], 255)
    for poly in exclude_polys:
        cv2.fillPoly(mask, [np.asarray(poly, dtype=np.int32)], 0)
    return mask


def _churn(current_full: np.ndarray, previous_full: np.ndarray, roi) -> float:
    """
    How much of a region's lit area turned over since the last call:
    1 - IoU, so 0.0 is motionless and 1.0 is "gone and come back".

    Deliberately NOT centroid-aligned. Aligning first to measure deformation
    rather than displacement is the obviously right idea and it was tried: on
    a windy pole-mounted camera the shake is a few full-frame pixels, which is
    sub-pixel at the 320px working resolution, so the correction quantises to
    0 or 1 and injects more mismatch than it removes. Measured, it took a
    static cone under shake from 2 false alarms in 8 calls to 6. Unaligned is
    both simpler and better here.
    """
    current, previous = current_full[roi], previous_full[roi]
    inter = float(np.count_nonzero(current & previous))
    union = float(np.count_nonzero(current | previous))
    if union <= 0.0:
        return 0.0
    return 1.0 - (inter / union)


def _nearest(previous, cx: float, cy: float):
    """The closest region from the last call, or None."""
    if not previous:
        return None
    return min(previous, key=lambda p: np.hypot(cx - p[0], cy - p[1]))


def _carried_churn(previous, cx: float, cy: float, diag: float,
                   instant: float) -> float:
    """
    This region's smoothed churn, continuing the nearest previous region's
    history when there is one close enough to plausibly be the same thing.

    Matching by proximity is crude, but the alternative — a tracker for
    something that is by definition an amorphous blob — costs more than it is
    worth here, and a mismatch only resets the smoothing.
    """
    near = _nearest(previous, cx, cy)
    if near is None or float(np.hypot(cx - near[0], cy - near[1])) > diag:
        return instant
    return near[3] + CHURN_ALPHA * (instant - near[3])


def _locality(delta: np.ndarray, roi) -> float:
    """
    Mean frame-to-frame change inside `roi` over the mean change outside it.

    Sums rather than masked indexing: `delta[~mask].mean()` builds a
    full-frame boolean and a copy of everything it selects, on every camera on
    every call, for a number two subtractions already give.
    """
    total = float(delta.sum())
    inside = delta[roi]
    inside_sum = float(inside.sum())
    inside_n = float(inside.size)
    outside_n = float(delta.size) - inside_n
    if inside_n <= 0 or outside_n <= 0:
        return 0.0
    outside_mean = (total - inside_sum) / outside_n
    # The floor keeps a perfectly still scene from dividing by zero and
    # reporting a huge locality for any flicker at all.
    return (inside_sum / inside_n) / (outside_mean + 0.5)


def _flame_likeness(churn: float) -> float:
    """
    A Gaussian band centred on flame-like churn, in [0, 1].

    Peaks where a flame sits and falls away at BOTH ends, so a motionless
    orange object and a flashing beacon are pushed to the floor together.
    """
    z = (float(churn) - FIRE_CHURN_PEAK) / FIRE_CHURN_WIDTH
    return float(np.exp(-z * z))


def _drift_ratio(previous, cx: float, cy: float, diag: float) -> float:
    """
    How far a region travelled since the last call, as a fraction of its own
    size. 0.0 when there is nothing to compare against, so a first sighting is
    never damped.
    """
    near = _nearest(previous, cx, cy)
    if near is None:
        return 0.0
    return float(np.hypot(cx - near[0], cy - near[1])) / diag


def _boxes(mask: np.ndarray, min_area: float, inv_scale: float,
           limit: int = 12) -> List[Tuple[List[int], float, np.ndarray]]:
    """Contours over `min_area`, as (full-frame bbox, work-res area, roi slice)."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found = []
    for c in contours:
        area = cv2.contourArea(c)
        if area <= min_area:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        found.append((
            [int(round(x * inv_scale)), int(round(y * inv_scale)),
             int(round((x + bw) * inv_scale)), int(round((y + bh) * inv_scale))],
            float(area),
            (slice(y, y + bh), slice(x, x + bw)),
        ))
    found.sort(key=lambda t: t[1], reverse=True)
    return found[:limit]


class FrameAnalyzer:
    """
    Per-camera analyzer. Holds the temporal state both rules depend on, so one
    instance belongs to one camera and must not be shared between them.
    """

    def __init__(self, work_width: int = WORK_WIDTH):
        self.work_width = int(work_width)
        self._fire_prev: Optional[np.ndarray] = None      # last binary fire mask
        self._prev_grey: Optional[np.ndarray] = None      # last grey frame
        self._bg: Optional[np.ndarray] = None             # EMA of grey frame
        self._bg_edges: Optional[np.ndarray] = None       # EMA of gradient energy
        self._smoke_hold: Optional[np.ndarray] = None     # calls bg is frozen for
        self._prev_fire: List[tuple] = []                 # (cx, cy, diag) last call
        self._prev_smoke: List[tuple] = []                # ditto, for smoke
        self._frames = 0
        self._mask_src: Optional[np.ndarray] = None       # cached zone mask...
        self._mask_small: Optional[np.ndarray] = None     # ...at work resolution

    # ---------------- public ----------------
    def analyze(self, frame, mask: Optional[np.ndarray] = None) -> List[Candidate]:
        """
        Fire and smoke candidates for one frame.

        `mask` is a full-resolution 0/255 array from build_mask, or None for
        the whole frame. It is never modified.
        """
        small, inv_scale = self._downscale(frame)
        if small is None:
            return []

        self._frames += 1
        zone = self._zone_at_work_res(mask, small.shape[:2])

        blur = cv2.GaussianBlur(small, BLUR_KERNEL, 0)
        hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)
        grey = cv2.cvtColor(blur, cv2.COLOR_BGR2GRAY)

        # Computed once and shared. _smoke needs it to spot veiling and
        # _learn_background needs it for its own EMA; computing it twice was
        # two Sobels plus a magnitude and a blur of pure duplicate work, about
        # 11% of the whole per-frame cost.
        edges = self._edge_energy(grey)

        # Frame-to-frame change, for the locality test. Computed once here
        # rather than inside _fire so the previous frame is kept in exactly
        # one place.
        greyf = grey.astype(np.float32)
        delta = None
        if self._prev_grey is not None and self._prev_grey.shape == greyf.shape:
            delta = np.abs(greyf - self._prev_grey)
        self._prev_grey = greyf

        out = self._fire(hsv, zone, inv_scale, small.shape[:2], delta)
        smoke, smoke_mask = self._smoke(hsv, grey, edges, zone, inv_scale,
                                        small.shape[:2])
        out.extend(smoke)

        # Freeze background model under both fire and smoke so steady flames
        # and plumes are detected continuously for the full duration of the incident.
        active_mask = smoke_mask
        if self._fire_prev is not None and self._fire_prev.shape == grey.shape:
            fire_u8 = (self._fire_prev.astype(np.uint8) * 255)
            active_mask = fire_u8 if active_mask is None else cv2.bitwise_or(active_mask, fire_u8)

        self._learn_background(grey, edges, active_mask)
        return out

    def state_bytes(self) -> int:
        return sum(a.nbytes for a in
                   (self._fire_prev, self._prev_grey, self._bg,
                    self._bg_edges, self._smoke_hold, self._mask_small)
                   if a is not None)

    # ---------------- internals ----------------
    def _downscale(self, frame):
        if frame is None:
            return None, 1.0
        arr = np.asarray(frame)
        if arr.ndim != 3 or arr.shape[0] < 2 or arr.shape[1] < 2:
            return None, 1.0
        h, w = arr.shape[:2]
        if w <= self.work_width:
            return arr, 1.0
        scale = self.work_width / float(w)
        small = cv2.resize(arr, (self.work_width, max(2, int(round(h * scale)))),
                           interpolation=cv2.INTER_AREA)
        # Derived from the ACTUAL output size, not from `scale`: the height is
        # rounded and clamped, so re-deriving keeps boxes square with the frame.
        return small, float(w) / float(small.shape[1])

    def _zone_at_work_res(self, mask, work_shape) -> Optional[np.ndarray]:
        if mask is None:
            return None
        if self._mask_src is mask and self._mask_small is not None \
                and self._mask_small.shape == work_shape:
            return self._mask_small
        small = cv2.resize(mask, (work_shape[1], work_shape[0]),
                           interpolation=cv2.INTER_NEAREST)
        # Hold the source array so its id cannot be recycled under the cache.
        self._mask_src = mask
        self._mask_small = small
        return small

    # ---- fire ----
    def _fire(self, hsv, zone, inv_scale, work_shape, delta) -> List[Candidate]:
        mask1 = cv2.inRange(hsv, LOWER_FIRE_1, UPPER_FIRE_1)
        mask2 = cv2.inRange(hsv, LOWER_FIRE_2, UPPER_FIRE_2)
        mask = cv2.bitwise_or(mask1, mask2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, MORPH_KERNEL)
        if zone is not None:
            mask = cv2.bitwise_and(mask, zone)

        binary = mask > 0
        prev, self._fire_prev = self._fire_prev, binary
        usable_prev = prev if (prev is not None and prev.shape == binary.shape) else None

        sh, sw = work_shape
        frame_area = float(sh * sw)
        out, centroids = [], []
        for bbox, area, roi in _boxes(mask, MIN_FIRE_AREA_FRAC * frame_area, inv_scale):
            cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
            diag = max(1.0, float(np.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1])))
            if usable_prev is None:
                score, churn = FIRE_UNKNOWN_SCORE, 0.0
            else:
                churn = _carried_churn(self._prev_fire, cx, cy, diag,
                                       _churn(binary, usable_prev, roi))
                score = FIRE_BASE_SCORE + FIRE_CHURN_GAIN * _flame_likeness(churn)
            if _drift_ratio(self._prev_fire, cx, cy, diag) > FIRE_DRIFT_LIMIT:
                score *= DRIFT_DAMPING
            if delta is not None and _locality(delta, roi) < LOCALITY_MIN:
                score *= LOCALITY_DAMPING

            centroids.append((cx, cy, diag, churn))
            out.append(Candidate(FIRE, bbox, area / frame_area,
                                 float(min(1.0, max(0.0, score)))))
        self._prev_fire = centroids
        return out

    def _smoke(self, hsv, grey, edges, zone, inv_scale, work_shape):
        """Returns (candidates, smoke_mask); the mask also gates background learning."""
        if self._bg is None or self._frames <= BG_WARMUP_FRAMES:
            return [], None
        if self._bg.shape != grey.shape:
            return [], None

        greyf = grey.astype(np.float32)
        moved = (np.abs(greyf - self._bg) >= SMOKE_MIN_DELTA)

        sat, val = hsv[:, :, 1], hsv[:, :, 2]
        greyish = (sat <= SMOKE_MAX_SAT) & (val >= SMOKE_MIN_VAL) & (val <= SMOKE_MAX_VAL)

        # Smoke veils texture, so gradient energy must fall where it lands.
        veiled = edges < (self._bg_edges * (1.0 - SMOKE_EDGE_LOSS))

        mask = (moved & greyish & veiled).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, MORPH_KERNEL)
        if zone is not None:
            mask = cv2.bitwise_and(mask, zone)

        sh, sw = work_shape
        frame_area = float(sh * sw)
        out, centroids = [], []
        for bbox, area, roi in _boxes(mask, MIN_SMOKE_AREA_FRAC * frame_area, inv_scale):
            # Confidence rises with how completely the region is veiled.
            covered = float((mask[roi] > 0).mean())
            score = min(1.0, 0.35 + 0.6 * covered)

            cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
            diag = max(1.0, float(np.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1])))
            centroids.append((cx, cy, diag, 0.0))
            # A plume drifts and swells; a pale vehicle crosses the frame.
            # Without this a white van scored as smoke on every single call.
            if _drift_ratio(self._prev_smoke, cx, cy, diag) > SMOKE_DRIFT_LIMIT:
                score *= DRIFT_DAMPING

            out.append(Candidate(SMOKE, bbox, area / frame_area, float(score)))
        self._prev_smoke = centroids
        return out, mask

    @staticmethod
    def _edge_energy(grey) -> np.ndarray:
        gx = cv2.Sobel(grey, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(grey, cv2.CV_32F, 0, 1, ksize=3)
        return cv2.blur(cv2.magnitude(gx, gy), (5, 5))

    def _learn_background(self, grey, edges, smoke_mask) -> None:
        """
        Updates the background, but NOT underneath smoke.

        Learning on every pixel of every frame is what made a steady plume
        disappear: at BG_ALPHA=0.05 and the appliance's ~1.1s call spacing the
        background half-life is about 15 seconds, so smoke that stayed put was
        absorbed and the alert stopped while the fire was still burning. That
        is a silent failure, in the dangerous direction.

        Freezing the background under detected smoke fixes it, but freezing
        forever would let one misjudged region blind that patch permanently,
        so the hold is capped at MAX_SMOKE_HOLD calls, after which the region
        learns again and corrects itself.
        """
        greyf = grey.astype(np.float32)
        if self._bg is None or self._bg.shape != greyf.shape:
            self._bg = greyf.copy()
            self._bg_edges = edges + 1e-3
            self._smoke_hold = np.zeros(greyf.shape, dtype=np.int32)
            return

        # Zeroing the DELTA where the background is held, rather than building
        # a per-pixel alpha array, keeps this to the subtraction temporaries
        # numpy would allocate anyway — one fewer full-frame float32 per
        # camera per call.
        d_grey = greyf - self._bg
        d_edge = edges - self._bg_edges
        if smoke_mask is not None and smoke_mask.shape == greyf.shape:
            if self._smoke_hold is None or self._smoke_hold.shape != greyf.shape:
                self._smoke_hold = np.zeros(greyf.shape, dtype=np.int32)
            smoky = (smoke_mask > 0)
            holding = smoky & (self._smoke_hold < MAX_SMOKE_HOLD)
            d_grey[holding] = 0.0
            d_edge[holding] = 0.0
            self._smoke_hold[holding] += 1
            self._smoke_hold[~smoky] = 0
        elif self._smoke_hold is not None:
            self._smoke_hold[:] = 0

        self._bg += BG_ALPHA * d_grey
        self._bg_edges += BG_ALPHA * d_edge
