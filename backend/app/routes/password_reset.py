# backend/app/routes/password_reset.py
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, EmailStr, Field, validator
from datetime import datetime, timedelta
import secrets
import hashlib
import re
from typing import Optional
from jose import jwt
from ..config import db, JWT_SECRET, JWT_ALGORITHM
from ..services.auth_service import hash_password
from ..services.email_service import send_reset_email, send_reset_confirmation
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Password Reset"])

# Rate limiting in memory (production: use Redis)
_ratelimit_store = {}

class ForgotPasswordRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    
    @validator('username')
    def validate_username(cls, v):
        if not v.strip():
            raise ValueError("Username cannot be empty")
        return v.strip()

class VerifyResetTokenRequest(BaseModel):
    token: str = Field(..., min_length=10)

class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=128)
    
    @validator('new_password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r'[A-Z]', v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r'[a-z]', v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r'[0-9]', v):
            raise ValueError("Password must contain at least one number")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError("Password must contain at least one special character")
        return v

class ResetWithOTPRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    otp: str = Field(..., pattern=r'^\d{6}$')  # Changed from regex to pattern
    new_password: str = Field(..., min_length=8, max_length=128)
    
    @validator('new_password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r'[A-Z]', v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r'[a-z]', v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r'[0-9]', v):
            raise ValueError("Password must contain at least one number")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError("Password must contain at least one special character")
        return v

def generate_otp() -> str:
    """Generate a 6-digit OTP."""
    return f"{secrets.randbelow(1000000):06d}"

def hash_token(token: str) -> str:
    """Hash a token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()

def is_rate_limited(identifier: str) -> bool:
    """Check if the identifier is rate limited."""
    now = datetime.utcnow()
    if identifier in _ratelimit_store:
        attempts, last_attempt = _ratelimit_store[identifier]
        # Reset if more than 1 hour old
        if now - last_attempt > timedelta(hours=1):
            _ratelimit_store[identifier] = (1, now)
            return False
        if attempts >= 5:  # Max 5 attempts per hour
            return True
        _ratelimit_store[identifier] = (attempts + 1, now)
    else:
        _ratelimit_store[identifier] = (1, now)
    return False

@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks
):
    """Request password reset with OTP sent via email."""
    identifier = request.username.lower()
    
    # Rate limiting
    if is_rate_limited(identifier):
        raise HTTPException(
            status_code=429,
            detail="Too many reset attempts. Please wait 1 hour."
        )
    
    # Find user by username or email
    user = await db.users.find_one({
        "$or": [
            {"username": {"$regex": f"^{request.username}$", "$options": "i"}},
            {"email": {"$regex": f"^{request.username}$", "$options": "i"}}
        ]
    })
    
    # For security, don't reveal if user exists
    if not user:
        return {"message": "If the account exists, a reset code has been sent to your email."}
    
    # Generate OTP
    otp = generate_otp()
    otp_hash = hash_token(otp)
    expiry = datetime.utcnow() + timedelta(minutes=15)
    
    # Store OTP hash in user document
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "reset_otp_hash": otp_hash,
            "reset_otp_expiry": expiry,
            "reset_attempts": 0
        }}
    )
    
    # Send OTP via email in background
    background_tasks.add_task(
        send_reset_email,
        user.get("email", ""),
        user.get("full_name", "User"),
        otp
    )
    
    return {"message": "If the account exists, a reset code has been sent to your email."}

@router.post("/verify-otp")
async def verify_otp(request: VerifyResetTokenRequest):
    """Verify OTP and return a temporary reset token."""
    # Try to find user with this OTP
    otp_hash = hash_token(request.token)
    
    user = await db.users.find_one({
        "reset_otp_hash": otp_hash,
        "reset_otp_expiry": {"$gt": datetime.utcnow()}
    })
    
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    # Check attempts
    attempts = user.get("reset_attempts", 0)
    if attempts >= 3:
        # Clear OTP after too many attempts
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$unset": {"reset_otp_hash": "", "reset_otp_expiry": ""}}
        )
        raise HTTPException(
            status_code=400,
            detail="Too many invalid attempts. Please request a new OTP."
        )
    
    # Generate a temporary reset token (valid for 5 minutes)
    reset_token = jwt.encode(
        {
            "sub": str(user["_id"]),
            "type": "password_reset",
            "exp": datetime.utcnow() + timedelta(minutes=5)
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    
    # Store the reset token
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "reset_token": reset_token,
            "reset_token_expiry": datetime.utcnow() + timedelta(minutes=5)
        }}
    )
    
    return {"reset_token": reset_token}

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password using a valid reset token."""
    try:
        payload = jwt.decode(request.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    if payload.get("type") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid token type")
    
    user_id = payload.get("sub")
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify token matches stored token
    stored_token = user.get("reset_token")
    if stored_token != request.token:
        raise HTTPException(status_code=400, detail="Invalid token")
    
    # Check token expiry
    expiry = user.get("reset_token_expiry")
    if not expiry or expiry < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token has expired")
    
    # Update password
    new_hashed = hash_password(request.new_password)
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"password_hash": new_hashed},
            "$unset": {
                "reset_otp_hash": "",
                "reset_otp_expiry": "",
                "reset_token": "",
                "reset_token_expiry": "",
                "reset_attempts": ""
            }
        }
    )
    
    # Send confirmation email in background
    # background_tasks.add_task(send_reset_confirmation, user.get("email", ""))
    
    return {"message": "Password reset successfully"}

@router.post("/resend-otp")
async def resend_otp(request: ForgotPasswordRequest):
    """Resend OTP for password reset."""
    identifier = request.username.lower()
    
    # Find user
    user = await db.users.find_one({
        "$or": [
            {"username": {"$regex": f"^{request.username}$", "$options": "i"}},
            {"email": {"$regex": f"^{request.username}$", "$options": "i"}}
        ]
    })
    
    if not user:
        return {"message": "If the account exists, a new code has been sent."}
    
    # Generate new OTP
    otp = generate_otp()
    otp_hash = hash_token(otp)
    expiry = datetime.utcnow() + timedelta(minutes=15)
    
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "reset_otp_hash": otp_hash,
            "reset_otp_expiry": expiry,
            "reset_attempts": 0
        }}
    )
    
    # Send email
    await send_reset_email(user.get("email", ""), user.get("full_name", "User"), otp)
    
    return {"message": "If the account exists, a new code has been sent."}

  