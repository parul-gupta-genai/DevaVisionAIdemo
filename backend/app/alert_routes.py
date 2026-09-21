from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.auth.dependencies import get_current_user
from app.services.alert_dispatcher import (
    load_alert_settings,
    save_alert_settings,
    send_telegram_alert,
    send_email_alert,
    send_webhook_alert,
    dispatch_event_alert
)

alerts_router = APIRouter(prefix="/api/alerts", tags=["Alerts"], dependencies=[Depends(get_current_user)])

class AlertSettingsUpdate(BaseModel):
    phone_number: Optional[str] = None
    whatsapp_enabled: Optional[bool] = None
    whatsapp_webhook_url: Optional[str] = None
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    email_enabled: Optional[bool] = None
    email_address: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    webhook_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None

class TestAlertRequest(BaseModel):
    channel: str  # "telegram", "email", "whatsapp", "all"
    sample_snapshot: Optional[str] = None

@alerts_router.get("/settings")
def get_alert_destinations() -> Dict[str, Any]:
    """Returns current alert configuration (masking passwords)."""
    settings = load_alert_settings()
    safe_settings = settings.copy()
    if safe_settings.get("smtp_password"):
        safe_settings["smtp_password"] = "***"
    return safe_settings

@alerts_router.post("/settings")
def update_alert_destinations(updates: AlertSettingsUpdate) -> Dict[str, Any]:
    """Updates and persists alert configuration."""
    clean_updates = {k: v for k, v in updates.model_dump().items() if v is not None}
    
    # Do not overwrite with masked placeholder
    if clean_updates.get("smtp_password") == "***":
        del clean_updates["smtp_password"]
        
    ok = save_alert_settings(clean_updates)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save alert settings")
    return {"status": "success", "message": "Alert settings updated successfully"}

@alerts_router.post("/test")
def test_alert_dispatch(req: TestAlertRequest) -> Dict[str, Any]:
    """Triggers an immediate test alert to verify Telegram / Email / Phone configurations."""
    settings = load_alert_settings()
    
    # Try finding an existing snapshot in snapshots/ directory if none provided
    import glob, os
    snapshot = req.sample_snapshot
    if not snapshot:
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        matches = glob.glob(os.path.join(backend_dir, "snapshots", "*", "*.jpg"))
        if matches:
            snapshot = matches[0]

    sample_msg = "✅ <b>TEST ALERT VERIFIED</b>\nThis is a test notification from DevaVision AI.\nSystem is operational."

    if req.channel == "telegram":
        token = settings.get("telegram_bot_token")
        chat_id = settings.get("telegram_chat_id")
        if not token or not chat_id:
            raise HTTPException(status_code=400, detail="Telegram Bot Token and Chat ID are required.")
        res = send_telegram_alert(token, chat_id, sample_msg, snapshot)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=f"Telegram test failed: {res.get('error')}")
        return {"status": "success", "message": "Test alert sent to Telegram successfully!"}

    elif req.channel == "email":
        to_email = settings.get("email_address")
        if not to_email:
            raise HTTPException(status_code=400, detail="Target Email Address is required.")
        res = send_email_alert(
            to_email=to_email,
            subject="[TEST] DevaVision AI Alert Verification",
            body_text="This is a test alert verifying your email notification configuration.",
            snapshot_path=snapshot,
            smtp_host=settings.get("smtp_host", "smtp.gmail.com"),
            smtp_port=int(settings.get("smtp_port", 587)),
            smtp_user=settings.get("smtp_user", ""),
            smtp_password=settings.get("smtp_password", ""),
            from_email=settings.get("smtp_from", "alerts@devavision.ai")
        )
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=f"Email test failed: {res.get('error')}")
        return {"status": "success", "message": f"Test alert sent to {to_email} successfully!"}

    elif req.channel == "whatsapp":
        url = settings.get("whatsapp_webhook_url")
        phone = settings.get("phone_number")
        if not url:
            raise HTTPException(status_code=400, detail="WhatsApp Webhook Gateway URL is required.")
        payload = {
            "event": "TEST_ALERT",
            "phone_number": phone,
            "message": "DevaVision AI Alert: Test notification verified."
        }
        res = send_webhook_alert(url, payload)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail="WhatsApp Webhook test failed")
        return {"status": "success", "message": f"Test webhook sent to {phone or url}!"}

    else:
        # Dispatch to all active channels
        results = dispatch_event_alert(
            event_type="TEST_ALERT",
            camera_name="Site Test Camera",
            description="Manual test notification triggered from Dashboard Settings.",
            severity="info",
            snapshot_path=snapshot
        )
        return {"status": "success", "dispatched": results}
