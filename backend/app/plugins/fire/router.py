"""
SOW 2.8 — the client-facing surface for fire and smoke monitoring.

Zone definition, rule configuration, the event log, acknowledgement, and the
commissioning probe the SOW calls testing: /api/fire/zones/{id}/test says
whether a detection at a given place and time would raise an alert, and if
not, which of the several possible reasons applies — without anyone setting
light to anything.

GET /api/fire/events keeps its original response shape. The dashboard reads
res.data.events and each item's id, camera_id, timestamp, fire_boxes and
snapshot_file, so those keys stay exactly as they were and everything richer
is an addition. While the new log is still empty the endpoint falls back to
the old camera_events scrape, so upgrading does not blank the page on the day
it lands.

Every response that reports an incident carries the statutory notice: this is
an AI visual early-warning aid and does not replace statutory fire detection,
alarm or suppression systems.

Route order is load-bearing. Zone routes live under /zones/... precisely so
that a literal path like /events can never be swallowed by a /{zone_id}
parameter route.
"""

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_permissions
from app.plugins.fire import permissions as perms
from app.plugins.fire.models import FIRE_EVENT_TYPES, FireZone, ZONE_KINDS
from app.plugins.fire.repository import (
    OVERRIDE_COLUMNS, FireZoneRepository, fire_event_log, fire_zone_registry,
    zone_to_snapshot,
)
from app.plugins.fire.rules import (
    KINDS, SENSITIVITIES, SEVERITIES, STATUTORY_NOTICE, default_severity,
    describe_schedule, describe_tuning, is_armed, next_transition,
    sanitize_kinds, sanitize_schedule, sanitize_sensitivity, sanitize_severity,
    tuning,
)
from app.plugins.fire.schemas import (
    AckRequest, FireCoverage, FireEventOut, FireTestRequest, FireTestResult,
    FireZoneCreate, FireZoneOut, FireZoneUpdate,
)
from app.plugins.fire.service import DETECT, EXCLUDE
from app.plugins.zones.geometry import MIN_ZONE_AREA, point_in_polygon, sanitize_polygon
from config.config import config
from database.session import SessionLocal

# require_permissions(...) is ALREADY a Security object, not a dependency
# factory — wrapping it in Depends() would silently drop the scope check.
fire_router = APIRouter(prefix="/api/fire", tags=["Fire & Smoke Analytics"],
                        dependencies=[Depends(get_current_user)])

PLUGIN_NAME = "FireDetectionPlugin"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _camera_names(db: Session, camera_ids) -> Dict[str, str]:
    """One query for every name needed, rather than one per row."""
    ids = [c for c in {str(c) for c in camera_ids if c}]
    if not ids:
        return {}
    from database.models.models import Camera

    rows = db.query(Camera.id, Camera.name).filter(Camera.id.in_(ids)).all()
    return {r[0]: r[1] for r in rows}


def _url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return path if str(path).startswith("/") else "/" + str(path)


def _validated_geometry(points) -> list:
    clean = sanitize_polygon(points)
    if clean is None:
        raise HTTPException(
            422,
            f"A zone needs at least 3 distinct points enclosing more than "
            f"{int(MIN_ZONE_AREA)} square pixels in the 1280x720 analytics "
            f"frame. Drag out a shape rather than tapping a line.")
    return clean


def _validated_schedule(schedule):
    if schedule is None:
        return None
    raw = [w.model_dump() if hasattr(w, "model_dump") else dict(w) for w in schedule]
    try:
        return sanitize_schedule(raw)
    except ValueError as exc:
        raise HTTPException(422, f"Schedule is not usable: {exc}")


def _validated_zone_kind(value: Optional[str]) -> str:
    kind = (value or DETECT).upper()
    if kind not in ZONE_KINDS:
        raise HTTPException(422, f"zone_kind must be one of {', '.join(ZONE_KINDS)}")
    return kind


def _validated_watch(value) -> List[str]:
    if value is None:
        return list(KINDS)
    unknown = [str(v) for v in value if str(v).strip().lower() not in KINDS]
    if unknown:
        raise HTTPException(
            422, f"watch may only contain {', '.join(KINDS)}; got {', '.join(unknown)}")
    return sanitize_kinds(value)


def _validated_sensitivity(value: Optional[str]) -> str:
    name = (value or "standard").strip().lower()
    if name not in SENSITIVITIES:
        raise HTTPException(
            422, f"sensitivity must be one of {', '.join(SENSITIVITIES)}")
    return name


def _validated_severity(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if str(value).strip().lower() not in SEVERITIES:
        raise HTTPException(422, f"severity must be one of {', '.join(SEVERITIES)}")
    return sanitize_severity(value)


def _zone_out(row: FireZone, camera_names: Dict[str, str],
              now: Optional[datetime] = None) -> FireZoneOut:
    overrides = {k: getattr(row, k) for k in OVERRIDE_COLUMNS
                 if getattr(row, k, None) is not None}
    watch = sanitize_kinds(row.watch)
    return FireZoneOut(
        zone_id=row.zone_id,
        camera_id=row.camera_id,
        camera_name=camera_names.get(row.camera_id),
        name=row.name,
        points=row.points or [],
        zone_kind=(row.zone_kind or DETECT).upper(),
        is_active=bool(row.is_active),
        watch=watch,
        sensitivity=sanitize_sensitivity(row.sensitivity),
        severity=row.severity,
        effective_severity={k: (row.severity or default_severity(k)) for k in watch},
        tuning=tuning(row.sensitivity, overrides),
        tuning_text=describe_tuning(row.sensitivity, overrides),
        overrides=overrides,
        schedule=row.schedule,
        schedule_text=describe_schedule(row.schedule),
        armed_now=is_armed(row.schedule, now),
        armed_changes_at=next_transition(row.schedule, now),
        notes=row.notes,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event_out(row, camera_names: Dict[str, str]) -> FireEventOut:
    details = row.details or {}
    ts_val = row.timestamp.replace(tzinfo=timezone.utc) if (row.timestamp and row.timestamp.tzinfo is None) else row.timestamp
    st_val = row.started_at.replace(tzinfo=timezone.utc) if (row.started_at and row.started_at.tzinfo is None) else row.started_at
    return FireEventOut(
        event_id=row.event_id,
        camera_id=row.camera_id,
        camera_name=camera_names.get(row.camera_id) or row.camera_name,
        zone_id=row.zone_id,
        zone_name=row.zone_name,
        event_type=row.event_type,
        kind=row.kind,
        severity=row.severity,
        timestamp=ts_val,
        started_at=st_val,
        duration_seconds=row.duration_seconds,
        score=row.score,
        area_frac=row.area_frac,
        bbox=row.bbox,
        snapshot_file=_url(row.snapshot_path),
        acknowledged=bool(row.acknowledged),
        acknowledged_by=row.acknowledged_by,
        acknowledged_at=row.acknowledged_at,
        ack_note=row.ack_note,
        details=details or None,
        description=details.get("description"),
    )


def _legacy_event_rows(db: Session, limit: int) -> List[dict]:
    """
    The pre-2.8 view, scraped out of camera_events.

    Used only while the dedicated log is still empty, so an upgrade does not
    blank the dashboard before the first new incident is recorded.
    """
    from database.models.models import CameraEvent

    rows = (db.query(CameraEvent)
            .filter(CameraEvent.events.op("->")(PLUGIN_NAME) != None)  # noqa: E711
            .order_by(desc(CameraEvent.timestamp)).limit(limit).all())
    out = []
    for e in rows:
        for pe in (e.events or {}).get(PLUGIN_NAME, []):
            if pe.get("event_type") != "FIRE_DETECTED":
                continue
            meta = pe.get("metadata") or {}
            out.append({
                "event_id": f"legacy:{e.id}",
                "id": str(e.id),
                "camera_id": e.camera_id,
                "camera_name": None,
                "zone_id": None, "zone_name": None,
                "event_type": "FIRE_DETECTED", "kind": "fire",
                "severity": "critical",
                "timestamp": e.timestamp.replace(tzinfo=timezone.utc).timestamp() if (e.timestamp and e.timestamp.tzinfo is None) else (e.timestamp.timestamp() if e.timestamp else None),
                "started_at": None, "duration_seconds": None,
                "score": None, "area_frac": None, "bbox": None,
                "fire_boxes": meta.get("fire_boxes", []),
                "snapshot_file": _url(pe.get("snapshot_path")
                                      or meta.get("snapshot_file")),
                "acknowledged": False, "acknowledged_by": None,
                "acknowledged_at": None, "ack_note": None,
                "details": None,
                "description": "Fire detected",
            })
    return out[:limit]


# ----------------------------------------------------------------------
# options, coverage, health
# ----------------------------------------------------------------------
@fire_router.get("/options",
                 dependencies=[require_permissions([perms.FIRE_READ])])
def fire_options():
    """Everything the zone editor needs to render itself."""
    return {
        "kinds": list(KINDS),
        "zone_kinds": list(ZONE_KINDS),
        "sensitivities": {name: tuning(name) for name in SENSITIVITIES},
        "sensitivity_text": {name: describe_tuning(name) for name in SENSITIVITIES},
        "severities": list(SEVERITIES),
        "default_severity": {k: default_severity(k) for k in KINDS},
        "event_types": list(FIRE_EVENT_TYPES),
        "override_keys": list(OVERRIDE_COLUMNS),
        "mux_space": [1280, 720],
        "statutory_notice": STATUTORY_NOTICE,
    }


@fire_router.get("/coverage", response_model=FireCoverage,
                 dependencies=[require_permissions([perms.FIRE_READ])])
def coverage(db: Session = Depends(get_db)):
    """
    Who is watched, and how.

    A camera with the plugin enabled and no zone drawn watches its whole
    frame. That is deliberate for fire — unlike a restricted zone, fire is
    meaningful wherever it appears — and this endpoint is where an operator
    can see it rather than assume it.
    """
    zones = FireZoneRepository(db).list_zones()
    active = [z for z in zones if z.is_active]
    with_zones = {z.camera_id for z in active}
    enabled = [cam for cam, plugins in (config.CAMERA_PLUGINS or {}).items()
               if PLUGIN_NAME in (plugins or [])]
    return FireCoverage(
        cameras_with_zones=len(with_zones),
        zones=len(active),
        detect_zones=len([z for z in active
                          if (z.zone_kind or DETECT).upper() == DETECT]),
        exclude_zones=len([z for z in active
                           if (z.zone_kind or DETECT).upper() == EXCLUDE]),
        cameras_watching_whole_frame=len([c for c in enabled if c not in with_zones]),
        plugin_enabled_cameras=len(enabled),
        statutory_notice=STATUTORY_NOTICE,
    )


@fire_router.get("/health", dependencies=[require_permissions([perms.FIRE_READ])])
def fire_health():
    return {"event_log": fire_event_log.health(),
            "registry_loaded": fire_zone_registry.loaded,
            "cameras_cached": len(fire_zone_registry.by_camera),
            "statutory_notice": STATUTORY_NOTICE}


# ----------------------------------------------------------------------
# events
# ----------------------------------------------------------------------
def _check_event_filters(event_type, kind, severity):
    if event_type and event_type not in FIRE_EVENT_TYPES:
        raise HTTPException(
            422, f"event_type must be one of {', '.join(FIRE_EVENT_TYPES)}")
    if kind and kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(KINDS)}")
    if severity and severity not in SEVERITIES:
        raise HTTPException(422, f"severity must be one of {', '.join(SEVERITIES)}")


@fire_router.get("/events",
                 dependencies=[require_permissions([perms.FIRE_READ])])
def list_events(camera_id: Optional[str] = Query(default=None),
                zone_id: Optional[str] = Query(default=None),
                event_type: Optional[str] = Query(default=None),
                kind: Optional[str] = Query(default=None),
                severity: Optional[str] = Query(default=None),
                acknowledged: Optional[bool] = Query(default=None),
                days: Optional[int] = Query(default=None, ge=1, le=365),
                limit: int = Query(default=50, ge=1, le=500),
                offset: int = Query(default=0, ge=0),
                db: Session = Depends(get_db)):
    """
    The incident log.

    Backwards compatible: `events` is still a list and each item still carries
    `id`, `camera_id`, `timestamp` (epoch seconds), `fire_boxes` and
    `snapshot_file`. Everything else is an addition.
    """
    _check_event_filters(event_type, kind, severity)
    since = datetime.utcnow() - timedelta(days=days) if days else None
    rows, total = FireZoneRepository(db).list_events(
        camera_id=camera_id, zone_id=zone_id, event_type=event_type, kind=kind,
        severity=severity, acknowledged=acknowledged, since=since,
        limit=limit, offset=offset)

    if not rows and total == 0 and offset == 0:
        legacy = _legacy_event_rows(db, limit)
        if legacy:
            return {"total": len(legacy), "limit": limit, "offset": 0,
                    "events": legacy, "source": "legacy",
                    "statutory_notice": STATUTORY_NOTICE}

    names = _camera_names(db, [r.camera_id for r in rows])
    events = []
    for row in rows:
        item = _event_out(row, names).model_dump(mode="json")
        # Legacy keys the dashboard already reads.
        item["id"] = row.event_id
        if row.timestamp:
            ts_dt = row.timestamp.replace(tzinfo=timezone.utc) if row.timestamp.tzinfo is None else row.timestamp
            item["timestamp"] = ts_dt.timestamp()
        else:
            item["timestamp"] = None
        item["fire_boxes"] = [row.bbox] if row.bbox else []
        events.append(item)
    return {"total": total, "limit": limit, "offset": offset, "events": events,
            "source": "fire_events", "statutory_notice": STATUTORY_NOTICE}


@fire_router.get("/events/summary",
                 dependencies=[require_permissions([perms.FIRE_READ])])
def events_summary(days: int = Query(default=7, ge=1, le=365),
                   db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=days)
    return FireZoneRepository(db).summary(since=since)


@fire_router.get("/events/export.csv",
                 dependencies=[require_permissions([perms.FIRE_READ])])
def export_events(camera_id: Optional[str] = Query(default=None),
                  zone_id: Optional[str] = Query(default=None),
                  kind: Optional[str] = Query(default=None),
                  days: int = Query(default=30, ge=1, le=365),
                  db: Session = Depends(get_db)):
    """The incident log as a file, for a safety review or an insurer."""
    _check_event_filters(None, kind, None)
    since = datetime.utcnow() - timedelta(days=days)
    rows, _ = FireZoneRepository(db).list_events(
        camera_id=camera_id, zone_id=zone_id, kind=kind, since=since, limit=500)
    names = _camera_names(db, [r.camera_id for r in rows])

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["event_id", "timestamp", "camera", "zone", "type", "kind",
                     "severity", "duration_sec", "confidence", "acknowledged",
                     "acknowledged_by", "note"])
    for r in rows:
        writer.writerow([
            r.event_id,
            r.timestamp.isoformat() if r.timestamp else "",
            names.get(r.camera_id) or r.camera_name or r.camera_id or "",
            r.zone_name or "(whole frame)",
            r.event_type, r.kind or "", r.severity or "",
            f"{r.duration_seconds:.1f}" if r.duration_seconds is not None else "",
            f"{r.score:.2f}" if r.score is not None else "",
            "yes" if r.acknowledged else "no",
            r.acknowledged_by or "", (r.ack_note or "").replace("\n", " "),
        ])
    writer.writerow([])
    writer.writerow([STATUTORY_NOTICE])
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition":
                 f"attachment; filename=fire-events-{datetime.utcnow():%Y%m%d}.csv"})


@fire_router.post("/events/{event_id}/ack", response_model=FireEventOut,
                  dependencies=[require_permissions([perms.FIRE_ACK])])
def acknowledge_event(event_id: str, body: AckRequest,
                      db: Session = Depends(get_db),
                      user=Depends(get_current_user)):
    who = getattr(user, "email", None) or getattr(user, "username", None)
    row = FireZoneRepository(db).acknowledge(event_id, who, body.note)
    if row is None:
        raise HTTPException(404, "Fire event not found")
    return _event_out(row, _camera_names(db, [row.camera_id]))


# ----------------------------------------------------------------------
# zones
# ----------------------------------------------------------------------
@fire_router.get("/zones", response_model=List[FireZoneOut],
                 dependencies=[require_permissions([perms.FIRE_READ])])
def list_zones(camera_id: Optional[str] = Query(default=None),
               active_only: bool = Query(default=False),
               db: Session = Depends(get_db)):
    rows = FireZoneRepository(db).list_zones(camera_id=camera_id,
                                             active_only=active_only)
    names = _camera_names(db, [r.camera_id for r in rows])
    now = datetime.now()
    return [_zone_out(r, names, now) for r in rows]


@fire_router.post("/zones", response_model=FireZoneOut, status_code=201,
                  dependencies=[require_permissions([perms.FIRE_CONFIG])])
def create_zone(body: FireZoneCreate, db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    repo = FireZoneRepository(db)
    if repo.name_taken(body.camera_id, body.name):
        raise HTTPException(409, f"Camera already has a fire zone named '{body.name}'.")
    row = repo.create_zone(
        camera_id=body.camera_id,
        name=body.name,
        points=_validated_geometry(body.points),
        zone_kind=_validated_zone_kind(body.zone_kind),
        is_active=body.is_active,
        watch=_validated_watch(body.watch),
        sensitivity=_validated_sensitivity(body.sensitivity),
        severity=_validated_severity(body.severity),
        min_score=body.min_score,
        min_frames=body.min_frames,
        confirm_sec=body.confirm_sec,
        min_area_frac=body.min_area_frac,
        clear_sec=body.clear_sec,
        alert_cooldown_sec=body.alert_cooldown_sec,
        schedule=_validated_schedule(body.schedule),
        notes=body.notes,
        created_by=getattr(user, "email", None),
    )
    return _zone_out(row, _camera_names(db, [row.camera_id]))


@fire_router.get("/zones/{zone_id}", response_model=FireZoneOut,
                 dependencies=[require_permissions([perms.FIRE_READ])])
def get_zone(zone_id: str, db: Session = Depends(get_db)):
    row = FireZoneRepository(db).get_zone(zone_id)
    if row is None:
        raise HTTPException(404, "Fire zone not found")
    return _zone_out(row, _camera_names(db, [row.camera_id]))


@fire_router.put("/zones/{zone_id}", response_model=FireZoneOut,
                 dependencies=[require_permissions([perms.FIRE_CONFIG])])
def update_zone(zone_id: str, body: FireZoneUpdate, db: Session = Depends(get_db)):
    repo = FireZoneRepository(db)
    row = repo.get_zone(zone_id)
    if row is None:
        raise HTTPException(404, "Fire zone not found")

    fields: Dict[str, Any] = {}
    if body.name is not None:
        if repo.name_taken(row.camera_id, body.name, exclude_id=zone_id):
            raise HTTPException(
                409, f"Camera already has a fire zone named '{body.name}'.")
        fields["name"] = body.name
    if body.points is not None:
        fields["points"] = _validated_geometry(body.points)
    if body.zone_kind is not None:
        fields["zone_kind"] = _validated_zone_kind(body.zone_kind)
    if body.is_active is not None:
        fields["is_active"] = body.is_active
    if body.watch is not None:
        fields["watch"] = _validated_watch(body.watch)
    if body.sensitivity is not None:
        fields["sensitivity"] = _validated_sensitivity(body.sensitivity)
    if body.severity is not None:
        fields["severity"] = _validated_severity(body.severity)
    if body.clear_schedule:
        fields["schedule"] = None
    elif body.schedule is not None:
        fields["schedule"] = _validated_schedule(body.schedule)
    if body.clear_overrides:
        for key in OVERRIDE_COLUMNS:
            fields[key] = None
    else:
        for key in OVERRIDE_COLUMNS:
            value = getattr(body, key, None)
            if value is not None:
                fields[key] = value
    if body.notes is not None:
        fields["notes"] = body.notes

    row = repo.update_zone(row, **fields)
    return _zone_out(row, _camera_names(db, [row.camera_id]))


@fire_router.delete("/zones/{zone_id}",
                    dependencies=[require_permissions([perms.FIRE_CONFIG])])
def delete_zone(zone_id: str, db: Session = Depends(get_db)):
    if not FireZoneRepository(db).delete_zone(zone_id):
        raise HTTPException(404, "Fire zone not found")
    # The log keeps its rows: the FK nulls out and zone_name preserves what the
    # alert was about, so deleting a zone never erases its history.
    return {"status": "deleted", "zone_id": zone_id}


@fire_router.post("/zones/{zone_id}/test", response_model=FireTestResult,
                  dependencies=[require_permissions([perms.FIRE_READ])])
def test_zone(zone_id: str, body: FireTestRequest, db: Session = Depends(get_db)):
    """
    Would a detection here, at this time, raise an alert?

    Answers with a reason rather than a bare boolean, because "no" has several
    causes — the zone is an exclusion, disabled, out of schedule, does not
    watch that kind, the region is too small, or the score too low — and each
    has a different fix. This is how the module is commissioned without
    setting anything alight.
    """
    row = FireZoneRepository(db).get_zone(zone_id)
    if row is None:
        raise HTTPException(404, "Fire zone not found")
    snapshot = zone_to_snapshot(row)
    if snapshot is None:
        raise HTTPException(409, "This zone's saved geometry is not usable; redraw it.")

    kind = str(body.kind or "fire").strip().lower()
    if kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(KINDS)}")

    if body.bbox and len(body.bbox) == 4:
        bbox = [float(v) for v in body.bbox]
    elif body.point and len(body.point) == 2:
        x, y = float(body.point[0]), float(body.point[1])
        bbox = [x, y, x, y]
    else:
        raise HTTPException(422, "Provide either bbox [x1,y1,x2,y2] or point [x,y].")

    when = body.at or datetime.now()
    tune = tuning(snapshot["sensitivity"], snapshot["overrides"])
    armed = is_armed(snapshot["schedule"], when)
    cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
    # point_in_polygon takes scalars first, polygon last.
    inside = point_in_polygon(cx, cy, snapshot["points"])
    excluded = snapshot["zone_kind"] == EXCLUDE
    watched = kind in snapshot["watch"]
    area_frac = body.area_frac
    if area_frac is None:
        area_frac = (abs(bbox[2] - bbox[0]) * abs(bbox[3] - bbox[1])) / (1280.0 * 720.0)
    big_enough = area_frac >= tune["min_area_frac"]
    strong_enough = body.score >= tune["min_score"]

    if excluded:
        reason = ("This is an EXCLUDE zone: detections inside it are "
                  "deliberately silenced.")
    elif not snapshot["is_active"]:
        reason = "Zone is disabled."
    elif not watched:
        reason = (f"This zone watches for {', '.join(snapshot['watch'])}, "
                  f"not {kind}.")
    elif not armed:
        reason = (f"Zone is not armed at {when:%a %H:%M} "
                  f"({describe_schedule(snapshot['schedule'])}).")
    elif not inside:
        reason = f"The centre ({cx:.0f}, {cy:.0f}) is outside the polygon."
    elif not big_enough:
        reason = (f"Region covers {area_frac:.2%} of the frame, below this "
                  f"zone's minimum of {tune['min_area_frac']:.2%}.")
    elif not strong_enough:
        reason = (f"Confidence {body.score:.0%} is below this zone's minimum "
                  f"of {tune['min_score']:.0%}.")
    else:
        reason = (f"Inside and armed — alerts after {tune['confirm_sec']:g}s "
                  f"and {int(tune['min_frames'])} sightings of evidence.")

    would = bool(not excluded and snapshot["is_active"] and watched and armed
                 and inside and big_enough and strong_enough)
    return FireTestResult(
        zone_id=row.zone_id, zone_name=row.name, kind=kind,
        inside=inside, armed=armed, would_alert=would, reason=reason,
        confirm_after=(f"{tune['confirm_sec']:g}s / "
                       f"{int(tune['min_frames'])} sightings"),
        evaluated_at=when,
        schedule_text=describe_schedule(snapshot["schedule"]),
        statutory_notice=STATUTORY_NOTICE,
    )
