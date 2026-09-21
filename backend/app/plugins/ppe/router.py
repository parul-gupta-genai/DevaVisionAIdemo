"""
HTTP surface for the PPE vendor colour-kit catalogue.

The calibration endpoints are the important part: colours defined by typing
HSV numbers do not survive contact with a real camera, so every colour here
can be derived from a frame the camera actually produced.
"""

from datetime import datetime
from typing import List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from loguru import logger
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_permissions
from app.plugins.ppe import permissions as perms
from app.plugins.ppe.colour import HUE_MAX, calibrate, coverage, region_slice
from app.plugins.ppe.models import BODY_REGIONS, ITEM_TYPES, VIOLATION_TYPES
from app.plugins.ppe.repository import PPERepository, kit_catalogue
from app.plugins.ppe.schemas import (
    CalibrationResult, CameraConfigIn, CameraConfigOut, ColourCreate, ColourOut,
    KitItemIn, KitItemOut, VendorCreate, VendorOut, VendorUpdate, ViolationOut,
    ViolationPage,
)
from database.session import SessionLocal

ppe_router = APIRouter(prefix="/api/ppe", tags=["PPE Vendor Kits"],
                       dependencies=[Depends(get_current_user)])

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


def _validate_ranges(ranges) -> None:
    """
    Rejects malformed HSV ranges at the edge.

    A range with a low bound above its high bound matches nothing, silently:
    the colour simply never fires and the vendor is never identified, with no
    error anywhere. Catching it here turns a mystery into a 422.
    """
    if not isinstance(ranges, list) or not ranges:
        raise HTTPException(422, "At least one HSV range is required.")
    for pair in ranges:
        if (not isinstance(pair, list) or len(pair) != 2
                or any(not isinstance(b, list) or len(b) != 3 for b in pair)):
            raise HTTPException(422, "Each range must be [[h,s,v],[h,s,v]].")
        lo, hi = pair
        for i, (a, b, limit) in enumerate(zip(lo, hi, (HUE_MAX, 255, 255))):
            if not (0 <= a <= limit and 0 <= b <= limit):
                raise HTTPException(
                    422, f"Channel {i} out of range (0-{limit}); hue is 0-{HUE_MAX} in OpenCV.")
            if a > b:
                raise HTTPException(
                    422, f"Lower bound {a} exceeds upper bound {b} in channel {i}; "
                         "this range would match nothing. Split a colour that wraps "
                         "the hue boundary into two ranges instead.")


def _colour_out(c, in_use: int = 0) -> ColourOut:
    return ColourOut(
        colour_id=c.colour_id, name=c.name, hsv_ranges=c.hsv_ranges or [],
        display_hex=c.display_hex, calibrated_on_camera=c.calibrated_on_camera,
        calibrated_at=c.calibrated_at,
        calibration_samples=c.calibration_samples or 0,
        wraps_hue=len(c.hsv_ranges or []) > 1, in_use_by=in_use, notes=c.notes,
    )


def _vendor_out(v) -> VendorOut:
    return VendorOut(
        vendor_id=v.vendor_id, name=v.name, code=v.code, contact=v.contact,
        display_hex=v.display_hex, is_active=bool(v.is_active), notes=v.notes,
        kit_items=[
            KitItemOut(
                item_id=i.item_id, colour_id=i.colour_id,
                colour_name=i.colour.name if i.colour else None,
                item_type=i.item_type, body_region=i.body_region,
                is_required=bool(i.is_required), min_coverage=float(i.min_coverage or 0),
            ) for i in v.kit_items
        ],
    )


# ===================================================================== #
# Reference data
# ===================================================================== #
@ppe_router.get("/meta")
def meta():
    """The vocabulary the UI builds its dropdowns from."""
    return {
        "item_types": list(ITEM_TYPES),
        "body_regions": {k: {"from": v[0], "to": v[1]} for k, v in BODY_REGIONS.items()},
        "violation_types": list(VIOLATION_TYPES),
        "hue_max": HUE_MAX,
        "catalogue_configured": kit_catalogue.configured,
    }


# ===================================================================== #
# Colours
# ===================================================================== #
@ppe_router.get("/colours", response_model=List[ColourOut])
def list_colours(db: Session = Depends(get_db)):
    repo = PPERepository(db)
    return [_colour_out(c, repo.colour_in_use(c.colour_id)) for c in repo.list_colours()]


@ppe_router.post("/colours", response_model=ColourOut,
                 dependencies=[require_permissions([perms.PPE_CONFIG])])
def create_colour(body: ColourCreate, db: Session = Depends(get_db)):
    _validate_ranges(body.hsv_ranges)
    repo = PPERepository(db)
    if repo.get_colour_by_name(body.name):
        raise HTTPException(409, detail={
            "code": "duplicate_name",
            "message": f"A colour called '{body.name}' already exists.",
        })
    row = repo.create_colour(
        name=body.name.strip(), hsv_ranges=body.hsv_ranges,
        display_hex=body.display_hex, notes=body.notes,
        calibrated_on_camera=body.calibrated_on_camera,
        calibrated_at=datetime.utcnow() if body.calibrated_on_camera else None,
    )
    kit_catalogue.invalidate()
    return _colour_out(row)


@ppe_router.delete("/colours/{colour_id}",
                   dependencies=[require_permissions([perms.PPE_CONFIG])])
def delete_colour(colour_id: str, db: Session = Depends(get_db)):
    repo = PPERepository(db)
    used = repo.colour_in_use(colour_id)
    if used:
        # Deleting it would leave kit items pointing at nothing, and those
        # vendors would silently stop being identified.
        raise HTTPException(409, detail={
            "code": "colour_in_use",
            "message": f"This colour is used by {used} kit item(s). "
                       "Remove those first.",
        })
    if not repo.delete_colour(colour_id):
        raise HTTPException(404, "No such colour.")
    kit_catalogue.invalidate()
    return {"status": "deleted", "colour_id": colour_id}


# ===================================================================== #
# Calibration
# ===================================================================== #
def _decode(data: bytes):
    try:
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


async def _read(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image too large.")
    if not data:
        raise HTTPException(400, "Empty upload.")
    return data


def _calibration_response(patch, db) -> CalibrationResult:
    result = calibrate(patch)
    if result is None:
        return CalibrationResult(
            ok=False,
            message="No coherent colour in that area — it looks like shadow, "
                    "glare or background. Select the garment itself.",
        )
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    existing = {}
    for c in PPERepository(db).list_colours():
        got = coverage(hsv, c.hsv_ranges or [])
        if got > 0.05:
            existing[c.name] = round(got, 3)
    return CalibrationResult(
        ok=True,
        message=("This area is already covered by an existing colour."
                 if existing else "Colour derived from the sample."),
        hsv_ranges=result["hsv_ranges"], display_hex=result["display_hex"],
        hue_centre=result["hue_centre"], hue_spread=result["hue_spread"],
        wraps_hue=result["wraps_hue"], sample_pixels=result["sample_pixels"],
        coverage_of_sample=result["coverage_of_sample"],
        matches_existing=existing,
    )


@ppe_router.post("/calibrate/upload", response_model=CalibrationResult,
                 dependencies=[require_permissions([perms.PPE_CONFIG])])
async def calibrate_upload(
    file: UploadFile = File(...),
    x1: Optional[int] = Form(None), y1: Optional[int] = Form(None),
    x2: Optional[int] = Form(None), y2: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Derive a colour from a photo of the actual garment.

    Optionally restricted to a rectangle, which is how the UI lets an operator
    drag a box over just the vest.
    """
    image = _decode(await _read(file))
    if image is None:
        raise HTTPException(422, "That file is not a readable image.")
    if None not in (x1, y1, x2, y2):
        h, w = image.shape[:2]
        ax1, ay1 = max(0, min(x1, x2)), max(0, min(y1, y2))
        ax2, ay2 = min(w, max(x1, x2)), min(h, max(y1, y2))
        if ax2 - ax1 < 4 or ay2 - ay1 < 4:
            raise HTTPException(422, "The selected area is too small.")
        image = image[ay1:ay2, ax1:ax2]
    return _calibration_response(image, db)


@ppe_router.post("/calibrate/camera", response_model=CalibrationResult,
                 dependencies=[require_permissions([perms.PPE_CONFIG])])
def calibrate_from_camera(
    camera_id: str = Query(...),
    region: str = Query("TORSO", pattern="^(HEAD|TORSO|LEGS|FULL)$"),
    db: Session = Depends(get_db),
):
    """
    Calibrate from what the camera is showing right now.

    This is the "under actual site conditions" path: it grabs a live frame
    from the running stream and samples the requested body region of the
    largest person in it, so the numbers come from that camera's own lighting
    rather than from a photograph taken on a phone.
    """
    from core.state import LATEST_DATA

    state = LATEST_DATA.get(camera_id)
    if not state:
        raise HTTPException(404, detail={
            "code": "camera_not_live",
            "message": "That camera is not currently producing analytics.",
        })

    boxes = [d for d in (state.get("detections") or [])
             if int(getattr(d, "class_id", d.get("class_id", -1) if isinstance(d, dict) else -1)) == 0]
    if not boxes:
        raise HTTPException(422, detail={
            "code": "no_person",
            "message": "No person is visible on that camera right now. "
                       "Ask someone in the kit to stand in view and try again.",
        })

    frame = _grab_frame(camera_id)
    if frame is None:
        raise HTTPException(503, detail={
            "code": "no_frame",
            "message": "Could not grab a frame from that camera's stream.",
        })

    def _box(d):
        return d.bbox if hasattr(d, "bbox") else d.get("bbox", [0, 0, 0, 0])

    largest = max(boxes, key=lambda d: (_box(d)[3] - _box(d)[1]))
    rect = region_slice(_box(largest), region, frame.shape)
    if rect is None:
        raise HTTPException(422, "The person is too small to sample.")
    rx1, ry1, rx2, ry2 = rect
    return _calibration_response(frame[ry1:ry2, rx1:rx2], db)


def _grab_frame(camera_id: str):
    """Pulls one frame from the camera's own output stream."""
    try:
        cap = cv2.VideoCapture(f"rtsp://localhost:8554/{camera_id}", cv2.CAP_FFMPEG)
        frame = None
        for _ in range(15):
            ok, f = cap.read()
            if ok and f is not None:
                frame = f
        cap.release()
        return frame
    except Exception as exc:
        logger.warning(f"PPE calibration frame grab failed for {camera_id}: {exc}")
        return None


# ===================================================================== #
# Vendors and kits
# ===================================================================== #
@ppe_router.get("/vendors", response_model=List[VendorOut])
def list_vendors(include_inactive: bool = False, db: Session = Depends(get_db)):
    rows = PPERepository(db).list_vendors(active_only=not include_inactive)
    return [_vendor_out(v) for v in rows]


@ppe_router.post("/vendors", response_model=VendorOut,
                 dependencies=[require_permissions([perms.PPE_CONFIG])])
def create_vendor(body: VendorCreate, db: Session = Depends(get_db)):
    repo = PPERepository(db)
    for c in repo.list_vendors(active_only=False):
        if c.name.strip().lower() == body.name.strip().lower():
            raise HTTPException(409, detail={
                "code": "duplicate_vendor",
                "message": f"A vendor called '{body.name}' already exists.",
            })
    for item in body.kit_items:
        if repo.get_colour(item.colour_id) is None:
            raise HTTPException(422, f"Unknown colour {item.colour_id}.")

    vendor = repo.create_vendor(
        name=body.name.strip(), code=body.code, contact=body.contact,
        display_hex=body.display_hex, notes=body.notes, is_active=True,
    )
    for item in body.kit_items:
        repo.add_kit_item(vendor.vendor_id, **item.model_dump())
    kit_catalogue.invalidate()
    return _vendor_out(repo.get_vendor(vendor.vendor_id))


@ppe_router.patch("/vendors/{vendor_id}", response_model=VendorOut,
                  dependencies=[require_permissions([perms.PPE_CONFIG])])
def update_vendor(vendor_id: str, body: VendorUpdate, db: Session = Depends(get_db)):
    repo = PPERepository(db)
    vendor = repo.get_vendor(vendor_id)
    if vendor is None:
        raise HTTPException(404, "No such vendor.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(vendor, k, v)
    db.commit()
    kit_catalogue.invalidate()
    return _vendor_out(repo.get_vendor(vendor_id))


@ppe_router.delete("/vendors/{vendor_id}",
                   dependencies=[require_permissions([perms.PPE_CONFIG])])
def delete_vendor(vendor_id: str, db: Session = Depends(get_db)):
    if not PPERepository(db).delete_vendor(vendor_id):
        raise HTTPException(404, "No such vendor.")
    kit_catalogue.invalidate()
    return {"status": "deleted", "vendor_id": vendor_id}


@ppe_router.post("/vendors/{vendor_id}/kit", response_model=VendorOut,
                 dependencies=[require_permissions([perms.PPE_CONFIG])])
def add_kit_item(vendor_id: str, body: KitItemIn, db: Session = Depends(get_db)):
    repo = PPERepository(db)
    if repo.get_vendor(vendor_id) is None:
        raise HTTPException(404, "No such vendor.")
    if repo.get_colour(body.colour_id) is None:
        raise HTTPException(422, f"Unknown colour {body.colour_id}.")
    try:
        repo.add_kit_item(vendor_id, **body.model_dump())
    except Exception:
        db.rollback()
        raise HTTPException(409, detail={
            "code": "duplicate_item",
            "message": f"This vendor already has a {body.item_type} "
                       f"defined for {body.body_region}.",
        })
    kit_catalogue.invalidate()
    return _vendor_out(repo.get_vendor(vendor_id))


@ppe_router.delete("/kit/{item_id}",
                   dependencies=[require_permissions([perms.PPE_CONFIG])])
def delete_kit_item(item_id: str, db: Session = Depends(get_db)):
    if not PPERepository(db).delete_kit_item(item_id):
        raise HTTPException(404, "No such kit item.")
    kit_catalogue.invalidate()
    return {"status": "deleted", "item_id": item_id}


# ===================================================================== #
# Camera-wise configuration
# ===================================================================== #
@ppe_router.get("/cameras", response_model=List[CameraConfigOut])
def list_camera_configs(db: Session = Depends(get_db)):
    repo = PPERepository(db)
    names = {v.vendor_id: v.name for v in repo.list_vendors(active_only=False)}
    out = []
    for cfg in repo.list_camera_configs():
        ids = cfg.expected_vendor_ids or []
        out.append(CameraConfigOut(
            camera_id=cfg.camera_id, expected_vendor_ids=ids,
            expected_vendor_names=[names.get(i, i) for i in ids],
            enforce=bool(cfg.enforce), alert_on=cfg.alert_on or [],
            severity=cfg.severity, alert_cooldown_sec=float(cfg.alert_cooldown_sec or 30),
            min_person_px=int(cfg.min_person_px or 80),
        ))
    return out


@ppe_router.put("/cameras/{camera_id}", response_model=CameraConfigOut,
                dependencies=[require_permissions([perms.PPE_CONFIG])])
def set_camera_config(camera_id: str, body: CameraConfigIn,
                      db: Session = Depends(get_db)):
    repo = PPERepository(db)
    fields = body.model_dump(exclude_unset=True)

    for vid in fields.get("expected_vendor_ids") or []:
        if repo.get_vendor(vid) is None:
            raise HTTPException(422, f"Unknown vendor {vid}.")
    for v in fields.get("alert_on") or []:
        if v not in VIOLATION_TYPES:
            raise HTTPException(422, f"Unknown violation type {v}.")

    # expected_vendor_ids and alert_on must be settable to an empty list —
    # "expect nobody in particular" and "alert on nothing" are both meaningful,
    # and upsert skips None, so pass them explicitly.
    cfg = repo.upsert_camera_config(camera_id, **fields)
    if "expected_vendor_ids" in fields:
        cfg.expected_vendor_ids = fields["expected_vendor_ids"]
    if "alert_on" in fields:
        cfg.alert_on = fields["alert_on"]
    if "enforce" in fields:
        cfg.enforce = bool(fields["enforce"])
    db.commit()
    db.refresh(cfg)
    kit_catalogue.invalidate()

    names = {v.vendor_id: v.name for v in repo.list_vendors(active_only=False)}
    ids = cfg.expected_vendor_ids or []
    return CameraConfigOut(
        camera_id=cfg.camera_id, expected_vendor_ids=ids,
        expected_vendor_names=[names.get(i, i) for i in ids],
        enforce=bool(cfg.enforce), alert_on=cfg.alert_on or [],
        severity=cfg.severity, alert_cooldown_sec=float(cfg.alert_cooldown_sec or 30),
        min_person_px=int(cfg.min_person_px or 80),
    )


@ppe_router.delete("/cameras/{camera_id}",
                   dependencies=[require_permissions([perms.PPE_CONFIG])])
def clear_camera_config(camera_id: str, db: Session = Depends(get_db)):
    if not PPERepository(db).delete_camera_config(camera_id):
        raise HTTPException(404, "No configuration for that camera.")
    kit_catalogue.invalidate()
    return {"status": "cleared", "camera_id": camera_id}


# ===================================================================== #
# Violations
# ===================================================================== #
@ppe_router.get("/violations", response_model=ViolationPage)
def list_violations(
    camera_id: Optional[str] = None,
    violation_type: Optional[str] = None,
    vendor_id: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows, total = PPERepository(db).list_violations(
        camera_id=camera_id, violation_type=violation_type, vendor_id=vendor_id,
        start=start, end=end, limit=limit, offset=offset,
    )
    return ViolationPage(total=total, items=[
        ViolationOut(
            violation_id=r.violation_id, camera_id=r.camera_id,
            camera_name=r.camera_name, violation_type=r.violation_type,
            severity=r.severity, timestamp=r.timestamp, vendor_id=r.vendor_id,
            vendor_name=r.vendor_name, snapshot_file=_url(r.snapshot_path),
            evidence=r.evidence,
        ) for r in rows
    ])
