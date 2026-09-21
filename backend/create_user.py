import os
os.environ["DATABASE_URL"] = "postgresql://admin:admin@localhost:5433/cctv"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

from database.models.auth import User
from database.persistence import SessionLocal
from app.auth.security import get_password_hash

def main():
    db = SessionLocal()
    email = "gauriirajpoot@gmail.com"
    password = "admin"
    
    user = db.query(User).filter(User.email == email).first()
    if user:
        print(f"User {email} already exists. Updating password and unlocking...")
        user.hashed_password = get_password_hash(password)
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()
    else:
        print(f"Creating user {email}...")
        new_user = User(
            email=email,
            hashed_password=get_password_hash(password),
            is_active=True,
            is_superuser=True,
            failed_login_attempts=0,
            locked_until=None
        )
        db.add(new_user)
        db.commit()
        print("User created successfully!")
        
    db.close()

if __name__ == "__main__":
    main()
