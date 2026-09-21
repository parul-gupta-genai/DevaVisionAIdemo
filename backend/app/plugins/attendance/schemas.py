from pydantic import BaseModel

class AttendanceEventSchema(BaseModel):
    camera_id: str
    timestamp: float
    confidence: float
    employee_id: int
    action: str  # "CHECK IN" or "CHECK OUT"
