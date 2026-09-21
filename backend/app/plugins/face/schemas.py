"""Request/response contracts for the face module."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PersonBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    person_code: Optional[str] = Field(None, max_length=64)
    person_type: str = Field("EMPLOYEE", pattern="^(EMPLOYEE|VENDOR|CONTRACTOR)$")
    department: Optional[str] = None
    designation: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    person_code: Optional[str] = None
    person_type: Optional[str] = Field(None, pattern="^(EMPLOYEE|VENDOR|CONTRACTOR)$")
    department: Optional[str] = None
    designation: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class PersonOut(BaseModel):
    person_id: str
    person_code: Optional[str] = None
    name: str
    person_type: str
    department: Optional[str] = None
    designation: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    photo: Optional[str] = None
    enrolment_count: int = 0
    is_active: bool = True
    # False when the person exists but has no usable face on file, which is
    # the difference between "absent" and "never finished enrolment".
    enrolled: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PersonPage(BaseModel):
    total: int
    items: List[PersonOut]


class EnrolmentOut(BaseModel):
    enrolment_id: str
    person_id: str
    snapshot_path: Optional[str] = None
    det_score: Optional[float] = None
    face_width: Optional[int] = None
    face_height: Optional[int] = None
    sharpness: Optional[float] = None
    source: Optional[str] = None
    enrolled_by: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WatchlistCreate(BaseModel):
    person_id: str
    category: str = Field("BLACKLIST",
                          pattern="^(BLACKLIST|VIP|PERSON_OF_INTEREST|EX_EMPLOYEE)$")
    severity: str = Field("critical", pattern="^(critical|warning|info)$")
    reason: Optional[str] = None
    active_from: Optional[datetime] = None
    active_until: Optional[datetime] = None
    camera_ids: Optional[List[str]] = None
    is_active: bool = True


class WatchlistOut(BaseModel):
    entry_id: str
    person_id: str
    person_name: Optional[str] = None
    person_code: Optional[str] = None
    photo: Optional[str] = None
    category: str
    severity: str
    reason: Optional[str] = None
    active_from: Optional[datetime] = None
    active_until: Optional[datetime] = None
    camera_ids: Optional[List[str]] = None
    is_active: bool
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None


class FaceEventOut(BaseModel):
    event_id: str
    event_type: str
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    person_code: Optional[str] = None
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    timestamp: datetime
    similarity: Optional[float] = None
    severity: Optional[str] = None
    watchlist_category: Optional[str] = None
    snapshot_file: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class FaceEventPage(BaseModel):
    total: int
    items: List[FaceEventOut]


class AttendanceRow(BaseModel):
    person_id: str
    person_code: Optional[str] = None
    name: str
    person_type: str
    department: Optional[str] = None
    company: Optional[str] = None
    photo: Optional[str] = None
    work_date: date
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    check_in_camera: Optional[str] = None
    check_out_camera: Optional[str] = None
    total_hours: Optional[float] = None
    sightings: int = 0
    status: str = "PRESENT"


class AttendanceSummary(BaseModel):
    work_date: date
    enrolled: int
    present: int
    absent: int
    by_type: Dict[str, int]
    average_hours: Optional[float] = None
    rows: List[AttendanceRow]


class TuningOut(BaseModel):
    values: Dict[str, float]
    checkin_cameras: List[str]
    checkout_cameras: List[str]
    engine_available: bool
