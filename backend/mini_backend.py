
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class LoginRequest(BaseModel):
    email: str
    password: str

ADMIN_USER = {
    "id": 1,
    "email": "gauriirajpoot@gmail.com",
    "name": "Admin User",
    "role": "super_admin",
    "roles": ["super_admin", "admin"],
    "permissions": ["*", "settings:read", "settings:write", "users:read", "users:write",
                    "cameras:read", "cameras:write", "analytics:read", "plugins:read",
                    "plugins:write", "system:admin"],
    "is_active": True,
    "is_superuser": True,
    "is_admin": True
}

@app.post("/auth/login")
def login(req: LoginRequest):
    return {"access_token": "demo-admin-token", "token_type": "bearer", "user": ADMIN_USER}

@app.get("/auth/me")
def me(): return ADMIN_USER

@app.get("/users/me")
def users_me(): return ADMIN_USER

@app.get("/api/cameras")
def cameras(): return []

@app.get("/api/cameras/active")
def active_cameras(): return []

@app.get("/api/events")
def events(): return {"items": [], "total": 0}

@app.get("/analytics/summary")
def analytics(): return {"total_events": 0, "active_cameras": 0, "alerts_today": 0}

@app.get("/api/plugins")
def plugins(): return []

@app.get("/users")
def users(): return [ADMIN_USER]

@app.get("/roles")
def roles(): return [{"id": 1, "name": "super_admin", "permissions": ["*"]}]

@app.get("/api/settings")
def settings(): return {}

@app.get("/api/system/info")
def system_info(): return {"version": "1.0.0", "status": "running"}

dist_candidates = [
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"),
    os.path.join(os.path.dirname(__file__), "frontend", "dist"),
    "/kaggle/working/DevaVisionAIdemo/frontend/dist",
    os.path.abspath("frontend/dist"),
    os.path.abspath("../frontend/dist")
]

for candidate in dist_candidates:
    if os.path.exists(candidate) and os.path.isdir(candidate):
        app.mount("/", StaticFiles(directory=candidate, html=True), name="static")
        print(f"Mounted frontend dist from: {candidate}")
        break
