import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.session import SessionLocal, engine, Base
from database.models import User, Camera
from app.auth.security import get_password_hash

# Create tables
Base.metadata.create_all(bind=engine)

db = SessionLocal()
existing = db.query(User).filter_by(email="gauriirajpoot@gmail.com").first()
if not existing:
    admin = User(
        email="gauriirajpoot@gmail.com",
        hashed_password=get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
        failed_login_attempts=0,
        locked_until=None
    )
    db.add(admin)
    db.commit()
    print("Admin user created successfully!")
else:
    # Update password and reset lockout for existing admin
    existing.hashed_password = get_password_hash("admin")
    existing.is_superuser = True
    existing.is_active = True
    existing.failed_login_attempts = 0
    existing.locked_until = None
    db.add(existing)
    db.commit()
    print("Admin user password updated to admin (account unlocked).")
