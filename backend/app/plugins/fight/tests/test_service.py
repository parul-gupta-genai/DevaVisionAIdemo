"""
SOW 2.7 — confirmation, alerting and clearing for fight/quarrel incidents.

The tuning question here is different from fire's. A fire that takes ten
seconds to confirm is still a useful alarm; a quarrel that takes ten seconds
to confirm is one nobody can intervene in, and intervention is the whole
point. So the windows are short, and these tests pin the consequence: brief
sharp movement must not alert, and a sustained scuffle must alert quickly.
"""

import math
from datetime import datetime

import pytest

from app.plugins.fight import dynamics as dyn
from app.plugins.fight import service
from app.plugins.fight.rules import tuning

CAM = "cam1"
FPS = 14.0
DT = 1.0 / FPS
H = 160.0
BOX = [[100, 100], [1100, 100], [1100, 650], [100, 650]]


def zone(**over):
    z = {"zone_id": "FT-1", "name": "Loading Bay", "camera_id": CAM,
         "points": BOX, "zone_kind": "DETECT", "is_active": True,
         "sensitivity": "standard", "overrides": {}, "schedule": None,
         "severity": None}
    z.update(over)
    return z


def person(cx, cy=400, h=H):
    w = h * 0.4
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]


def scuffle_pair(step, x=500):
    a = x + math.sin(step * 2.6) * 0.28 * H + math.sin(step * 5.1) * 0.12 * H
    b = x + 0.6 * H + math.sin(step * 2.9 + 1) * 0.28 * H
    return [(1, person(a, 400 + math.sin(step * 3.7) * 0.10 * H)),
            (2, person(b, 400 + math.sin(step * 4.1) * 0.10 * H))]


def calm_pair(step, x=500):
    return [(1, person(x + math.sin(step * 0.7))),
            (2, person(x + 0.8 * H + math.sin(step * 0.6)))]


def run(frames, zones=None, state=None, t0=1000.0, dt=DT):
    zones = zones if zones is not None else [zone()]
    state = state if state is not None else {}
    hits = []
    for i, boxes in enumerate(frames):
        hits.extend(service.evaluate(CAM, boxes, zones, state, now=t0 + i * dt))
    return hits, state


def types(hits):
    return [h.event_type for h in hits]


# ----------------------------------------------------------------------
# confirmation
# ----------------------------------------------------------------------
def test_a_couple_of_sharp_frames_do_not_alert():
    hits, _ = run([scuffle_pair(i) for i in range(3)])
    assert types(hits) == []


def test_a_sustained_scuffle_alerts_once():
    hits, _ = run([scuffle_pair(i) for i in range(60)])
    fights = [h for h in hits if h.event_type == service.FIGHT_DETECTED]
    assert len(fights) == 1


def test_it_alerts_quickly_enough_to_intervene():
    """A quarrel confirmed after ten seconds is one nobody can intervene in."""
    hits, _ = run([scuffle_pair(i) for i in range(60)])
    fight = [h for h in hits if h.event_type == service.FIGHT_DETECTED][0]
    assert fight.timestamp - fight.started_at <= 4.0


def test_two_people_standing_and_talking_never_alerts():
    hits, _ = run([calm_pair(i) for i in range(80)])
    assert types(hits) == []


def test_confirmation_needs_both_time_and_frames():
    """A burst of frames delivered in milliseconds is not 1.5 seconds."""
    hits, _ = run([scuffle_pair(i) for i in range(30)], dt=0.005)
    assert types(hits) == []


def test_an_empty_frame_stream_is_harmless():
    hits, _ = run([[] for _ in range(30)])
    assert types(hits) == []


# ----------------------------------------------------------------------
# clearing and cooldown
# ----------------------------------------------------------------------
def test_an_incident_clears_once_it_stops():
    frames = [scuffle_pair(i) for i in range(60)] + [calm_pair(i) for i in range(200)]
    hits, _ = run(frames)
    assert service.FIGHT_CLEARED in types(hits)


def test_a_momentary_separation_does_not_clear_a_live_fight():
    frames = ([scuffle_pair(i) for i in range(60)] + [[] for _ in range(4)]
              + [scuffle_pair(i) for i in range(60)])
    hits, _ = run(frames)
    assert service.FIGHT_CLEARED not in types(hits)


def test_a_continuing_fight_does_not_re_alert_inside_the_cooldown():
    hits, _ = run([scuffle_pair(i) for i in range(900)])
    fights = [h for h in hits if h.event_type == service.FIGHT_DETECTED]
    assert len(fights) == 1


def test_a_fight_that_resumes_after_an_all_clear_alerts_again():
    """Once security has been told it is over, a restart must be reported."""
    block = ([scuffle_pair(i) for i in range(60)] + [calm_pair(i) for i in range(200)])
    hits, _ = run(block * 2)
    assert len([h for h in hits if h.event_type == service.FIGHT_DETECTED]) == 2
    assert len([h for h in hits if h.event_type == service.FIGHT_CLEARED]) == 2


# ----------------------------------------------------------------------
# zones and schedules
# ----------------------------------------------------------------------
def test_a_fight_outside_the_detect_zone_is_ignored():
    zones = [zone(points=[[900, 100], [1200, 100], [1200, 300], [900, 300]])]
    hits, _ = run([scuffle_pair(i) for i in range(60)], zones=zones)
    assert types(hits) == []


def test_a_fight_inside_an_exclusion_zone_is_ignored():
    zones = [zone(), zone(zone_id="FT-X", name="Gym", zone_kind="EXCLUDE",
                          points=[[300, 200], [800, 200], [800, 600], [300, 600]])]
    hits, _ = run([scuffle_pair(i) for i in range(60)], zones=zones)
    assert types(hits) == []


def test_with_no_zones_configured_the_whole_frame_is_watched():
    hits, _ = run([scuffle_pair(i) for i in range(60)], zones=[])
    assert service.FIGHT_DETECTED in types(hits)


def test_an_inactive_zone_is_not_evaluated():
    hits, _ = run([scuffle_pair(i) for i in range(60)],
                  zones=[zone(is_active=False)])
    assert types(hits) == []


def test_a_disarmed_zone_raises_nothing():
    night = [{"start": "22:00", "end": "23:00", "days": list(range(7))}]
    state, hits = {}, []
    for i in range(60):
        hits += service.evaluate(CAM, scuffle_pair(i), [zone(schedule=night)],
                                 state, now=1000.0 + i * DT,
                                 local_now=datetime(2026, 9, 1, 9, 0))
    assert types(hits) == []


def test_an_armed_zone_inside_its_window_alerts():
    night = [{"start": "22:00", "end": "23:00", "days": list(range(7))}]
    state, hits = {}, []
    for i in range(60):
        hits += service.evaluate(CAM, scuffle_pair(i), [zone(schedule=night)],
                                 state, now=1000.0 + i * DT,
                                 local_now=datetime(2026, 9, 1, 22, 30))
    assert service.FIGHT_DETECTED in types(hits)


def test_deleting_a_zone_mid_incident_closes_it_out():
    state = {}
    run([scuffle_pair(i) for i in range(60)], state=state)
    zones = [zone(zone_id="OTHER", name="Other",
                  points=[[10, 10], [60, 10], [60, 60], [10, 60]])]
    closing = service.evaluate(CAM, scuffle_pair(99), zones, state, now=2000.0)
    assert service.FIGHT_CLEARED in types(closing)


# ----------------------------------------------------------------------
# what an alert carries
# ----------------------------------------------------------------------
def test_an_alert_carries_what_a_guard_needs():
    hits, _ = run([scuffle_pair(i) for i in range(60)])
    h = [x for x in hits if x.event_type == service.FIGHT_DETECTED][0]
    assert h.camera_id == CAM
    assert h.zone_name == "Loading Bay"
    assert len(h.track_ids) == 2
    assert len(h.bbox) == 4
    assert 0.0 < h.score <= 1.0
    assert h.severity == "critical"


def test_the_description_says_it_needs_human_verification():
    """SOW 2.7: the client must be told this is an aid, not a verdict."""
    hits, _ = run([scuffle_pair(i) for i in range(60)])
    h = [x for x in hits if x.event_type == service.FIGHT_DETECTED][0]
    assert "human verification" in h.describe().lower()


def test_the_advisory_notice_says_what_it_must():
    text = service.ADVISORY_NOTICE.lower()
    assert "does not replace" in text
    assert "human security intervention" in text


def test_a_hit_is_drawable():
    hits, _ = run([scuffle_pair(i) for i in range(60)])
    h = [x for x in hits if x.event_type == service.FIGHT_DETECTED][0]
    assert any(d.get("type") == "rect" for d in service.hit_drawings(h))


def test_zone_outlines_are_drawable():
    assert service.zone_outline_drawings([zone()])


def test_state_stays_bounded():
    state = {}
    for i in range(600):
        service.evaluate(CAM, scuffle_pair(i), [zone()], state, now=1000.0 + i * DT)
    assert len(state) < 40


def test_a_zone_with_broken_geometry_is_skipped():
    hits, _ = run([scuffle_pair(i) for i in range(60)],
                  zones=[zone(points=[[1, 2]])])
    assert types(hits) == []
