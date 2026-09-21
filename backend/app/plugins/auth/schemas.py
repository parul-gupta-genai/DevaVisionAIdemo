# backend/app/plugins/auth/schemas.py
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime


class PermissionSchema(BaseModel):
    """Permission schema"""
    id: int
    name: str
    description: Optional[str] = None
    
    class Config:
        from_attributes = True


class RoleSchema(BaseModel):
    """Role schema"""
    id: int
    name: str
    description: Optional[str] = None
    permissions: List[PermissionSchema] = []
    
    class Config:
        from_attributes = True


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """User creation schema"""
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    
    @validator('password')
    def validate_password(cls, v):
        """Validate password complexity"""
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class UserUpdate(BaseModel):
    """User update schema"""
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None


class UserLogin(BaseModel):
    """User login schema"""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response schema"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = 1800  # seconds


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str


class UserResponse(UserBase):
    """User response schema"""
    id: int
    is_active: bool
    is_superuser: bool
    is_email_verified: bool
    roles: List[RoleSchema] = []
    created_at: datetime
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class AuditLogSchema(BaseModel):
    """Audit log schema"""
    id: int
    user_id: Optional[int] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    status: str
    created_at: datetime
    details: Optional[dict] = None
    
    class Config:
        from_attributes = True


class PasswordChangeRequest(BaseModel):
    """Password change request"""
    old_password: str
    new_password: str = Field(..., min_length=8)
    
    @validator('new_password')
    def validate_new_password(cls, v):
        """Validate new password complexity"""
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class RoleAssignRequest(BaseModel):
    """Request to assign role to user"""
    user_id: int
    role_id: int


class PermissionCheckRequest(BaseModel):
    """Request to check user permission"""
    permission_name: str
