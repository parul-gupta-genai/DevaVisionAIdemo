"""Request and response shapes for the fight/quarrel API."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.plugins.fight.rules import SENSITIVITIES, SEVERITIES
from app.plugins.zones.geometry import MAX_ZONE_POINTS, MIN_ZONE_POINTS

VERDICTS = ("confirmed", "dismissed")


class ScheduleWindow(BaseModel):
    start: str = Field(..., description="24h local time, HH:MM")
    end: str = Field(..., description="24h local time, HH:MM; earlier than start wraps past midnight")
    days: Optional[List[int]] = Field(
        default=None, description="0=Mon .. 6=Sun; empty or null means every day")


class FightZoneBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    points: List[Any] = Field(..., min_length=MIN_ZONE_POINTS, max_length=MAX_ZONE_POINTS,
                              description="Polygon vertices in 1280x720 mux space")
    zone_kind: str = Field(default="DETECT",
                           description="DETECT watches the area; EXCLUDE silences it")
    is_active: bool = True
    sensitivity: str = Field(default="standard",
                             description=f"One of {', '.join(SENSITIVITIES)}")
    severity: Optional[str] = None
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    min_frames: Optional[int] = Field(default=None, ge=1, le=300)
    confirm_sec: Optional[float] = Field(default=None, ge=0.0, le=600.0)
    engage_separation: Optional[float] = Field(default=None, gt=0.0, le=10.0)
    clear_sec: Optional[float] = Field(default=None, ge=1.0, le=3600.0)
    alert_cooldown_sec: Optional[float] = Field(default=None, ge=0.0, le=86400.0)
    schedule: Optional[List[ScheduleWindow]] = None
    notes: Optional[str] = None


class FightZoneCreate(FightZoneBase):
    camera_id: str = Field(..., min_length=1)


class FightZoneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    points: Optional[List[Any]] = None
    zone_kind: Optional[str] = None
    is_active: Optional[bool] = None
    sensitivity: Optional[str] = None
    severity: Optional[str] = None
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    min_frames: Optional[int] = Field(default=None, ge=1, le=300)
    confirm_sec: Optional[float] = Field(default=None, ge=0.0, le=600.0)
    engage_separation: Optional[float] = Field(default=None, gt=0.0, le=10.0)
    clear_sec: Optional[float] = Field(default=None, ge=1.0, le=3600.0)
    alert_cooldown_sec: Optional[float] = Field(default=None, ge=0.0, le=86400.0)
    schedule: Optional[List[ScheduleWindow]] = None
    clear_schedule: bool = False
    clear_overrides: bool = False
    notes: Optional[str] = None


class FightZoneOut(BaseModel):
    zone_id: str
    camera_id: str
    camera_name: Optional[str] = None
    name: str
    points: List[Any]
    zone_kind: str
    is_active: bool
    sensitivity: str
    severity: Optional[str] = None
    effective_severity: str
    tuning: Dict[str, Any]
    tuning_text: str
    overrides: Dict[str, Any]
    schedule: Optional[List[Dict[str, Any]]] = None
    schedule_text: str
    armed_now: bool
    armed_changes_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FightEventOut(BaseModel):
    event_id: str
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    event_type: str
    severity: Optional[str] = None
    timestamp: datetime
    started_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    score: Optional[float] = None
    track_ids: Optional[List[Any]] = None
    bbox: Optional[List[Any]] = None
    snapshot_file: Optional[str] = None
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    ack_note: Optional[str] = None
    verified: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    description: Optional[str] = None


class AckRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=1000)


class VerifyRequest(BaseModel):
    """A human's judgement on an indication. The module cannot make this call."""

    verdict: str = Field(..., description=f"One of {', '.join(VERDICTS)}")
    note: Optional[str] = Field(default=None, max_length=1000)


class FightTestRequest(BaseModel):
    """A hypothetical pair, for commissioning without staging a fight."""

    boxes: Optional[List[List[float]]] = Field(
        default=None, description="Two person boxes [[x1,y1,x2,y2], [...]]")
    point: Optional[List[float]] = Field(default=None, description="[x,y]")
    score: float = Field(default=0.8, ge=0.0, le=1.0)
    at: Optional[datetime] = None


class FightTestResult(BaseModel):
    zone_id: str
    zone_name: str
    inside: bool
    armed: bool
    engaged: Optional[bool] = None
    separation: Optional[float] = None
    would_alert: bool
    reason: str
    confirm_after: str
    evaluated_at: datetime
    schedule_text: str
    advisory_notice: str


class FightCoverage(BaseModel):
    cameras_with_zones: int
    zones: int
    detect_zones: int
    exclude_zones: int
    cameras_watching_whole_frame: int
    plugin_enabled_cameras: int
    advisory_notice: str
