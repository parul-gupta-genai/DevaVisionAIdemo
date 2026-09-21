from typing import List, Optional

from pydantic import BaseModel


class IntrusionEventSchema(BaseModel):
    """
    One intrusion as the pipeline reports it.

    Kept for the legacy shape; the authoritative record is ZoneEvent in
    app/plugins/zones/models.py, which also carries the zone, the rule that
    fired and the dwell time.
    """
    camera_id: str
    timestamp: float
    confidence: float
    track_id: int
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    severity: Optional[str] = None
    dwell_seconds: Optional[float] = None
    snapshot_path: Optional[str] = None
    zone_coords: List[List[int]] = []
