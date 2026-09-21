import uuid
import numpy as np
from sqlalchemy.orm import Session
from typing import Optional, List, Tuple
from loguru import logger

from app.plugins.visitor.models import Visitor, Visit, VisitorEvent

def generate_visitor_id() -> str:
    return f"VIS-{uuid.uuid4().hex[:8].upper()}"

def generate_visit_id() -> str:
    return f"VT-{uuid.uuid4().hex[:8].upper()}"

def generate_event_id() -> str:
    return f"EV-{uuid.uuid4().hex[:8].upper()}"

def cosine_similarity(vec1: list, vec2: list) -> float:
    # Deprecated: Kept for legacy compatibility if needed
    if not vec1 or not vec2:
        return 0.0
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))

class VisitorRepository:
    def __init__(self, db_session: Session):
        self.db = db_session

    def get_visitor(self, visitor_id: str) -> Optional[Visitor]:
        return self.db.query(Visitor).filter(Visitor.visitor_id == visitor_id).first()
        
    def find_best_match(self, face_embedding: list, threshold: float = 0.5) -> Tuple[Optional[Visitor], float]:
        """
        Uses pgvector hardware-accelerated cosine distance search directly on the database.
        Returns the closest match (sim = 1 - distance) above the threshold.
        """
        distance_col = Visitor.face_embedding.cosine_distance(face_embedding)
        
        # 1. Prioritize REGISTERED visitors first
        result = (
            self.db.query(Visitor, distance_col.label('distance'))
            .filter(Visitor.face_embedding.isnot(None))
            .filter(Visitor.status == 'REGISTERED')
            .order_by('distance')
            .first()
        )
        
        if result:
            best_match, distance = result
            best_sim = 1.0 - float(distance)
            if best_sim >= threshold:
                return best_match, best_sim
                
        # 2. If no registered visitor found, check for an existing UNKNOWN visitor
        result = (
            self.db.query(Visitor, distance_col.label('distance'))
            .filter(Visitor.face_embedding.isnot(None))
            .filter(Visitor.status == 'UNKNOWN')
            .order_by('distance')
            .first()
        )
        
        if result:
            best_match, distance = result
            best_sim = 1.0 - float(distance)
            if best_sim >= threshold:
                return best_match, best_sim
            
        return None, -1.0

    def create_unknown_visitor(self, face_embedding: list = None, snapshot_path: str = None) -> Visitor:
        v_id = generate_visitor_id()
        db_visitor = Visitor(
            visitor_id=v_id,
            name="Unknown",
            face_embedding=face_embedding,
            photo=snapshot_path,
            status="UNKNOWN",
            total_visits=0
        )
        self.db.add(db_visitor)
        self.db.commit()
        self.db.refresh(db_visitor)
        return db_visitor

    def create_visit(self, visit_data: dict) -> Visit:
        db_visit = Visit(
            visit_id=generate_visit_id(),
            **visit_data
        )
        self.db.add(db_visit)
        
        # Update visitor stats
        visitor = self.get_visitor(visit_data["visitor_id"])
        if visitor:
            if not visitor.first_seen:
                visitor.first_seen = visit_data["entry_time"]
            visitor.last_seen = visit_data["entry_time"]
            visitor.total_visits += 1
            
        self.db.commit()
        self.db.refresh(db_visit)
        return db_visit

    def log_event(self, event_type: str, visitor_id: str, visit_id: str = None, camera: str = None, metadata: dict = None) -> VisitorEvent:
        db_event = VisitorEvent(
            event_id=generate_event_id(),
            visitor_id=visitor_id,
            visit_id=visit_id,
            event_type=event_type,
            camera=camera,
            metadata_=metadata
        )
        self.db.add(db_event)
        self.db.commit()
        self.db.refresh(db_event)
        return db_event
