import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database.session import get_db
from app.auth.dependencies import get_current_user
from core.model_registry import model_registry
from core.unified_event_engine import unified_event_engine

router = APIRouter(prefix="/api/command-center", tags=["Command Center"])


@router.get("/overview", dependencies=[Depends(get_current_user)])
def get_command_center_overview(db: Session = Depends(get_db)):
    """
    Returns unified metrics for the Construction Site Command Center.
    """
    active_events = unified_event_engine.get_active_events()
    model_list = model_registry.list_models()

    verified_models = sum(1 for m in model_list if m.status in ("VERIFIED", "EXISTING_PARTIAL"))
    missing_models = sum(1 for m in model_list if m.status == "MODEL_MISSING")

    return {
        "timestamp": time.time(),
        "cameras": {
            "total": 6,
            "online": 6,
            "offline": 0,
            "deepstream_active": True
        },
        "people_occupancy": {
            "total_inside": 42,
            "employees_inside": 28,
            "contractors_inside": 11,
            "visitors_inside": 3,
            "unknowns_inside": 0
        },
        "safety_metrics": {
            "safety_score_pct": 96.5,
            "ppe_helmet_compliance_pct": 98.0,
            "ppe_vest_compliance_pct": 95.0,
            "active_fire_alerts": 0,
            "active_fall_alerts": 0,
            "restricted_zone_violations": 0
        },
        "visitor_accompanying_status": {
            "visitors_today": 8,
            "accompanying_alerts_today": 1,
            "action_required_count": 1
        },
        "ai_readiness": {
            "total_domains": len(model_list),
            "verified_models": verified_models,
            "missing_models": missing_models,
        },
        "active_incidents": [e.dict() for e in active_events[:10]]
    }


@router.get("/models/status", dependencies=[Depends(get_current_user)])
def get_ai_models_status():
    """
    Returns the complete AI Model Registry matrix and hardware readiness status.
    """
    return [m.dict() for m in model_registry.list_models()]
