from fastapi import Depends, HTTPException, status, Security
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from fastapi import Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from database.session import get_async_db
from database.models.auth import User, Role, Permission
from app.auth.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    scopes={
        "admin": "Superuser access",
        "cameras:read": "Read camera streams",
        "users:manage": "Manage users"
    }
)

async def get_current_user(
    security_scopes: SecurityScopes,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id_str: str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except ValueError:
        raise credentials_exception

    # Fetch user with eager loaded roles and permissions
    stmt = select(User).options(
        selectinload(User.roles).selectinload(Role.permissions)
    ).where(User.id == user_id)
    
    result = await db.execute(stmt)
    user = result.scalars().first()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    # If scopes are required for this endpoint, check them
    if security_scopes.scopes and not user.is_superuser:
        user_scopes = []
        for role in user.roles:
            for perm in role.permissions:
                user_scopes.append(perm.name)
                
        for scope in security_scopes.scopes:
            if scope not in user_scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Not enough permissions. Required: {scope}",
                    headers={"WWW-Authenticate": authenticate_value},
                )

    return user

def require_permissions(required_scopes: list[str]):
    """
    Convenience wrapper to enforce permissions using FastAPI Security scopes.
    Example: Depends(require_permissions(["users:manage"]))
    """
    return Security(get_current_user, scopes=required_scopes)

async def get_current_user_query(
    security_scopes: SecurityScopes,
    token: str = Query(None),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    """
    Extract token from query parameters instead of Authorization header.
    Useful for WebSockets and <img> tags.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await get_current_user(security_scopes, token=token, db=db)
