"""
SOW 2.9 — Zone definition and rule configuration, at the API boundary.

These are the bounds the client's input is held to before anything reaches
the database. A rule saved out of range is a rule that silently never fires,
so the limits matter as much as the happy path.
"""

import pytest
from pydantic import ValidationError

from app.plugins.zones.geometry import MAX_ZONE_POINTS, MIN_ZONE_POINTS
from app.plugins.zones.schemas import (
    AckRequest, ScheduleWindow, ZoneCreate, ZoneTestRequest, ZoneUpdate,
)

TRIANGLE = [[0, 0], [100, 0], [100, 100]]


def make(**over):
    body = {"camera_id": "cam1", "name": "Switchyard", "points": TRIANGLE}
    body.update(over)
    return ZoneCreate(**body)


# ----------------------------------------------------------------------
# Required fields and defaults
# ----------------------------------------------------------------------
def test_a_zone_needs_a_camera_a_name_and_a_polygon():
    for missing in ("camera_id", "name", "points"):
        body = {"camera_id": "cam1", "name": "Z", "points": TRIANGLE}
        body.pop(missing)
        with pytest.raises(ValidationError):
            ZoneCreate(**body)


def test_the_defaults_are_the_documented_ones():
    z = make()
    assert z.is_active is True
    assert z.object_classes is None          # resolved to [0] downstream
    assert z.min_confidence == 0.4
    assert z.anchor == "FEET"
    assert z.min_box_px == 0
    assert z.schedule is None                # always armed
    assert z.min_dwell_sec == 2.0
    assert z.loiter_sec is None              # escalation off
    assert z.exit_grace_sec == 3.0
    assert z.alert_cooldown_sec == 30.0
    assert z.severity == "warning"


# ----------------------------------------------------------------------
# Polygon bounds
# ----------------------------------------------------------------------
def test_a_polygon_needs_at_least_three_points():
    with pytest.raises(ValidationError):
        make(points=[[0, 0], [10, 10]])
    assert len(make(points=TRIANGLE).points) == MIN_ZONE_POINTS


def test_a_polygon_is_capped():
    with pytest.raises(ValidationError):
        make(points=[[i, i] for i in range(MAX_ZONE_POINTS + 1)])


def test_an_empty_name_is_rejected():
    with pytest.raises(ValidationError):
        make(name="")


def test_an_overlong_name_is_rejected():
    with pytest.raises(ValidationError):
        make(name="x" * 81)


# ----------------------------------------------------------------------
# Rule bounds
# ----------------------------------------------------------------------
@pytest.mark.parametrize("field,bad", [
    ("min_confidence", -0.1), ("min_confidence", 1.1),
    ("min_box_px", -1), ("min_box_px", 721),
    ("min_dwell_sec", -1), ("min_dwell_sec", 3601),
    ("exit_grace_sec", -1), ("exit_grace_sec", 601),
    ("alert_cooldown_sec", -1), ("alert_cooldown_sec", 86401),
    ("loiter_sec", 0.5), ("loiter_sec", 86401),
])
def test_out_of_range_rules_are_rejected(field, bad):
    with pytest.raises(ValidationError):
        make(**{field: bad})


@pytest.mark.parametrize("field,ok", [
    ("min_confidence", 0.0), ("min_confidence", 1.0),
    ("min_box_px", 0), ("min_box_px", 720),
    ("min_dwell_sec", 0.0), ("exit_grace_sec", 0.0),
    ("alert_cooldown_sec", 0.0), ("loiter_sec", 1.0),
])
def test_the_boundary_values_themselves_are_allowed(field, ok):
    assert getattr(make(**{field: ok}), field) == ok


# ----------------------------------------------------------------------
# Schedule windows
# ----------------------------------------------------------------------
def test_a_schedule_window_carries_start_end_and_optional_days():
    w = ScheduleWindow(start="18:00", end="06:00")
    assert (w.start, w.end, w.days) == ("18:00", "06:00", None)
    assert ScheduleWindow(start="18:00", end="06:00", days=[4, 5]).days == [4, 5]


def test_a_zone_can_carry_several_windows():
    z = make(schedule=[{"start": "06:00", "end": "09:00"},
                       {"start": "17:00", "end": "20:00"}])
    assert len(z.schedule) == 2


# ----------------------------------------------------------------------
# Partial update semantics
# ----------------------------------------------------------------------
def test_an_update_may_be_entirely_empty():
    u = ZoneUpdate()
    assert u.model_dump(exclude_unset=True) == {}


def test_clearing_a_schedule_is_an_explicit_flag():
    """
    `schedule: null` in a PATCH body cannot be told apart from an omitted
    field, and 'armed around the clock' must be a deliberate choice.
    """
    u = ZoneUpdate(clear_schedule=True)
    assert u.clear_schedule is True and u.schedule is None
    assert ZoneUpdate().clear_schedule is False


def test_clearing_loitering_is_an_explicit_flag():
    assert ZoneUpdate(clear_loiter=True).clear_loiter is True
    assert ZoneUpdate().clear_loiter is False


def test_an_update_enforces_the_same_bounds_as_a_create():
    with pytest.raises(ValidationError):
        ZoneUpdate(min_confidence=2.0)
    with pytest.raises(ValidationError):
        ZoneUpdate(name="")


def test_only_the_fields_sent_are_marked_set():
    u = ZoneUpdate(name="Yard")
    assert u.model_dump(exclude_unset=True) == {"name": "Yard"}


# ----------------------------------------------------------------------
# Commissioning probe
# ----------------------------------------------------------------------
def test_the_test_probe_accepts_a_box_a_point_or_neither():
    assert ZoneTestRequest(bbox=[0, 0, 10, 10]).bbox == [0, 0, 10, 10]
    assert ZoneTestRequest(point=[5, 5]).point == [5, 5]
    assert ZoneTestRequest().bbox is None and ZoneTestRequest().point is None


def test_the_test_probe_can_ask_about_another_time_of_day():
    from datetime import datetime

    req = ZoneTestRequest(point=[5, 5], at=datetime(2026, 9, 1, 23, 0))
    assert req.at.hour == 23


# ----------------------------------------------------------------------
# Acknowledgement
# ----------------------------------------------------------------------
def test_an_ack_note_is_optional_and_bounded():
    assert AckRequest().note is None
    assert AckRequest(note="checked, contractor").note == "checked, contractor"
    with pytest.raises(ValidationError):
        AckRequest(note="x" * 501)
