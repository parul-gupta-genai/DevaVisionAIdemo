"""Request and response shapes for the restricted-zone API."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.plugins.zones.geometry import ANCHORS, MAX_ZONE_POINTS, MIN_ZONE_POINTS


class ScheduleWindow(BaseModel):
    start: str = Field(..., description="24h local time, HH:MM")
    end: str = Field(..., description="24h local time, HH:MM; earlier than start wraps past midnight")
    days: Optional[List[int]] = Field(
        default=None, description="0=Mon .. 6=Sun; empty or null means every day")


class ZoneBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    points: List[Any] = Field(..., min_length=MIN_ZONE_POINTS, max_length=MAX_ZONE_POINTS,
                              description="Polygon vertices in 1280x720 mux space")
    is_active: bool = True
    object_classes: Optional[List[int]] = Field(
        default=None, description="COCO class ids to watch; defaults to [0] (person)")
    min_confidence: float = Field(default=0.4, ge=0.0, le=1.0)
    anchor: str = Field(default="FEET", description=f"One of {', '.join(ANCHORS)}")
    min_box_px: int = Field(default=0, ge=0, le=720)
    schedule: Optional[List[ScheduleWindow]] = None
    min_dwell_sec: float = Field(default=2.0, ge=0.0, le=3600.0)
    loiter_sec: Optional[float] = Field(default=None, ge=1.0, le=86400.0)
    exit_grace_sec: float = Field(default=3.0, ge=0.0, le=600.0)
    alert_cooldown_sec: float = Field(default=30.0, ge=0.0, le=86400.0)
    severity: str = Field(default="warning")
    notes: Optional[str] = None


class ZoneCreate(ZoneBase):
    camera_id: str = Field(..., min_length=1)


class ZoneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    points: Optional[List[Any]] = None
    is_active: Optional[bool] = None
    object_classes: Optional[List[int]] = None
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    anchor: Optional[str] = None
    min_box_px: Optional[int] = Field(default=None, ge=0, le=720)
    schedule: Optional[List[ScheduleWindow]] = None
    # Explicit flag, because `schedule: null` in a PATCH body is
    # indistinguishable from an omitted field and "armed around the clock" is
    # a setting an operator must be able to choose deliberately.
    clear_schedule: bool = False
    min_dwell_sec: Optional[float] = Field(default=None, ge=0.0, le=3600.0)
    loiter_sec: Optional[float] = Field(default=None, ge=1.0, le=86400.0)
    clear_loiter: bool = False
    exit_grace_sec: Optional[float] = Field(default=None, ge=0.0, le=600.0)
    alert_cooldown_sec: Optional[float] = Field(default=None, ge=0.0, le=86400.0)
    severity: Optional[str] = None
    notes: Optional[str] = None


class ZoneOut(BaseModel):
    zone_id: str
    camera_id: str
    camera_name: Optional[str] = None
    name: str
    points: List[Any]
    is_active: bool
    object_classes: List[int]
    class_names: List[str]
    min_confidence: float
    anchor: str
    min_box_px: int
    schedule: Optional[List[Dict[str, Any]]] = None
    schedule_text: str
    armed_now: bool
    armed_changes_at: Optional[datetime] = None
    min_dwell_sec: float
    loiter_sec: Optional[float] = None
    exit_grace_sec: float
    alert_cooldown_sec: float
    severity: str
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # True when another enabled plugin owns evaluation for this camera, so
    # the UI can explain why a zone is live under a different name.
    evaluated_by: Optional[str] = None


class ZoneEventOut(BaseModel):
    event_id: str
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    event_type: str
    severity: Optional[str] = None
    timestamp: datetime
    started_at: Optional[datetime] = None
    dwell_seconds: Optional[float] = None
    track_id: Optional[str] = None
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[List[Any]] = None
    snapshot_url: Optional[str] = None
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    ack_note: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ZoneEventPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[ZoneEventOut]


class AckRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class ZoneTestRequest(BaseModel):
    """A point or box to check against a zone, for commissioning."""
    bbox: Optional[List[float]] = Field(
        default=None, description="[x1, y1, x2, y2] in mux space")
    point: Optional[List[float]] = Field(
        default=None, description="[x, y] in mux space; treated as a zero-size box")
    at: Optional[datetime] = Field(
        default=None, description="Local time to evaluate the schedule at; defaults to now")


class ZoneTestResult(BaseModel):
    zone_id: str
    zone_name: str
    inside: bool
    armed: bool
    would_alert: bool
    reason: str
    anchor: str
    anchor_point: List[float]
    evaluated_at: datetime
    schedule_text: str


class ZoneCoverage(BaseModel):
    """What zone monitoring is actually doing across the site."""
    cameras_with_plugin: int
    cameras_with_zones: int
    cameras_missing_zones: List[str]
    total_zones: int
    armed_now: int
    legacy_config_cameras: List[str]
