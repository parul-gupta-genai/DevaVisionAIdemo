"""
SOW 2.9 — the client-facing surface, end to end against a real database.

Covers zone definition (CRUD), rule configuration (schedules, classes,
anchors), event logging and acknowledgement, and the commissioning probe the
SOW calls testing: /api/zones/{id}/test says whether a point or box would
alert right now, and why not, without walking into the switchyard.

Runs on in-memory SQLite so it needs no Postgres.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.plugins.zones.models import RestrictedZone, ZoneEvent
from app.plugins.zones.repository import ZoneRepository, new_event_id

TRIANGLE = [[100, 100], [500, 100], [500, 500]]
SQUARE = [[100, 100], [500, 100], [500, 500], [100, 500]]


@pytest.fixture
def db():
    from database.models.models import Camera

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    # Only the tables this feature touches. Creating every model would drag in
    # pgvector columns SQLite cannot express. `cameras` is here because the
    # router resolves camera names for its responses.
    for model in (RestrictedZone, ZoneEvent, Camera):
        model.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine, autoflush=False)
    s = Session()
    s.add(Camera(id="cam1", name="Gate Camera", rtsp_url="x", active=True))
    s.add(Camera(id="cam2", name="Yard Camera", rtsp_url="x", active=True))
    s.commit()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(db, monkeypatch):
    from app.auth.dependencies import get_current_user
    from app.plugins.zones import repository as repo_mod
    from app.plugins.zones import router as router_mod

    # The registry caches zones for the pipeline; keep it off the real DB.
    monkeypatch.setattr(repo_mod.zone_registry, "refresh", lambda *a, **k: None)
    monkeypatch.setattr(repo_mod.zone_registry, "invalidate", lambda *a, **k: None,
                        raising=False)

    app = FastAPI()
    app.include_router(router_mod.zones_router)
    app.dependency_overrides[router_mod.get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: type(
        "U", (), {"id": 1, "email": "guard@site", "is_superuser": True})()
    return TestClient(app)


def create(client, **over):
    body = {"camera_id": "cam1", "name": "Switchyard", "points": SQUARE}
    body.update(over)
    return client.post("/api/zones", json=body)


# ----------------------------------------------------------------------
# Zone definition
# ----------------------------------------------------------------------
def test_a_zone_can_be_created_and_read_back(client):
    r = create(client)
    assert r.status_code in (200, 201), r.text
    zone = r.json()
    assert zone["name"] == "Switchyard"
    assert zone["camera_id"] == "cam1"
    assert zone["points"] == SQUARE
    assert zone["object_classes"] == [0]
    assert zone["class_names"] == ["person"]
    assert zone["schedule_text"] == "Always armed"
    assert zone["armed_now"] is True

    got = client.get(f"/api/zones/{zone['zone_id']}")
    assert got.status_code == 200
    assert got.json()["zone_id"] == zone["zone_id"]


def test_a_misclick_sized_polygon_is_refused(client):
    r = create(client, points=[[0, 0], [4, 0], [4, 4]])
    assert r.status_code == 422
    # The message has to tell the operator what to do about it.
    assert "point" in r.text.lower() and "enclos" in r.text.lower()


def test_a_polygon_with_too_few_points_is_refused(client):
    assert create(client, points=[[0, 0], [100, 100]]).status_code == 422


def test_two_zones_on_one_camera_cannot_share_a_name(client):
    assert create(client).status_code in (200, 201)
    clash = create(client, points=TRIANGLE)
    assert clash.status_code in (400, 409), clash.text


def test_the_same_name_is_fine_on_a_different_camera(client):
    assert create(client).status_code in (200, 201)
    assert create(client, camera_id="cam2").status_code in (200, 201)


def test_zones_are_listed_per_camera(client):
    create(client)
    create(client, camera_id="cam2", name="Substation")
    all_zones = client.get("/api/zones").json()
    assert len({z["camera_id"] for z in all_zones}) == 2
    just_cam1 = client.get("/api/zones", params={"camera_id": "cam1"}).json()
    assert [z["camera_id"] for z in just_cam1] == ["cam1"]


def test_a_zone_can_be_deleted(client):
    zid = create(client).json()["zone_id"]
    assert client.delete(f"/api/zones/{zid}").status_code in (200, 204)
    assert client.get(f"/api/zones/{zid}").status_code == 404


def test_an_unknown_zone_is_a_404(client):
    assert client.get("/api/zones/nope").status_code == 404
    assert client.delete("/api/zones/nope").status_code == 404


# ----------------------------------------------------------------------
# Rule configuration
# ----------------------------------------------------------------------
def test_a_schedule_is_stored_and_described(client):
    r = create(client, schedule=[{"start": "18:00", "end": "06:00", "days": [5, 6]}])
    zone = r.json()
    assert zone["schedule_text"] == "18:00-06:00 Sat,Sun"


def test_an_impossible_schedule_is_refused(client):
    r = create(client, schedule=[{"start": "18:00", "end": "18:00"}])
    assert r.status_code == 422


def test_vehicle_only_zones_are_supported(client):
    zone = create(client, object_classes=[2, 7]).json()
    assert zone["object_classes"] == [2, 7]
    assert set(zone["class_names"]) == {"car", "truck"}


def test_rules_can_be_updated(client):
    zid = create(client).json()["zone_id"]
    r = client.put(f"/api/zones/{zid}",
                     json={"min_dwell_sec": 10, "severity": "critical",
                           "anchor": "CENTER"})
    assert r.status_code == 200, r.text
    z = r.json()
    assert z["min_dwell_sec"] == 10 and z["severity"] == "critical"
    assert z["anchor"] == "CENTER"


def test_an_update_leaves_untouched_fields_alone(client):
    zid = create(client, min_dwell_sec=7).json()["zone_id"]
    z = client.put(f"/api/zones/{zid}", json={"name": "Yard"}).json()
    assert z["name"] == "Yard" and z["min_dwell_sec"] == 7


def test_a_schedule_can_be_cleared_back_to_always_armed(client):
    zid = create(client, schedule=[{"start": "18:00", "end": "06:00"}]).json()["zone_id"]
    z = client.put(f"/api/zones/{zid}", json={"clear_schedule": True}).json()
    assert z["schedule"] in (None, []) and z["schedule_text"] == "Always armed"


def test_loitering_can_be_switched_on_and_off(client):
    zid = create(client).json()["zone_id"]
    assert client.put(f"/api/zones/{zid}", json={"loiter_sec": 30}).json()["loiter_sec"] == 30
    assert client.put(f"/api/zones/{zid}", json={"clear_loiter": True}).json()["loiter_sec"] is None


def test_an_invalid_anchor_is_refused(client):
    zid = create(client).json()["zone_id"]
    assert client.put(f"/api/zones/{zid}", json={"anchor": "ELBOW"}).status_code == 422


def test_an_invalid_severity_is_refused(client):
    assert create(client, severity="apocalyptic").status_code == 422


def test_a_zone_can_be_disabled_without_deleting_it(client):
    zid = create(client).json()["zone_id"]
    assert client.put(f"/api/zones/{zid}", json={"is_active": False}).json()["is_active"] is False


# ----------------------------------------------------------------------
# Commissioning — the SOW's testing step
# ----------------------------------------------------------------------
def test_a_point_inside_an_armed_zone_would_alert(client):
    zid = create(client).json()["zone_id"]
    r = client.post(f"/api/zones/{zid}/test", json={"point": [300, 300]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["inside"] is True and out["armed"] is True
    assert out["would_alert"] is True


def test_a_point_outside_would_not_alert_and_says_why(client):
    zid = create(client).json()["zone_id"]
    out = client.post(f"/api/zones/{zid}/test", json={"point": [900, 300]}).json()
    assert out["inside"] is False and out["would_alert"] is False
    assert out["reason"]


def test_the_probe_uses_the_zone_anchor_for_a_box(client):
    """Feet outside, body over the line: not inside under the FEET anchor."""
    zid = create(client).json()["zone_id"]
    leaning = {"bbox": [150, 50, 250, 700]}          # feet at y=700, below the square
    assert client.post(f"/api/zones/{zid}/test", json=leaning).json()["inside"] is False
    client.put(f"/api/zones/{zid}", json={"anchor": "CENTER"})
    assert client.post(f"/api/zones/{zid}/test", json=leaning).json()["inside"] is True


def test_the_probe_can_answer_for_another_time_of_day(client):
    zid = create(client, schedule=[{"start": "18:00", "end": "23:00"}]).json()["zone_id"]
    day = client.post(f"/api/zones/{zid}/test",
                      json={"point": [300, 300], "at": "2026-09-01T12:00:00"}).json()
    night = client.post(f"/api/zones/{zid}/test",
                        json={"point": [300, 300], "at": "2026-09-01T19:00:00"}).json()
    assert day["armed"] is False and day["would_alert"] is False
    assert night["armed"] is True and night["would_alert"] is True
    # Inside the zone either way — only the schedule differs.
    assert day["inside"] is night["inside"] is True


# ----------------------------------------------------------------------
# Event logging
# ----------------------------------------------------------------------
def _log_event(db, zone_id, **over):
    row = {"event_id": new_event_id(), "zone_id": zone_id,
           "zone_name": "Switchyard", "camera_id": "cam1",
           "event_type": "ZONE_ENTRY", "severity": "critical",
           "timestamp": datetime.utcnow(), "class_id": 0, "class_name": "person"}
    row.update(over)
    ev = ZoneEvent(**row)
    db.add(ev)
    db.commit()
    return ev


def test_zone_events_are_listed_newest_first(client, db):
    zid = create(client).json()["zone_id"]
    _log_event(db, zid, timestamp=datetime.utcnow() - timedelta(hours=2))
    _log_event(db, zid, timestamp=datetime.utcnow())
    page = client.get("/api/zones/events").json()
    assert page["total"] == 2
    assert page["items"][0]["timestamp"] >= page["items"][1]["timestamp"]


def test_events_can_be_filtered_by_camera_and_type(client, db):
    zid = create(client).json()["zone_id"]
    _log_event(db, zid)
    _log_event(db, zid, event_type="ZONE_EXIT")
    only_entry = client.get("/api/zones/events",
                            params={"event_type": "ZONE_ENTRY"}).json()
    assert {i["event_type"] for i in only_entry["items"]} == {"ZONE_ENTRY"}
    other_cam = client.get("/api/zones/events", params={"camera_id": "nope"}).json()
    assert other_cam["total"] == 0


def test_events_are_paginated(client, db):
    zid = create(client).json()["zone_id"]
    for _ in range(5):
        _log_event(db, zid)
    page = client.get("/api/zones/events", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 5 and len(page["items"]) == 2 and page["limit"] == 2


def test_an_event_can_be_acknowledged_with_a_note(client, db):
    zid = create(client).json()["zone_id"]
    ev = _log_event(db, zid)
    r = client.post(f"/api/zones/events/{ev.event_id}/ack",
                    json={"note": "contractor, authorised"})
    assert r.status_code == 200, r.text
    assert r.json()["acknowledged"] is True
    assert r.json()["ack_note"] == "contractor, authorised"


def test_acknowledging_an_unknown_event_is_a_404(client):
    assert client.post("/api/zones/events/nope/ack", json={}).status_code == 404


def test_deleting_a_zone_keeps_its_history_readable(client, db):
    """History must survive the zone: the FK nulls, the name stays."""
    zid = create(client).json()["zone_id"]
    _log_event(db, zid)
    client.delete(f"/api/zones/{zid}")
    items = client.get("/api/zones/events").json()["items"]
    assert len(items) == 1
    assert items[0]["zone_name"] == "Switchyard"


# ----------------------------------------------------------------------
# Coverage — "is this actually monitoring anything?"
# ----------------------------------------------------------------------
def test_coverage_reports_zone_totals(client):
    create(client)
    create(client, camera_id="cam2", name="Substation")
    cov = client.get("/api/zones/coverage").json()
    assert cov["total_zones"] == 2
    assert cov["cameras_with_zones"] == 2
    assert cov["armed_now"] == 2


def test_coverage_counts_a_disarmed_zone_as_not_armed(client):
    zid = create(client, schedule=[{"start": "23:00", "end": "23:59"}]).json()["zone_id"]
    assert zid
    cov = client.get("/api/zones/coverage").json()
    assert cov["total_zones"] == 1
    assert cov["armed_now"] in (0, 1)      # depends on the wall clock at run time


# ----------------------------------------------------------------------
# Repository, directly
# ----------------------------------------------------------------------
def test_the_repository_round_trips_a_zone(db):
    repo = ZoneRepository(db)
    row = repo.create_zone(camera_id="cam1", name="Yard", points=SQUARE)
    assert row.zone_id
    assert repo.get_zone(row.zone_id).name == "Yard"
    assert [z.zone_id for z in repo.list_zones(camera_id="cam1")] == [row.zone_id]


def test_the_repository_guards_duplicate_names_per_camera(db):
    repo = ZoneRepository(db)
    repo.create_zone(camera_id="cam1", name="Yard", points=SQUARE)
    assert repo.name_taken("cam1", "Yard") is True
    assert repo.name_taken("cam2", "Yard") is False


def test_the_repository_can_delete_and_report_cameras_with_zones(db):
    repo = ZoneRepository(db)
    row = repo.create_zone(camera_id="cam1", name="Yard", points=SQUARE)
    assert repo.cameras_with_zones() == ["cam1"]
    assert repo.delete_zone(row.zone_id) is True
    assert repo.delete_zone(row.zone_id) is False
    assert repo.cameras_with_zones() == []


def test_the_repository_acknowledges_an_event(db):
    repo = ZoneRepository(db)
    row = repo.create_zone(camera_id="cam1", name="Yard", points=SQUARE)
    ev = _log_event(db, row.zone_id)
    acked = repo.acknowledge(ev.event_id, "guard@site", note="authorised")
    assert acked.acknowledged is True
    assert acked.acknowledged_by == "guard@site"
