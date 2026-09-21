"""
SOW 2.9 — Rule configuration.

The client sets the operating rules: which objects a zone watches and, above
all, *when* it is enforcing. A restricted area is usually only restricted
some of the time, and a schedule that silently never matches is worse than no
schedule at all — hence the validator raising rather than saving.
"""

from datetime import datetime, timedelta

import pytest

from app.plugins.zones import rules as r


# ----------------------------------------------------------------------
# sanitize_schedule
# ----------------------------------------------------------------------
def test_no_schedule_means_always_armed():
    assert r.sanitize_schedule(None) is None
    assert r.sanitize_schedule([]) is None


def test_a_valid_window_is_normalised():
    out = r.sanitize_schedule([{"start": "18:00", "end": "06:00", "days": [4, 5]}])
    assert out == [{"start": "18:00", "end": "06:00", "days": [4, 5]}]


def test_omitted_days_mean_every_day():
    out = r.sanitize_schedule([{"start": "09:00", "end": "17:00"}])
    assert out[0]["days"] == list(range(7))
    out = r.sanitize_schedule([{"start": "09:00", "end": "17:00", "days": []}])
    assert out[0]["days"] == list(range(7))


def test_days_are_deduplicated_and_sorted():
    out = r.sanitize_schedule([{"start": "09:00", "end": "17:00", "days": [5, 1, 1]}])
    assert out[0]["days"] == [1, 5]


@pytest.mark.parametrize("bad", ["18:00", {"start": "18:00"}, 7])
def test_schedule_must_be_a_list_of_windows(bad):
    with pytest.raises(ValueError):
        r.sanitize_schedule(bad)


def test_rejects_more_windows_than_the_cap():
    many = [{"start": "01:00", "end": "02:00"}] * (r.MAX_WINDOWS + 1)
    with pytest.raises(ValueError):
        r.sanitize_schedule(many)


@pytest.mark.parametrize("start,end", [
    ("25:00", "06:00"), ("18:00", "60:99"), ("6pm", "6am"), ("", ""), ("1800", "0600"),
])
def test_rejects_times_that_are_not_24h_hhmm(start, end):
    with pytest.raises(ValueError):
        r.sanitize_schedule([{"start": start, "end": end}])


def test_rejects_a_window_that_starts_and_ends_together():
    """Ambiguous between 'never' and 'always' — the operator must say which."""
    with pytest.raises(ValueError) as exc:
        r.sanitize_schedule([{"start": "18:00", "end": "18:00"}])
    assert "00:00" in str(exc.value)          # the message suggests the fix


@pytest.mark.parametrize("days", [[9], [-1], ["mon"], [True], 3])
def test_rejects_invalid_day_numbers(days):
    with pytest.raises(ValueError):
        r.sanitize_schedule([{"start": "09:00", "end": "17:00", "days": days}])


# ----------------------------------------------------------------------
# is_armed
# ----------------------------------------------------------------------
def test_a_zone_with_no_schedule_is_always_armed():
    assert r.is_armed(None, datetime(2026, 9, 1, 3, 0)) is True
    assert r.is_armed([], datetime(2026, 9, 1, 15, 0)) is True


def test_a_daytime_window_arms_only_inside_itself():
    sched = r.sanitize_schedule([{"start": "09:00", "end": "17:00"}])
    assert r.is_armed(sched, datetime(2026, 9, 1, 12, 0)) is True
    assert r.is_armed(sched, datetime(2026, 9, 1, 8, 59)) is False
    assert r.is_armed(sched, datetime(2026, 9, 1, 17, 0)) is False   # end exclusive
    assert r.is_armed(sched, datetime(2026, 9, 1, 16, 59)) is True


def test_a_window_only_arms_on_its_own_days():
    day = datetime(2026, 9, 1, 12, 0)
    sched = r.sanitize_schedule(
        [{"start": "09:00", "end": "17:00", "days": [day.weekday()]}])
    assert r.is_armed(sched, day) is True
    assert r.is_armed(sched, day + timedelta(days=1)) is False


def test_an_overnight_window_covers_the_early_hours_of_the_next_day():
    """
    'Friday 22:00 to 06:00' must still be armed at 02:00 on Saturday — the
    day filter applies to the day the window opened.
    """
    opens = datetime(2026, 9, 4, 23, 0)
    sched = r.sanitize_schedule(
        [{"start": "22:00", "end": "06:00", "days": [opens.weekday()]}])
    assert r.is_armed(sched, opens) is True
    assert r.is_armed(sched, opens + timedelta(hours=3)) is True     # 02:00 next day
    assert r.is_armed(sched, opens + timedelta(hours=8)) is False    # 07:00, closed
    # The following night is a different weekday, so it must NOT be armed.
    assert r.is_armed(sched, opens + timedelta(days=1)) is False


def test_any_matching_window_arms_the_zone():
    sched = r.sanitize_schedule([
        {"start": "06:00", "end": "09:00"},
        {"start": "17:00", "end": "20:00"},
    ])
    assert r.is_armed(sched, datetime(2026, 9, 1, 7, 0)) is True
    assert r.is_armed(sched, datetime(2026, 9, 1, 18, 0)) is True
    assert r.is_armed(sched, datetime(2026, 9, 1, 12, 0)) is False


# ----------------------------------------------------------------------
# next_transition — the "armed until 06:00" line in the UI
# ----------------------------------------------------------------------
def test_always_armed_never_transitions():
    assert r.next_transition(None) is None


def test_next_transition_finds_the_disarm_moment():
    sched = r.sanitize_schedule([{"start": "09:00", "end": "17:00"}])
    nxt = r.next_transition(sched, datetime(2026, 9, 1, 12, 0))
    assert nxt == datetime(2026, 9, 1, 17, 0)


def test_next_transition_finds_the_arm_moment():
    sched = r.sanitize_schedule([{"start": "09:00", "end": "17:00"}])
    nxt = r.next_transition(sched, datetime(2026, 9, 1, 7, 0))
    assert nxt == datetime(2026, 9, 1, 9, 0)


def test_armed_state_returns_both_answers_together():
    sched = r.sanitize_schedule([{"start": "09:00", "end": "17:00"}])
    armed, nxt = r.armed_state(sched, datetime(2026, 9, 1, 12, 0))
    assert armed is True and nxt == datetime(2026, 9, 1, 17, 0)


# ----------------------------------------------------------------------
# describe_schedule — what the operator reads
# ----------------------------------------------------------------------
def test_describes_an_always_on_zone():
    assert r.describe_schedule(None) == "Always armed"


def test_describes_an_everyday_window():
    sched = r.sanitize_schedule([{"start": "18:00", "end": "06:00"}])
    assert r.describe_schedule(sched) == "18:00-06:00 every day"


def test_describes_named_days():
    sched = r.sanitize_schedule([{"start": "18:00", "end": "06:00", "days": [5, 6]}])
    assert r.describe_schedule(sched) == "18:00-06:00 Sat,Sun"


# ----------------------------------------------------------------------
# sanitize_classes — what the zone watches for
# ----------------------------------------------------------------------
def test_defaults_to_person():
    assert r.sanitize_classes(None) == [0]
    assert r.DEFAULT_CLASSES == [0]


def test_accepts_a_bare_class_id():
    assert r.sanitize_classes(2) == [2]


def test_deduplicates_and_sorts():
    assert r.sanitize_classes([7, 2, 2, 0]) == [0, 2, 7]


def test_drops_classes_the_detector_never_emits():
    """A zone must keep working for the classes that are still valid."""
    assert r.sanitize_classes([0, 999]) == [0]


def test_falls_back_to_person_when_nothing_survives():
    assert r.sanitize_classes([999, 1000]) == [0]
    assert r.sanitize_classes("person") == [0]
    assert r.sanitize_classes([True]) == [0]


def test_class_labels_are_human_readable():
    assert r.class_label(0) == "person"
    assert r.class_label(7) == "truck"
    assert "42" in r.class_label(42)
