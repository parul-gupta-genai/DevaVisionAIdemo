"""
SOW 2.8 — the two properties that make this EARLY warning rather than late
confirmation. Both were found by replaying a synthetic incident clip end to
end; neither was caught by the unit tests written against hand-built frames.

1. A fire must be caught while it is still small. The area floor inherited
   from the legacy detector demanded 4.34% of the frame — a 200x200 pixel
   region at 720p. A bin fire or an early electrical fire never reaches that
   until it is a serious blaze, so the detector only "worked" once the
   warning was worthless.

2. Smoke must keep being reported while it is still there. The detector
   learns a background so it can tell an arriving veil from a grey wall, but
   it was learning on every frame including frames containing the smoke. At
   the plugin's real invocation rate on the appliance (interval 15 at ~13.5
   fps, so ~1.1s per call) the background half-life is about 15 seconds: a
   steady plume is absorbed and the alert silently stops while the fire is
   still burning.
"""

import numpy as np

from app.plugins.fire import detector as det

H, W = 720, 1280


def yard(seed=3):
    """A textured background, so smoke has detail to veil."""
    rng = np.random.default_rng(seed)
    f = rng.integers(40, 90, (H, W, 3), dtype=np.uint8)
    for x in range(0, W, 40):
        f[:, x:x + 6] = 200
    for y in range(0, H, 40):
        f[y:y + 6, :] = 200
    return f


def paint_flame(frame, cx, cy, half_w, half_h, phase):
    """A flame front of a given size that changes shape with `phase`."""
    rng = np.random.default_rng(phase % 9973)
    layer = np.zeros_like(frame)
    for i in range(4):
        w = max(4, half_w + int(half_w * 0.3 * np.sin(phase + i)))
        h = max(4, half_h + int(half_h * 0.3 * np.sin(phase * 1.7 + i)))
        ox = int(half_w * 0.25 * np.sin(phase * 0.9 + i))
        cv_ellipse(layer, cx + ox, cy, w, h,
                   (20, int(180 + rng.integers(-25, 26)), 255))
    lit = layer.any(axis=2)
    frame[lit] = layer[lit]
    return frame


def cv_ellipse(img, cx, cy, rx, ry, colour):
    import cv2
    cv2.ellipse(img, (int(cx), int(cy)), (int(rx), int(ry)), 0, 0, 360, colour, -1)


# ----------------------------------------------------------------------
# 1. small fire
# ----------------------------------------------------------------------
def test_a_fire_is_caught_while_it_is_still_small():
    """
    A flame roughly 110x110px at 720p — about 1.3% of the frame, a metre-scale
    fire on a typical yard camera. This is the size at which a warning is
    still worth something.
    """
    a = det.FrameAnalyzer()
    seen = 0
    for i in range(8):
        frame = yard().astype(np.uint8)
        paint_flame(frame, 640, 400, 55, 55, phase=i)
        if [c for c in a.analyze(frame) if c.kind == det.FIRE]:
            seen += 1
    assert seen >= 4, (
        f"a 110x110px flame registered on only {seen}/8 frames; the area "
        f"floor is {det.MIN_FIRE_AREA_FRAC:.2%} of frame, which demands a "
        f"{int((det.MIN_FIRE_AREA_FRAC * W * H) ** 0.5)}px square")


def test_the_fire_area_floor_is_an_early_warning_size():
    """Pins the intent, so nobody quietly raises it back to a late warning."""
    side = (det.MIN_FIRE_AREA_FRAC * W * H) ** 0.5
    assert side <= 120, (
        f"the smallest detectable fire is {side:.0f}x{side:.0f}px at 720p — "
        f"too big for an early-warning system")


def test_a_small_static_orange_object_still_does_not_alarm():
    """
    The area floor comes down, so the traffic cone now clears it. Flicker is
    the only thing left holding the line — this is the test that proves it
    still does.
    """
    import cv2
    a = det.FrameAnalyzer()
    frame = yard().astype(np.uint8)
    cv2.circle(frame, (400, 400), 60, (25, 190, 255), -1)   # cone-sized, static
    scores = []
    for _ in range(8):
        c = [c for c in a.analyze(frame.copy()) if c.kind == det.FIRE]
        scores.append(c[0].score if c else 0.0)
    assert scores[-1] < det.FIRE_ALARM_SCORE, (
        f"a motionless orange object scored {scores[-1]:.2f} once the area "
        f"floor allowed it through")


# ----------------------------------------------------------------------
# 2. persistent smoke
# ----------------------------------------------------------------------
def _smoky(bg, strength=0.75):
    out = bg.copy()
    region = out[150:600, 300:900]
    out[150:600, 300:900] = (region * (1 - strength) + 160 * strength).astype(np.uint8)
    return out


def test_a_steady_plume_is_still_reported_a_minute_later():
    """
    The failure this catches is silent and dangerous: the alert appears, then
    stops, while the smoke is still there. 60 calls at the appliance's ~1.1s
    spacing is a bit over a minute of continuous smoke.
    """
    a = det.FrameAnalyzer()
    bg = yard()
    for _ in range(det.BG_WARMUP_FRAMES + 4):
        a.analyze(bg.copy())

    smoky = _smoky(bg)
    first = bool([c for c in a.analyze(smoky.copy()) if c.kind == det.SMOKE])
    assert first, "smoke was not detected when it arrived"

    for _ in range(58):
        a.analyze(smoky.copy())
    still = [c for c in a.analyze(smoky.copy()) if c.kind == det.SMOKE]
    assert still, (
        "smoke stopped being reported while it was still present — the "
        "background model absorbed it")


def test_the_background_still_follows_a_genuine_scene_change():
    """
    Freezing the background under smoke must not freeze it entirely, or a
    light coming on at dusk would be reported as smoke forever.
    """
    a = det.FrameAnalyzer()
    bg = yard()
    for _ in range(det.BG_WARMUP_FRAMES + 4):
        a.analyze(bg.copy())

    brighter = np.clip(bg.astype(np.int16) + 55, 0, 255).astype(np.uint8)
    for _ in range(60):
        a.analyze(brighter.copy())
    assert [c for c in a.analyze(brighter.copy()) if c.kind == det.SMOKE] == [], \
        "a settled brightness change must be learned, not reported as smoke"


# ----------------------------------------------------------------------
# 3. what a live site actually contains
# ----------------------------------------------------------------------
def _confirms(frames, dt=1.1, zones=None):
    """Runs frames through detector AND service; returns the incidents raised."""
    from app.plugins.fire import service

    a = det.FrameAnalyzer()
    state, hits = {}, []
    for i, f in enumerate(frames):
        hits += service.evaluate("cam", a.analyze(f), zones or [], state,
                                 now=1000.0 + i * dt)
    return hits


def _cone_frame(dx=0, dy=0):
    import cv2
    f = cv2.circle(yard(), (400, 400), 60, (25, 190, 255), -1)
    return np.roll(np.roll(f, dx, axis=1), dy, axis=0)


def test_a_flashing_beacon_never_confirms_an_incident():
    import cv2

    frames = []
    for i in range(30):
        f = yard()
        if i % 2 == 0:
            cv2.circle(f, (400, 400), 60, (25, 190, 255), -1)
        frames.append(f)
    assert _confirms(frames) == []


def test_a_shaking_camera_does_not_turn_a_cone_into_a_fire():
    """
    A pole-mounted camera in wind. Shake displaces every edge in the scene, so
    an orange object in shot churns exactly as a flame does — measured, this
    confirmed a fire on a traffic cone. What separates them is locality: a
    flame's change is ~27x the change around it, a shaking scene's is ~2x.
    """
    rng = np.random.default_rng(1)
    frames = [_cone_frame(int(rng.integers(-6, 7)), int(rng.integers(-6, 7)))
              for _ in range(30)]
    assert _confirms(frames) == []


def test_even_heavy_shake_does_not_turn_a_cone_into_a_fire():
    rng = np.random.default_rng(9)
    frames = [_cone_frame(int(rng.integers(-20, 21)), int(rng.integers(-20, 21)))
              for _ in range(30)]
    assert _confirms(frames) == []


def test_a_real_flame_still_confirms_under_the_same_rules():
    """The control: the same pipeline that stays silent above must still fire."""
    from app.plugins.fire import service
    from app.plugins.fire.tests.test_detector import flame_front

    hits = _confirms([flame_front(yard(), i) for i in range(30)])
    assert [h for h in hits if h.event_type == service.FIRE_DETECTED]


def test_a_pale_vehicle_crossing_frame_is_not_smoke():
    """
    Measured: before the travel test, a white van produced a smoke candidate
    on 8 of 8 calls. A plume drifts and swells; a van crosses.
    """
    import cv2
    from app.plugins.fire import service

    a = det.FrameAnalyzer()
    bg = yard()
    for _ in range(det.BG_WARMUP_FRAMES + 4):
        a.analyze(bg.copy())

    state, hits = {}, []
    for i in range(10):
        f = bg.copy()
        x = 60 + i * 120
        cv2.rectangle(f, (x, 300), (x + 380, 600), (185, 185, 185), -1)
        hits += service.evaluate("cam", a.analyze(f), [], state, now=1000.0 + i * 1.1)
    assert [h for h in hits if h.event_type == service.SMOKE_DETECTED] == []
