"""
SOW 2.7 — the client-facing surface, end to end against a real database.

Covers zone definition, threshold configuration, the incident log, the
commissioning probe that stands in for "demonstrate test events", and the
verify endpoint that keeps an indication from reading as a finding of fact.

Runs on in-memory SQLite so it needs no Postgres.
"""

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.plugins.fight.models import FightEvent, FightZone
from app.plugins.fight.repository import new_event_id

SQUARE = [[100, 100], [900, 100], [900, 600], [100, 600]]


@pytest.fixture
def db():
    from database.models.models import Camera

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    for model in (FightZone, FightEvent, Camera):
        model.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine, autoflush=False)
    s = Session()
    s.add(Camera(id="cam1", name="Loading Bay Camera", rtsp_url="x", active=True))
    s.commit()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(db, monkeypatch):
    from app.auth.dependencies import get_current_user
    from app.plugins.fight import repository as repo_mod
    from app.plugins.fight import router as router_mod

    monkeypatch.setattr(repo_mod.fight_zone_registry, "refresh", lambda *a, **k: None)
    monkeypatch.setattr(repo_mod.fight_zone_registry, "invalidate", lambda *a, **k: None,
                        raising=False)
    app = FastAPI()
    app.include_router(router_mod.fight_router)
    app.dependency_overrides[router_mod.get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: type(
        "U", (), {"id": 1, "email": "guard@site", "is_superuser": True})()
    return TestClient(app)


def create(client, **over):
    body = {"camera_id": "cam1", "name": "Loading Bay", "points": SQUARE}
    body.update(over)
    return client.post("/api/fight/zones", json=body)


# ---------------- zones ----------------
def test_a_zone_can_be_created_and_read_back(client):
    r = create(client)
    assert r.status_code in (200, 201), r.text
    zid = r.json()["zone_id"]
    got = client.get(f"/api/fight/zones/{zid}")
    assert got.status_code == 200
    assert got.json()["name"] == "Loading Bay"
    assert got.json()["camera_name"] == "Loading Bay Camera"


def test_a_zone_reports_its_effective_thresholds(client):
    body = create(client).json()
    assert body["tuning"]["min_score"] > 0
    assert isinstance(body["tuning"]["min_frames"], int)
    assert "confirm over" in body["tuning_text"]


def test_a_per_zone_override_shows_up_in_the_effective_thresholds(client):
    body = create(client, confirm_sec=4.0).json()
    assert body["tuning"]["confirm_sec"] == 4.0
    assert body["overrides"] == {"confirm_sec": 4.0}


def test_overrides_can_be_cleared_back_to_the_preset(client):
    zid = create(client, confirm_sec=4.0).json()["zone_id"]
    r = client.put(f"/api/fight/zones/{zid}", json={"clear_overrides": True})
    assert r.status_code == 200
    assert r.json()["overrides"] == {}


def test_a_duplicate_name_on_one_camera_is_rejected(client):
    create(client)
    assert create(client).status_code == 409


def test_unusable_geometry_is_rejected_with_an_explanation(client):
    r = create(client, points=[[0, 0], [1, 0], [2, 0]])      # collinear
    assert r.status_code == 422
    assert "points" in r.text.lower() or "shape" in r.text.lower()


def test_an_unknown_sensitivity_is_rejected(client):
    assert create(client, sensitivity="paranoid").status_code == 422


def test_an_exclusion_zone_can_be_created(client):
    body = create(client, zone_kind="EXCLUDE", name="Gym").json()
    assert body["zone_kind"] == "EXCLUDE"


def test_a_bad_schedule_is_rejected_with_a_reason(client):
    r = create(client, schedule=[{"start": "25:00", "end": "06:00"}])
    assert r.status_code == 422


def test_deleting_a_zone_keeps_its_incidents(client, db):
    zid = create(client).json()["zone_id"]
    db.add(FightEvent(event_id=new_event_id(), zone_id=zid, zone_name="Loading Bay",
                      camera_id="cam1", event_type="FIGHT_DETECTED",
                      severity="critical", timestamp=datetime.utcnow(), score=0.9))
    db.commit()
    assert client.delete(f"/api/fight/zones/{zid}").status_code == 200
    events = client.get("/api/fight/events").json()["events"]
    assert len(events) == 1
    assert events[0]["zone_name"] == "Loading Bay"


# ---------------- the commissioning probe ----------------
def test_the_probe_says_an_engaged_pair_inside_the_zone_would_alert(client):
    zid = create(client).json()["zone_id"]
    r = client.post(f"/api/fight/zones/{zid}/test", json={
        "boxes": [[400, 320, 460, 480], [480, 320, 540, 480]], "score": 0.9})
    assert r.status_code == 200, r.text
    assert r.json()["would_alert"] is True
    assert "alerts after" in r.json()["reason"]


def test_the_probe_explains_a_pair_that_is_too_far_apart(client):
    zid = create(client).json()["zone_id"]
    r = client.post(f"/api/fight/zones/{zid}/test", json={
        "boxes": [[150, 320, 210, 480], [800, 320, 860, 480]], "score": 0.9})
    assert r.json()["would_alert"] is False
    assert "body heights apart" in r.json()["reason"]


def test_the_probe_explains_a_point_outside_the_zone(client):
    zid = create(client).json()["zone_id"]
    r = client.post(f"/api/fight/zones/{zid}/test", json={"point": [1200, 680]})
    assert r.json()["would_alert"] is False
    assert "outside the polygon" in r.json()["reason"]


def test_the_probe_explains_an_exclusion_zone(client):
    zid = create(client, zone_kind="EXCLUDE", name="Gym").json()["zone_id"]
    r = client.post(f"/api/fight/zones/{zid}/test", json={"point": [400, 400]})
    assert r.json()["would_alert"] is False
    assert "EXCLUDE" in r.json()["reason"]


def test_the_probe_carries_the_advisory_notice(client):
    zid = create(client).json()["zone_id"]
    r = client.post(f"/api/fight/zones/{zid}/test", json={"point": [400, 400]})
    assert "does not replace" in r.json()["advisory_notice"].lower()


# ---------------- events, acknowledgement and verification ----------------
def _event(db, **over):
    fields = dict(event_id=new_event_id(), camera_id="cam1",
                  event_type="FIGHT_DETECTED", severity="critical",
                  timestamp=datetime.utcnow(), score=0.85,
                  track_ids=["1", "2"], details={"description": "Possible fight"})
    fields.update(over)
    row = FightEvent(**fields)
    db.add(row)
    db.commit()
    return row.event_id


def test_events_come_back_unverified_by_default(client, db):
    _event(db)
    body = client.get("/api/fight/events").json()
    assert body["total"] == 1
    assert body["events"][0]["verified"] is None
    assert "does not replace" in body["advisory_notice"].lower()


def test_an_indication_can_be_confirmed_by_a_human(client, db):
    eid = _event(db)
    r = client.post(f"/api/fight/events/{eid}/verify",
                    json={"verdict": "confirmed", "note": "reviewed footage"})
    assert r.status_code == 200
    assert r.json()["verified"] == "confirmed"
    assert r.json()["acknowledged"] is True


def test_an_indication_can_be_dismissed(client, db):
    eid = _event(db)
    r = client.post(f"/api/fight/events/{eid}/verify", json={"verdict": "dismissed"})
    assert r.json()["verified"] == "dismissed"


def test_an_unknown_verdict_is_rejected(client, db):
    eid = _event(db)
    assert client.post(f"/api/fight/events/{eid}/verify",
                       json={"verdict": "probably"}).status_code == 422


def test_events_can_be_filtered_by_human_verdict(client, db):
    a, b = _event(db), _event(db)
    client.post(f"/api/fight/events/{a}/verify", json={"verdict": "dismissed"})
    got = client.get("/api/fight/events?verified=dismissed").json()
    assert got["total"] == 1 and got["events"][0]["event_id"] == a


def test_the_summary_reports_the_human_verdict_split(client, db):
    a = _event(db)
    _event(db)
    client.post(f"/api/fight/events/{a}/verify", json={"verdict": "dismissed"})
    s = client.get("/api/fight/events/summary").json()
    assert s["by_verdict"].get("dismissed") == 1
    assert "does not replace" in s["advisory_notice"].lower()


def test_an_event_can_be_acknowledged(client, db):
    eid = _event(db)
    r = client.post(f"/api/fight/events/{eid}/ack", json={"note": "guard sent"})
    assert r.status_code == 200 and r.json()["acknowledged"] is True
    assert r.json()["acknowledged_by"] == "guard@site"


def test_acknowledging_a_missing_event_is_a_404(client):
    assert client.post("/api/fight/events/nope/ack", json={}).status_code == 404


def test_the_csv_export_records_the_human_verdict(client, db):
    _event(db)
    r = client.get("/api/fight/events/export.csv")
    assert r.status_code == 200
    assert "human_verdict" in r.text
    assert "not reviewed" in r.text
    assert "does not replace" in r.text.lower()


# ---------------- options and coverage ----------------
def test_options_describe_every_preset(client):
    body = client.get("/api/fight/options").json()
    assert set(body["sensitivities"]) == {"high", "standard", "low"}
    assert body["verdicts"] == ["confirmed", "dismissed"]
    assert body["mux_space"] == [1280, 720]


def test_coverage_counts_zones(client):
    create(client)
    create(client, name="Gym", zone_kind="EXCLUDE")
    body = client.get("/api/fight/coverage").json()
    assert body["zones"] == 2
    assert body["detect_zones"] == 1 and body["exclude_zones"] == 1
    assert body["cameras_with_zones"] == 1
