"""
HTTP surface for restricted zones.

Two endpoints here are not CRUD and matter more than the CRUD does:

  * /api/zones/coverage answers "is this actually monitoring anything" —
    which cameras have the plugin enabled but no zone drawn. Without it the
    only way to find out was to wait for an alert that never came.
  * /api/zones/{id}/test evaluates a point or a box against a zone right now
    and says whether it would alert and why not. That is the commissioning
    step the SOW calls testing, done from a desk instead of by walking into
    the switchyard and hoping.
"""

import csv
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_permissions
from app.plugins.zones import permissions as perms
from app.plugins.zones.adapter import PRIMARY_PLUGIN, owns_camera
from app.plugins.zones.geometry import (
    ANCHORS, MIN_ZONE_AREA, anchor_point, detection_in_zone, sanitize_polygon,
)
from app.plugins.zones.models import RestrictedZone, SEVERITIES, ZONE_EVENT_TYPES
from app.plugins.zones.repository import (
    ZoneRepository, zone_event_log, zone_registry, zone_to_snapshot,
)
from app.plugins.zones.rules import (
    CLASS_NAMES, armed_state, class_label, describe_schedule, is_armed,
    sanitize_classes, sanitize_schedule,
)
from app.plugins.zones.schemas import (
    AckRequest, ZoneCoverage, ZoneCreate, ZoneEventOut, ZoneEventPage, ZoneOut,
    ZoneTestRequest, ZoneTestResult, ZoneUpdate,
)
from database.session import SessionLocal

zones_router = APIRouter(prefix="/api/zones", tags=["Restricted Zones"],
                         dependencies=[Depends(get_current_user)])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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


def _validated_anchor(anchor: Optional[str]) -> str:
    value = (anchor or "FEET").upper()
    if value not in ANCHORS:
        raise HTTPException(422, f"anchor must be one of {', '.join(ANCHORS)}")
    return value


def _validated_severity(severity: Optional[str]) -> str:
    value = (severity or "warning").lower()
    if value not in SEVERITIES:
        raise HTTPException(422, f"severity must be one of {', '.join(SEVERITIES)}")
    return value


def _zone_out(row: RestrictedZone, camera_names: Dict[str, str],
              now: Optional[datetime] = None) -> ZoneOut:
    classes = sanitize_classes(row.object_classes)
    armed, changes_at = armed_state(row.schedule, now)
    other = (None if owns_camera("RestrictionZonePlugin", row.camera_id)
             else PRIMARY_PLUGIN)
    return ZoneOut(
        zone_id=row.zone_id,
        camera_id=row.camera_id,
        camera_name=camera_names.get(row.camera_id),
        name=row.name,
        points=row.points or [],
        is_active=bool(row.is_active),
        object_classes=classes,
        class_names=[class_label(c) for c in classes],
        min_confidence=float(row.min_confidence or 0.0),
        anchor=(row.anchor or "FEET").upper(),
        min_box_px=int(row.min_box_px or 0),
        schedule=row.schedule,
        schedule_text=describe_schedule(row.schedule),
        armed_now=armed,
        armed_changes_at=changes_at,
        min_dwell_sec=float(row.min_dwell_sec or 0.0),
        loiter_sec=float(row.loiter_sec) if row.loiter_sec else None,
        exit_grace_sec=float(row.exit_grace_sec or 0.0),
        alert_cooldown_sec=float(row.alert_cooldown_sec or 0.0),
        severity=row.severity or "warning",
        notes=row.notes,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        evaluated_by=other,
    )


# ---------------------------------------------------------------- metadata
@zones_router.get("/options", dependencies=[require_permissions([perms.ZONES_READ])])
def zone_options():
    """Everything the editor needs to build its form without hardcoding it."""
    return {
        "anchors": list(ANCHORS),
        "severities": list(SEVERITIES),
        "event_types": list(ZONE_EVENT_TYPES),
        "classes": [{"id": k, "name": v} for k, v in sorted(CLASS_NAMES.items())],
        "mux_size": [1280, 720],
        "server_local_time": datetime.now().isoformat(),
        "primary_plugin": PRIMARY_PLUGIN,
    }


@zones_router.get("/coverage", response_model=ZoneCoverage,
                  dependencies=[require_permissions([perms.ZONES_READ])])
def coverage(db: Session = Depends(get_db)):
    """
    Which cameras are actually being monitored.

    A camera with the plugin switched on and no zone drawn is monitoring
    nothing, silently. That was the state of all 62 zone-enabled cameras on
    this appliance, so it is reported rather than left to be discovered.
    """
    from config.config import config

    with_plugin = [
        cam for cam, plugins in (config.CAMERA_PLUGINS or {}).items()
        if any(p in (plugins or []) for p in
               ("IntrusionDetectionPlugin", "RestrictionZonePlugin"))
    ]
    zones = ZoneRepository(db).list_zones(active_only=True)
    by_camera: Dict[str, List[RestrictedZone]] = {}
    for z in zones:
        by_camera.setdefault(z.camera_id, []).append(z)

    legacy = [cam for cam in with_plugin
              if cam not in by_camera and (config.RESTRICTED_ZONES or {}).get(cam)]
    now = datetime.now()
    return ZoneCoverage(
        cameras_with_plugin=len(with_plugin),
        cameras_with_zones=len(by_camera),
        cameras_missing_zones=sorted(c for c in with_plugin
                                     if c not in by_camera and c not in legacy),
        total_zones=len(zones),
        armed_now=sum(1 for z in zones if is_armed(z.schedule, now)),
        legacy_config_cameras=sorted(legacy),
    )


# ------------------------------------------------------------------ events
# Declared before /{zone_id}: FastAPI matches in declaration order, and a
# path parameter route placed first would swallow /events as a zone id.

def _event_out(row, camera_names: Dict[str, str]) -> ZoneEventOut:
    return ZoneEventOut(
        event_id=row.event_id, zone_id=row.zone_id, zone_name=row.zone_name,
        camera_id=row.camera_id,
        camera_name=camera_names.get(row.camera_id) or row.camera_name,
        event_type=row.event_type, severity=row.severity,
        timestamp=row.timestamp, started_at=row.started_at,
        dwell_seconds=row.dwell_seconds, track_id=row.track_id,
        class_id=row.class_id, class_name=row.class_name,
        confidence=row.confidence, bbox=row.bbox,
        snapshot_url=_url(row.snapshot_path),
        acknowledged=bool(row.acknowledged), acknowledged_by=row.acknowledged_by,
        acknowledged_at=row.acknowledged_at, ack_note=row.ack_note,
        details=row.details,
    )


def _event_filters(camera_id, zone_id, event_type, severity, acknowledged,
                   hours, since, until) -> dict:
    if event_type and event_type not in ZONE_EVENT_TYPES:
        raise HTTPException(422, f"event_type must be one of {', '.join(ZONE_EVENT_TYPES)}")
    if severity and severity not in SEVERITIES:
        raise HTTPException(422, f"severity must be one of {', '.join(SEVERITIES)}")
    if since is None and hours:
        since = datetime.utcnow() - timedelta(hours=max(1, min(hours, 24 * 365)))
    return {"camera_id": camera_id, "zone_id": zone_id, "event_type": event_type,
            "severity": severity, "acknowledged": acknowledged,
            "since": since, "until": until}


@zones_router.get("/events", response_model=ZoneEventPage,
                  dependencies=[require_permissions([perms.ZONES_READ])])
def list_events(camera_id: Optional[str] = Query(default=None),
                zone_id: Optional[str] = Query(default=None),
                event_type: Optional[str] = Query(default=None),
                severity: Optional[str] = Query(default=None),
                acknowledged: Optional[bool] = Query(default=None),
                hours: Optional[int] = Query(default=168, ge=1, le=24 * 365),
                since: Optional[datetime] = Query(default=None),
                until: Optional[datetime] = Query(default=None),
                limit: int = Query(default=50, ge=1, le=500),
                offset: int = Query(default=0, ge=0),
                db: Session = Depends(get_db)):
    filters = _event_filters(camera_id, zone_id, event_type, severity,
                             acknowledged, hours, since, until)
    rows, total = ZoneRepository(db).list_events(limit=limit, offset=offset, **filters)
    names = _camera_names(db, [r.camera_id for r in rows])
    return ZoneEventPage(total=total, limit=limit, offset=offset,
                         items=[_event_out(r, names) for r in rows])


@zones_router.get("/events/summary",
                  dependencies=[require_permissions([perms.ZONES_READ])])
def events_summary(days: int = Query(default=7, ge=1, le=365),
                   db: Session = Depends(get_db)):
    return ZoneRepository(db).summary(
        since=datetime.utcnow() - timedelta(days=days))


@zones_router.get("/events/export.csv",
                  dependencies=[require_permissions([perms.ZONES_READ])])
def export_events(camera_id: Optional[str] = Query(default=None),
                  zone_id: Optional[str] = Query(default=None),
                  event_type: Optional[str] = Query(default=None),
                  severity: Optional[str] = Query(default=None),
                  acknowledged: Optional[bool] = Query(default=None),
                  hours: Optional[int] = Query(default=168, ge=1, le=24 * 365),
                  since: Optional[datetime] = Query(default=None),
                  until: Optional[datetime] = Query(default=None),
                  limit: int = Query(default=5000, ge=1, le=50000),
                  db: Session = Depends(get_db)):
    """The zone log as a file, for the incident report the client has to file."""
    filters = _event_filters(camera_id, zone_id, event_type, severity,
                             acknowledged, hours, since, until)
    repo = ZoneRepository(db)
    rows: list = []
    offset = 0
    # Paged rather than one huge query so an export cannot pin the whole log
    # in memory on an 8GB appliance.
    while len(rows) < limit:
        page, _ = repo.list_events(limit=min(500, limit - len(rows)),
                                   offset=offset, **filters)
        if not page:
            break
        rows.extend(page)
        offset += len(page)
        if len(page) < 500:
            break

    names = _camera_names(db, [r.camera_id for r in rows])
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["event_id", "timestamp_utc", "started_at_utc", "camera",
                     "zone", "event_type", "severity", "class", "track_id",
                     "dwell_seconds", "confidence", "acknowledged",
                     "acknowledged_by", "acknowledged_at", "note", "snapshot"])
    for r in rows:
        writer.writerow([
            r.event_id,
            r.timestamp.isoformat() if r.timestamp else "",
            r.started_at.isoformat() if r.started_at else "",
            names.get(r.camera_id) or r.camera_name or r.camera_id or "",
            r.zone_name or "", r.event_type, r.severity or "",
            r.class_name or "", r.track_id or "",
            f"{r.dwell_seconds:.1f}" if r.dwell_seconds is not None else "",
            f"{r.confidence:.3f}" if r.confidence is not None else "",
            "yes" if r.acknowledged else "no",
            r.acknowledged_by or "",
            r.acknowledged_at.isoformat() if r.acknowledged_at else "",
            (r.ack_note or "").replace("\n", " "),
            _url(r.snapshot_path) or "",
        ])
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="zone-events-{stamp}.csv"'})


@zones_router.post("/events/{event_id}/ack", response_model=ZoneEventOut,
                   dependencies=[require_permissions([perms.ZONES_ACK])])
def acknowledge_event(event_id: str, body: AckRequest,
                      db: Session = Depends(get_db),
                      user=Depends(get_current_user)):
    who = getattr(user, "username", None) or getattr(user, "email", None) or "unknown"
    row = ZoneRepository(db).acknowledge(event_id, who, body.note)
    if row is None:
        raise HTTPException(404, "Zone event not found")
    return _event_out(row, _camera_names(db, [row.camera_id]))


@zones_router.get("/health", dependencies=[require_permissions([perms.ZONES_READ])])
def zone_health():
    """Registry freshness and write-queue backlog, for the settings page."""
    zone_registry.refresh()
    return {
        "registry_loaded": zone_registry.loaded,
        "cameras_with_zones": len(zone_registry.by_camera),
        "zones": sum(len(v) for v in zone_registry.by_camera.values()),
        "event_log": zone_event_log.health(),
        "server_local_time": datetime.now().isoformat(),
    }


# ------------------------------------------------------------------- zones
@zones_router.get("", response_model=List[ZoneOut],
                  dependencies=[require_permissions([perms.ZONES_READ])])
def list_zones(camera_id: Optional[str] = Query(default=None),
               active_only: bool = Query(default=False),
               db: Session = Depends(get_db)):
    rows = ZoneRepository(db).list_zones(camera_id=camera_id, active_only=active_only)
    names = _camera_names(db, [r.camera_id for r in rows])
    now = datetime.now()
    return [_zone_out(r, names, now) for r in rows]


@zones_router.post("", response_model=ZoneOut, status_code=201,
                   dependencies=[require_permissions([perms.ZONES_CONFIG])])
def create_zone(body: ZoneCreate, db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    repo = ZoneRepository(db)
    if repo.name_taken(body.camera_id, body.name):
        raise HTTPException(409, f"Camera already has a zone named '{body.name}'.")
    row = repo.create_zone(
        camera_id=body.camera_id,
        name=body.name.strip(),
        points=_validated_geometry(body.points),
        is_active=body.is_active,
        object_classes=sanitize_classes(body.object_classes),
        min_confidence=body.min_confidence,
        anchor=_validated_anchor(body.anchor),
        min_box_px=body.min_box_px,
        schedule=_validated_schedule(body.schedule),
        min_dwell_sec=body.min_dwell_sec,
        loiter_sec=body.loiter_sec,
        exit_grace_sec=body.exit_grace_sec,
        alert_cooldown_sec=body.alert_cooldown_sec,
        severity=_validated_severity(body.severity),
        notes=body.notes,
        created_by=getattr(user, "username", None) or getattr(user, "email", None),
    )
    return _zone_out(row, _camera_names(db, [row.camera_id]))


@zones_router.get("/{zone_id}", response_model=ZoneOut,
                  dependencies=[require_permissions([perms.ZONES_READ])])
def get_zone(zone_id: str, db: Session = Depends(get_db)):
    row = ZoneRepository(db).get_zone(zone_id)
    if row is None:
        raise HTTPException(404, "Zone not found")
    return _zone_out(row, _camera_names(db, [row.camera_id]))


@zones_router.put("/{zone_id}", response_model=ZoneOut,
                  dependencies=[require_permissions([perms.ZONES_CONFIG])])
def update_zone(zone_id: str, body: ZoneUpdate, db: Session = Depends(get_db)):
    repo = ZoneRepository(db)
    row = repo.get_zone(zone_id)
    if row is None:
        raise HTTPException(404, "Zone not found")

    fields = {}
    if body.name is not None:
        if repo.name_taken(row.camera_id, body.name.strip(), exclude_id=zone_id):
            raise HTTPException(409, f"Camera already has a zone named '{body.name}'.")
        fields["name"] = body.name.strip()
    if body.points is not None:
        fields["points"] = _validated_geometry(body.points)
    if body.is_active is not None:
        fields["is_active"] = body.is_active
    if body.object_classes is not None:
        fields["object_classes"] = sanitize_classes(body.object_classes)
    if body.min_confidence is not None:
        fields["min_confidence"] = body.min_confidence
    if body.anchor is not None:
        fields["anchor"] = _validated_anchor(body.anchor)
    if body.min_box_px is not None:
        fields["min_box_px"] = body.min_box_px
    if body.clear_schedule:
        fields["schedule"] = None
    elif body.schedule is not None:
        fields["schedule"] = _validated_schedule(body.schedule)
    if body.min_dwell_sec is not None:
        fields["min_dwell_sec"] = body.min_dwell_sec
    if body.clear_loiter:
        fields["loiter_sec"] = None
    elif body.loiter_sec is not None:
        fields["loiter_sec"] = body.loiter_sec
    if body.exit_grace_sec is not None:
        fields["exit_grace_sec"] = body.exit_grace_sec
    if body.alert_cooldown_sec is not None:
        fields["alert_cooldown_sec"] = body.alert_cooldown_sec
    if body.severity is not None:
        fields["severity"] = _validated_severity(body.severity)
    if body.notes is not None:
        fields["notes"] = body.notes

    row = repo.update_zone(row, **fields)
    return _zone_out(row, _camera_names(db, [row.camera_id]))


@zones_router.delete("/{zone_id}",
                     dependencies=[require_permissions([perms.ZONES_CONFIG])])
def delete_zone(zone_id: str, db: Session = Depends(get_db)):
    if not ZoneRepository(db).delete_zone(zone_id):
        raise HTTPException(404, "Zone not found")
    # The log keeps its rows: the FK nulls out and zone_name preserves what
    # the alert was about, so deleting a zone never erases its history.
    return {"status": "deleted", "zone_id": zone_id}


@zones_router.post("/{zone_id}/test", response_model=ZoneTestResult,
                   dependencies=[require_permissions([perms.ZONES_READ])])
def test_zone(zone_id: str, body: ZoneTestRequest, db: Session = Depends(get_db)):
    """
    Would this position, at this time, raise an alert?

    Answers with a reason rather than a bare boolean, because "no" has four
    different causes — outside the polygon, outside the schedule, zone
    disabled, or the box too small — and each has a different fix.
    """
    row = ZoneRepository(db).get_zone(zone_id)
    if row is None:
        raise HTTPException(404, "Zone not found")
    snapshot = zone_to_snapshot(row)
    if snapshot is None:
        raise HTTPException(409, "This zone's saved geometry is not usable; redraw it.")

    if body.bbox and len(body.bbox) == 4:
        bbox = [float(v) for v in body.bbox]
    elif body.point and len(body.point) == 2:
        x, y = float(body.point[0]), float(body.point[1])
        bbox = [x, y, x, y]
    else:
        raise HTTPException(422, "Provide either bbox [x1,y1,x2,y2] or point [x,y].")

    when = body.at or datetime.now()
    armed = is_armed(snapshot["schedule"], when)
    inside = detection_in_zone(bbox, snapshot["points"], snapshot["anchor"])
    ax, ay = anchor_point(bbox, snapshot["anchor"])
    height = abs(bbox[3] - bbox[1])
    too_small = bool(snapshot["min_box_px"]) and height < snapshot["min_box_px"]

    if not snapshot["is_active"]:
        reason = "Zone is disabled."
    elif not armed:
        reason = f"Zone is not armed at {when:%a %H:%M} ({describe_schedule(snapshot['schedule'])})."
    elif not inside:
        reason = (f"The {snapshot['anchor'].lower()} point ({ax:.0f}, {ay:.0f}) "
                  f"is outside the polygon.")
    elif too_small:
        reason = (f"Box is {height:.0f}px tall, below this zone's minimum of "
                  f"{snapshot['min_box_px']}px.")
    else:
        reason = (f"Inside and armed — alerts after "
                  f"{snapshot['min_dwell_sec']:g}s of dwell.")

    return ZoneTestResult(
        zone_id=row.zone_id, zone_name=row.name,
        inside=inside, armed=armed,
        would_alert=bool(snapshot["is_active"] and armed and inside and not too_small),
        reason=reason,
        anchor=snapshot["anchor"], anchor_point=[round(ax, 1), round(ay, 1)],
        evaluated_at=when, schedule_text=describe_schedule(snapshot["schedule"]),
    )
