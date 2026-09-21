"""
SOW 2.8 — the pixel layer: what counts as fire, what counts as smoke.

These are the tests that decide whether the module is an early-warning system
or a nuisance generator. Two of them matter more than the rest:

  * a static orange object must NOT alarm. A traffic cone, a hi-vis jacket,
    a sodium lamp and a "no entry" sign are all in the fire colour band, and
    a detector that only thresholds colour calls every one of them a fire
    for as long as the camera can see it.
  * a grey wall must NOT alarm as smoke. Smoke has no colour of its own, so
    a single-frame greyness rule flags every concrete surface on site.

Both are answered temporally, so the analyzer holds per-camera state and the
tests drive it frame by frame.
"""

import numpy as np
import pytest

from app.plugins.fire import detector as det


# ----------------------------------------------------------------------
# frame helpers
# ----------------------------------------------------------------------
H, W = 720, 1280


def blank(value=0):
    return np.full((H, W, 3), value, dtype=np.uint8)


def paint_fire(frame, x1, y1, x2, y2, jitter=0):
    """
    Bright saturated flame orange, in BGR because OpenCV frames are BGR.

    BGR(20, 190, 255) lands at HSV(22, 235, 255), mid-band for the detector's
    15-35 hue window. `jitter` varies the green channel, which walks the hue
    across and outside that window the way a real flame front does — that is
    what gives the mask something to flicker with.
    """
    rng = np.random.default_rng(abs(hash((x1, y1, jitter))) % (2**32))
    patch = np.zeros((y2 - y1, x2 - x1, 3), dtype=np.uint8)
    patch[:, :, 0] = 20                                  # B
    green = 190
    if jitter:
        green = 190 + rng.integers(-jitter, jitter + 1, patch.shape[:2])
    patch[:, :, 1] = np.clip(green, 0, 255)              # G
    patch[:, :, 2] = 255                                 # R
    frame[y1:y2, x1:x2] = patch
    return frame


def paint_grey(frame, x1, y1, x2, y2, value=150):
    frame[y1:y2, x1:x2] = value
    return frame


def textured_background(seed=0):
    """A background with edge detail, so smoke has something to veil."""
    rng = np.random.default_rng(seed)
    frame = rng.integers(40, 90, (H, W, 3), dtype=np.uint8)
    for x in range(0, W, 40):                     # vertical structure
        frame[:, x:x + 6] = 200
    for y in range(0, H, 40):
        frame[y:y + 6, :] = 200
    return frame


# ----------------------------------------------------------------------
# fire, single frame
# ----------------------------------------------------------------------
def test_a_large_orange_blob_is_a_fire_candidate():
    a = det.FrameAnalyzer()
    frame = paint_fire(blank(), 400, 200, 800, 560)
    cands = a.analyze(frame)
    fires = [c for c in cands if c.kind == det.FIRE]
    assert fires, "a 400x360 orange blob should register as fire"


def test_a_tiny_orange_speck_is_ignored():
    a = det.FrameAnalyzer()
    frame = paint_fire(blank(), 10, 10, 24, 24)
    assert [c for c in a.analyze(frame) if c.kind == det.FIRE] == []


def test_fire_boxes_come_back_in_full_frame_coordinates():
    a = det.FrameAnalyzer()
    frame = paint_fire(blank(), 400, 200, 800, 560)
    fires = [c for c in a.analyze(frame) if c.kind == det.FIRE]
    x1, y1, x2, y2 = fires[0].bbox
    # Generous bounds: the work resolution quantises the edges.
    assert 350 < x1 < 450 and 150 < y1 < 250
    assert 750 < x2 < 850 and 510 < y2 < 610
    assert x2 <= W and y2 <= H


def test_an_empty_frame_produces_nothing():
    a = det.FrameAnalyzer()
    assert a.analyze(blank()) == []


@pytest.mark.parametrize("shape", [(1, 1, 3), (0, 0, 3), (2, 900, 3)])
def test_degenerate_frames_do_not_raise(shape):
    a = det.FrameAnalyzer()
    assert a.analyze(np.zeros(shape, dtype=np.uint8)) == []


def test_none_frame_does_not_raise():
    assert det.FrameAnalyzer().analyze(None) == []


# ----------------------------------------------------------------------
# fire, over time — the false-positive killer
# ----------------------------------------------------------------------
def test_a_static_orange_object_stops_scoring_as_fire():
    """
    A traffic cone does not flicker. After the analyzer has seen the same
    orange pixels in the same place for several frames, its score must fall
    below the alarm threshold even though the colour still matches.
    """
    a = det.FrameAnalyzer()
    frame = paint_fire(blank(), 400, 200, 800, 560)
    scores = []
    for _ in range(8):
        cands = [c for c in a.analyze(frame.copy()) if c.kind == det.FIRE]
        scores.append(cands[0].score if cands else 0.0)
    assert scores[0] > 0, "the first sighting must still be a candidate"
    assert scores[-1] < det.FIRE_ALARM_SCORE, (
        f"a motionless orange object kept scoring {scores[-1]:.2f}")


def flame_front(frame, phase, cx=640, cy=400):
    """
    A flame whose SHAPE turns over between calls.

    A rigid rectangle sliding across the frame is not this. That was the
    original stimulus here, and it is what a moving object looks like, not
    what a burning one looks like — the detector is right to score it low.
    The plugin samples roughly once a second, so consecutive calls see a
    flame that has moved on a long way.
    """
    import cv2
    rng = np.random.default_rng(phase % 977)
    for i in range(6):
        ph = phase * 2.3 + i * 1.7
        rx = max(10, int(75 + 45 * np.sin(ph) + rng.integers(-18, 19)))
        ry = max(10, int(80 + 50 * np.sin(ph * 1.6 + 0.9) + rng.integers(-18, 19)))
        ox = int(28 * np.sin(ph * 0.7)) + int(rng.integers(-10, 11))
        oy = int(24 * np.sin(ph * 1.1)) + int(rng.integers(-10, 11))
        cv2.ellipse(frame, (cx + ox, cy + oy), (rx, ry), 0, 0, 360,
                    (20, int(190 + rng.integers(-35, 36)), 255), -1)
    return frame


def test_a_real_flame_front_scores_as_fire():
    """A flame's lit region turns over between calls; that is the signal."""
    a = det.FrameAnalyzer()
    scores = []
    for i in range(8):
        cands = [c for c in a.analyze(flame_front(blank(), i)) if c.kind == det.FIRE]
        scores.append(cands[0].score if cands else 0.0)
    above = [s for s in scores if s >= det.FIRE_ALARM_SCORE]
    assert len(above) >= 4, (
        f"a flame front cleared the threshold on only {len(above)}/8 calls: "
        f"{['%.2f' % s for s in scores]}")


def test_a_flashing_amber_beacon_is_not_fire():
    """
    Measured, not theorised: scoring "more change = more fire" gave a beacon
    that is fully lit on one call and dark on the next the MAXIMUM score of
    1.00, while a real flame sat around 0.5. Every industrial yard has
    beacons, so this is the false positive that would have defined the
    feature.
    """
    import cv2
    a = det.FrameAnalyzer()
    scores = []
    for i in range(10):
        frame = blank()
        if i % 2 == 0:
            cv2.circle(frame, (400, 400), 60, (25, 190, 255), -1)
        cands = [c for c in a.analyze(frame) if c.kind == det.FIRE]
        scores.append(cands[0].score if cands else 0.0)
    # The first sighting is always the unknown-history score; after that the
    # beacon must be on the floor.
    assert all(s < det.FIRE_ALARM_SCORE for s in scores[1:]), (
        f"a flashing beacon scored {['%.2f' % s for s in scores]}")


def test_churn_scores_as_a_band_not_a_ramp():
    """The property the beacon test depends on, stated directly."""
    still = det._flame_likeness(0.02)
    flame = det._flame_likeness(det.FIRE_CHURN_PEAK)
    blinking = det._flame_likeness(1.0)
    assert flame > still and flame > blinking
    assert blinking < still, "a region that vanishes must score below one that never moves"


# ----------------------------------------------------------------------
# smoke
# ----------------------------------------------------------------------
def test_a_static_grey_scene_is_not_smoke():
    a = det.FrameAnalyzer()
    frame = textured_background()
    for _ in range(10):
        cands = a.analyze(frame.copy())
    assert [c for c in cands if c.kind == det.SMOKE] == [], \
        "an unchanging grey scene must never register as smoke"


def test_grey_veil_appearing_over_a_learned_background_is_smoke():
    a = det.FrameAnalyzer()
    bg = textured_background()
    for _ in range(det.BG_WARMUP_FRAMES + 4):        # learn the background
        a.analyze(bg.copy())

    smoky = bg.copy()
    region = smoky[150:600, 300:900]
    # Smoke: pulls the region toward a flat mid grey, killing local contrast.
    smoky[150:600, 300:900] = (region * 0.25 + 160 * 0.75).astype(np.uint8)

    cands = a.analyze(smoky)
    smoke = [c for c in cands if c.kind == det.SMOKE]
    assert smoke, "a grey veil over learned background should register as smoke"


def test_smoke_needs_the_background_to_be_learned_first():
    """
    On the very first frames the analyzer has no background, so it must stay
    quiet rather than call the whole scene smoke.
    """
    a = det.FrameAnalyzer()
    smoky = np.full((H, W, 3), 160, dtype=np.uint8)
    assert [c for c in a.analyze(smoky) if c.kind == det.SMOKE] == []


def test_a_saturated_colour_change_is_not_smoke():
    """A blue tarpaulin unrolling is motion, but it is not smoke."""
    a = det.FrameAnalyzer()
    bg = textured_background()
    for _ in range(det.BG_WARMUP_FRAMES + 4):
        a.analyze(bg.copy())
    tarp = bg.copy()
    tarp[150:600, 300:900] = (200, 40, 20)      # strong blue, BGR
    assert [c for c in a.analyze(tarp) if c.kind == det.SMOKE] == []


# ----------------------------------------------------------------------
# zone masking — SOW "detection zones"
# ----------------------------------------------------------------------
def test_a_detect_mask_suppresses_fire_outside_it():
    a = det.FrameAnalyzer()
    frame = paint_fire(blank(), 40, 40, 420, 380)      # top-left
    mask = det.build_mask(
        (H, W),
        detect_polys=[[[640, 360], [1270, 360], [1270, 710], [640, 710]]],
        exclude_polys=[])
    assert [c for c in a.analyze(frame, mask=mask) if c.kind == det.FIRE] == []


def test_a_detect_mask_keeps_fire_inside_it():
    a = det.FrameAnalyzer()
    frame = paint_fire(blank(), 700, 400, 1100, 700)
    mask = det.build_mask(
        (H, W),
        detect_polys=[[[640, 360], [1270, 360], [1270, 710], [640, 710]]],
        exclude_polys=[])
    assert [c for c in a.analyze(frame, mask=mask) if c.kind == det.FIRE]


def test_an_exclusion_zone_silences_a_known_hot_spot():
    """The welding bay is orange all shift; the client marks it excluded."""
    a = det.FrameAnalyzer()
    frame = paint_fire(blank(), 700, 400, 1100, 700)
    mask = det.build_mask(
        (H, W), detect_polys=[],
        exclude_polys=[[[640, 360], [1270, 360], [1270, 710], [640, 710]]])
    assert [c for c in a.analyze(frame, mask=mask) if c.kind == det.FIRE] == []


def test_no_polygons_means_watch_the_whole_frame():
    mask = det.build_mask((H, W), detect_polys=[], exclude_polys=[])
    assert mask is None, "no zones configured should cost nothing at runtime"


def test_a_mask_is_reusable_across_frames():
    """Masks are cached per camera; analyze must not mutate the one it gets."""
    a = det.FrameAnalyzer()
    poly = [[[640, 360], [1270, 360], [1270, 710], [640, 710]]]
    mask = det.build_mask((H, W), detect_polys=poly, exclude_polys=[])
    before = mask.copy()
    a.analyze(paint_fire(blank(), 700, 400, 1100, 700), mask=mask)
    assert np.array_equal(mask, before)


# ----------------------------------------------------------------------
# housekeeping
# ----------------------------------------------------------------------
def test_analyzer_state_is_bounded_per_camera():
    """One analyzer per camera; it must not grow without limit."""
    a = det.FrameAnalyzer()
    for i in range(50):
        a.analyze(paint_fire(blank(), 400, 200, 800, 560, jitter=i))
    assert a.state_bytes() < 4 * 1024 * 1024


def test_candidates_carry_area_fraction_and_score():
    a = det.FrameAnalyzer()
    c = [c for c in a.analyze(paint_fire(blank(), 400, 200, 800, 560))
         if c.kind == det.FIRE][0]
    assert 0.0 < c.area_frac <= 1.0
    assert 0.0 <= c.score <= 1.0


def test_locality_separates_a_local_event_from_a_moving_camera():
    """
    The property that lets a shaking camera keep an orange object in shot
    without turning it into a fire. Fire changes its own patch and nothing
    else; shake displaces every edge in the scene at once.
    """
    delta = np.zeros((180, 320), dtype=np.float32)
    roi = (slice(60, 120), slice(100, 180))

    delta[roi] = 30.0                       # a local event
    local = det._locality(delta, roi)

    delta[:] = 30.0                         # the whole picture moved
    global_ = det._locality(delta, roi)

    assert local > det.LOCALITY_MIN
    assert global_ < det.LOCALITY_MIN
    assert local > global_ * 5


def test_locality_is_finite_on_a_perfectly_still_frame():
    delta = np.zeros((180, 320), dtype=np.float32)
    assert det._locality(delta, (slice(0, 10), slice(0, 10))) == 0.0
