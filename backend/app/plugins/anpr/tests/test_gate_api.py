"""
SOW 2.6 — configuring gates and calibrating them, over HTTP.

Includes /anpr/gates/{id}/test, the commissioning step: it answers what the
gate would do with a given vehicle right now, using exactly the code the
pipeline uses, so a site can be calibrated from a desk rather than by driving
a vehicle at the barrier.

Runs on in-memory SQLite; no Postgres needed.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.plugins.anpr.models import ANPRGate, ANPRWatchlist


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    for model in (ANPRGate, ANPRWatchlist):
        model.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine, autoflush=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(db, monkeypatch):
    from app.auth.dependencies import get_current_user
    from app.plugins.anpr import router as router_mod
    from database.session import get_db

    monkeypatch.setattr(router_mod.gate_registry, "invalidate", lambda: None)

    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: type(
        "U", (), {"id": 1, "email": "guard@site", "is_superuser": True})()
    return TestClient(app)


def create(client, **over):
    body = {"name": "Main Gate", "camera_id": "cam1", "role": "ENTRY"}
    body.update(over)
    return client.post("/anpr/gates", json=body)


# ----------------------------------------------------------------------
# Gate-wise setup
# ----------------------------------------------------------------------
def test_a_gate_can_be_designated_on_a_camera(client):
    r = create(client)
    assert r.status_code == 201, r.text
    gate = r.json()
    assert gate["name"] == "Main Gate"
    assert gate["camera_id"] == "cam1"
    assert gate["role"] == "ENTRY"
    assert gate["access_rules"] == {"allow": [], "deny": [], "unlisted": "ALLOW"}
    assert "any list" in gate["rules_text"]


def test_a_role_is_normalised_from_what_the_operator_typed(client):
    assert create(client, role="in").json()["role"] == "ENTRY"


def test_a_camera_can_only_have_one_active_gate(client):
    """Two would make the direction of a pass ambiguous."""
    assert create(client).status_code == 201
    clash = create(client, name="Second Gate")
    assert clash.status_code == 409, clash.text


def test_a_second_gate_is_fine_on_another_camera(client):
    assert create(client).status_code == 201
    assert create(client, camera_id="cam2", name="Works Gate",
                  role="EXIT").status_code == 201


def test_gates_are_listed_and_filterable_by_camera(client):
    create(client)
    create(client, camera_id="cam2", name="Works Gate", role="EXIT")
    assert len(client.get("/anpr/gates").json()) == 2
    only = client.get("/anpr/gates", params={"camera_id": "cam2"}).json()
    assert [g["name"] for g in only] == ["Works Gate"]


def test_a_gate_can_be_read_updated_and_deleted(client):
    gid = create(client).json()["gate_id"]
    assert client.get(f"/anpr/gates/{gid}").status_code == 200
    upd = client.put(f"/anpr/gates/{gid}", json={"role": "EXIT", "name": "Back Gate"})
    assert upd.status_code == 200 and upd.json()["role"] == "EXIT"
    assert client.delete(f"/anpr/gates/{gid}").status_code == 200
    assert client.get(f"/anpr/gates/{gid}").status_code == 404


def test_unknown_gates_are_404(client):
    assert client.get("/anpr/gates/nope").status_code == 404
    assert client.put("/anpr/gates/nope", json={"name": "x"}).status_code == 404
    assert client.delete("/anpr/gates/nope").status_code == 404


def test_the_options_endpoint_tells_the_ui_what_it_may_offer(client):
    opts = client.get("/anpr/gates/options").json()
    assert set(opts["roles"]) == {"ENTRY", "EXIT", "BIDIRECTIONAL"}
    assert set(opts["unlisted_policies"]) == {"ALLOW", "DENY"}
    assert "EMPLOYEE" in opts["whitelist_types"]
    assert "BLACKLIST" in opts["blacklist_types"]


def test_an_invalid_axis_is_refused(client):
    assert create(client, axis="DIAGONAL").status_code == 422


# ----------------------------------------------------------------------
# Access rules — what the client supplies
# ----------------------------------------------------------------------
def test_access_rules_are_stored_normalised(client):
    gate = create(client, access_rules={"allow": ["employee", "vip"],
                                        "unlisted": "deny"}).json()
    assert gate["access_rules"]["allow"] == ["EMPLOYEE", "VIP"]
    assert gate["access_rules"]["unlisted"] == "DENY"
    assert "denied" in gate["rules_text"]


def test_malformed_access_rules_are_refused(client):
    assert create(client, access_rules={"unlisted": "maybe"}).status_code == 422
    assert create(client, access_rules={"allow": "employee "}).status_code == 201


def test_rules_can_be_replaced_later(client):
    gid = create(client).json()["gate_id"]
    out = client.put(f"/anpr/gates/{gid}",
                     json={"access_rules": {"deny": ["CONTRACTOR"]}}).json()
    assert out["access_rules"]["deny"] == ["CONTRACTOR"]


# ----------------------------------------------------------------------
# Commissioning / calibration
# ----------------------------------------------------------------------
def test_the_probe_reports_direction_decision_and_reason(client):
    gid = create(client).json()["gate_id"]
    out = client.post(f"/anpr/gates/{gid}/test",
                      json={"plate_number": "UP16B3895"}).json()
    assert out["direction"] == "ENTRY"          # designated gate
    assert out["access"] == "ALLOW"
    assert out["event_type"] == "VEHICLE_ENTRY"
    assert "not on any list" in out["reason"].lower()


def test_the_probe_can_try_a_list_type_before_the_vehicle_is_listed(client):
    gid = create(client, access_rules={"allow": ["VIP"]}).json()["gate_id"]
    out = client.post(f"/anpr/gates/{gid}/test",
                      json={"list_type": "CONTRACTOR"}).json()
    assert out["access"] == "DENY"
    assert out["event_type"] == "ACCESS_DENIED"
    assert "not permitted at this gate" in out["reason"].lower()


def test_the_probe_looks_the_plate_up_on_the_watchlist(client, monkeypatch):
    """
    The probe must resolve a bare plate through the live watchlist, so
    commissioning reflects the lists the client actually loaded. The
    watchlist's own database loading is its concern, not this endpoint's.
    """
    from app.plugins.anpr import router as router_mod

    seen = {}

    def fake_match(plate):
        seen["plate"] = plate
        return {"id": "w1", "plate_number": "UP16B3895",
                "list_type": "BLACKLIST", "reason": "stolen",
                "priority": 1}, "exact"

    monkeypatch.setattr(router_mod.plate_watchlist, "match", fake_match)

    gid = create(client).json()["gate_id"]
    out = client.post(f"/anpr/gates/{gid}/test",
                      json={"plate_number": "UP16B3895"}).json()
    assert seen["plate"] == "UP16B3895"
    assert out["list_type"] == "BLACKLIST"
    assert out["access"] == "DENY"
    assert out["event_type"] == "ACCESS_DENIED"


def test_an_explicit_list_type_skips_the_watchlist_lookup(client, monkeypatch):
    from app.plugins.anpr import router as router_mod

    def boom(plate):
        raise AssertionError("watchlist must not be consulted")

    monkeypatch.setattr(router_mod.plate_watchlist, "match", boom)
    gid = create(client).json()["gate_id"]
    out = client.post(f"/anpr/gates/{gid}/test",
                      json={"plate_number": "UP16B3895",
                            "list_type": "EMPLOYEE"}).json()
    assert out["list_type"] == "EMPLOYEE"


def test_the_probe_infers_direction_for_a_bidirectional_gate(client):
    gid = create(client, role="BIDIRECTIONAL").json()["gate_id"]
    arriving = client.post(f"/anpr/gates/{gid}/test",
                           json={"first_point": [300, 100],
                                 "last_point": [300, 600]}).json()
    leaving = client.post(f"/anpr/gates/{gid}/test",
                          json={"first_point": [300, 600],
                                "last_point": [300, 100]}).json()
    assert arriving["direction"] == "ENTRY"
    assert leaving["direction"] == "EXIT"


def test_the_probe_admits_when_it_cannot_tell_the_direction(client):
    gid = create(client, role="BIDIRECTIONAL").json()["gate_id"]
    out = client.post(f"/anpr/gates/{gid}/test",
                      json={"first_point": [300, 300],
                            "last_point": [300, 305]}).json()
    assert out["direction"] is None
    assert out["event_type"] == "VEHICLE_PASS"     # still a recorded pass


def test_probing_an_unknown_gate_is_a_404(client):
    assert client.post("/anpr/gates/nope/test", json={}).status_code == 404
