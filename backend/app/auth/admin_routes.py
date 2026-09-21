from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import Any, List

from database.session import get_async_db
from database.models.auth import User, Role, Permission
from app.auth.schemas import UserResponse, UserCreate, RoleResponse, UserRoleUpdate
from app.auth.security import get_password_hash
from app.auth.dependencies import require_permissions

admin_router = APIRouter(tags=["administration"])

@admin_router.get("/users", response_model=List[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_async_db),
    _ = require_permissions(["users:manage"])
) -> Any:
    """List all users."""
    stmt = select(User).options(selectinload(User.roles))
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    return [
        UserResponse(
            id=u.id, email=u.email, is_active=u.is_active, 
            is_superuser=u.is_superuser, created_at=u.created_at,
            roles=[r.name for r in u.roles]
        ) for u in users
    ]

@admin_router.post("/users", response_model=UserResponse)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_async_db),
    _ = require_permissions(["users:manage"])
) -> Any:
    """Create a new user."""
    stmt = select(User).where(User.email == user_in.email)
    result = await db.execute(stmt)
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="User with this email already exists.")
        
    hashed_password = get_password_hash(user_in.password)
    user = User(
        email=user_in.email,
        hashed_password=hashed_password,
        is_active=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse(
        id=user.id, email=user.email, is_active=user.is_active, 
        is_superuser=user.is_superuser, created_at=user.created_at, roles=[]
    )

@admin_router.put("/users/{user_id}/role", response_model=UserResponse)
async def assign_role(
    user_id: int,
    role_in: UserRoleUpdate,
    db: AsyncSession = Depends(get_async_db),
    _ = require_permissions(["users:manage"])
) -> Any:
    """Assign a role to a user (replaces existing roles for simplicity)."""
    # Fetch User
    stmt = select(User).where(User.id == user_id).options(selectinload(User.roles))
    result = await db.execute(stmt)
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch Role
    stmt = select(Role).where(Role.name == role_in.role_name)
    result = await db.execute(stmt)
    role = result.scalars().first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Prevent demoting the last superuser accidentally (basic safety net)
    if user.is_superuser and role_in.role_name != "admin":
        raise HTTPException(status_code=400, detail="Cannot downgrade superuser.")

    # Assign role
    user.roles = [role]
    await db.commit()
    await db.refresh(user)
    
    return UserResponse(
        id=user.id, email=user.email, is_active=user.is_active, 
        is_superuser=user.is_superuser, created_at=user.created_at,
        roles=[r.name for r in user.roles]
    )

@admin_router.get("/roles", response_model=List[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_async_db),
    _ = require_permissions(["roles:manage"])
) -> Any:
    """List all roles."""
    stmt = select(Role).options(selectinload(Role.permissions))
    result = await db.execute(stmt)
    roles = result.scalars().all()
    return [
        RoleResponse(
            id=r.id, name=r.name, 
            permissions=[p.name for p in r.permissions]
        ) for r in roles
    ]

@admin_router.get("/permissions", response_model=List[str])
async def list_permissions(
    db: AsyncSession = Depends(get_async_db),
    _ = require_permissions(["roles:manage"])
) -> Any:
    """List all permissions."""
    stmt = select(Permission)
    result = await db.execute(stmt)
    permissions = result.scalars().all()
    return [p.name for p in permissions]
