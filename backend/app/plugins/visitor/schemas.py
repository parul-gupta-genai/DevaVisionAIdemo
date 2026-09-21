from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class VisitorBase(BaseModel):
    google_form_submission_id: Optional[str] = None
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    photo: Optional[str] = None
    role: Optional[str] = "VISITOR"
    company: Optional[str] = None
    purpose: Optional[str] = None
    vehicle_number: Optional[str] = None
    id_document_number: Optional[str] = None
    host_employee_id: Optional[str] = None
    host_name: Optional[str] = None
    expected_accompanying_persons: int = 0

class VisitorCreate(VisitorBase):
    pass

class VisitorRegisterRequest(VisitorBase):
    photo_front: str # Base64 image
    photo_left: str # Base64 image
    photo_right: str # Base64 image

class VisitorResponse(VisitorBase):
    visitor_id: str
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    total_visits: int
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class VisitBase(BaseModel):
    visitor_id: str
    entry_time: datetime
    camera_id: str
    track_id: str
    snapshot_path: Optional[str] = None
    confidence: Optional[float] = None

class VisitResponse(VisitBase):
    visit_id: str
    exit_time: Optional[datetime] = None
    duration: Optional[float] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class VisitorEventResponse(BaseModel):
    event_id: str
    visitor_id: str
    visit_id: Optional[str] = None
    event_type: str
    timestamp: datetime
    camera: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True

class PaginatedVisitorResponse(BaseModel):
    data: List[VisitorResponse]
    total: int
    page: int
    limit: int
