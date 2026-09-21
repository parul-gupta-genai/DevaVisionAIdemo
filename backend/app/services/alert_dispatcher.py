import os
import json
import urllib.request
import urllib.parse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from typing import Optional, Dict, Any
from datetime import datetime
from loguru import logger

# Configuration storage path (persists in backend data/alerts_config.json)
CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
CONFIG_FILE = os.path.join(CONFIG_DIR, "alerts_config.json")

DEFAULT_SETTINGS = {
    "phone_number": "",
    "whatsapp_enabled": False,
    "whatsapp_webhook_url": "",
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "email_enabled": False,
    "email_address": "",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "alerts@devavision.ai",
    "webhook_enabled": False,
    "webhook_url": ""
}

def load_alert_settings() -> Dict[str, Any]:
    """Loads saved alert destination settings from JSON storage."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = DEFAULT_SETTINGS.copy()
                merged.update(data)
                return merged
    except Exception as e:
        logger.warning(f"Could not load alert settings: {e}")
    return DEFAULT_SETTINGS.copy()

def save_alert_settings(settings: Dict[str, Any]) -> bool:
    """Saves alert destination settings to JSON storage."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        current = load_alert_settings()
        current.update(settings)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save alert settings: {e}")
        return False

def _resolve_snapshot_path(snapshot_path: Optional[str]) -> Optional[str]:
    """Resolves relative snapshot URL to absolute local filesystem path."""
    if not snapshot_path:
        return None
    if os.path.isabs(snapshot_path) and os.path.exists(snapshot_path):
        return snapshot_path
    
    # Strip leading slash if present
    clean_path = snapshot_path.lstrip("/")
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidate = os.path.join(backend_dir, clean_path)
    if os.path.exists(candidate):
        return candidate
    return None

def send_telegram_alert(
    bot_token: str,
    chat_id: str,
    caption: str,
    snapshot_path: Optional[str] = None
) -> Dict[str, Any]:
    """Sends a formatted message with an optional snapshot photo to Telegram."""
    if not bot_token or not chat_id:
        return {"success": False, "error": "Bot token or Chat ID is missing"}

    resolved_image = _resolve_snapshot_path(snapshot_path)

    try:
        if resolved_image and os.path.exists(resolved_image):
            # Send photo via multipart/form-data
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            boundary = "----DevaVisionAlertBoundary"
            
            with open(resolved_image, "rb") as img_file:
                img_bytes = img_file.read()

            body = bytearray()
            # Chat ID field
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(b'Content-Disposition: form-data; name="chat_id"\r\n\r\n')
            body.extend(f"{chat_id}\r\n".encode("utf-8"))
            # Caption field
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(b'Content-Disposition: form-data; name="caption"\r\n\r\n')
            body.extend(f"{caption}\r\n".encode("utf-8"))
            # Parse mode field
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(b'Content-Disposition: form-data; name="parse_mode"\r\n\r\n')
            body.extend(b"HTML\r\n")
            # Photo file field
            filename = os.path.basename(resolved_image)
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'.encode("utf-8"))
            body.extend(b"Content-Type: image/jpeg\r\n\r\n")
            body.extend(img_bytes)
            body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

            req = urllib.request.Request(
                url,
                data=bytes(body),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return {"success": res_data.get("ok", False), "data": res_data}
        else:
            # Send text message only
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = json.dumps({
                "chat_id": chat_id,
                "text": caption,
                "parse_mode": "HTML"
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return {"success": res_data.get("ok", False), "data": res_data}
    except Exception as e:
        logger.error(f"Telegram dispatch failed: {e}")
        return {"success": False, "error": str(e)}

def send_email_alert(
    to_email: str,
    subject: str,
    body_text: str,
    snapshot_path: Optional[str] = None,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_password: str = "",
    from_email: str = "alerts@devavision.ai"
) -> Dict[str, Any]:
    """Sends an email alert with an optional attached snapshot image."""
    if not to_email:
        return {"success": False, "error": "Target email is missing"}
    if not smtp_user or not smtp_password:
        return {"success": False, "error": "SMTP User / App Password not configured"}

    resolved_image = _resolve_snapshot_path(snapshot_path)

    try:
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject

        html_content = f"""
        <div style="font-family: Arial, sans-serif; padding: 15px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <h2 style="color: #dc2626; margin-top: 0;">🚨 DevaVision AI Alert</h2>
            <p style="font-size: 14px; line-height: 1.6;">{body_text.replace(chr(10), '<br>')}</p>
            {f'<p><strong>Snapshot Attached:</strong></p>' if resolved_image else ''}
            <hr style="border: none; border-top: 1px solid #eaeaea; margin: 15px 0;" />
            <p style="font-size: 11px; color: #888;">Automated alert from DevaVision AI Surveillance Platform</p>
        </div>
        """
        msg.attach(MIMEText(html_content, "html"))

        if resolved_image and os.path.exists(resolved_image):
            with open(resolved_image, "rb") as f:
                img_data = f.read()
                image_part = MIMEImage(img_data, name=os.path.basename(resolved_image))
                msg.attach(image_part)

        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()

        return {"success": True, "message": "Email sent successfully"}
    except Exception as e:
        logger.error(f"Email dispatch failed: {e}")
        return {"success": False, "error": str(e)}

def send_webhook_alert(
    webhook_url: str,
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Sends JSON alert payload to custom Webhook (e.g. WhatsApp Gateway, Slack)."""
    if not webhook_url:
        return {"success": False, "error": "Webhook URL missing"}

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"success": resp.status in [200, 201, 202, 204]}
    except Exception as e:
        logger.error(f"Webhook dispatch failed: {e}")
        return {"success": False, "error": str(e)}

def dispatch_event_alert(
    event_type: str,
    camera_name: str,
    description: str,
    severity: str = "warning",
    snapshot_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Unified entry point: dispatches alert to all enabled channels
    (Telegram, Email, WhatsApp/Webhook) based on saved settings.
    """
    settings = load_alert_settings()
    results = {}

    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"🚨 <b>{event_type.upper()} DETECTED</b>"
    text_content = (
        f"{title}\n"
        f"<b>Camera:</b> {camera_name}\n"
        f"<b>Severity:</b> {severity.upper()}\n"
        f"<b>Details:</b> {description}\n"
        f"<b>Time:</b> {timestamp_str}"
    )

    # 1. Telegram Dispatch
    if settings.get("telegram_enabled"):
        token = settings.get("telegram_bot_token")
        chat_id = settings.get("telegram_chat_id")
        if token and chat_id:
            results["telegram"] = send_telegram_alert(token, chat_id, text_content, snapshot_path)

    # 2. Email Dispatch
    if settings.get("email_enabled"):
        to_email = settings.get("email_address")
        if to_email:
            results["email"] = send_email_alert(
                to_email=to_email,
                subject=f"[{severity.upper()}] DevaVision Alert: {event_type} at {camera_name}",
                body_text=text_content.replace("<b>", "").replace("</b>", ""),
                snapshot_path=snapshot_path,
                smtp_host=settings.get("smtp_host", "smtp.gmail.com"),
                smtp_port=int(settings.get("smtp_port", 587)),
                smtp_user=settings.get("smtp_user", ""),
                smtp_password=settings.get("smtp_password", ""),
                from_email=settings.get("smtp_from", "alerts@devavision.ai")
            )

    # 3. Webhook / WhatsApp Gateway Dispatch
    if settings.get("webhook_enabled") or settings.get("whatsapp_enabled"):
        target_url = settings.get("whatsapp_webhook_url") if settings.get("whatsapp_enabled") else settings.get("webhook_url")
        if target_url:
            payload = {
                "event": event_type,
                "camera": camera_name,
                "severity": severity,
                "description": description,
                "phone_number": settings.get("phone_number"),
                "snapshot_url": snapshot_path
            }
            results["webhook"] = send_webhook_alert(target_url, payload)

    return results
