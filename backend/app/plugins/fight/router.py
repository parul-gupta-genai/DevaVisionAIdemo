"""
SOW 2.7 — the client-facing surface for fight/quarrel analytics.

Zone definition, threshold tuning, the incident log, acknowledgement, the
commissioning probe, and one thing the other analytics modules do not have: a
VERIFY endpoint.

That endpoint exists because of what the SOW requires the Contractor to
communicate. This is an automated visual analytics aid, not a finding of
fact. Without a way to record "reviewed, and it was horseplay", the incident
log reads as a list of confirmed assaults — which is both wrong and, given it
names people by track and stores footage, the kind of wrong that matters. So
every indication can be marked confirmed or dismissed by a human, and the
summary reports the split.

Route order: zone routes live under /zones/... so a literal path like /events
can never be swallowed by a /{zone_id} parameter route.
"""

import csv
import io
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_permissions
from app.plugins.fight import permissions as perms
from app.plugins.fight.dynamics import separation
from app.plugins.fight.models import FIGHT_EVENT_TYPES, FightZone, ZONE_KINDS
from app.plugins.fight.repository import (
    OVERRIDE_COLUMNS, FightZoneRepository, fight_event_log, fight_zone_registry,
    zone_to_snapshot,
)
from app.plugins.fight.rules import (
    ADVISORY_NOTICE, SENSITIVITIES, SEVERITIES, describe_schedule,
    describe_tuning, is_armed, next_transition, sanitize_schedule,
    sanitize_sensitivity, sanitize_severity, tuning,
)
from app.plugins.fight.schemas import (
    AckRequest, FightCoverage, FightEventOut, FightTestRequest, FightTestResult,
    FightZoneCreate, FightZoneOut, FightZoneUpdate, VERDICTS, VerifyRequest,
)
from app.plugins.fight.service import DETECT, EXCLUDE
from app.plugins.zones.geometry import MIN_ZONE_AREA, point_in_polygon, sanitize_polygon
from config.config import config
from database.session import SessionLocal

# require_permissions(...) is already a Security object, not a dependency
# factory — wrapping it in Depends() would silently drop the scope check.
fight_router = APIRouter(prefix="/api/fight", tags=["Fight & Quarrel Analytics"],
                         dependencies=[Depends(get_current_user)])

PLUGIN_NAME = "FightDetectionPlugin"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _camera_names(db: Session, camera_ids) -> Dict[str, str]:
    ids = [c for c in {str(c) for c in camera_ids if c}]
    if not ids:
        return {}
    from database.models.models import Camera

    return {r[0]: r[1] for r in
            db.query(Camera.id, Camera.name).filter(Camera.id.in_(ids)).all()}


def _url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return path if str(path).startswith("/") else "/" + str(path)


def _validated_geometry(points) -> list:
    clean = sanitize_polygon(points)
    if clean is None:
        raise HTTPException(
            422, f"A zone needs at least 3 distinct points enclosing more than "
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


def _validated_sensitivity(value: Optional[str]) -> str:
    name = (value or "standard").strip().lower()
    if name not in SENSITIVITIES:
        raise HTTPException(422, f"sensitivity must be one of {', '.join(SENSITIVITIES)}")
    return name


def _validated_severity(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if str(value).strip().lower() not in SEVERITIES:
        raise HTTPException(422, f"severity must be one of {', '.join(SEVERITIES)}")
    return sanitize_severity(value)


def _zone_out(row: FightZone, names: Dict[str, str],
              now: Optional[datetime] = None) -> FightZoneOut:
    overrides = {k: getattr(row, k) for k in OVERRIDE_COLUMNS
                 if getattr(row, k, None) is not None}
    return FightZoneOut(
        zone_id=row.zone_id, camera_id=row.camera_id,
        camera_name=names.get(row.camera_id), name=row.name,
        points=row.points or [], zone_kind=(row.zone_kind or DETECT).upper(),
        is_active=bool(row.is_active),
        sensitivity=sanitize_sensitivity(row.sensitivity), severity=row.severity,
        effective_severity=sanitize_severity(row.severity),
        tuning=tuning(row.sensitivity, overrides),
        tuning_text=describe_tuning(row.sensitivity, overrides),
        overrides=overrides, schedule=row.schedule,
        schedule_text=describe_schedule(row.schedule),
        armed_now=is_armed(row.schedule, now),
        armed_changes_at=next_transition(row.schedule, now),
        notes=row.notes, created_by=row.created_by,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _event_out(row, names: Dict[str, str]) -> FightEventOut:
    details = row.details or {}
    return FightEventOut(
        event_id=row.event_id, camera_id=row.camera_id,
        camera_name=names.get(row.camera_id) or row.camera_name,
        zone_id=row.zone_id, zone_name=row.zone_name,
        event_type=row.event_type, severity=row.severity,
        timestamp=row.timestamp, started_at=row.started_at,
        duration_seconds=row.duration_seconds, score=row.score,
        track_ids=row.track_ids, bbox=row.bbox,
        snapshot_file=_url(row.snapshot_path),
        acknowledged=bool(row.acknowledged), acknowledged_by=row.acknowledged_by,
        acknowledged_at=row.acknowledged_at, ack_note=row.ack_note,
        verified=row.verified, details=details or None,
        description=details.get("description"),
    )


# ----------------------------------------------------------------------
# options, coverage, health
# ----------------------------------------------------------------------
@fight_router.get("/options", dependencies=[require_permissions([perms.FIGHT_READ])])
def fight_options():
    return {
        "zone_kinds": list(ZONE_KINDS),
        "sensitivities": {n: tuning(n) for n in SENSITIVITIES},
        "sensitivity_text": {n: describe_tuning(n) for n in SENSITIVITIES},
        "severities": list(SEVERITIES),
        "event_types": list(FIGHT_EVENT_TYPES),
        "verdicts": list(VERDICTS),
        "override_keys": list(OVERRIDE_COLUMNS),
        "mux_space": [1280, 720],
        "advisory_notice": ADVISORY_NOTICE,
    }


@fight_router.get("/coverage", response_model=FightCoverage,
                  dependencies=[require_permissions([perms.FIGHT_READ])])
def coverage(db: Session = Depends(get_db)):
    zones = [z for z in FightZoneRepository(db).list_zones() if z.is_active]
    with_zones = {z.camera_id for z in zones}
    enabled = [c for c, p in (config.CAMERA_PLUGINS or {}).items()
               if PLUGIN_NAME in (p or [])]
    return FightCoverage(
        cameras_with_zones=len(with_zones), zones=len(zones),
        detect_zones=len([z for z in zones
                          if (z.zone_kind or DETECT).upper() == DETECT]),
        exclude_zones=len([z for z in zones
                           if (z.zone_kind or DETECT).upper() == EXCLUDE]),
        cameras_watching_whole_frame=len([c for c in enabled if c not in with_zones]),
        plugin_enabled_cameras=len(enabled),
        advisory_notice=ADVISORY_NOTICE,
    )


@fight_router.get("/health", dependencies=[require_permissions([perms.FIGHT_READ])])
def fight_health():
    return {"event_log": fight_event_log.health(),
            "registry_loaded": fight_zone_registry.loaded,
            "cameras_cached": len(fight_zone_registry.by_camera),
            "advisory_notice": ADVISORY_NOTICE}


# ----------------------------------------------------------------------
# events
# ----------------------------------------------------------------------
@fight_router.get("/events", dependencies=[require_permissions([perms.FIGHT_READ])])
def list_events(camera_id: Optional[str] = Query(default=None),
                zone_id: Optional[str] = Query(default=None),
                event_type: Optional[str] = Query(default=None),
                severity: Optional[str] = Query(default=None),
                acknowledged: Optional[bool] = Query(default=None),
                verified: Optional[str] = Query(default=None),
                days: Optional[int] = Query(default=None, ge=1, le=365),
                limit: int = Query(default=50, ge=1, le=500),
                offset: int = Query(default=0, ge=0),
                db: Session = Depends(get_db)):
    if event_type and event_type not in FIGHT_EVENT_TYPES:
        raise HTTPException(422, f"event_type must be one of {', '.join(FIGHT_EVENT_TYPES)}")
    if severity and severity not in SEVERITIES:
        raise HTTPException(422, f"severity must be one of {', '.join(SEVERITIES)}")
    if verified and verified not in VERDICTS:
        raise HTTPException(422, f"verified must be one of {', '.join(VERDICTS)}")

    since = datetime.utcnow() - timedelta(days=days) if days else None
    rows, total = FightZoneRepository(db).list_events(
        camera_id=camera_id, zone_id=zone_id, event_type=event_type,
        severity=severity, acknowledged=acknowledged, verified=verified,
        since=since, limit=limit, offset=offset)
    names = _camera_names(db, [r.camera_id for r in rows])
    return {"total": total, "limit": limit, "offset": offset,
            "events": [_event_out(r, names).model_dump(mode="json") for r in rows],
            "advisory_notice": ADVISORY_NOTICE}


@fight_router.get("/events/summary",
                  dependencies=[require_permissions([perms.FIGHT_READ])])
def events_summary(days: int = Query(default=7, ge=1, le=365),
                   db: Session = Depends(get_db)):
    return FightZoneRepository(db).summary(
        since=datetime.utcnow() - timedelta(days=days))


@fight_router.get("/events/export.csv",
                  dependencies=[require_permissions([perms.FIGHT_READ])])
def export_events(camera_id: Optional[str] = Query(default=None),
                  days: int = Query(default=30, ge=1, le=365),
                  db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=days)
    rows, _ = FightZoneRepository(db).list_events(
        camera_id=camera_id, since=since, limit=500)
    names = _camera_names(db, [r.camera_id for r in rows])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["event_id", "timestamp", "camera", "zone", "type", "severity",
                "duration_sec", "confidence", "human_verdict", "acknowledged",
                "acknowledged_by", "note"])
    for r in rows:
        w.writerow([r.event_id, r.timestamp.isoformat() if r.timestamp else "",
                    names.get(r.camera_id) or r.camera_name or r.camera_id or "",
                    r.zone_name or "(whole frame)", r.event_type, r.severity or "",
                    f"{r.duration_seconds:.1f}" if r.duration_seconds is not None else "",
                    f"{r.score:.2f}" if r.score is not None else "",
                    r.verified or "not reviewed",
                    "yes" if r.acknowledged else "no", r.acknowledged_by or "",
                    (r.ack_note or "").replace("\n", " ")])
    w.writerow([])
    w.writerow([ADVISORY_NOTICE])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition":
                             f"attachment; filename=fight-events-{datetime.utcnow():%Y%m%d}.csv"})


@fight_router.post("/events/{event_id}/ack", response_model=FightEventOut,
                   dependencies=[require_permissions([perms.FIGHT_ACK])])
def acknowledge_event(event_id: str, body: AckRequest,
                      db: Session = Depends(get_db), user=Depends(get_current_user)):
    who = getattr(user, "email", None) or getattr(user, "username", None)
    row = FightZoneRepository(db).acknowledge(event_id, who, body.note)
    if row is None:
        raise HTTPException(404, "Fight event not found")
    return _event_out(row, _camera_names(db, [row.camera_id]))


@fight_router.post("/events/{event_id}/verify", response_model=FightEventOut,
                   dependencies=[require_permissions([perms.FIGHT_VERIFY])])
def verify_event(event_id: str, body: VerifyRequest,
                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    """
    Records a human's judgement on an indication.

    The module raises indications; only a person can decide whether one was a
    fight. Without this the log reads as a list of confirmed assaults, which
    it is not — and it names people by track and stores footage, so the
    difference matters.
    """
    verdict = str(body.verdict or "").strip().lower()
    if verdict not in VERDICTS:
        raise HTTPException(422, f"verdict must be one of {', '.join(VERDICTS)}")
    repo = FightZoneRepository(db)
    row = repo.get_event(event_id)
    if row is None:
        raise HTTPException(404, "Fight event not found")
    row.verified = verdict
    if body.note:
        row.ack_note = body.note
    row.acknowledged = True
    row.acknowledged_by = getattr(user, "email", None) or getattr(user, "username", None)
    row.acknowledged_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _event_out(row, _camera_names(db, [row.camera_id]))


# ----------------------------------------------------------------------
# zones
# ----------------------------------------------------------------------
@fight_router.get("/zones", response_model=List[FightZoneOut],
                  dependencies=[require_permissions([perms.FIGHT_READ])])
def list_zones(camera_id: Optional[str] = Query(default=None),
               active_only: bool = Query(default=False),
               db: Session = Depends(get_db)):
    rows = FightZoneRepository(db).list_zones(camera_id=camera_id,
                                              active_only=active_only)
    names = _camera_names(db, [r.camera_id for r in rows])
    now = datetime.now()
    return [_zone_out(r, names, now) for r in rows]


@fight_router.post("/zones", response_model=FightZoneOut, status_code=201,
                   dependencies=[require_permissions([perms.FIGHT_CONFIG])])
def create_zone(body: FightZoneCreate, db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    repo = FightZoneRepository(db)
    if repo.name_taken(body.camera_id, body.name):
        raise HTTPException(409, f"Camera already has a fight zone named '{body.name}'.")
    row = repo.create_zone(
        camera_id=body.camera_id, name=body.name,
        points=_validated_geometry(body.points),
        zone_kind=_validated_zone_kind(body.zone_kind), is_active=body.is_active,
        sensitivity=_validated_sensitivity(body.sensitivity),
        severity=_validated_severity(body.severity),
        min_score=body.min_score, min_frames=body.min_frames,
        confirm_sec=body.confirm_sec, engage_separation=body.engage_separation,
        clear_sec=body.clear_sec, alert_cooldown_sec=body.alert_cooldown_sec,
        schedule=_validated_schedule(body.schedule), notes=body.notes,
        created_by=getattr(user, "email", None))
    return _zone_out(row, _camera_names(db, [row.camera_id]))


@fight_router.get("/zones/{zone_id}", response_model=FightZoneOut,
                  dependencies=[require_permissions([perms.FIGHT_READ])])
def get_zone(zone_id: str, db: Session = Depends(get_db)):
    row = FightZoneRepository(db).get_zone(zone_id)
    if row is None:
        raise HTTPException(404, "Fight zone not found")
    return _zone_out(row, _camera_names(db, [row.camera_id]))


@fight_router.put("/zones/{zone_id}", response_model=FightZoneOut,
                  dependencies=[require_permissions([perms.FIGHT_CONFIG])])
def update_zone(zone_id: str, body: FightZoneUpdate, db: Session = Depends(get_db)):
    repo = FightZoneRepository(db)
    row = repo.get_zone(zone_id)
    if row is None:
        raise HTTPException(404, "Fight zone not found")

    fields: Dict[str, Any] = {}
    if body.name is not None:
        if repo.name_taken(row.camera_id, body.name, exclude_id=zone_id):
            raise HTTPException(409, f"Camera already has a fight zone named '{body.name}'.")
        fields["name"] = body.name
    if body.points is not None:
        fields["points"] = _validated_geometry(body.points)
    if body.zone_kind is not None:
        fields["zone_kind"] = _validated_zone_kind(body.zone_kind)
    if body.is_active is not None:
        fields["is_active"] = body.is_active
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


@fight_router.delete("/zones/{zone_id}",
                     dependencies=[require_permissions([perms.FIGHT_CONFIG])])
def delete_zone(zone_id: str, db: Session = Depends(get_db)):
    if not FightZoneRepository(db).delete_zone(zone_id):
        raise HTTPException(404, "Fight zone not found")
    return {"status": "deleted", "zone_id": zone_id}


@fight_router.post("/zones/{zone_id}/test", response_model=FightTestResult,
                   dependencies=[require_permissions([perms.FIGHT_READ])])
def test_zone(zone_id: str, body: FightTestRequest, db: Session = Depends(get_db)):
    """
    Would an incident here, at this time, raise an alert?

    Answers with a reason rather than a bare boolean, because "no" has several
    causes — outside the polygon, out of schedule, an exclusion zone, the two
    people too far apart, or the score too low — and each has a different fix.
    This is how the module is demonstrated and calibrated without staging a
    fight, which is what SOW 2.7's "demonstrate test events" asks for.
    """
    row = FightZoneRepository(db).get_zone(zone_id)
    if row is None:
        raise HTTPException(404, "Fight zone not found")
    snapshot = zone_to_snapshot(row)
    if snapshot is None:
        raise HTTPException(409, "This zone's saved geometry is not usable; redraw it.")

    sep, engaged = None, None
    if body.boxes and len(body.boxes) == 2 and all(len(b) == 4 for b in body.boxes):
        a, b = body.boxes
        cx = (a[0] + a[2] + b[0] + b[2]) / 4.0
        cy = (a[1] + a[3] + b[1] + b[3]) / 4.0
        sep = separation(a, b)
    elif body.point and len(body.point) == 2:
        cx, cy = float(body.point[0]), float(body.point[1])
    else:
        raise HTTPException(
            422, "Provide either two person boxes, or a point [x,y].")

    when = body.at or datetime.now()
    tune = tuning(snapshot["sensitivity"], snapshot["overrides"])
    armed = is_armed(snapshot["schedule"], when)
    inside = point_in_polygon(cx, cy, snapshot["points"])
    excluded = snapshot["zone_kind"] == EXCLUDE
    if sep is not None:
        engaged = sep <= tune["engage_separation"]
    strong_enough = body.score >= tune["min_score"]

    if excluded:
        reason = "This is an EXCLUDE zone: indications inside it are deliberately silenced."
    elif not snapshot["is_active"]:
        reason = "Zone is disabled."
    elif not armed:
        reason = (f"Zone is not armed at {when:%a %H:%M} "
                  f"({describe_schedule(snapshot['schedule'])}).")
    elif not inside:
        reason = f"The pair's centre ({cx:.0f}, {cy:.0f}) is outside the polygon."
    elif engaged is False:
        reason = (f"The two people are {sep:.2f} body heights apart, beyond this "
                  f"zone's engagement distance of {tune['engage_separation']:g}.")
    elif not strong_enough:
        reason = (f"Confidence {body.score:.0%} is below this zone's minimum of "
                  f"{tune['min_score']:.0%}.")
    else:
        reason = (f"Inside and armed — alerts after {tune['confirm_sec']:g}s "
                  f"and {int(tune['min_frames'])} frames of sustained agitation.")

    would = bool(not excluded and snapshot["is_active"] and armed and inside
                 and strong_enough and engaged is not False)
    return FightTestResult(
        zone_id=row.zone_id, zone_name=row.name, inside=inside, armed=armed,
        engaged=engaged, separation=round(sep, 3) if sep is not None else None,
        would_alert=would, reason=reason,
        confirm_after=f"{tune['confirm_sec']:g}s / {int(tune['min_frames'])} frames",
        evaluated_at=when, schedule_text=describe_schedule(snapshot["schedule"]),
        advisory_notice=ADVISORY_NOTICE)
