"""
SOW 2.8 — the alert mechanism: turning frames of evidence into an incident.

The rule that earns this layer its place is confirmation. A single frame that
looks like fire is not a fire; it is a reflection, a passing forklift beacon,
or one bad auto-exposure step. Alerting on it is how a safety system becomes
the thing everyone mutes. Evidence must therefore persist for a configured
time AND a configured number of frames before anybody is told.

The other half is that an incident has to END. Without a clear rule the
appliance keeps a fire "active" forever, the dashboard shows a permanent red
banner, and the next real fire on that camera is invisible inside it.
"""

import pytest

from app.plugins.fire import detector as det
from app.plugins.fire import service
from app.plugins.fire.rules import tuning

CAM = "cam1"
BOX = [[100, 100], [900, 100], [900, 600], [100, 600]]


def zone(**over):
    z = {
        "zone_id": "FZ-1", "name": "Boiler House", "camera_id": CAM,
        "points": BOX, "zone_kind": "DETECT", "is_active": True,
        "watch": ["fire", "smoke"], "sensitivity": "standard",
        "overrides": {}, "schedule": None, "severity": None,
    }
    z.update(over)
    return z


def fire_at(x1=200, y1=200, x2=700, y2=500, score=0.8):
    return det.Candidate(det.FIRE, [x1, y1, x2, y2], 0.10, score)


def smoke_at(x1=200, y1=200, x2=700, y2=500, score=0.8):
    return det.Candidate(det.SMOKE, [x1, y1, x2, y2], 0.12, score)


def run(cands_by_frame, zones=None, state=None, t0=1000.0, dt=0.5):
    """Feeds frames in and returns the flattened hits, with the state."""
    zones = zones if zones is not None else [zone()]
    state = state if state is not None else {}
    hits = []
    for i, cands in enumerate(cands_by_frame):
        hits.extend(service.evaluate(CAM, cands, zones, state, now=t0 + i * dt))
    return hits, state


def types(hits):
    return [h.event_type for h in hits]


# ----------------------------------------------------------------------
# confirmation
# ----------------------------------------------------------------------
def test_one_frame_of_fire_does_not_alert():
    hits, _ = run([[fire_at()]])
    assert types(hits) == []


def test_sustained_fire_confirms_and_alerts_once():
    t = tuning("standard")
    frames = [[fire_at()]] * 12                       # 6 seconds at 0.5s/frame
    hits, _ = run(frames)
    fires = [h for h in hits if h.event_type == service.FIRE_DETECTED]
    assert len(fires) == 1, f"expected exactly one alert, got {len(fires)}"
    assert fires[0].kind == det.FIRE


def test_confirmation_needs_both_time_and_frames():
    """
    Three frames 10ms apart is three frames, but it is not two seconds.
    A camera delivering a burst must not shortcut the window.
    """
    hits, _ = run([[fire_at()]] * 6, dt=0.01)
    assert types(hits) == []


def test_evidence_below_the_score_threshold_never_confirms():
    weak = tuning("standard")["min_score"] - 0.05
    hits, _ = run([[fire_at(score=weak)]] * 20)
    assert types(hits) == []


def test_a_region_smaller_than_the_area_floor_is_ignored():
    tiny = det.Candidate(det.FIRE, [200, 200, 210, 210], 0.0001, 0.9)
    hits, _ = run([[tiny]] * 20)
    assert types(hits) == []


def test_intermittent_evidence_does_not_accumulate_forever():
    """
    One flash every ten seconds is not a fire. Frames must land inside the
    confirmation window, so an incident that goes quiet resets.
    """
    frames = []
    for _ in range(6):
        frames.append([fire_at()])
        frames.extend([[]] * 60)          # 30s of nothing at 0.5s/frame
    hits, _ = run(frames)
    assert service.FIRE_DETECTED not in types(hits)


# ----------------------------------------------------------------------
# smoke
# ----------------------------------------------------------------------
def test_sustained_smoke_raises_a_smoke_event_not_a_fire_one():
    hits, _ = run([[smoke_at()]] * 12)
    kinds = {h.event_type for h in hits if h.event_type != service.FIRE_CLEARED}
    assert kinds == {service.SMOKE_DETECTED}


def test_fire_and_smoke_together_raise_both():
    hits, _ = run([[fire_at(), smoke_at()]] * 12)
    raised = {h.event_type for h in hits}
    assert service.FIRE_DETECTED in raised
    assert service.SMOKE_DETECTED in raised


def test_a_zone_watching_only_smoke_ignores_flames():
    hits, _ = run([[fire_at()]] * 12, zones=[zone(watch=["smoke"])])
    assert types(hits) == []


def test_fire_carries_critical_severity_and_smoke_carries_warning():
    hits, _ = run([[fire_at(), smoke_at()]] * 12)
    by_type = {h.event_type: h for h in hits}
    assert by_type[service.FIRE_DETECTED].severity == "critical"
    assert by_type[service.SMOKE_DETECTED].severity == "warning"


def test_an_explicit_zone_severity_overrides_the_default():
    hits, _ = run([[smoke_at()]] * 12, zones=[zone(severity="critical")])
    smoke = [h for h in hits if h.event_type == service.SMOKE_DETECTED][0]
    assert smoke.severity == "critical"


# ----------------------------------------------------------------------
# cooldown and clearing
# ----------------------------------------------------------------------
def test_a_continuing_fire_does_not_re_alert_inside_the_cooldown():
    hits, _ = run([[fire_at()]] * 200, dt=0.5)        # 100 seconds
    fires = [h for h in hits if h.event_type == service.FIRE_DETECTED]
    assert len(fires) == 1, "a fire that is still burning is still one fire"


def test_a_fire_re_alerts_once_the_cooldown_has_passed():
    cooldown = tuning("standard")["alert_cooldown_sec"]
    frames = [[fire_at()]] * int((cooldown * 2.5) / 0.5)
    hits, _ = run(frames, dt=0.5)
    fires = [h for h in hits if h.event_type == service.FIRE_DETECTED]
    assert len(fires) >= 2


def test_an_incident_clears_after_the_quiet_period():
    frames = [[fire_at()]] * 12 + [[]] * 60           # 30s of quiet
    hits, _ = run(frames)
    assert service.FIRE_CLEARED in types(hits)


def test_clearing_reports_how_long_the_incident_ran():
    frames = [[fire_at()]] * 12 + [[]] * 60
    hits, _ = run(frames)
    cleared = [h for h in hits if h.event_type == service.FIRE_CLEARED][0]
    assert cleared.duration_sec >= 5.0


def test_a_brief_gap_does_not_clear_a_live_fire():
    """Flames flicker out of the colour band for a frame or two constantly."""
    frames = [[fire_at()]] * 12 + [[]] * 2 + [[fire_at()]] * 12
    hits, _ = run(frames)
    assert service.FIRE_CLEARED not in types(hits)


def test_a_cleared_incident_can_start_again_later():
    frames = ([[fire_at()]] * 12 + [[]] * 60) * 2
    hits, _ = run(frames, dt=0.5)
    assert len([h for h in hits if h.event_type == service.FIRE_DETECTED]) == 2
    assert len([h for h in hits if h.event_type == service.FIRE_CLEARED]) == 2


# ----------------------------------------------------------------------
# zones
# ----------------------------------------------------------------------
def test_fire_outside_every_detect_zone_is_ignored():
    hits, _ = run([[fire_at(1000, 620, 1200, 700)]] * 12)
    assert types(hits) == []


def test_fire_inside_an_exclusion_zone_is_ignored():
    zones = [zone(), zone(zone_id="FZ-X", name="Welding Bay",
                          zone_kind="EXCLUDE",
                          points=[[150, 150], [500, 150], [500, 400], [150, 400]])]
    hits, _ = run([[fire_at(200, 200, 450, 380)]] * 12, zones=zones)
    assert types(hits) == []


def test_an_exclusion_zone_does_not_silence_the_rest_of_the_frame():
    zones = [zone(), zone(zone_id="FZ-X", zone_kind="EXCLUDE", name="Welding Bay",
                          points=[[150, 150], [300, 150], [300, 300], [150, 300]])]
    hits, _ = run([[fire_at(500, 350, 800, 550)]] * 12, zones=zones)
    assert service.FIRE_DETECTED in types(hits)


def test_with_no_zones_configured_the_whole_frame_is_watched():
    """
    Fire anywhere in shot is meaningful, so an operator who never drew a zone
    must still be protected. This is the opposite of a restricted zone, which
    means nothing without geometry.
    """
    hits, _ = run([[fire_at()]] * 12, zones=[])
    assert service.FIRE_DETECTED in types(hits)


def test_an_inactive_zone_is_not_evaluated():
    hits, _ = run([[fire_at()]] * 12, zones=[zone(is_active=False)])
    assert types(hits) == []


def test_two_zones_on_one_camera_alert_independently():
    zones = [zone(zone_id="A", name="Store"),
             zone(zone_id="B", name="Dock",
                  points=[[950, 100], [1270, 100], [1270, 600], [950, 600]])]
    frames = [[fire_at(200, 200, 700, 500), fire_at(1000, 200, 1200, 500)]] * 12
    hits, _ = run(frames, zones=zones)
    fired = {h.zone_id for h in hits if h.event_type == service.FIRE_DETECTED}
    assert fired == {"A", "B"}


# ----------------------------------------------------------------------
# schedules
# ----------------------------------------------------------------------
def test_a_disarmed_zone_raises_nothing():
    from datetime import datetime
    night = [{"start": "22:00", "end": "23:00", "days": [0, 1, 2, 3, 4, 5, 6]}]
    zones = [zone(schedule=night)]
    state = {}
    hits = []
    for i in range(20):
        hits.extend(service.evaluate(
            CAM, [fire_at()], zones, state, now=1000.0 + i * 0.5,
            local_now=datetime(2026, 9, 1, 9, 0)))      # 09:00, outside window
    assert types(hits) == []


def test_an_armed_zone_inside_its_window_still_alerts():
    from datetime import datetime
    night = [{"start": "22:00", "end": "23:00", "days": [0, 1, 2, 3, 4, 5, 6]}]
    zones = [zone(schedule=night)]
    state = {}
    hits = []
    for i in range(20):
        hits.extend(service.evaluate(
            CAM, [fire_at()], zones, state, now=1000.0 + i * 0.5,
            local_now=datetime(2026, 9, 1, 22, 30)))
    assert service.FIRE_DETECTED in types(hits)


# ----------------------------------------------------------------------
# incident content
# ----------------------------------------------------------------------
def test_an_alert_carries_the_evidence_an_operator_needs():
    hits, _ = run([[fire_at()]] * 12)
    h = [x for x in hits if x.event_type == service.FIRE_DETECTED][0]
    assert h.camera_id == CAM
    assert h.zone_name == "Boiler House"
    assert h.bbox and len(h.bbox) == 4
    assert 0.0 < h.score <= 1.0
    assert h.started_at <= h.timestamp
    assert "Boiler House" in h.describe()


def test_the_alert_reports_the_peak_score_not_the_last_one():
    frames = [[fire_at(score=0.95)]] * 4 + [[fire_at(score=0.55)]] * 8
    hits, _ = run(frames)
    h = [x for x in hits if x.event_type == service.FIRE_DETECTED][0]
    assert h.score == pytest.approx(0.95)


def test_state_does_not_grow_without_bound():
    state = {}
    for i in range(500):
        service.evaluate(CAM, [fire_at()] if i % 2 else [], [zone()], state,
                         now=1000.0 + i * 0.5)
    assert len(state) < 50


# ----------------------------------------------------------------------
# overlay
# ----------------------------------------------------------------------
def test_zone_outlines_are_drawable():
    d = service.zone_outline_drawings([zone()])
    assert d and all("type" in x and "coords" in x for x in d)


def test_an_implicit_whole_frame_zone_draws_nothing():
    """Nothing was configured, so there is no outline to show."""
    assert service.zone_outline_drawings([]) == []


def test_a_hit_is_drawable_in_red():
    hits, _ = run([[fire_at()]] * 12)
    h = [x for x in hits if x.event_type == service.FIRE_DETECTED][0]
    d = service.hit_drawings(h)
    assert d and any(x.get("type") == "rect" for x in d)


# ----------------------------------------------------------------------
# robustness
# ----------------------------------------------------------------------
def test_a_zone_with_broken_geometry_is_skipped_not_fatal():
    hits, _ = run([[fire_at()]] * 12, zones=[zone(points=[[1, 2]])])
    assert types(hits) == []


def test_evaluate_tolerates_no_candidates_and_no_zones():
    assert service.evaluate(CAM, [], [], {}, now=1.0) == []


# ----------------------------------------------------------------------
# a threshold an operator can set must be a threshold that can be reached
# ----------------------------------------------------------------------
def test_a_high_min_frames_override_can_still_be_reached():
    """
    min_frames is settable per zone up to 300. If the evidence window did not
    grow with it, a zone configured that way would sit in the UI looking
    armed while being incapable of ever alerting — the worst kind of wrong,
    because nothing about it looks broken.
    """
    hits, _ = run([[fire_at()]] * 90, zones=[zone(overrides={"min_frames": 30})],
                  dt=0.5)
    assert service.FIRE_DETECTED in types(hits)


def test_the_evidence_window_scales_with_the_sightings_required():
    from app.plugins.fire.rules import tuning as _t
    narrow = service._window(_t("standard", {"min_frames": 3}))
    wide = service._window(_t("standard", {"min_frames": 60}))
    assert wide > narrow
    assert wide >= 60 * service.WORST_CASE_GAP_SEC


# ----------------------------------------------------------------------
# incidents must not be able to disappear
# ----------------------------------------------------------------------
def test_deleting_a_zone_mid_incident_closes_the_incident_out():
    """
    Otherwise the incident log keeps a confirmed fire open forever: no
    FIRE_CLEARED is ever written and the dashboard shows a permanent alarm
    for a zone that no longer exists.
    """
    state = {}
    zones = [zone()]
    hits = []
    for i in range(12):
        hits += service.evaluate(CAM, [fire_at()], zones, state, now=1000.0 + i * 0.5)
    assert service.FIRE_DETECTED in types(hits)

    # The operator deletes the zone while it is still burning.
    closing = service.evaluate(CAM, [fire_at()], [], state, now=1010.0)
    assert service.FIRE_CLEARED in types(closing)
    # Passing no zones also starts whole-frame monitoring on the same call, so
    # only the deleted zone's own state should be gone.
    survivors = [k for k in state
                 if k.startswith("FZ-1|")
                 and not k.startswith(service.COOLDOWN_PREFIX)]
    assert survivors == [], f"the deleted zone's incident survived: {survivors}"


def test_disarming_a_zone_mid_incident_closes_the_incident_out():
    from datetime import datetime

    night = [{"start": "22:00", "end": "23:00", "days": list(range(7))}]
    state = {}
    hits = []
    for i in range(12):
        hits += service.evaluate(CAM, [fire_at()], [zone(schedule=night)], state,
                                 now=1000.0 + i * 0.5,
                                 local_now=datetime(2026, 9, 1, 22, 30))
    assert service.FIRE_DETECTED in types(hits)

    closing = service.evaluate(CAM, [fire_at()], [zone(schedule=night)], state,
                               now=1010.0, local_now=datetime(2026, 9, 1, 9, 0))
    assert service.FIRE_CLEARED in types(closing)


def test_an_unconfirmed_incident_that_expires_raises_nothing():
    """Only incidents somebody was told about need closing out."""
    state = {}
    service.evaluate(CAM, [fire_at()], [zone()], state, now=1000.0)
    closing = service.evaluate(CAM, [fire_at()], [], state, now=1001.0)
    assert types(closing) == []


# ----------------------------------------------------------------------
# the cooldown is a property of the zone, not of one incident
# ----------------------------------------------------------------------
def test_a_brief_evidence_lapse_cannot_restart_the_cooldown():
    """
    An incident record is closed and reopened by ordinary detection noise, so
    the cooldown cannot live on it: a fire whose evidence lapses for a few
    seconds would otherwise open a fresh incident with a clean history and
    page somebody again straight away.

    Note the deliberate asymmetry with the test below. A gap SHORT of
    clear_sec is noise and must not re-alert; a gap long enough to have
    raised an all-clear must.
    """
    gap = int((tuning("standard")["clear_sec"] * 0.7) / 0.5)
    frames = ([[fire_at()]] * 12 + [[]] * gap) * 3
    hits, _ = run(frames, dt=0.5)
    fires = [h for h in hits if h.event_type == service.FIRE_DETECTED]
    assert len(fires) == 1, f"alerted {len(fires)} times inside one cooldown"


def test_a_fire_that_returns_after_an_all_clear_alerts_again():
    """
    The other half, and the more important one. Once the system has told an
    operator the fire is out they may have stood down, so a suppressed
    re-alarm is the dangerous direction to fail in — the cooldown must not
    outlive its own all-clear.
    """
    frames = ([[fire_at()]] * 12 + [[]] * 60) * 2       # burn, CLEAR, burn
    hits, _ = run(frames, dt=0.5)
    assert len([h for h in hits if h.event_type == service.FIRE_DETECTED]) == 2
    assert len([h for h in hits if h.event_type == service.FIRE_CLEARED]) == 2


def test_the_cooldown_still_expires_normally():
    cooldown = tuning("standard")["alert_cooldown_sec"]
    frames = [[fire_at()]] * int((cooldown * 2.5) / 0.5)
    hits, _ = run(frames, dt=0.5)
    assert len([h for h in hits if h.event_type == service.FIRE_DETECTED]) >= 2


# ----------------------------------------------------------------------
# the tracking cap must not lock out a real fire
# ----------------------------------------------------------------------
def test_a_busy_camera_cannot_lock_out_a_new_fire():
    """
    MAX_TRACKED bounds the state, but refusing all new evidence once it is
    full makes the cap a denial-of-service on the feature: whatever happened
    to be seen first keeps its slot forever.
    """
    state = {}
    zones = [zone(zone_id=f"Z{i}", name=f"Zone {i}",
                  points=[[10 + i, 10], [40 + i, 10], [40 + i, 40], [10 + i, 40]])
             for i in range(service.MAX_TRACKED + 4)]
    # Fill the tracker with stale, never-confirmed noise.
    for i in range(len(zones)):
        service.evaluate(CAM, [fire_at(12 + i, 12, 38 + i, 38)], zones, state,
                         now=1000.0 + i)
    incidents = [k for k in state if not k.startswith(service.COOLDOWN_PREFIX)]
    assert len(incidents) <= service.MAX_TRACKED

    # A real, sustained fire arrives much later in the LAST zone.
    hits = []
    for i in range(12):
        hits += service.evaluate(
            CAM, [fire_at(12 + len(zones) - 1, 12, 38 + len(zones) - 1, 38)],
            zones, state, now=2000.0 + i * 0.5)
    assert service.FIRE_DETECTED in types(hits)
