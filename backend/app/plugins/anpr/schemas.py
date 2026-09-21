from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class WatchlistBase(BaseModel):
    plate_number: str
    list_type: str
    priority: int = 0
    notification_rules: Optional[Dict[str, Any]] = None
    expiry: Optional[float] = None
    reason: Optional[str] = None
    notes: Optional[str] = None

class WatchlistCreate(WatchlistBase):
    pass

class WatchlistUpdate(BaseModel):
    plate_number: Optional[str] = None
    list_type: Optional[str] = None
    priority: Optional[int] = None
    notification_rules: Optional[Dict[str, Any]] = None
    expiry: Optional[float] = None
    reason: Optional[str] = None
    notes: Optional[str] = None

class WatchlistResponse(WatchlistBase):
    id: str
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True

class ANPREventResponse(BaseModel):
    id: str
    event_type: str
    plate_number: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: float
    camera_id: str
    track_id: Optional[str] = None
    recognition_time_ms: Optional[float] = None
    ocr_confidence: Optional[float] = None
    detection_confidence: Optional[float] = None
    metadata_json: Optional[Dict[str, Any]] = None

    class Config:
        orm_mode = True
        from_attributes = True

class PlateHistoryResponse(BaseModel):
    id: str
    plate_number: str
    confidence: float
    timestamp: float
    camera_id: str
    track_id: Optional[str] = None
    vehicle_snapshot: Optional[str] = None
    plate_snapshot: Optional[str] = None
    direction: Optional[str] = None
    lane: Optional[str] = None

    class Config:
        orm_mode = True
        from_attributes = True

class PlateStatisticsResponse(BaseModel):
    total_reads_today: int
    unique_vehicles: int
    watchlist_matches: int
    average_accuracy: float

    class Config:
        orm_mode = True
        from_attributes = True


# ---- Gate-wise ANPR setup (SOW 2.6) --------------------------------------

class GateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    role: str = Field(default="BIDIRECTIONAL",
                      description="ENTRY, EXIT or BIDIRECTIONAL")
    axis: str = Field(default="VERTICAL",
                      description="Axis a bidirectional gate infers direction along")
    invert: bool = Field(default=False,
                         description="Set when the camera faces the other way")
    min_travel_px: float = Field(
        default=40.0, ge=0.0, le=1280.0,
        description="Below this a vehicle is treated as not having moved")
    # {"allow": [...], "deny": [...], "unlisted": "ALLOW"|"DENY"}
    access_rules: Optional[Dict[str, Any]] = None
    is_active: bool = True
    notes: Optional[str] = None


class GateCreate(GateBase):
    camera_id: str = Field(..., min_length=1)


class GateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    role: Optional[str] = None
    axis: Optional[str] = None
    invert: Optional[bool] = None
    min_travel_px: Optional[float] = Field(default=None, ge=0.0, le=1280.0)
    access_rules: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class GateResponse(BaseModel):
    gate_id: str
    name: str
    camera_id: str
    role: str
    axis: str
    invert: bool
    min_travel_px: float
    access_rules: Dict[str, Any]
    rules_text: str
    is_active: bool
    notes: Optional[str] = None


class GateTestRequest(BaseModel):
    """Commissioning probe: what would this gate do with this vehicle?"""
    plate_number: Optional[str] = None
    # Overrides the watchlist lookup, for testing a rule before the vehicle
    # is on any list.
    list_type: Optional[str] = None
    first_point: Optional[List[float]] = None
    last_point: Optional[List[float]] = None
