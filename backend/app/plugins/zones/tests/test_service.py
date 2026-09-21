"""
SOW 2.9 — Intrusion detection and alert generation.

The state machine is a pure function over a state dict, so a whole breach can
be played out frame by frame against a fake clock with no pipeline, camera or
database in sight.

The three rules under test are the ones that separate an alarm an operator
trusts from a stream they mute: dwell before it counts, grace before leaving
is believed, and a cooldown so a queue at a doorway produces one alert.
"""

from datetime import datetime

import pytest

from app.engine.base import NormalizedDetection
from app.plugins.zones import service as s

SQUARE = [[100, 100], [500, 100], [500, 500], [100, 500]]

# Feet at (300, 400): inside SQUARE.
INSIDE = [250, 200, 350, 400]
# Feet at (900, 400): well clear of it.
OUTSIDE = [850, 200, 950, 400]


def zone(**over):
    z = {
        "zone_id": "z1",
        "name": "Switchyard",
        "points": SQUARE,
        "classes": [0],
        "min_confidence": 0.4,
        "min_box_px": 0,
        "anchor": "FEET",
        "min_dwell_sec": 2.0,
        "loiter_sec": None,
        "exit_grace_sec": 3.0,
        "alert_cooldown_sec": 30.0,
        "severity": "warning",
        "is_active": True,
        "schedule": None,
    }
    z.update(over)
    return z


def det(bbox=INSIDE, track_id=1, class_id=0, confidence=0.9):
    return NormalizedDetection(bbox=list(bbox), track_id=track_id,
                               class_id=class_id, confidence=confidence)


def run(zones, dets, state, t):
    return s.evaluate("cam1", dets, zones, state, now=t,
                      local_now=datetime(2026, 9, 1, 12, 0))


def types(hits):
    return [h.event_type for h in hits]


# ----------------------------------------------------------------------
# The dwell rule
# ----------------------------------------------------------------------
def test_a_single_frame_inside_is_not_an_intrusion():
    """Two frames of box jitter over the boundary must not raise an alarm."""
    st = {}
    assert run([zone()], [det()], st, 100.0) == []


def test_the_alert_fires_once_the_dwell_is_satisfied():
    st = {}
    run([zone()], [det()], st, 100.0)
    assert run([zone()], [det()], st, 101.9) == []          # still short
    assert types(run([zone()], [det()], st, 102.0)) == [s.ZONE_ENTRY]


def test_the_entry_alert_is_raised_only_once_per_visit():
    st = {}
    run([zone()], [det()], st, 100.0)
    run([zone()], [det()], st, 103.0)
    for t in (104.0, 105.0, 106.0):
        assert run([zone()], [det()], st, t) == []


def test_zero_dwell_alerts_on_the_first_frame():
    st = {}
    assert types(run([zone(min_dwell_sec=0)], [det()], st, 100.0)) == [s.ZONE_ENTRY]


def test_a_detection_outside_never_starts_a_visit():
    st = {}
    for t in (100.0, 105.0, 110.0):
        assert run([zone()], [det(bbox=OUTSIDE)], st, t) == []


# ----------------------------------------------------------------------
# Leaving, and the grace period
# ----------------------------------------------------------------------
def test_a_brief_occlusion_does_not_close_the_visit():
    st = {}
    run([zone()], [det()], st, 100.0)
    run([zone()], [det()], st, 103.0)                       # ENTRY
    assert run([zone()], [], st, 105.0) == []               # occluded, inside grace


def test_leaving_is_believed_after_the_grace_period():
    st = {}
    run([zone()], [det()], st, 100.0)
    run([zone()], [det()], st, 103.0)
    hits = run([zone()], [], st, 106.5)
    assert types(hits) == [s.ZONE_EXIT]


def test_exit_dwell_excludes_the_grace_window():
    """
    Grace is confirmation that they left, not time spent in the zone, so it
    must not inflate the recorded dwell.
    """
    st = {}
    run([zone()], [det()], st, 100.0)
    run([zone()], [det()], st, 103.0)                       # last frame inside
    hit = run([zone()], [], st, 106.5)[0]
    assert hit.dwell_seconds == pytest.approx(3.0)


def test_a_visit_that_never_alerted_exits_silently():
    """Somebody who crossed a corner for one frame leaves no record."""
    st = {}
    run([zone()], [det()], st, 100.0)                       # below dwell
    assert run([zone()], [], st, 104.0) == []


def test_a_new_visit_can_start_after_a_confirmed_exit():
    st = {}
    run([zone(alert_cooldown_sec=0)], [det()], st, 100.0)
    run([zone(alert_cooldown_sec=0)], [det()], st, 103.0)
    run([zone(alert_cooldown_sec=0)], [], st, 107.0)        # EXIT
    run([zone(alert_cooldown_sec=0)], [det()], st, 200.0)
    assert types(run([zone(alert_cooldown_sec=0)], [det()], st, 203.0)) == [s.ZONE_ENTRY]


# ----------------------------------------------------------------------
# The cooldown
# ----------------------------------------------------------------------
def test_a_second_person_inside_the_cooldown_is_suppressed():
    st = {}
    z = [zone(min_dwell_sec=0, alert_cooldown_sec=30)]
    assert types(run(z, [det(track_id=1)], st, 100.0)) == [s.ZONE_ENTRY]
    assert run(z, [det(track_id=1), det(track_id=2)], st, 105.0) == []


def test_a_suppressed_alert_is_not_lost_but_deferred():
    """
    Being inside the cooldown must not mark the visit as alerted: the person
    is still standing in the zone, so the alert fires when the cooldown
    lapses rather than never.
    """
    st = {}
    z = [zone(min_dwell_sec=0, alert_cooldown_sec=30)]
    both = [det(track_id=1), det(track_id=2)]
    run(z, [det(track_id=1)], st, 100.0)                    # first alert
    assert run(z, both, st, 110.0) == []                    # second one suppressed
    # Cooldown lapsed and track 2 is still standing there: it alerts now.
    assert types(run(z, both, st, 131.0)) == [s.ZONE_ENTRY]


def test_a_zone_that_has_never_alerted_always_may():
    """
    The cooldown must key off 'no previous alert', not a zero timestamp — a
    frame clock starting near zero would otherwise swallow the first alert.
    """
    st = {}
    hits = s.evaluate("cam1", [det()], [zone(min_dwell_sec=0)], st,
                      now=0.5, local_now=datetime(2026, 9, 1, 12, 0))
    assert types(hits) == [s.ZONE_ENTRY]


def test_cooldowns_are_independent_per_zone():
    st = {}
    a = zone(zone_id="a", min_dwell_sec=0, alert_cooldown_sec=30)
    b = zone(zone_id="b", name="Substation", min_dwell_sec=0,
             alert_cooldown_sec=30)
    hits = run([a, b], [det()], st, 100.0)
    assert sorted(h.zone_id for h in hits) == ["a", "b"]


# ----------------------------------------------------------------------
# Loitering escalation
# ----------------------------------------------------------------------
def test_loitering_escalates_after_the_configured_dwell():
    st = {}
    z = [zone(min_dwell_sec=0, loiter_sec=10)]
    run(z, [det()], st, 100.0)                              # ENTRY
    assert run(z, [det()], st, 105.0) == []
    assert types(run(z, [det()], st, 110.0)) == [s.ZONE_LOITERING]


def test_loitering_repeats_at_the_configured_interval():
    st = {}
    z = [zone(min_dwell_sec=0, loiter_sec=10)]
    run(z, [det()], st, 100.0)
    run(z, [det()], st, 110.0)
    assert run(z, [det()], st, 115.0) == []
    assert types(run(z, [det()], st, 120.0)) == [s.ZONE_LOITERING]


def test_loitering_is_off_unless_configured():
    st = {}
    z = [zone(min_dwell_sec=0, loiter_sec=None)]
    run(z, [det()], st, 100.0)
    assert run(z, [det()], st, 500.0) == []


def test_loitering_never_precedes_the_entry_alert():
    """A visit suppressed by cooldown must not escalate to loitering."""
    st = {}
    z = [zone(min_dwell_sec=0, loiter_sec=5, alert_cooldown_sec=1000)]
    run(z, [det(track_id=1)], st, 100.0)                    # takes the alert slot
    hits = run(z, [det(track_id=1), det(track_id=2)], st, 130.0)
    # Track 1 alerted and may escalate; track 2 never alerted, so it must
    # contribute nothing at all rather than loitering its way to an alarm.
    assert all(h.track_id != 2 for h in hits), types(hits)


# ----------------------------------------------------------------------
# Schedules
# ----------------------------------------------------------------------
def _at(hour):
    return datetime(2026, 9, 1, hour, 0)


def test_a_disarmed_zone_produces_nothing():
    st = {}
    z = [zone(min_dwell_sec=0,
              schedule=[{"start": "18:00", "end": "23:00", "days": list(range(7))}])]
    assert s.evaluate("cam1", [det()], z, st, now=100.0, local_now=_at(12)) == []


def test_arming_does_not_alert_on_somebody_already_standing_there():
    """
    Someone in the area legitimately while it was open must not trigger the
    instant it closes — the visit is forgotten while disarmed.
    """
    st = {}
    z = [zone(min_dwell_sec=0,
              schedule=[{"start": "18:00", "end": "23:00", "days": list(range(7))}])]
    s.evaluate("cam1", [det()], z, st, now=100.0, local_now=_at(12))
    assert st.get("visits", {}).get("z1") in (None, {})


def test_an_armed_schedule_behaves_normally():
    st = {}
    z = [zone(min_dwell_sec=0,
              schedule=[{"start": "18:00", "end": "23:00", "days": list(range(7))}])]
    hits = s.evaluate("cam1", [det()], z, st, now=100.0, local_now=_at(19))
    assert types(hits) == [s.ZONE_ENTRY]


def test_an_inactive_zone_is_skipped_entirely():
    st = {}
    assert run([zone(is_active=False, min_dwell_sec=0)], [det()], st, 100.0) == []


# ----------------------------------------------------------------------
# Eligibility filters
# ----------------------------------------------------------------------
def test_only_the_configured_classes_count():
    st = {}
    z = [zone(min_dwell_sec=0, classes=[2])]                # vehicles only
    assert run(z, [det(class_id=0)], st, 100.0) == []
    assert types(run(z, [det(class_id=2)], st, 101.0)) == [s.ZONE_ENTRY]


def test_low_confidence_detections_are_ignored():
    st = {}
    z = [zone(min_dwell_sec=0, min_confidence=0.6)]
    assert run(z, [det(confidence=0.5)], st, 100.0) == []
    assert types(run(z, [det(confidence=0.7)], st, 101.0)) == [s.ZONE_ENTRY]


def test_boxes_below_the_pixel_floor_are_ignored():
    """A 20px-tall box across a yard is as likely to be a bush as a person."""
    st = {}
    z = [zone(min_dwell_sec=0, min_box_px=100)]
    tiny = [290, 380, 310, 400]                             # 20px tall, feet inside
    assert run(z, [det(bbox=tiny)], st, 100.0) == []
    assert types(run(z, [det()], st, 101.0)) == [s.ZONE_ENTRY]


def test_untracked_detections_are_ignored():
    """Without a track id there is no visit to measure dwell against."""
    st = {}
    assert run([zone(min_dwell_sec=0)], [det(track_id=None)], st, 100.0) == []


# ----------------------------------------------------------------------
# Bounds
# ----------------------------------------------------------------------
def test_visit_tracking_is_bounded():
    """A camera minting fresh track ids must not grow state without limit."""
    st = {}
    z = [zone(min_dwell_sec=0, alert_cooldown_sec=0, exit_grace_sec=10_000)]
    for i in range(s.MAX_TRACKS_PER_ZONE + 50):
        run(z, [det(track_id=i)], st, 100.0 + i * 0.01)
    assert len(st["visits"]["z1"]) <= s.MAX_TRACKS_PER_ZONE


# ----------------------------------------------------------------------
# What the operator is told
# ----------------------------------------------------------------------
def test_hit_descriptions_name_the_zone_and_the_object():
    st = {}
    hit = run([zone(min_dwell_sec=0)], [det()], st, 100.0)[0]
    assert hit.describe() == "Person entered Switchyard"
    assert hit.is_alert is True
    assert hit.zone_name == "Switchyard"
    assert hit.class_name == "person"
    assert hit.severity == "warning"


def test_an_exit_is_recorded_but_is_not_an_alert():
    st = {}
    run([zone(min_dwell_sec=0)], [det()], st, 100.0)
    hit = run([zone(min_dwell_sec=0)], [], st, 110.0)[0]
    assert hit.event_type == s.ZONE_EXIT
    assert hit.is_alert is False
    assert "left Switchyard" in hit.describe()


def test_loitering_description_carries_the_dwell():
    st = {}
    z = [zone(min_dwell_sec=0, loiter_sec=10)]
    run(z, [det()], st, 100.0)
    hit = run(z, [det()], st, 112.0)[0]
    assert "loitering in Switchyard" in hit.describe()
    assert "12s" in hit.describe()


# ----------------------------------------------------------------------
# Overlay drawings
# ----------------------------------------------------------------------
def test_an_armed_zone_is_drawn_solid_with_its_severity_colour():
    out = s.zone_outline_drawings([zone(severity="critical")], _at(12))
    poly = next(d for d in out if d["type"] == "poly")
    assert poly["color"] == s.SEVERITY_BGR["critical"]
    assert poly["opacity"] == 0.30
    assert next(d for d in out if d["type"] == "text")["text"] == "Switchyard"


def test_a_disarmed_zone_is_dimmed_and_labelled_off():
    """A zone that looks the same whether or not it is enforcing is not trusted."""
    z = zone(schedule=[{"start": "18:00", "end": "23:00", "days": list(range(7))}])
    out = s.zone_outline_drawings([z], _at(12))
    poly = next(d for d in out if d["type"] == "poly")
    assert poly["color"] == [150, 150, 150]
    assert poly["opacity"] < 0.30
    assert next(d for d in out if d["type"] == "text")["text"].endswith("(off)")


def test_inactive_zones_are_not_drawn_at_all():
    assert s.zone_outline_drawings([zone(is_active=False)], _at(12)) == []


def test_hit_drawings_label_the_breach():
    st = {}
    hit = run([zone(min_dwell_sec=0)], [det()], st, 100.0)[0]
    out = s.hit_drawings(hit)
    assert next(d for d in out if d["type"] == "text")["text"] == "INTRUDER"
    assert next(d for d in out if d["type"] == "rect")["coords"] == INSIDE
