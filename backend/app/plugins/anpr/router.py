from fastapi import APIRouter, Depends, HTTPException, Query
import time

from sqlalchemy import func

from app.auth.dependencies import get_current_user, require_permissions
from app.plugins.anpr.permissions import ANPR_GATES, ANPR_READ, ANPR_WATCHLIST
from app.plugins.anpr import gates
from app.plugins.anpr.repository import gate_registry, gate_to_dict
from app.plugins.anpr.watchlist import (
    BLACKLIST_TYPES, WHITELIST_TYPES, is_blacklist, is_whitelist,
    normalise, plate_watchlist,
)
from sqlalchemy.orm import Session
from typing import List, Optional
from database.session import get_db

from app.plugins.anpr.repository import ANPRRepository
from app.plugins.anpr.schemas import (
    WatchlistCreate, WatchlistUpdate, WatchlistResponse,
    ANPREventResponse, PlateHistoryResponse, PlateStatisticsResponse,
    GateCreate, GateUpdate, GateResponse, GateTestRequest,
)
from app.plugins.anpr.models import ANPREvent, ANPRGate, ANPRWatchlist, ANPRPlateHistory, ANPRStatistics

router = APIRouter(prefix="/anpr", tags=["ANPR"], dependencies=[Depends(get_current_user)])

@router.get("/events", response_model=List[ANPREventResponse])
def get_recent_events(limit: int = 50, db: Session = Depends(get_db)):
    events = db.query(ANPREvent).order_by(ANPREvent.timestamp.desc()).limit(limit).all()
    return events

@router.get("/stats", response_model=PlateStatisticsResponse)
def get_anpr_stats(db: Session = Depends(get_db)):
    from datetime import datetime, time
    today = datetime.combine(datetime.now().date(), time.min)
    
    total_reads = db.query(ANPRPlateHistory).filter(ANPRPlateHistory.timestamp >= today.timestamp()).count()
    unique_plates = db.query(ANPRPlateHistory.plate_number).filter(ANPRPlateHistory.timestamp >= today.timestamp()).distinct().count()
    
    return PlateStatisticsResponse(
        total_reads_today=total_reads,
        unique_vehicles=unique_plates,
        watchlist_matches=0,
        average_accuracy=98.4
    )

@router.get("/search", response_model=List[PlateHistoryResponse])
def search_plate_history(
    plate: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(ANPRPlateHistory)
    if plate:
        query = query.filter(ANPRPlateHistory.plate_number.ilike(f"%{plate}%"))
    if camera_id:
        query = query.filter(ANPRPlateHistory.camera_id == camera_id)
        
    return query.order_by(ANPRPlateHistory.timestamp.desc()).limit(limit).all()

@router.get("/watchlists", response_model=List[WatchlistResponse])
def get_watchlists(
    list_type: Optional[str] = Query(None, description="BLACKLIST, WHITELIST, VIP..."),
    kind: Optional[str] = Query(None, pattern="^(blacklist|whitelist)$",
                                description="Group several list_types at once"),
    include_expired: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(ANPRWatchlist)
    if list_type:
        q = q.filter(func.upper(ANPRWatchlist.list_type) == list_type.strip().upper())
    if kind:
        wanted = BLACKLIST_TYPES if kind == "blacklist" else WHITELIST_TYPES
        q = q.filter(func.upper(ANPRWatchlist.list_type).in_(sorted(wanted)))
    rows = q.order_by(ANPRWatchlist.priority.desc(),
                      ANPRWatchlist.plate_number).all()
    if not include_expired:
        now = time.time()
        rows = [r for r in rows if not (r.expiry and float(r.expiry) < now)]
    return rows


@router.get("/watchlists/check")
def check_plate(
    plate: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
):
    """
    Ask what a given read would match, and how.

    The point of this endpoint is that the answer is rarely a simple yes: a
    read can hit the list exactly, only after collapsing OCR confusions, or
    within one further character. Showing which of those happened is what
    lets an operator judge a hit rather than trust it blindly.
    """
    entry, kind = plate_watchlist.match(plate)
    return {
        "plate": plate,
        "normalised": normalise(plate),
        "matched": entry is not None,
        "match_kind": kind,
        "entry": entry,
        "is_blacklist": is_blacklist(entry["list_type"]) if entry else False,
        "is_whitelist": is_whitelist(entry["list_type"]) if entry else False,
        "list_size": plate_watchlist.size,
    }


@router.post("/watchlists", response_model=WatchlistResponse,
             dependencies=[require_permissions([ANPR_WATCHLIST])])
def create_watchlist(watchlist: WatchlistCreate, db: Session = Depends(get_db)):
    data = watchlist.model_dump()
    # Store the normalised plate. An entry typed "UP 16 B 3895" that is stored
    # verbatim can never be matched by a reader that emits "UP16B3895".
    data["plate_number"] = normalise(data.get("plate_number"))
    if not data["plate_number"]:
        raise HTTPException(422, "A plate number is required.")
    data["list_type"] = (data.get("list_type") or "BLACKLIST").strip().upper()

    existing = (
        db.query(ANPRWatchlist)
        .filter(ANPRWatchlist.plate_number == data["plate_number"])
        .first()
    )
    if existing is not None:
        raise HTTPException(409, detail={
            "code": "already_listed",
            "message": f"{data['plate_number']} is already on the "
                       f"{existing.list_type} list.",
            "id": existing.id,
            "list_type": existing.list_type,
        })

    db_watchlist = ANPRWatchlist(**data)
    db.add(db_watchlist)
    db.commit()
    db.refresh(db_watchlist)
    # The matcher works from a cached index; without this the new entry would
    # not fire until the cache expired.
    plate_watchlist.invalidate()
    return db_watchlist


@router.patch("/watchlists/{watchlist_id}", response_model=WatchlistResponse,
              dependencies=[require_permissions([ANPR_WATCHLIST])])
def update_watchlist(watchlist_id: str, watchlist: WatchlistUpdate,
                     db: Session = Depends(get_db)):
    db_watchlist = db.query(ANPRWatchlist).filter(ANPRWatchlist.id == watchlist_id).first()
    if not db_watchlist:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")

    updates = watchlist.model_dump(exclude_unset=True)
    if "plate_number" in updates:
        updates["plate_number"] = normalise(updates["plate_number"])
        if not updates["plate_number"]:
            raise HTTPException(422, "A plate number is required.")
    if "list_type" in updates and updates["list_type"]:
        updates["list_type"] = updates["list_type"].strip().upper()

    for key, value in updates.items():
        setattr(db_watchlist, key, value)

    db.commit()
    db.refresh(db_watchlist)
    plate_watchlist.invalidate()
    return db_watchlist


@router.delete("/watchlists/{watchlist_id}",
               dependencies=[require_permissions([ANPR_WATCHLIST])])
def delete_watchlist(watchlist_id: str, db: Session = Depends(get_db)):
    db_watchlist = db.query(ANPRWatchlist).filter(ANPRWatchlist.id == watchlist_id).first()
    if not db_watchlist:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
        
    db.delete(db_watchlist)
    db.commit()
    plate_watchlist.invalidate()
    return {"status": "deleted"}


# ==========================================================================
# Gate-wise ANPR setup (SOW 2.6)
#
# A gate names what a camera is watching, so a plate read becomes an entry or
# an exit, and carries the access rules the client supplies. Kept behind its
# own scope: designating a gate can deny a vehicle that is on no list at all,
# which is a site-access decision rather than a list edit.
# ==========================================================================

@router.get("/gates", response_model=List[GateResponse],
            dependencies=[require_permissions([ANPR_READ])])
def list_gates(camera_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(ANPRGate)
    if camera_id:
        q = q.filter(ANPRGate.camera_id == camera_id)
    return [_gate_out(g) for g in q.order_by(ANPRGate.name).all()]


@router.get("/gates/options", dependencies=[require_permissions([ANPR_READ])])
def gate_options():
    """Everything the configuration screen needs to render itself."""
    return {
        "roles": list(gates.ROLES),
        "axes": [gates.VERTICAL, gates.HORIZONTAL],
        "unlisted_policies": list(gates.UNLISTED_POLICIES),
        "list_types": sorted(WHITELIST_TYPES | BLACKLIST_TYPES),
        "whitelist_types": sorted(WHITELIST_TYPES),
        "blacklist_types": sorted(BLACKLIST_TYPES),
    }


@router.post("/gates", response_model=GateResponse, status_code=201,
             dependencies=[require_permissions([ANPR_GATES])])
def create_gate(body: GateCreate, db: Session = Depends(get_db)):
    existing = (db.query(ANPRGate)
                .filter(ANPRGate.camera_id == body.camera_id,
                        ANPRGate.is_active.is_(True)).first())
    if existing:
        # Two active gates on one camera makes the direction of a pass
        # ambiguous, and the registry only serves one per camera.
        raise HTTPException(
            409, f"Camera already has an active gate ('{existing.name}')")

    row = ANPRGate(
        name=body.name.strip(),
        camera_id=body.camera_id,
        role=gates.normalise_role(body.role),
        axis=_validated_axis(body.axis),
        invert=bool(body.invert),
        min_travel_px=float(body.min_travel_px),
        access_rules=_validated_rules(body.access_rules),
        is_active=body.is_active,
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    gate_registry.invalidate()
    return _gate_out(row)


@router.get("/gates/{gate_id}", response_model=GateResponse,
            dependencies=[require_permissions([ANPR_READ])])
def get_gate(gate_id: str, db: Session = Depends(get_db)):
    row = db.query(ANPRGate).filter(ANPRGate.gate_id == gate_id).first()
    if not row:
        raise HTTPException(404, "Gate not found")
    return _gate_out(row)


@router.put("/gates/{gate_id}", response_model=GateResponse,
            dependencies=[require_permissions([ANPR_GATES])])
def update_gate(gate_id: str, body: GateUpdate, db: Session = Depends(get_db)):
    row = db.query(ANPRGate).filter(ANPRGate.gate_id == gate_id).first()
    if not row:
        raise HTTPException(404, "Gate not found")

    if body.name is not None:
        row.name = body.name.strip()
    if body.role is not None:
        row.role = gates.normalise_role(body.role)
    if body.axis is not None:
        row.axis = _validated_axis(body.axis)
    if body.invert is not None:
        row.invert = bool(body.invert)
    if body.min_travel_px is not None:
        row.min_travel_px = float(body.min_travel_px)
    if body.access_rules is not None:
        row.access_rules = _validated_rules(body.access_rules)
    if body.is_active is not None:
        row.is_active = body.is_active
    if body.notes is not None:
        row.notes = body.notes

    db.commit()
    db.refresh(row)
    gate_registry.invalidate()
    return _gate_out(row)


@router.delete("/gates/{gate_id}",
               dependencies=[require_permissions([ANPR_GATES])])
def delete_gate(gate_id: str, db: Session = Depends(get_db)):
    row = db.query(ANPRGate).filter(ANPRGate.gate_id == gate_id).first()
    if not row:
        raise HTTPException(404, "Gate not found")
    db.delete(row)
    db.commit()
    gate_registry.invalidate()
    return {"status": "deleted"}


@router.post("/gates/{gate_id}/test", dependencies=[require_permissions([ANPR_READ])])
def test_gate(gate_id: str, body: GateTestRequest, db: Session = Depends(get_db)):
    """
    Commissioning: what would this gate do with this plate, right now?

    The calibration step the SOW asks for, done from a desk instead of by
    driving a vehicle at the barrier — it answers the direction, the decision
    and the reason, using exactly the code the pipeline uses.
    """
    row = db.query(ANPRGate).filter(ANPRGate.gate_id == gate_id).first()
    if not row:
        raise HTTPException(404, "Gate not found")

    gate = gate_to_dict(row)
    list_type = body.list_type
    if list_type is None and body.plate_number:
        entry, _kind = plate_watchlist.match(body.plate_number)
        list_type = entry["list_type"] if entry else None

    direction = gates.resolve_direction(
        gate["role"],
        tuple(body.first_point) if body.first_point else None,
        tuple(body.last_point) if body.last_point else None,
        axis=gate["axis"], invert=gate["invert"],
        min_travel_px=gate["min_travel_px"],
    )
    decision, reason = gates.decide_access(list_type, gate["access_rules"])
    return {
        "gate_id": gate["gate_id"],
        "gate_name": gate["name"],
        "plate_number": body.plate_number,
        "list_type": list_type,
        "direction": direction,
        "access": decision,
        "reason": reason,
        "event_type": gates.event_type_for(direction, decision),
        "rules_text": gates.describe_rules(gate["access_rules"]),
    }


def _validated_axis(axis: Optional[str]) -> str:
    value = (axis or gates.VERTICAL).strip().upper()
    if value not in (gates.VERTICAL, gates.HORIZONTAL):
        raise HTTPException(422, f"axis must be {gates.VERTICAL} or {gates.HORIZONTAL}")
    return value


def _validated_rules(rules) -> dict:
    try:
        return gates.sanitize_rules(rules)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def _gate_out(row: ANPRGate) -> dict:
    gate = gate_to_dict(row)
    gate["is_active"] = bool(row.is_active)
    gate["notes"] = row.notes
    gate["rules_text"] = gates.describe_rules(gate["access_rules"])
    return gate
