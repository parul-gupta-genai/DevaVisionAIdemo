"""Contracts for the PPE vendor colour-kit catalogue."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

HSVRanges = List[List[List[int]]]


class ColourCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    # [[ [h,s,v], [h,s,v] ], ...] — several ranges so red can wrap the hue
    # boundary; validated in the router against the 0-179 hue space.
    hsv_ranges: HSVRanges
    display_hex: Optional[str] = None
    calibrated_on_camera: Optional[str] = None
    notes: Optional[str] = None


class ColourOut(BaseModel):
    colour_id: str
    name: str
    hsv_ranges: HSVRanges
    display_hex: Optional[str] = None
    calibrated_on_camera: Optional[str] = None
    calibrated_at: Optional[datetime] = None
    calibration_samples: int = 0
    wraps_hue: bool = False
    in_use_by: int = 0
    notes: Optional[str] = None


class KitItemIn(BaseModel):
    colour_id: str
    item_type: str = Field("VEST", pattern="^(HELMET|VEST|JACKET|TROUSERS|GLOVES|BOOTS|OTHER)$")
    body_region: str = Field("TORSO", pattern="^(HEAD|TORSO|LEGS|FULL)$")
    is_required: bool = True
    min_coverage: float = Field(0.12, ge=0.0, le=1.0)


class KitItemOut(KitItemIn):
    item_id: str
    colour_name: Optional[str] = None


class VendorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    code: Optional[str] = None
    contact: Optional[str] = None
    display_hex: Optional[str] = None
    notes: Optional[str] = None
    kit_items: List[KitItemIn] = []


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    contact: Optional[str] = None
    display_hex: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class VendorOut(BaseModel):
    vendor_id: str
    name: str
    code: Optional[str] = None
    contact: Optional[str] = None
    display_hex: Optional[str] = None
    is_active: bool = True
    notes: Optional[str] = None
    kit_items: List[KitItemOut] = []


class CameraConfigIn(BaseModel):
    expected_vendor_ids: Optional[List[str]] = None
    enforce: Optional[bool] = None
    alert_on: Optional[List[str]] = None
    severity: Optional[str] = Field(None, pattern="^(critical|warning|info)$")
    alert_cooldown_sec: Optional[float] = Field(None, ge=0.0, le=3600.0)
    min_person_px: Optional[int] = Field(None, ge=20, le=1000)


class CameraConfigOut(BaseModel):
    camera_id: str
    camera_name: Optional[str] = None
    expected_vendor_ids: List[str] = []
    expected_vendor_names: List[str] = []
    enforce: bool = True
    alert_on: List[str] = []
    severity: str = "warning"
    alert_cooldown_sec: float = 30.0
    min_person_px: int = 80


class ViolationOut(BaseModel):
    violation_id: str
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    violation_type: str
    severity: Optional[str] = None
    timestamp: datetime
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    snapshot_file: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None


class ViolationPage(BaseModel):
    total: int
    items: List[ViolationOut]


class CalibrationResult(BaseModel):
    ok: bool
    message: str
    hsv_ranges: Optional[HSVRanges] = None
    display_hex: Optional[str] = None
    hue_centre: Optional[float] = None
    hue_spread: Optional[float] = None
    wraps_hue: bool = False
    sample_pixels: int = 0
    coverage_of_sample: float = 0.0
    # How much of the sampled region each EXISTING colour already claims, so
    # an operator can see they are about to define a duplicate.
    matches_existing: Dict[str, float] = {}
