# backend/app/services/auth_service.py
from datetime import datetime, timedelta
from jose import jwt
import bcrypt
from ..config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, db
from ..models.user import USER_COLLECTION

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

async def authenticate_user(username: str, password: str):
    print(f"[DEBUG] authenticate_user: looking for username={username}")
    user = await db[USER_COLLECTION].find_one({"username": username, "is_active": True})
    print(f"[DEBUG] authenticate_user: user found? {user is not None}")
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        print(f"[DEBUG] authenticate_user: password mismatch for {username}")
        return None
    print(f"[DEBUG] authenticate_user: success for {username}")
    return user

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_refresh_token(data: dict):
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = data.copy()
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.JWTError:
        return None

