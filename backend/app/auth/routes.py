from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from database.session import get_async_db
from database.models.auth import User
from app.auth.schemas import Token, LoginRequest, RefreshRequest, UserResponse
from app.auth.services import authenticate_user, refresh_access_token, logout_user
from app.auth.dependencies import get_current_user, require_permissions

router = APIRouter(prefix="/auth", tags=["auth"])
from api.limiter import limiter

@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_async_db)
) -> Any:
    """Authenticate user and return JWT access and refresh tokens."""
    return await authenticate_user(db, login_data)

@router.post("/refresh", response_model=Token)
async def refresh_token(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_async_db)
) -> Any:
    """Obtain a new access token using a refresh token (sent in the body)."""
    return await refresh_access_token(db, payload.refresh_token)

@router.post("/logout")
async def logout(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_async_db)
) -> Any:
    """Revoke a refresh token (sent in the body)."""
    await logout_user(db, payload.refresh_token)
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(get_current_user)
) -> Any:
    """Get current logged in user."""
    # Convert ORM relationships to list of strings for response
    roles_list = [r.name for r in current_user.roles]
    
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        created_at=current_user.created_at,
        roles=roles_list
    )

# Example protected route enforcing specific permissions
@router.get("/admin-only")
async def admin_only_route(
    current_user: User = require_permissions(["users:manage"])
):
    """Example route that requires users:manage permission."""
    return {"message": "You have the required permission!"}
