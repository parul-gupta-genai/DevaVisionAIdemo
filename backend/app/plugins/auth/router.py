# backend/app/plugins/auth/router.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from passlib.context import CryptContext
from typing import Optional

from database.session import get_db_session
from .models import User, Role, Permission, RefreshToken, AuditLog
from .schemas import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    RefreshTokenRequest, PasswordChangeRequest, AuditLogSchema
)
from .dependencies import (
    get_current_user, get_current_admin, create_access_token,
    create_refresh_token, ACCESS_TOKEN_EXPIRE_MINUTES
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)


async def log_audit(
    db: AsyncSession,
    user_id: Optional[int],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    status: str = "success",
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
):
    """Log audit event"""
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        status=status,
        ip_address=ip_address,
        user_agent=user_agent
    )
    db.add(audit_log)
    await db.flush()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db_session)
):
    """Register new user"""
    # Check if user exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        await log_audit(
            db, None, "register", "user", user_data.email,
            status="failure", ip_address=request.client.host,
            details={"reason": "email_already_exists"}
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists"
        )
    
    # Create user
    hashed_password = hash_password(user_data.password)
    new_user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed_password
    )
    
    # Assign default role
    result = await db.execute(select(Role).where(Role.is_default == True))
    default_role = result.scalar_one_or_none()
    if default_role:
        new_user.roles.append(default_role)
    
    db.add(new_user)
    await db.flush()
    
    await log_audit(
        db, new_user.id, "register", "user", new_user.email,
        ip_address=request.client.host
    )
    
    await db.commit()
    await db.refresh(new_user)
    
    return new_user


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db_session)
):
    """Login user and return tokens"""
    # Find user
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()
    
    if not user:
        await log_audit(
            db, None, "login", "user", credentials.email,
            status="failure", ip_address=request.client.host,
            details={"reason": "user_not_found"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Check if locked (too many failed attempts)
    if user.locked_until and datetime.utcnow() < user.locked_until:
        await log_audit(
            db, user.id, "login", "user", user.email,
            status="failure", ip_address=request.client.host,
            details={"reason": "account_locked"}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account locked due to too many failed login attempts"
        )
    
    # Verify password
    if not verify_password(credentials.password, user.hashed_password):
        user.failed_login_attempts += 1
        
        # Lock account after 5 failed attempts
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        
        await db.commit()
        
        await log_audit(
            db, user.id, "login", "user", user.email,
            status="failure", ip_address=request.client.host,
            details={"reason": "invalid_password", "attempts": user.failed_login_attempts}
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Reset failed attempts on successful login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    
    # Create tokens
    access_token = create_access_token({"sub": user.id})
    refresh_token = create_refresh_token({"sub": user.id})
    
    # Store refresh token
    refresh_token_obj = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db.add(refresh_token_obj)
    await db.commit()
    
    await log_audit(
        db, user.id, "login", "user", user.email,
        ip_address=request.client.host
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Refresh access token using refresh token"""
    # Verify refresh token exists and is valid
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == request.refresh_token,
            RefreshToken.is_revoked == False,
            RefreshToken.expires_at > datetime.utcnow()
        )
    )
    token_obj = result.scalar_one_or_none()
    
    if not token_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    # Create new access token
    access_token = create_access_token({"sub": token_obj.user_id})
    
    return TokenResponse(
        access_token=access_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Logout user and revoke refresh tokens"""
    # Revoke all refresh tokens
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == current_user.id,
            RefreshToken.is_revoked == False
        )
    )
    tokens = result.scalars().all()
    
    for token in tokens:
        token.is_revoked = True
        token.revoked_at = datetime.utcnow()
    
    await db.commit()
    
    return {"message": "Successfully logged out"}


@router.post("/change-password")
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Change user password"""
    # Verify old password
    if not verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid current password"
        )
    
    # Update password
    current_user.hashed_password = hash_password(password_data.new_password)
    db.add(current_user)
    await db.commit()
    
    return {"message": "Password changed successfully"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user info"""
    return current_user


@router.get("/audit-logs", response_model=list[AuditLogSchema])
async def get_audit_logs(
    current_user: User = Depends(get_current_admin),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db_session)
):
    """Get audit logs (admin only)"""
    result = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "auth"}
