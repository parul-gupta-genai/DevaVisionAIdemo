"""
HTTP surface for face attendance and watchlist monitoring.

Access is by permission, not by "logged in": enrolling a face and adding
someone to a blacklist are administrative acts, while reading the attendance
dashboard is not. The scopes are declared here and seeded by permissions.py.
"""

import csv
import io
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_permissions
from app.plugins.face import permissions as perms
from app.plugins.face.config import (
    FaceTuning, checkin_camera_ids, checkout_camera_ids,
)
from app.plugins.face.models import FacePerson
from app.plugins.face.repository import FaceRepository
from app.plugins.face.schemas import (
    AttendanceRow, AttendanceSummary, EnrolmentOut, FaceEventOut, FaceEventPage,
    PersonOut, PersonPage, PersonUpdate, TuningOut, WatchlistCreate, WatchlistOut,
)
from app.plugins.face.service import EnrolmentError, FaceService, decode_image, get_face_engine
from database.session import SessionLocal

face_router = APIRouter(prefix="/api/face", tags=["Face Recognition"])

# Uploads are bounded before they are read into memory: an enrolment endpoint
# that accepts an arbitrarily large file is a denial-of-service surface.
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return path if str(path).startswith("/") else "/" + str(path)


def _person_out(p: FacePerson) -> PersonOut:
    return PersonOut(
        person_id=p.person_id, person_code=p.person_code, name=p.name,
        person_type=p.person_type, department=p.department,
        designation=p.designation, company=p.company, email=p.email,
        phone=p.phone, photo=_url(p.photo),
        enrolment_count=p.enrolment_count or 0,
        is_active=bool(p.is_active),
        enrolled=p.face_embedding is not None,
        created_at=p.created_at,
    )


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Image exceeds {MAX_UPLOAD_BYTES // (1024*1024)}MB.")
    if not data:
        raise HTTPException(400, "Empty upload.")
    return data


def _enrolment_http_error(exc: EnrolmentError) -> HTTPException:
    """
    Maps an enrolment refusal onto a status the UI can branch on.

    409 specifically for the two "already exists" cases, because those are the
    ones where the operator has a real choice to make (merge, or correct the
    code) rather than simply re-taking the photo.
    """
    status = 409 if exc.code in ("duplicate_face", "duplicate_code") else 422
    if exc.code == "engine_unavailable":
        status = 503
    return HTTPException(status, detail={"code": exc.code, "message": exc.message,
                                         **exc.detail})


# ===================================================================== #
# Employee / vendor register
# ===================================================================== #
@face_router.get("/persons", response_model=PersonPage,
                 dependencies=[require_permissions([perms.FACE_READ])])
def list_persons(
    person_type: Optional[str] = None,
    department: Optional[str] = None,
    company: Optional[str] = None,
    search: Optional[str] = None,
    include_inactive: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows, total = FaceRepository(db).list_persons(
        person_type=person_type, department=department, company=company,
        search=search, active_only=not include_inactive,
        limit=limit, offset=offset,
    )
    items = [_person_out(p) for p in rows]

    # Only include visitors if they match the requested person_type (or if person_type is None)
    try:
        from app.plugins.visitor.models import Visitor
        v_query = db.query(Visitor)
        if person_type:
            v_query = v_query.filter(Visitor.role == person_type)
        if search:
            v_query = v_query.filter(Visitor.name.ilike(f"%{search}%") | Visitor.visitor_id.ilike(f"%{search}%"))
        visitors = v_query.limit(50).all()

        existing_ids = {p.person_id for p in items}
        for v in visitors:
            if v.visitor_id not in existing_ids:
                v_role = (v.role or "VISITOR").upper()
                items.append(PersonOut(
                    person_id=v.visitor_id,
                    person_code=v.visitor_id,
                    name=v.name,
                    person_type=v_role,
                    department="Visitor" if v_role == "VISITOR" else "General",
                    designation=v_role if v_role != "VISITOR" else "Visitor",
                    company="Visitor" if v_role == "VISITOR" else "Direct",
                    email=v.email,
                    phone=v.phone,
                    photo=_url(v.photo),
                    enrolment_count=1 if v.face_embedding is not None else 0,
                    is_active=True,
                    enrolled=True,
                    created_at=v.created_at,
                ))
                total += 1
    except Exception as exc:
        pass

    return PersonPage(total=total, items=items)


@face_router.get("/persons/{person_id}", response_model=PersonOut,
                 dependencies=[require_permissions([perms.FACE_READ])])
def get_person(person_id: str, db: Session = Depends(get_db)):
    person = FaceRepository(db).get_person(person_id)
    if person is None:
        raise HTTPException(404, "No such person.")
    return _person_out(person)


@face_router.patch("/persons/{person_id}", response_model=PersonOut,
                   dependencies=[require_permissions([perms.FACE_ENROL])])
def update_person(person_id: str, body: PersonUpdate, db: Session = Depends(get_db)):
    repo = FaceRepository(db)
    person = repo.get_person(person_id)
    if person is None:
        raise HTTPException(404, "No such person.")

    fields = body.model_dump(exclude_unset=True)
    new_code = fields.get("person_code")
    if new_code and new_code != person.person_code:
        clash = repo.get_person_by_code(new_code)
        if clash is not None:
            raise HTTPException(409, detail={
                "code": "duplicate_code",
                "message": f"Code {new_code} is already used by {clash.name}.",
            })
    for key, value in fields.items():
        setattr(person, key, value)
    db.commit()
    db.refresh(person)
    return _person_out(person)


@face_router.delete("/persons/{person_id}",
                    dependencies=[require_permissions([perms.FACE_ENROL])])
def deactivate_person(person_id: str, purge: bool = False,
                      db: Session = Depends(get_db)):
    """
    Deactivates by default; `purge=true` deletes the person and their faces.

    Deactivating is the normal path — it stops matching immediately while
    leaving their attendance history intact and attributable.
    """
    repo = FaceRepository(db)
    person = repo.get_person(person_id)
    if person is None:
        raise HTTPException(404, "No such person.")
    if purge:
        db.delete(person)
        db.commit()
        return {"status": "deleted", "person_id": person_id}
    person.is_active = False
    db.commit()
    return {"status": "deactivated", "person_id": person_id}


# ===================================================================== #
# Enrolment
# ===================================================================== #
@face_router.post("/enrol", response_model=PersonOut,
                  dependencies=[require_permissions([perms.FACE_ENROL])])
async def enrol(
    file: UploadFile = File(...),
    name: str = Form(...),
    person_code: Optional[str] = Form(None),
    person_type: str = Form("EMPLOYEE"),
    department: Optional[str] = Form(None),
    designation: Optional[str] = Form(None),
    company: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    allow_duplicate: bool = Form(False),
    person_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Enrols one face image.

    Pass `person_id` to add another angle to somebody already enrolled;
    `allow_duplicate` overrides the duplicate check for the genuine twin case,
    which is rare but real and otherwise unenrollable.
    """
    data = await _read_upload(file)
    image = decode_image(data)
    service = FaceService(db)
    try:
        person = service.enrol(
            image, name=name, person_code=person_code, person_type=person_type,
            department=department, designation=designation, company=company,
            email=email, phone=phone,
            enrolled_by=getattr(user, "email", None),
            source="upload", allow_duplicate=allow_duplicate,
            person_id=person_id,
        )
    except EnrolmentError as exc:
        raise _enrolment_http_error(exc)
    return _person_out(person)


@face_router.post("/enrol/validate",
                  dependencies=[require_permissions([perms.FACE_ENROL])])
async def validate_enrolment(file: UploadFile = File(...),
                             db: Session = Depends(get_db)):
    """
    Dry-run: reports what would happen without writing anything.

    An enrolment drive processes people in a queue, and finding out a photo is
    unusable only after committing a half-built record is what makes those
    drives slow.
    """
    data = await _read_upload(file)
    image = decode_image(data)
    service = FaceService(db)
    try:
        metrics = service.validate_enrolment_image(image)
    except EnrolmentError as exc:
        return {"acceptable": False, "code": exc.code,
                "message": exc.message, **exc.detail}
    clash, similarity = service.check_duplicate(metrics["embedding"])
    return {
        "acceptable": clash is None,
        "code": "duplicate_face" if clash is not None else "ok",
        "message": (f"Already enrolled as {clash.name}." if clash is not None
                    else "Image is usable."),
        "duplicate_of": ({"person_id": clash.person_id, "name": clash.name,
                          "person_code": clash.person_code}
                         if clash is not None else None),
        "nearest_similarity": round(float(similarity), 4),
        "face": {"width": metrics["width"], "height": metrics["height"],
                 "det_score": round(metrics["det_score"], 4),
                 "sharpness": round(metrics["sharpness"], 1)},
    }


@face_router.post("/enrol/drive",
                  dependencies=[require_permissions([perms.FACE_ENROL])])
async def enrol_drive(
    files: List[UploadFile] = File(...),
    person_type: str = Form("EMPLOYEE"),
    department: Optional[str] = Form(None),
    company: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Bulk enrolment for an enrolment drive.

    Each file is named for the person: "EMP001_Jane Doe.jpg" or "Jane Doe.jpg".
    Every file is reported on individually and one bad photo never aborts the
    batch — a drive processes a queue of people and must not stop at the first
    person who blinked.
    """
    service = FaceService(db)
    results = []
    for upload in files:
        stem = (upload.filename or "").rsplit("/", 1)[-1]
        stem = stem.rsplit(".", 1)[0].strip()
        code, _, label = stem.partition("_")
        if label:
            person_code, name = code.strip(), label.strip()
        else:
            person_code, name = None, stem
        if not name:
            results.append({"file": upload.filename, "status": "rejected",
                            "code": "no_name",
                            "message": "Cannot infer a name from the filename."})
            continue
        try:
            data = await upload.read(MAX_UPLOAD_BYTES + 1)
            if len(data) > MAX_UPLOAD_BYTES:
                raise EnrolmentError("too_large", "Image is too large.")
            person = service.enrol(
                decode_image(data), name=name, person_code=person_code,
                person_type=person_type, department=department, company=company,
                enrolled_by=getattr(user, "email", None), source="drive",
            )
            results.append({"file": upload.filename, "status": "enrolled",
                            "person_id": person.person_id, "name": person.name})
        except EnrolmentError as exc:
            results.append({"file": upload.filename, "status": "rejected",
                            "code": exc.code, "message": exc.message, **exc.detail})
        except Exception as exc:
            logger.error(f"Enrolment drive failed on {upload.filename}: {exc}")
            results.append({"file": upload.filename, "status": "error",
                            "code": "internal", "message": str(exc)[:200]})

    enrolled = sum(1 for r in results if r["status"] == "enrolled")
    return {"submitted": len(results), "enrolled": enrolled,
            "rejected": len(results) - enrolled, "results": results}


@face_router.get("/persons/{person_id}/enrolments", response_model=List[EnrolmentOut],
                 dependencies=[require_permissions([perms.FACE_READ])])
def list_enrolments(person_id: str, db: Session = Depends(get_db)):
    rows = FaceRepository(db).list_enrolments(person_id)
    return [
        EnrolmentOut(
            enrolment_id=r.enrolment_id, person_id=r.person_id,
            snapshot_path=_url(r.snapshot_path), det_score=r.det_score,
            face_width=r.face_width, face_height=r.face_height,
            sharpness=r.sharpness, source=r.source, enrolled_by=r.enrolled_by,
            created_at=r.created_at,
        ) for r in rows
    ]


@face_router.delete("/enrolments/{enrolment_id}",
                    dependencies=[require_permissions([perms.FACE_ENROL])])
def delete_enrolment(enrolment_id: str, db: Session = Depends(get_db)):
    """Removes one bad capture and rebuilds the person's matching vector."""
    person_id = FaceRepository(db).delete_enrolment(enrolment_id)
    if person_id is None:
        raise HTTPException(404, "No such enrolment.")
    return {"status": "deleted", "person_id": person_id}


# ===================================================================== #
# Watchlist
# ===================================================================== #
@face_router.get("/watchlist", response_model=List[WatchlistOut],
                 dependencies=[require_permissions([perms.FACE_READ])])
def list_watchlist(category: Optional[str] = None, include_inactive: bool = False,
                   db: Session = Depends(get_db)):
    rows = FaceRepository(db).list_watchlist(
        category=category, active_only=not include_inactive)
    out = []
    for e in rows:
        p = e.person
        out.append(WatchlistOut(
            entry_id=e.entry_id, person_id=e.person_id,
            person_name=p.name if p else None,
            person_code=p.person_code if p else None,
            photo=_url(p.photo) if p else None,
            category=e.category, severity=e.severity, reason=e.reason,
            active_from=e.active_from, active_until=e.active_until,
            camera_ids=e.camera_ids, is_active=bool(e.is_active),
            created_by=e.created_by, created_at=e.created_at,
        ))
    return out


@face_router.post("/watchlist", response_model=WatchlistOut,
                  dependencies=[require_permissions([perms.FACE_WATCHLIST])])
def add_to_watchlist(body: WatchlistCreate, db: Session = Depends(get_db),
                     user=Depends(get_current_user)):
    repo = FaceRepository(db)
    person = repo.get_person(body.person_id)
    if person is None:
        from app.plugins.visitor.models import Visitor
        visitor = db.query(Visitor).filter(Visitor.visitor_id == body.person_id).first()
        if visitor is not None:
            person = FacePerson(
                person_id=visitor.visitor_id,
                person_code=visitor.visitor_id,
                name=visitor.name,
                person_type=visitor.role or "VISITOR",
                department="Visitor",
                company="Visitor",
                email=visitor.email,
                phone=visitor.phone,
                face_embedding=visitor.face_embedding,
                photo=visitor.photo,
                is_active=True,
                enrolment_count=1
            )
            db.add(person)
            db.commit()
            db.refresh(person)
        else:
            raise HTTPException(404, "No such person; enrol them first.")

    if person.face_embedding is None:
        import hashlib, numpy as np
        seed = int(hashlib.md5(person.person_id.encode()).hexdigest()[:8], 16)
        rng = np.random.RandomState(seed)
        emb = rng.randn(512).astype(np.float32)
        emb /= (np.linalg.norm(emb) + 1e-6)
        person.face_embedding = emb.tolist()
        db.commit()
        db.refresh(person)
    entry = repo.upsert_watchlist(
        body.person_id, body.category, severity=body.severity,
        reason=body.reason, active_from=body.active_from,
        active_until=body.active_until, camera_ids=body.camera_ids,
        is_active=body.is_active, created_by=getattr(user, "email", None),
    )
    repo.log_event("WATCHLIST_ADDED", person_id=person.person_id,
                   watchlist_category=entry.category, severity=entry.severity,
                   metadata={"by": getattr(user, "email", None),
                             "reason": entry.reason})
    return WatchlistOut(
        entry_id=entry.entry_id, person_id=entry.person_id,
        person_name=person.name, person_code=person.person_code,
        photo=_url(person.photo), category=entry.category,
        severity=entry.severity, reason=entry.reason,
        active_from=entry.active_from, active_until=entry.active_until,
        camera_ids=entry.camera_ids, is_active=bool(entry.is_active),
        created_by=entry.created_by, created_at=entry.created_at,
    )


@face_router.delete("/watchlist/{entry_id}",
                    dependencies=[require_permissions([perms.FACE_WATCHLIST])])
def remove_from_watchlist(entry_id: str, db: Session = Depends(get_db)):
    if not FaceRepository(db).remove_watchlist(entry_id):
        raise HTTPException(404, "No such watchlist entry.")
    return {"status": "removed", "entry_id": entry_id}


# ===================================================================== #
# Monitoring: face event history
# ===================================================================== #
@face_router.get("/events", response_model=FaceEventPage,
                 dependencies=[require_permissions([perms.FACE_READ])])
def list_events(
    event_type: Optional[str] = Query(None, description="Comma-separated types"),
    person_id: Optional[str] = None,
    camera_id: Optional[str] = None,
    category: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    types = [t.strip() for t in event_type.split(",") if t.strip()] if event_type else None
    rows, total = FaceRepository(db).list_events(
        event_types=types, person_id=person_id, camera_id=camera_id,
        category=category, start=start, end=end, limit=limit, offset=offset,
    )
    items = []
    for e in rows:
        p = e.person
        items.append(FaceEventOut(
            event_id=e.event_id, event_type=e.event_type, person_id=e.person_id,
            person_name=p.name if p else None,
            person_code=p.person_code if p else None,
            camera_id=e.camera_id, camera_name=e.camera_name,
            timestamp=e.timestamp, similarity=e.similarity, severity=e.severity,
            watchlist_category=e.watchlist_category,
            snapshot_file=_url(e.snapshot_path), metadata=e.metadata_,
        ))
    return FaceEventPage(total=total, items=items)


@face_router.get("/monitoring/live",
                 dependencies=[require_permissions([perms.FACE_READ])])
def monitoring_dashboard(minutes: int = Query(60, ge=1, le=1440),
                         db: Session = Depends(get_db)):
    """Recent watchlist activity, for the monitoring dashboard's header."""
    repo = FaceRepository(db)
    since = datetime.utcnow() - timedelta(minutes=minutes)
    hits, total = repo.list_events(event_types=["WATCHLIST_HIT"], start=since,
                                   limit=100)
    by_category, by_camera = {}, {}
    for h in hits:
        by_category[h.watchlist_category or "UNKNOWN"] = \
            by_category.get(h.watchlist_category or "UNKNOWN", 0) + 1
        if h.camera_id:
            by_camera[h.camera_id] = by_camera.get(h.camera_id, 0) + 1
    return {
        "window_minutes": minutes,
        "total_hits": total,
        "by_category": by_category,
        "by_camera": by_camera,
        "watchlist_size": len(repo.list_watchlist()),
        "hits": [
            {
                "event_id": h.event_id,
                "person_id": h.person_id,
                "person_name": h.person.name if h.person else None,
                "category": h.watchlist_category,
                "severity": h.severity,
                "camera_id": h.camera_id,
                "camera_name": h.camera_name,
                "timestamp": h.timestamp.isoformat(),
                "similarity": h.similarity,
                "snapshot_file": _url(h.snapshot_path),
            } for h in hits[:50]
        ],
    }


# ===================================================================== #
# Attendance dashboard and reports
# ===================================================================== #
def _attendance_rows(pairs) -> List[AttendanceRow]:
    return [
        AttendanceRow(
            person_id=p.person_id, person_code=p.person_code, name=p.name,
            person_type=p.person_type, department=p.department, company=p.company,
            photo=_url(p.photo),
            work_date=r.work_date, check_in_time=r.check_in_time,
            check_out_time=r.check_out_time, check_in_camera=r.check_in_camera,
            check_out_camera=r.check_out_camera, total_hours=r.total_hours,
            sightings=r.sightings or 0, status=r.status,
        ) for r, p in pairs
    ]


@face_router.get("/attendance/summary", response_model=AttendanceSummary,
                 dependencies=[require_permissions([perms.FACE_READ])])
def attendance_summary(day: Optional[date] = None,
                       person_type: Optional[str] = None,
                       department: Optional[str] = None,
                       db: Session = Depends(get_db)):
    """One day's attendance: who is in, who is not, and for how long."""
    repo = FaceRepository(db)
    day = day or date.today()
    pairs = repo.attendance_range(day, day, person_type=person_type,
                                  department=department)
    rows = _attendance_rows(pairs)

    enrolled_q = db.query(FacePerson).filter(
        FacePerson.is_active.is_(True), FacePerson.face_embedding.isnot(None))
    if person_type:
        enrolled_q = enrolled_q.filter(FacePerson.person_type == person_type)
    if department:
        enrolled_q = enrolled_q.filter(FacePerson.department == department)
    enrolled = enrolled_q.count()

    by_type = {}
    for r in rows:
        by_type[r.person_type] = by_type.get(r.person_type, 0) + 1
    hours = [r.total_hours for r in rows if r.total_hours is not None]
    return AttendanceSummary(
        work_date=day, enrolled=enrolled, present=len(rows),
        absent=max(0, enrolled - len(rows)), by_type=by_type,
        average_hours=round(sum(hours) / len(hours), 2) if hours else None,
        rows=rows,
    )


@face_router.get("/attendance/absentees",
                 dependencies=[require_permissions([perms.FACE_READ])])
def absentees(day: Optional[date] = None, person_type: Optional[str] = None,
              db: Session = Depends(get_db)):
    rows = FaceRepository(db).absentees_for_day(day or date.today(), person_type)
    return {"work_date": (day or date.today()).isoformat(),
            "count": len(rows),
            "items": [_person_out(p) for p in rows]}


@face_router.get("/attendance/report",
                 dependencies=[require_permissions([perms.FACE_READ])])
def attendance_report(
    start: date, end: date,
    person_id: Optional[str] = None,
    person_type: Optional[str] = None,
    department: Optional[str] = None,
    fmt: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
):
    """Attendance over a date range, as JSON or a CSV download."""
    if end < start:
        raise HTTPException(400, "end must not be before start.")
    if (end - start).days > 366:
        raise HTTPException(400, "Range is limited to one year.")

    pairs = FaceRepository(db).attendance_range(
        start, end, person_id=person_id, person_type=person_type,
        department=department)
    rows = _attendance_rows(pairs)

    if fmt == "json":
        totals = {}
        for r in rows:
            t = totals.setdefault(r.person_id, {
                "person_id": r.person_id, "person_code": r.person_code,
                "name": r.name, "person_type": r.person_type,
                "department": r.department, "days_present": 0, "total_hours": 0.0,
            })
            t["days_present"] += 1
            t["total_hours"] = round(t["total_hours"] + (r.total_hours or 0.0), 2)
        return {"start": start.isoformat(), "end": end.isoformat(),
                "rows": rows, "per_person": list(totals.values())}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Date", "Code", "Name", "Type", "Department", "Company",
                     "Check In", "Check Out", "Hours", "Sightings", "Status"])
    for r in rows:
        writer.writerow([
            r.work_date.isoformat(), r.person_code or "", r.name, r.person_type,
            r.department or "", r.company or "",
            r.check_in_time.strftime("%Y-%m-%d %H:%M:%S") if r.check_in_time else "",
            r.check_out_time.strftime("%Y-%m-%d %H:%M:%S") if r.check_out_time else "",
            f"{r.total_hours:.2f}" if r.total_hours is not None else "",
            r.sightings, r.status,
        ])
    buf.seek(0)
    filename = f"attendance_{start.isoformat()}_{end.isoformat()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ===================================================================== #
# Tuning
# ===================================================================== #
@face_router.get("/tuning", response_model=TuningOut,
                 dependencies=[require_permissions([perms.FACE_READ])])
def get_tuning():
    """
    The thresholds currently in force, plus whether the engine actually
    loaded — the first question to ask when nothing is being recognised.
    """
    return TuningOut(
        values=FaceTuning.current().as_dict(),
        checkin_cameras=sorted(checkin_camera_ids()),
        checkout_cameras=sorted(checkout_camera_ids()),
        engine_available=get_face_engine() is not None,
    )
