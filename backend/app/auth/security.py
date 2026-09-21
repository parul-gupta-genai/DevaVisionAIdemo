from datetime import datetime, timedelta
from typing import Any, Union, List
import jwt
import bcrypt
from config.config import config

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(
    subject: Union[str, Any], 
    scopes: List[str], 
    expires_delta: timedelta = None
) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # Defaults from config, fallback to 15 mins
        expire = datetime.utcnow() + timedelta(
            minutes=getattr(config, "ACCESS_TOKEN_EXPIRE_MINUTES", 15)
        )
        
    to_encode = {
        "exp": expire, 
        "sub": str(subject),
        "scopes": scopes
    }
    
    # We will need SECRET_KEY and ALGORITHM in config.py
    secret = config.SECRET_KEY
    algorithm = config.ALGORITHM
    
    encoded_jwt = jwt.encode(to_encode, secret, algorithm=algorithm)
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    secret = config.SECRET_KEY
    algorithm = config.ALGORITHM
    try:
        decoded_token = jwt.decode(token, secret, algorithms=[algorithm])
        return decoded_token
    except jwt.PyJWTError:
        return None
