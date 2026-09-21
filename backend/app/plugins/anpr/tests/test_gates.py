"""
SOW 2.6 — gate-wise ANPR setup, and the entry/exit decision.

The client designates gates and supplies the access rules; this is the pure
logic that turns "plate X was recognised at gate Y" into a direction and an
allow/deny, with a reason a guard can read off a screen.

Kept dependency-free so it can be exercised without a pipeline or a database,
and so the API validator and the plugin can never disagree about what a rule
means.
"""

import pytest

from app.plugins.anpr import gates as g


# ----------------------------------------------------------------------
# Gate roles
# ----------------------------------------------------------------------
def test_the_three_roles_a_gate_can_have():
    assert g.ENTRY == "ENTRY"
    assert g.EXIT == "EXIT"
    assert g.BIDIRECTIONAL == "BIDIRECTIONAL"
    assert set(g.ROLES) == {"ENTRY", "EXIT", "BIDIRECTIONAL"}


@pytest.mark.parametrize("raw,expected", [
    ("entry", "ENTRY"), ("  Exit ", "EXIT"), ("BIDIRECTIONAL", "BIDIRECTIONAL"),
    ("in", "ENTRY"), ("out", "EXIT"), ("both", "BIDIRECTIONAL"),
])
def test_roles_are_normalised_from_what_operators_type(raw, expected):
    assert g.normalise_role(raw) == expected


@pytest.mark.parametrize("bad", [None, "", "sideways", 7])
def test_an_unknown_role_defaults_to_bidirectional(bad):
    """The safe reading: record the pass, do not invent a direction."""
    assert g.normalise_role(bad) == g.BIDIRECTIONAL


# ----------------------------------------------------------------------
# Direction — a designated gate answers it by definition
# ----------------------------------------------------------------------
def test_a_designated_entry_gate_always_reports_entry():
    assert g.resolve_direction(g.ENTRY, None, None) == "ENTRY"


def test_a_designated_exit_gate_always_reports_exit():
    assert g.resolve_direction(g.EXIT, None, None) == "EXIT"


def test_a_designated_gate_ignores_vehicle_motion():
    """Most sites designate the gate; motion must not override the label."""
    assert g.resolve_direction(g.ENTRY, (100, 500), (100, 100)) == "ENTRY"


# ----------------------------------------------------------------------
# Direction — a bidirectional gate infers it from vehicle motion
# ----------------------------------------------------------------------
def test_a_bidirectional_gate_reads_approach_as_entry():
    """Moving down the frame (towards the camera) is arriving."""
    assert g.resolve_direction(g.BIDIRECTIONAL, (300, 100), (300, 500)) == "ENTRY"


def test_a_bidirectional_gate_reads_recession_as_exit():
    assert g.resolve_direction(g.BIDIRECTIONAL, (300, 500), (300, 100)) == "EXIT"


def test_a_bidirectional_gate_can_be_inverted_for_a_camera_facing_the_other_way():
    assert g.resolve_direction(g.BIDIRECTIONAL, (300, 100), (300, 500),
                               invert=True) == "EXIT"


def test_a_horizontal_gate_uses_the_x_axis():
    assert g.resolve_direction(g.BIDIRECTIONAL, (100, 300), (500, 300),
                               axis="HORIZONTAL") == "ENTRY"
    assert g.resolve_direction(g.BIDIRECTIONAL, (500, 300), (100, 300),
                               axis="HORIZONTAL") == "EXIT"


def test_a_vehicle_that_barely_moved_has_no_direction():
    """
    A parked or crawling vehicle must not be recorded as entering: an
    unknown direction is honest, a guessed one corrupts the gate log.
    """
    assert g.resolve_direction(g.BIDIRECTIONAL, (300, 300), (300, 302)) is None


def test_a_bidirectional_gate_without_positions_has_no_direction():
    assert g.resolve_direction(g.BIDIRECTIONAL, None, None) is None
    assert g.resolve_direction(g.BIDIRECTIONAL, (300, 100), None) is None


def test_the_movement_threshold_is_configurable():
    assert g.resolve_direction(g.BIDIRECTIONAL, (300, 300), (300, 340),
                               min_travel_px=100) is None
    assert g.resolve_direction(g.BIDIRECTIONAL, (300, 300), (300, 340),
                               min_travel_px=10) == "ENTRY"


# ----------------------------------------------------------------------
# Access rules — what the client supplies per gate
# ----------------------------------------------------------------------
def test_rules_default_to_recording_everything_and_denying_nobody():
    """
    A gate with no rules yet must not start refusing vehicles; ANPR is a
    logging feature until the client says otherwise.
    """
    rules = g.sanitize_rules(None)
    assert rules["allow"] == []
    assert rules["deny"] == []
    assert rules["unlisted"] == g.ALLOW


def test_list_types_are_normalised_and_deduplicated():
    rules = g.sanitize_rules({"allow": ["employee", " VIP ", "EMPLOYEE"]})
    assert rules["allow"] == ["EMPLOYEE", "VIP"]


def test_an_unlisted_policy_of_deny_is_honoured():
    assert g.sanitize_rules({"unlisted": "deny"})["unlisted"] == g.DENY


def test_an_unknown_unlisted_policy_is_rejected():
    with pytest.raises(ValueError):
        g.sanitize_rules({"unlisted": "maybe"})


def test_rules_must_be_an_object():
    with pytest.raises(ValueError):
        g.sanitize_rules(["allow"])


# ----------------------------------------------------------------------
# The access decision
# ----------------------------------------------------------------------
def decide(list_type, **rules):
    return g.decide_access(list_type, g.sanitize_rules(rules or None))


def test_a_blacklisted_plate_is_denied_even_with_no_rules_configured():
    """Blacklisting is the one rule that must never need opting in to."""
    decision, reason = decide("BLACKLIST")
    assert decision == g.DENY
    assert "blacklist" in reason.lower()


def test_every_blacklist_family_denies():
    for t in ("BLACKLIST", "STOLEN", "STOLEN VEHICLE", "EXPIRED ACCESS", "POLICE"):
        assert decide(t)[0] == g.DENY, t


def test_an_unlisted_vehicle_is_allowed_by_default_and_says_so():
    decision, reason = decide(None)
    assert decision == g.ALLOW
    assert "not on any list" in reason.lower()


def test_an_unlisted_vehicle_is_denied_at_a_closed_gate():
    decision, reason = decide(None, unlisted="deny")
    assert decision == g.DENY
    assert "not on any list" in reason.lower()


def test_a_permitted_list_type_is_allowed_and_names_the_list():
    decision, reason = decide("EMPLOYEE", allow=["EMPLOYEE", "VIP"])
    assert decision == g.ALLOW
    assert "EMPLOYEE" in reason


def test_a_list_type_outside_the_allow_list_is_denied_at_that_gate():
    """A contractor pass is valid at the works gate, not the executive one."""
    decision, reason = decide("CONTRACTOR", allow=["EMPLOYEE", "VIP"])
    assert decision == g.DENY
    assert "not permitted at this gate" in reason.lower()


def test_an_explicit_deny_beats_an_allow():
    decision, reason = decide("CONTRACTOR", allow=["CONTRACTOR"], deny=["CONTRACTOR"])
    assert decision == g.DENY


def test_an_empty_allow_list_permits_every_non_blacklisted_type():
    """No allow-list means 'no restriction', not 'permit nothing'."""
    assert decide("CONTRACTOR")[0] == g.ALLOW
    assert decide("VISITOR")[0] == g.ALLOW


def test_the_decision_is_case_insensitive_about_list_types():
    assert decide("employee", allow=["EMPLOYEE"])[0] == g.ALLOW
    assert decide("BlackList")[0] == g.DENY


# ----------------------------------------------------------------------
# The event a pass produces
# ----------------------------------------------------------------------
def test_an_allowed_entry_produces_a_vehicle_entry_event():
    assert g.event_type_for("ENTRY", g.ALLOW) == "VEHICLE_ENTRY"


def test_an_allowed_exit_produces_a_vehicle_exit_event():
    assert g.event_type_for("EXIT", g.ALLOW) == "VEHICLE_EXIT"


def test_a_denial_produces_an_access_denied_event_whichever_way_it_was_going():
    assert g.event_type_for("ENTRY", g.DENY) == "ACCESS_DENIED"
    assert g.event_type_for("EXIT", g.DENY) == "ACCESS_DENIED"
    assert g.event_type_for(None, g.DENY) == "ACCESS_DENIED"


def test_an_allowed_pass_with_no_known_direction_is_still_recorded():
    """A bidirectional gate that could not infer direction must still log."""
    assert g.event_type_for(None, g.ALLOW) == "VEHICLE_PASS"
