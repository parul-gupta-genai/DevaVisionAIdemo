"""
A blacklisted vehicle must actually reach a person.

The plugin sets metadata["active_alerts"] = ["BLACKLIST_MATCH"] on a hit, with
a comment saying that is "the key the alert engine reads, so a blacklisted
vehicle dispatches SMS/email with no extra wiring". It was not wired: the
alert engine escalates only the event types in its two sets, and
BLACKLIST_MATCH was in neither. So the barred vehicle appeared in the feed and
the plate list, and nobody was told.
"""

from core.alert_engine import AlertEngine


def _engine():
    return AlertEngine()


def test_a_blacklisted_plate_is_escalated():
    e = _engine()
    assert e._is_critical("BLACKLIST_MATCH", ["BLACKLIST_MATCH"], "critical") is True


def test_a_blacklisted_plate_with_no_severity_is_still_escalated():
    """Severity is set by the plugin today, but a missing one must not mute it."""
    e = _engine()
    assert e._is_critical("BLACKLIST_MATCH", ["BLACKLIST_MATCH"], None) is True


def test_a_whitelist_match_is_not_escalated():
    """An authorised vehicle arriving is not a reason to wake anybody."""
    e = _engine()
    assert e._is_critical("WHITELIST_MATCH", ["WHITELIST_MATCH"], "info") is False


def test_a_plain_plate_read_is_not_escalated():
    e = _engine()
    assert e._is_critical("NEW_PLATE", [], None) is False


def test_fire_is_still_escalated():
    """Guard against the fix narrowing something that already worked."""
    e = _engine()
    assert e._is_critical("FIRE_DETECTED", ["FIRE_DETECTED"], None) is True
