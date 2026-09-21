"""
SOW 2.8 — rule configuration.

Sensitivity is the knob the client actually turns during commissioning: a
boiler house wants every wisp reported, a car park with sodium lighting wants
almost nothing. Rather than expose six numbers, the presets bundle them and
these tests pin the ordering that makes them meaningful — a more sensitive
preset must never be harder to trigger than a less sensitive one.

Schedules are shared with restricted zones rather than reimplemented; the
tests here check the wiring and the fire-specific defaults, not the calendar
maths, which zones' own suite already covers.
"""

import pytest

from app.plugins.fire import rules


# ----------------------------------------------------------------------
# sensitivity presets
# ----------------------------------------------------------------------
def test_the_three_presets_exist():
    assert set(rules.SENSITIVITIES) == {"high", "standard", "low"}


def test_default_sensitivity_is_a_real_preset():
    assert rules.DEFAULT_SENSITIVITY in rules.SENSITIVITIES


@pytest.mark.parametrize("name", ["high", "standard", "low"])
def test_every_preset_defines_every_threshold(name):
    p = rules.tuning(name)
    for key in ("min_score", "confirm_sec", "min_frames", "min_area_frac",
                "clear_sec", "alert_cooldown_sec"):
        assert key in p, f"{name} preset is missing {key}"
        assert p[key] is not None


def test_higher_sensitivity_triggers_more_easily():
    """The whole point of the preset ordering."""
    high, std, low = (rules.tuning(n) for n in ("high", "standard", "low"))
    assert high["min_score"] <= std["min_score"] <= low["min_score"]
    assert high["confirm_sec"] <= std["confirm_sec"] <= low["confirm_sec"]
    assert high["min_frames"] <= std["min_frames"] <= low["min_frames"]
    assert high["min_area_frac"] <= std["min_area_frac"] <= low["min_area_frac"]


def test_an_unknown_sensitivity_falls_back_to_the_default():
    assert rules.tuning("paranoid") == rules.tuning(rules.DEFAULT_SENSITIVITY)
    assert rules.tuning(None) == rules.tuning(rules.DEFAULT_SENSITIVITY)


def test_tuning_returns_a_copy_so_a_caller_cannot_poison_the_preset():
    t = rules.tuning("standard")
    t["min_score"] = 99.0
    assert rules.tuning("standard")["min_score"] != 99.0


def test_per_zone_overrides_win_over_the_preset():
    t = rules.tuning("standard", overrides={"confirm_sec": 7.5})
    assert t["confirm_sec"] == 7.5
    assert t["min_score"] == rules.tuning("standard")["min_score"]


def test_null_overrides_are_ignored_rather_than_erasing_the_preset():
    base = rules.tuning("standard")
    t = rules.tuning("standard", overrides={"confirm_sec": None, "min_score": None})
    assert t == base


# ----------------------------------------------------------------------
# what a zone watches for
# ----------------------------------------------------------------------
def test_watch_defaults_to_both_fire_and_smoke():
    assert set(rules.sanitize_kinds(None)) == {"fire", "smoke"}


def test_a_zone_can_watch_for_smoke_only():
    assert rules.sanitize_kinds(["smoke"]) == ["smoke"]


def test_unknown_kinds_are_dropped():
    assert rules.sanitize_kinds(["smoke", "flood", "aliens"]) == ["smoke"]


def test_an_empty_watch_list_falls_back_to_both():
    """A zone that watches for nothing is a zone that cannot ever fire."""
    assert set(rules.sanitize_kinds([])) == {"fire", "smoke"}
    assert set(rules.sanitize_kinds(["flood"])) == {"fire", "smoke"}


def test_kinds_are_normalised_and_deduplicated():
    assert rules.sanitize_kinds(["FIRE", "Fire", " fire "]) == ["fire"]


# ----------------------------------------------------------------------
# severity
# ----------------------------------------------------------------------
def test_fire_severity_defaults_to_critical():
    """Smoke is a warning; open flame is not."""
    assert rules.default_severity("fire") == "critical"


def test_smoke_severity_defaults_to_warning():
    assert rules.default_severity("smoke") == "warning"


def test_unknown_severity_is_rejected_to_a_known_one():
    assert rules.sanitize_severity("catastrophic") in rules.SEVERITIES
    assert rules.sanitize_severity(None) in rules.SEVERITIES
    assert rules.sanitize_severity("critical") == "critical"


# ----------------------------------------------------------------------
# scheduling — shared with restricted zones, wired not reimplemented
# ----------------------------------------------------------------------
def test_a_zone_with_no_schedule_is_always_armed():
    assert rules.is_armed(None) is True


def test_schedule_helpers_are_the_shared_ones():
    from app.plugins.zones import rules as zone_rules
    assert rules.is_armed is zone_rules.is_armed
    assert rules.sanitize_schedule is zone_rules.sanitize_schedule
    assert rules.describe_schedule is zone_rules.describe_schedule


def test_a_bad_schedule_still_raises_for_the_api_to_report():
    with pytest.raises(ValueError):
        rules.sanitize_schedule([{"start": "25:00", "end": "06:00"}])


# ----------------------------------------------------------------------
# the statutory position
# ----------------------------------------------------------------------
def test_the_statutory_notice_is_available_and_says_what_it_must():
    text = rules.STATUTORY_NOTICE.lower()
    assert "not replace" in text or "does not replace" in text
    for word in ("detection", "alarm", "suppression"):
        assert word in text
