import os
import json
import uuid
import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from loguru import logger

router = APIRouter(prefix="/api/provider", tags=["Solution Provider Hub"])
customer_router = APIRouter(prefix="/api/customer", tags=["Customer License & Billing"])

STATE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "provider_state.json"))

# Available AI Modules and Services in DevaVision AI
AVAILABLE_SERVICES = [
    {
        "id": "ppe_detection",
        "name": "Safety & PPE Compliance",
        "category": "Industrial Safety",
        "description": "Hardhat, safety vest, and worker safety gear monitoring.",
        "icon": "🦺",
        "basePrice": 1999
    },
    {
        "id": "fire_smoke",
        "name": "Fire & Smoke Early Warning",
        "category": "Disaster Prevention",
        "description": "Real-time flame and thermal smoke surge detection.",
        "icon": "🔥",
        "basePrice": 2499
    },
    {
        "id": "anpr_vehicles",
        "name": "ANPR & Vehicle Gate",
        "category": "Access Control",
        "description": "License plate extraction, parking, and barrier gate control.",
        "icon": "🚗",
        "basePrice": 2999
    },
    {
        "id": "face_attendance",
        "name": "Face Attendance & Watchlist",
        "category": "Biometrics",
        "description": "Staff recognition, blacklist alerts, and VIP arrival.",
        "icon": "👥",
        "basePrice": 1999
    },
    {
        "id": "visitor_vms",
        "name": "Visitor Management (VMS)",
        "category": "Visitor Security",
        "description": "Visitor badges, pre-registration, and path tracking.",
        "icon": "📋",
        "basePrice": 1499
    },
    {
        "id": "fight_violence",
        "name": "Fight & Violence Detection",
        "category": "Physical Security",
        "description": "Affray, physical altercations, and weapon detection.",
        "icon": "🥊",
        "basePrice": 2499
    },
    {
        "id": "restricted_zones",
        "name": "Restricted Zone Intrusion",
        "category": "Perimeter Security",
        "description": "Virtual tripwire and boundary trespass alarms.",
        "icon": "🚫",
        "basePrice": 1499
    },
    {
        "id": "voice_assistant",
        "name": "AI Voice Assistant",
        "category": "Conversational AI",
        "description": "Hands-free voice queries, HD TTS, and push alerts.",
        "icon": "🎙️",
        "basePrice": 999
    }
]

# Default Mock Seed Data if state file does not exist
def get_default_state() -> Dict[str, Any]:
    today = datetime.datetime.now()
    exp_1y = (today + datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    exp_3m = (today + datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    exp_1m = (today + datetime.timedelta(days=15)).strftime("%Y-%m-%d") # Expiring soon demo

    return {
        "customers": [
            {
                "id": "cust_101",
                "companyName": "Reliance Industrial Hub",
                "clientName": "Vikram Patel",
                "email": "v.patel@ril-hub.in",
                "phone": "+91 98765 43210",
                "siteLocation": "Hazira Manufacturing Complex, Gujarat",
                "maxCameras": 16,
                "activeCameras": 8,
                "licenseKey": "DEVA-CORP-7749-X9K1",
                "planName": "Enterprise Comprehensive",
                "duration": "1 Year",
                "startDate": today.strftime("%Y-%m-%d"),
                "expiryDate": exp_1y,
                "status": "Active",
                "enabledServices": [
                    "ppe_detection",
                    "fire_smoke",
                    "anpr_vehicles",
                    "face_attendance",
                    "visitor_vms",
                    "restricted_zones",
                    "voice_assistant"
                ],
                "monthlyFee": 14490,
                "createdAt": today.strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "id": "cust_102",
                "companyName": "Apex Logistics & Warehousing",
                "clientName": "Sunil Sharma",
                "email": "sunil.s@apexlogistics.com",
                "phone": "+91 98111 22334",
                "siteLocation": "Bhiwandi Hub 4, Mumbai",
                "maxCameras": 8,
                "activeCameras": 4,
                "licenseKey": "DEVA-PRO-3810-M2L4",
                "planName": "Logistics & Perimeter",
                "duration": "3 Months",
                "startDate": today.strftime("%Y-%m-%d"),
                "expiryDate": exp_3m,
                "status": "Active",
                "enabledServices": [
                    "anpr_vehicles",
                    "restricted_zones",
                    "fire_smoke",
                    "voice_assistant"
                ],
                "monthlyFee": 7996,
                "createdAt": today.strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "id": "cust_103",
                "companyName": "Grand Horizon Tech Park",
                "clientName": "Pooja Reddy",
                "email": "admin@horizonpark.co.in",
                "phone": "+91 99000 88776",
                "siteLocation": "Electronic City Phase 1, Bengaluru",
                "maxCameras": 24,
                "activeCameras": 12,
                "licenseKey": "DEVA-BIZ-9104-Z8P3",
                "planName": "Commercial Standard",
                "duration": "1 Month",
                "startDate": (today - datetime.timedelta(days=15)).strftime("%Y-%m-%d"),
                "expiryDate": exp_1m,
                "status": "Expiring Soon",
                "enabledServices": [
                    "face_attendance",
                    "visitor_vms",
                    "ppe_detection",
                    "voice_assistant"
                ],
                "monthlyFee": 6496,
                "createdAt": today.strftime("%Y-%m-%d %H:%M:%S")
            }
        ],
        "payments": [
            {
                "id": "INV-2026-0891",
                "customerId": "cust_101",
                "companyName": "Reliance Industrial Hub",
                "amount": 173880,
                "plan": "Enterprise Comprehensive (1 Year)",
                "paymentMethod": "UPI / NetBanking",
                "transactionId": "TXN_UPI_9824109283",
                "status": "Paid",
                "date": today.strftime("%Y-%m-%d %H:%M"),
                "expiryAfterPayment": exp_1y
            },
            {
                "id": "INV-2026-0874",
                "customerId": "cust_102",
                "companyName": "Apex Logistics & Warehousing",
                "amount": 23988,
                "plan": "Logistics & Perimeter (3 Months)",
                "paymentMethod": "Corporate Credit Card",
                "transactionId": "TXN_CARD_44910283",
                "status": "Paid",
                "date": (today - datetime.timedelta(days=5)).strftime("%Y-%m-%d %H:%M"),
                "expiryAfterPayment": exp_3m
            },
            {
                "id": "INV-2026-0850",
                "customerId": "cust_103",
                "companyName": "Grand Horizon Tech Park",
                "amount": 6496,
                "plan": "Commercial Standard (1 Month)",
                "paymentMethod": "Razorpay Direct",
                "transactionId": "TXN_RZP_1102938",
                "status": "Paid",
                "date": (today - datetime.timedelta(days=15)).strftime("%Y-%m-%d %H:%M"),
                "expiryAfterPayment": exp_1m
            }
        ]
    }

def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[Provider State] Failed to read {STATE_FILE}: {e}")
    state = get_default_state()
    save_state(state)
    return state

def save_state(state: Dict[str, Any]):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[Provider State] Failed to save {STATE_FILE}: {e}")

def generate_license_key(prefix: str = "DEVA") -> str:
    import random
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    part1 = "".join(random.choices(chars, k=4))
    part2 = "".join(random.choices(chars, k=4))
    part3 = "".join(random.choices(chars, k=4))
    return f"{prefix}-{part1}-{part2}-{part3}"

# ─── Pydantic Schemas ────────────────────────────────────────────────────────

class CustomerCreateRequest(BaseModel):
    companyName: str = Field(..., min_length=2)
    clientName: str = Field(..., min_length=2)
    email: str = Field(..., min_length=5)
    phone: Optional[str] = ""
    siteLocation: Optional[str] = "Main Facility"
    maxCameras: int = Field(8, ge=1, le=256)
    duration: str = Field("1 Year", description="1 Month, 3 Months, 6 Months, 1 Year, Lifetime, Custom")
    customExpiryDate: Optional[str] = None
    enabledServices: List[str] = Field(default_factory=list)

class CustomerUpdateRequest(BaseModel):
    companyName: Optional[str] = None
    clientName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    siteLocation: Optional[str] = None
    maxCameras: Optional[int] = None
    duration: Optional[str] = None
    customExpiryDate: Optional[str] = None
    enabledServices: Optional[List[str]] = None
    status: Optional[str] = None

class PaymentCreateRequest(BaseModel):
    customerId: str
    amount: float
    plan: str
    paymentMethod: Optional[str] = "UPI / NetBanking"
    transactionId: Optional[str] = None
    durationMonths: Optional[int] = 12

# ─── Solution Provider Endpoints ─────────────────────────────────────────────

@router.get("/stats")
def get_provider_stats():
    """Returns overview metrics for the Solution Provider dashboard."""
    state = load_state()
    customers = state.get("customers", [])
    payments = state.get("payments", [])
    
    total_customers = len(customers)
    active_licenses = sum(1 for c in customers if c.get("status") == "Active")
    expiring_soon = sum(1 for c in customers if c.get("status") == "Expiring Soon")
    total_cameras_managed = sum(c.get("activeCameras", 0) for c in customers)
    
    total_revenue = sum(p.get("amount", 0) for p in payments if p.get("status") == "Paid")
    monthly_recurring_revenue = sum(c.get("monthlyFee", 0) for c in customers if c.get("status") == "Active")

    return {
        "totalCustomers": total_customers,
        "activeLicenses": active_licenses,
        "expiringSoon": expiring_soon,
        "totalCamerasManaged": total_cameras_managed,
        "totalRevenue": total_revenue,
        "monthlyRecurringRevenue": monthly_recurring_revenue,
        "availableServices": AVAILABLE_SERVICES,
    }

@router.get("/customers")
def list_customers(status: Optional[str] = None):
    """Lists all customer accounts and their active provisions."""
    state = load_state()
    customers = state.get("customers", [])
    if status:
        customers = [c for c in customers if c.get("status", "").lower() == status.lower()]
    return {"customers": customers}

@router.post("/customers")
def create_customer(req: CustomerCreateRequest):
    """Onboards a new client with specified AI modules and license duration."""
    state = load_state()
    today = datetime.datetime.now()
    
    # Calculate expiry date
    if req.duration == "1 Month":
        exp = today + datetime.timedelta(days=30)
    elif req.duration == "3 Months":
        exp = today + datetime.timedelta(days=90)
    elif req.duration == "6 Months":
        exp = today + datetime.timedelta(days=180)
    elif req.duration == "1 Year":
        exp = today + datetime.timedelta(days=365)
    elif req.duration == "Lifetime":
        exp = today + datetime.timedelta(days=3650)
    elif req.customExpiryDate:
        exp = datetime.datetime.strptime(req.customExpiryDate, "%Y-%m-%d")
    else:
        exp = today + datetime.timedelta(days=365)
        
    # Calculate monthly fee from selected services
    fee = 0
    service_id_map = {s["id"]: s["basePrice"] for s in AVAILABLE_SERVICES}
    for s_id in req.enabledServices:
        fee += service_id_map.get(s_id, 999)

    new_cust = {
        "id": f"cust_{uuid.uuid4().hex[:6]}",
        "companyName": req.companyName,
        "clientName": req.clientName,
        "email": req.email,
        "phone": req.phone or "",
        "siteLocation": req.siteLocation or "Main Site",
        "maxCameras": req.maxCameras,
        "activeCameras": min(4, req.maxCameras),
        "licenseKey": generate_license_key("DEVA"),
        "planName": f"{len(req.enabledServices)} Services AI Suite",
        "duration": req.duration,
        "startDate": today.strftime("%Y-%m-%d"),
        "expiryDate": exp.strftime("%Y-%m-%d"),
        "status": "Active",
        "enabledServices": req.enabledServices,
        "monthlyFee": fee,
        "createdAt": today.strftime("%Y-%m-%d %H:%M:%S")
    }

    state.setdefault("customers", []).append(new_cust)
    save_state(state)
    logger.info(f"[Provider Hub] Created new customer: {req.companyName} ({new_cust['id']})")
    return {"customer": new_cust, "message": "Customer onboarded and license issued successfully."}

@router.put("/customers/{customer_id}")
def update_customer(customer_id: str, req: CustomerUpdateRequest):
    """Updates features, camera quotas, or extends license for a customer."""
    state = load_state()
    customers = state.get("customers", [])
    
    target = None
    for c in customers:
        if c.get("id") == customer_id:
            target = c
            break
            
    if not target:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    if req.companyName is not None: target["companyName"] = req.companyName
    if req.clientName is not None: target["clientName"] = req.clientName
    if req.email is not None: target["email"] = req.email
    if req.phone is not None: target["phone"] = req.phone
    if req.siteLocation is not None: target["siteLocation"] = req.siteLocation
    if req.maxCameras is not None: target["maxCameras"] = req.maxCameras
    if req.status is not None: target["status"] = req.status
    if req.enabledServices is not None:
        target["enabledServices"] = req.enabledServices
        service_id_map = {s["id"]: s["basePrice"] for s in AVAILABLE_SERVICES}
        target["monthlyFee"] = sum(service_id_map.get(s_id, 999) for s_id in req.enabledServices)
        
    if req.customExpiryDate is not None:
        target["expiryDate"] = req.customExpiryDate
        target["status"] = "Active"
    elif req.duration is not None:
        target["duration"] = req.duration
        today = datetime.datetime.now()
        if req.duration == "1 Month": exp = today + datetime.timedelta(days=30)
        elif req.duration == "3 Months": exp = today + datetime.timedelta(days=90)
        elif req.duration == "6 Months": exp = today + datetime.timedelta(days=180)
        elif req.duration == "1 Year": exp = today + datetime.timedelta(days=365)
        elif req.duration == "Lifetime": exp = today + datetime.timedelta(days=3650)
        else: exp = today + datetime.timedelta(days=365)
        target["expiryDate"] = exp.strftime("%Y-%m-%d")
        target["status"] = "Active"

    save_state(state)
    return {"customer": target, "message": "Customer updated successfully."}

@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: str):
    """Deactivates / removes a customer from the platform."""
    state = load_state()
    initial_len = len(state.get("customers", []))
    state["customers"] = [c for c in state.get("customers", []) if c.get("id") != customer_id]
    
    if len(state["customers"]) == initial_len:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    save_state(state)
    return {"message": "Customer removed successfully."}

@router.get("/payments")
def list_payments():
    """Lists all customer billing history and payments."""
    state = load_state()
    return {"payments": state.get("payments", [])}

@router.post("/payments")
def record_payment(req: PaymentCreateRequest):
    """Records a customer invoice payment and extends their license validity."""
    state = load_state()
    today = datetime.datetime.now()
    
    customers = state.get("customers", [])
    target_cust = next((c for c in customers if c.get("id") == req.customerId), None)
    
    company_name = target_cust.get("companyName") if target_cust else "Enterprise Client"
    
    months = req.durationMonths or 12
    new_expiry = (today + datetime.timedelta(days=months * 30)).strftime("%Y-%m-%d")
    
    inv_num = f"INV-{today.strftime('%Y')}-{uuid.uuid4().hex[:4].upper()}"
    new_payment = {
        "id": inv_num,
        "customerId": req.customerId,
        "companyName": company_name,
        "amount": req.amount,
        "plan": req.plan,
        "paymentMethod": req.paymentMethod or "UPI / NetBanking",
        "transactionId": req.transactionId or f"TXN_{uuid.uuid4().hex[:10].upper()}",
        "status": "Paid",
        "date": today.strftime("%Y-%m-%d %H:%M"),
        "expiryAfterPayment": new_expiry
    }
    
    state.setdefault("payments", []).insert(0, new_payment)
    
    if target_cust:
        target_cust["expiryDate"] = new_expiry
        target_cust["status"] = "Active"
        
    save_state(state)
    logger.info(f"[Provider Billing] Payment recorded: {inv_num} for {company_name} (₹{req.amount})")
    return {"payment": new_payment, "message": "Payment recorded and license extended."}

# ─── Customer Self-Service Endpoints ─────────────────────────────────────────

@customer_router.get("/license")
def get_customer_license(customer_id: Optional[str] = "cust_101"):
    """Returns the current customer's active license, permitted AI modules, and days left."""
    state = load_state()
    customers = state.get("customers", [])
    
    # Default to first customer if not found
    cust = next((c for c in customers if c.get("id") == customer_id), customers[0] if customers else None)
    if not cust:
        raise HTTPException(status_code=404, detail="No active license found")
        
    today = datetime.datetime.now().date()
    try:
        exp_date = datetime.datetime.strptime(cust.get("expiryDate"), "%Y-%m-%d").date()
        days_remaining = max(0, (exp_date - today).days)
    except Exception:
        days_remaining = 365
        
    return {
        "customerId": cust.get("id"),
        "companyName": cust.get("companyName"),
        "licenseKey": cust.get("licenseKey"),
        "planName": cust.get("planName"),
        "status": cust.get("status"),
        "expiryDate": cust.get("expiryDate"),
        "daysRemaining": days_remaining,
        "maxCameras": cust.get("maxCameras"),
        "activeCameras": cust.get("activeCameras"),
        "enabledServices": cust.get("enabledServices", []),
        "monthlyFee": cust.get("monthlyFee", 0),
        "availableServices": AVAILABLE_SERVICES,
    }

@customer_router.post("/pay-renew")
def customer_self_renew(req: PaymentCreateRequest):
    """Handles self-renewal by a client from their dashboard."""
    return record_payment(req)
