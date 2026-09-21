"""
SOW 2.6 — entry/exit event generation, wired end to end.

The pure decision logic is covered in test_gates.py; this is the part that
turns it into events and a populated `direction` column, plus the registry
that feeds it. The registry runs on the analytics thread, so its failure
behaviour matters as much as its happy path.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.plugins.anpr import gates as g
from app.plugins.anpr.events import ANPREventType
from app.plugins.anpr.models import ANPRGate
from app.plugins.anpr.repository import GateRegistry, gate_to_dict
from app.plugins.anpr.tracker import ANPRTracker, TrackedVehicle


# ----------------------------------------------------------------------
# The event vocabulary the rest of the system reads
# ----------------------------------------------------------------------
def test_the_gate_event_types_exist():
    assert ANPREventType.VEHICLE_ENTRY.value == "VEHICLE_ENTRY"
    assert ANPREventType.VEHICLE_EXIT.value == "VEHICLE_EXIT"
    assert ANPREventType.VEHICLE_PASS.value == "VEHICLE_PASS"
    assert ANPREventType.ACCESS_DENIED.value == "ACCESS_DENIED"


def test_the_pure_logic_and_the_enum_agree():
    """A drift here would emit event types nothing downstream recognises."""
    for name in (g.VEHICLE_ENTRY, g.VEHICLE_EXIT, g.VEHICLE_PASS, g.ACCESS_DENIED):
        assert ANPREventType(name).value == name


# ----------------------------------------------------------------------
# Position tracking — what direction inference is built on
# ----------------------------------------------------------------------
def test_a_new_track_has_no_position_yet():
    v = TrackedVehicle(1, 100.0)
    assert v.first_point is None and v.last_point is None


def test_the_first_position_is_kept_and_the_last_one_moves():
    v = TrackedVehicle(1, 100.0)
    v.update(101.0, point=(300, 100))
    v.update(102.0, point=(300, 300))
    v.update(103.0, point=(300, 500))
    assert v.first_point == (300.0, 100.0)
    assert v.last_point == (300.0, 500.0)


def test_updating_without_a_position_still_advances_the_clock():
    """Frames where the plate was read but the box was not passed in."""
    v = TrackedVehicle(1, 100.0)
    v.update(105.0)
    assert v.last_seen == 105.0
    assert v.first_point is None


def test_a_tracked_pass_resolves_to_a_direction():
    v = TrackedVehicle(1, 100.0)
    v.update(101.0, point=(300, 100))
    v.update(102.0, point=(300, 600))
    assert g.resolve_direction(g.BIDIRECTIONAL, v.first_point, v.last_point) == "ENTRY"


def test_the_tracker_still_finalises_normally_with_positions(monkeypatch):
    t = ANPRTracker(track_timeout=1.0)
    v = t.get_or_create_track(7, 100.0, vehicle_type="LMV")
    v.update(100.5, point=(300, 100))
    assert t.cleanup_stale_tracks(100.9) == []
    stale = t.cleanup_stale_tracks(200.0)
    assert [s.track_id for s in stale] == [7]
    assert stale[0].first_point == (300.0, 100.0)


# ----------------------------------------------------------------------
# The registry the analytics thread calls
# ----------------------------------------------------------------------
@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    ANPRGate.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine, autoflush=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()


def add_gate(db, **over):
    row = {"gate_id": "g1", "name": "Main Gate", "camera_id": "cam1",
           "role": "ENTRY", "axis": "VERTICAL", "invert": False,
           "min_travel_px": 40.0, "access_rules": None, "is_active": True}
    row.update(over)
    gate = ANPRGate(**row)
    db.add(gate)
    db.commit()
    return gate


def test_a_gate_row_becomes_a_plain_dict_for_the_pipeline(db):
    d = gate_to_dict(add_gate(db, role="in"))
    assert d["gate_id"] == "g1" and d["name"] == "Main Gate"
    assert d["role"] == "ENTRY"                    # normalised from "in"
    assert d["access_rules"] == {"allow": [], "deny": [], "unlisted": "ALLOW"}
    # An ORM row must never escape onto the analytics thread.
    assert isinstance(d, dict)


def test_access_rules_survive_the_round_trip(db):
    row = add_gate(db, access_rules={"allow": ["employee"], "unlisted": "deny"})
    d = gate_to_dict(row)
    assert d["access_rules"]["allow"] == ["EMPLOYEE"]
    assert d["access_rules"]["unlisted"] == "DENY"


def test_a_rule_saved_before_validation_tightened_does_not_break_the_gate(db):
    """A bad stored rule must degrade to permissive, not raise on the pipeline."""
    row = add_gate(db, access_rules={"unlisted": "sometimes"})
    d = gate_to_dict(row)
    assert d["access_rules"]["unlisted"] == "ALLOW"


def test_the_registry_serves_gates_by_camera(db, monkeypatch):
    add_gate(db)
    add_gate(db, gate_id="g2", name="Works Gate", camera_id="cam2", role="EXIT")
    reg = GateRegistry(ttl_sec=0.0)
    monkeypatch.setattr("database.session.SessionLocal", lambda: db)
    assert reg.for_camera("cam1")["name"] == "Main Gate"
    assert reg.for_camera("cam2")["role"] == "EXIT"


def test_a_camera_with_no_gate_gets_none(db, monkeypatch):
    add_gate(db)
    reg = GateRegistry(ttl_sec=0.0)
    monkeypatch.setattr("database.session.SessionLocal", lambda: db)
    assert reg.for_camera("cam-with-no-gate") is None


def test_an_inactive_gate_is_not_served(db, monkeypatch):
    add_gate(db, is_active=False)
    reg = GateRegistry(ttl_sec=0.0)
    monkeypatch.setattr("database.session.SessionLocal", lambda: db)
    assert reg.for_camera("cam1") is None


def test_the_registry_caches_rather_than_querying_every_call(db, monkeypatch):
    add_gate(db)
    calls = {"n": 0}

    def counted():
        calls["n"] += 1
        return db

    reg = GateRegistry(ttl_sec=300.0)
    monkeypatch.setattr("database.session.SessionLocal", counted)
    for _ in range(50):
        reg.for_camera("cam1")
    assert calls["n"] == 1, f"{calls['n']} queries for 50 lookups"


def test_invalidating_forces_the_next_lookup_to_refetch(db, monkeypatch):
    add_gate(db)
    calls = {"n": 0}

    def counted():
        calls["n"] += 1
        return db

    reg = GateRegistry(ttl_sec=300.0)
    monkeypatch.setattr("database.session.SessionLocal", counted)
    reg.for_camera("cam1")
    reg.invalidate()
    reg.for_camera("cam1")
    assert calls["n"] == 2


def test_a_database_failure_keeps_serving_the_last_snapshot(db, monkeypatch):
    """
    The registry runs on the analytics thread. A blip must degrade ANPR to
    plate logging, never raise into the pipeline.
    """
    add_gate(db)
    reg = GateRegistry(ttl_sec=0.0)
    monkeypatch.setattr("database.session.SessionLocal", lambda: db)
    assert reg.for_camera("cam1") is not None

    def boom():
        raise RuntimeError("database gone")

    monkeypatch.setattr("database.session.SessionLocal", boom)
    assert reg.for_camera("cam1") is not None      # previous snapshot, no raise


def test_a_failure_before_any_successful_load_is_still_survivable(monkeypatch):
    def boom():
        raise RuntimeError("database gone")

    reg = GateRegistry(ttl_sec=0.0)
    monkeypatch.setattr("database.session.SessionLocal", boom)
    assert reg.for_camera("cam1") is None           # no gate, no exception


# ----------------------------------------------------------------------
# The whole pass, decided
# ----------------------------------------------------------------------
def _pass(role, first, last, list_type=None, rules=None, **kw):
    """What the plugin does for one finalised track, in one place."""
    direction = g.resolve_direction(role, first, last, **kw)
    decision, reason = g.decide_access(list_type, g.sanitize_rules(rules))
    return g.event_type_for(direction, decision), direction, reason


def test_an_employee_arriving_at_the_main_gate_is_an_entry():
    ev, direction, _ = _pass("ENTRY", (300, 100), (300, 500),
                             list_type="EMPLOYEE", rules={"allow": ["EMPLOYEE"]})
    assert ev == "VEHICLE_ENTRY" and direction == "ENTRY"


def test_the_same_vehicle_leaving_by_the_exit_gate_is_an_exit():
    ev, direction, _ = _pass("EXIT", (300, 500), (300, 100),
                             list_type="EMPLOYEE", rules={"allow": ["EMPLOYEE"]})
    assert ev == "VEHICLE_EXIT" and direction == "EXIT"


def test_a_stolen_vehicle_is_denied_at_a_gate_with_no_rules_configured():
    ev, direction, reason = _pass("ENTRY", (300, 100), (300, 500),
                                  list_type="STOLEN")
    assert ev == "ACCESS_DENIED"
    assert direction == "ENTRY"                    # still records which way
    assert "blacklist" in reason.lower()


def test_a_contractor_at_the_executive_gate_is_denied():
    ev, _, reason = _pass("ENTRY", (300, 100), (300, 500),
                          list_type="CONTRACTOR", rules={"allow": ["VIP"]})
    assert ev == "ACCESS_DENIED"
    assert "not permitted at this gate" in reason.lower()


def test_an_unknown_vehicle_at_an_open_gate_is_recorded_not_refused():
    ev, _, reason = _pass("ENTRY", (300, 100), (300, 500))
    assert ev == "VEHICLE_ENTRY"
    assert "not on any list" in reason.lower()


def test_an_unknown_vehicle_at_a_closed_gate_is_refused():
    ev, _, _ = _pass("ENTRY", (300, 100), (300, 500), rules={"unlisted": "deny"})
    assert ev == "ACCESS_DENIED"


def test_a_crawling_vehicle_at_a_bidirectional_gate_is_logged_without_a_direction():
    ev, direction, _ = _pass("BIDIRECTIONAL", (300, 300), (300, 305))
    assert ev == "VEHICLE_PASS" and direction is None
