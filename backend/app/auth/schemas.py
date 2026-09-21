from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    """
    Refresh tokens travel in the request BODY, never the query string — a URL
    lands in uvicorn/proxy access logs, browser history and Referer headers,
    and these are long-lived (7 day) credentials.
    """
    refresh_token: str

class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None
    scopes: List[str] = []

class LoginRequest(BaseModel):
    email: str
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserRoleUpdate(BaseModel):
    role_name: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    is_superuser: bool
    created_at: datetime
    roles: List[str] = []

    class Config:
        from_attributes = True

class RoleResponse(BaseModel):
    id: int
    name: str
    permissions: List[str] = []

    class Config:
        from_attributes = True
