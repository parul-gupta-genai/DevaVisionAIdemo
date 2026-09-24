from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import Any

from database.session import get_db
from database.models.auth import User
from app.auth.schemas import Token, LoginRequest, RefreshRequest, UserResponse
from app.auth.services import authenticate_user, refresh_access_token, logout_user
from app.auth.dependencies import get_current_user, require_permissions

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=Token)
def login(
    request: Request,
    login_data: LoginRequest,
    db: Session = Depends(get_db)
) -> Any:
    """Authenticate user and return JWT access and refresh tokens."""
    return authenticate_user(db, login_data)

@router.post("/refresh", response_model=Token)
def refresh_token(
    payload: RefreshRequest,
    db: Session = Depends(get_db)
) -> Any:
    """Obtain a new access token using a refresh token (sent in the body)."""
    return refresh_access_token(db, payload.refresh_token)

@router.post("/logout")
def logout(
    payload: RefreshRequest,
    db: Session = Depends(get_db)
) -> Any:
    """Revoke a refresh token (sent in the body)."""
    logout_user(db, payload.refresh_token)
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserResponse)
def read_users_me(
    current_user: User = Depends(get_current_user)
) -> Any:
    """Get current logged in user."""
    roles_list = [r.name for r in getattr(current_user, 'roles', [])]
    
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        created_at=current_user.created_at,
        roles=roles_list
    )

@router.get("/admin-only")
def admin_only_route(
    current_user: User = require_permissions(["users:manage"])
):
    """Example route that requires users:manage permission."""
    return {"message": "You have the required permission!"}

