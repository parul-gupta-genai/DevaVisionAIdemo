import secrets
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database.models.auth import User, RefreshToken, AuditLog
from app.auth.schemas import LoginRequest, Token
from app.auth.security import verify_password, create_access_token

def authenticate_user(db: Session, login_data: LoginRequest) -> Token:
    user = db.query(User).filter(User.email == login_data.email).first()

    if not user:
        # Prevent timing attacks by still running a verification
        verify_password(login_data.password, "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjIQqiRQYq")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Check Lockout
    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked due to multiple failed login attempts."
        )

    if not verify_password(login_data.password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Success reset failed attempts
    user.failed_login_attempts = 0
    user.locked_until = None
    
    # Generate Tokens
    access_token = create_access_token(
        subject=user.id, 
        scopes=["admin"] if user.is_superuser else []
    )
    
    refresh_token_str = secrets.token_urlsafe(32)
    refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    
    db.add(refresh_token)
    
    # Audit Log
    log = AuditLog(user_id=user.id, action="LOGIN", ip_address="Unknown")
    db.add(log)
    
    db.commit()
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token_str,
        token_type="bearer"
    )

def refresh_access_token(db: Session, refresh_token_str: str) -> Token:
    token_obj = db.query(RefreshToken).filter(
        RefreshToken.token == refresh_token_str,
        RefreshToken.is_revoked == False
    ).first()
    
    if not token_obj or token_obj.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
        
    user = db.query(User).filter(User.id == token_obj.user_id).first()
    
    access_token = create_access_token(
        subject=user.id, 
        scopes=["admin"] if user.is_superuser else []
    )
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token_str,
        token_type="bearer"
    )

def logout_user(db: Session, refresh_token_str: str):
    token_obj = db.query(RefreshToken).filter(RefreshToken.token == refresh_token_str).first()
    
    if token_obj:
        token_obj.is_revoked = True
        log = AuditLog(user_id=token_obj.user_id, action="LOGOUT")
        db.add(log)
        db.commit()

