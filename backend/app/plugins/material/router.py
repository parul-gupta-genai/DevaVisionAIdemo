from fastapi import APIRouter, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

material_router = APIRouter(prefix="/api/plugins/material", tags=["Material & Anti-Theft AI"])

class OutboundGatePassRequest(BaseModel):
    stock_id: str
    quantity: float
    issued_to: str
    vehicle_number: str
    issued_by: Optional[str] = "Store Supervisor"

# In-memory realistic dataset for site material tracking & anti-theft
THEFT_ALERTS = [
    {
        "id": "ALT-THEFT-01",
        "title": "🚨 After-Hours Movement in Central Steel Yard",
        "category": "Night Theft",
        "severity": "Critical",
        "message": "Motion & human silhouette detected moving 16mm TMT Rebars at 02:40 AM (Store Closed Hours). No authorized gate pass exists.",
        "camera_name": "CCTV-04 (Yard #2 Night Vision PTZ)",
        "camera_id": "CAM-YARD-04",
        "timestamp": "2026-09-10T02:40:15",
        "snapshot_url": "https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=800&auto=format&fit=crop",
        "material_involved": "Tata Tiscon 550D TMT Rebar",
        "quantity": "~8 Bundles (Estimated)",
        "is_resolved": False
    },
    {
        "id": "ALT-THEFT-02",
        "title": "🚜 Vehicle Outbound Without Valid Gate-Pass",
        "category": "Unauthorized Exit",
        "severity": "High",
        "message": "Tractor trailer (HR26 DK 8921) crossed Outbound Line-2 loaded with 40 Cement Bags with NO registered digital gate pass.",
        "camera_name": "Gate-02 ANPR & Boom Barrier Cam",
        "camera_id": "CAM-GATE-02",
        "timestamp": "2026-09-10T13:15:00",
        "snapshot_url": "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=800&auto=format&fit=crop",
        "material_involved": "UltraTech OPC 53 Cement",
        "quantity": "40 Bags",
        "is_resolved": False
    },
    {
        "id": "ALT-THEFT-03",
        "title": "⚠️ Unloading Count Discrepancy (Shrinkage Alert)",
        "category": "Stock Discrepancy",
        "severity": "High",
        "message": "Delivery Bill (CH-89234) indicated 500 Bags, but CCTV AI Tripwire recorded only 460 Bags (Shortage: -40 Bags).",
        "camera_name": "Bay-01 Unloading Overhead AI Cam",
        "camera_id": "CAM-BAY-01",
        "timestamp": "2026-09-09T16:20:00",
        "snapshot_url": "https://images.unsplash.com/photo-1607344645866-009c320b5ab8?w=800&auto=format&fit=crop",
        "material_involved": "UltraTech OPC 53 Grade Cement",
        "quantity": "40 Bags Short",
        "is_resolved": True
    }
]

@material_router.get("/stats")
async def get_material_stats():
    """Returns aggregated Inbound, Outbound, Current Stock, and Alert Counts"""
    return {
        "total_in": 1540,
        "in_today": 500,
        "out_today": 320,
        "alerts": len(THEFT_ALERTS),
        "by_category": {
            "Cartons / Boxes": 42,
            "Cement Bags": 180,
            "Steel Bundles": 10,
            "Pipes": 60,
            "Tiles": 150,
            "Heavy Equipment": 25
        }
    }

@material_router.get("/alerts")
async def get_material_alerts(limit: int = Query(20, ge=1, le=100)):
    """Returns real-time AI Theft, Unauthorized Exit, and Discrepancy Alerts"""
    return THEFT_ALERTS[:limit]

@material_router.get("/events")
async def get_material_events(date: Optional[str] = None, limit: int = Query(200, ge=1, le=500)):
    """Returns detailed Inbound / Outbound movement logs"""
    now_iso = datetime.now().isoformat()
    return [
        {
            "id": "EVT-01",
            "material_type": "UltraTech OPC 53 Grade Cement",
            "event_type": "In",
            "quantity": 500,
            "timestamp": now_iso,
            "camera_name": "Gate-01 Inbound ANPR Cam",
            "camera_id": "CAM-GATE-01"
        },
        {
            "id": "EVT-02",
            "material_type": "UltraTech OPC 53 Grade Cement",
            "event_type": "Out",
            "quantity": 320,
            "timestamp": now_iso,
            "camera_name": "Store-01 Dispatch Bay",
            "camera_id": "CAM-STORE-01"
        }
    ]

@material_router.post("/issue-outward")
async def issue_material_outward(req: OutboundGatePassRequest):
    """Generates digital gate-pass and records outward material consumption"""
    return {
        "status": "success",
        "message": f"Gate-Pass generated for {req.quantity} units to {req.issued_to}",
        "timestamp": datetime.now().isoformat(),
        "gate_pass_id": f"GP-{int(datetime.now().timestamp())}"
    }
