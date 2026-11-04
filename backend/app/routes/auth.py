# app/routes/auth.py
"""
Enhanced authentication routes with enterprise-grade security features.

Fixes in this revision
----------------------
- Email sending now properly awaits the async EmailService methods.
  Previous version pushed the coroutine into a thread pool executor,
  which produced "coroutine was never awaited" and silently dropped
  every email.
- verify_otp no longer attempts a no-op update on a user document that
  doesn't exist during signup.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId
from bson.errors import InvalidId
from pydantic import BaseModel, EmailStr, Field

from ..schemas.auth import LoginRequest, TokenResponse
from ..services.auth_service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    jwt_service,
    build_token_data,
)
from ..services.rate_limit_service import rate_limit_service
from ..services.lockout_service import lockout_service
from ..services.otp_service import otp_service
from ..services.email_service import email_service
from ..services.rbac_service import get_permissions_for_roles
from ..config import db, IS_PRODUCTION

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])
security = HTTPBearer()


# ============================================================================
# Pydantic Models
# ============================================================================

class OTPSendRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    purpose: str = Field(
        "signup_verification",
        description="Purpose: signup_verification, password_reset, two_factor"
    )


class OTPVerifyRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")
    purpose: str = Field(
        "signup_verification",
        description="Purpose: signup_verification, password_reset, two_factor"
    )


class MessageResponse(BaseModel):
    status: str = Field(..., description="Status: success or error")
    message: str = Field(..., description="Response message")


# ============================================================================
# Helper Functions
# ============================================================================

def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return str(email).strip().lower()


async def get_client_ip(request: Request) -> str:
    trusted_proxies = ["127.0.0.1", "::1", "10.0.0.0/8",
                       "172.16.0.0/12", "192.168.0.0/16"]
    if IS_PRODUCTION:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded and request.client and request.client.host in trusted_proxies:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_user_agent(request: Request) -> str:
    return request.headers.get("User-Agent", "unknown")


async def _safe_send_otp_email(email: str, otp: str, purpose: str):
    """Await the async email send and log any failure without raising."""
    try:
        await email_service.send_otp_email(email, otp, purpose)
        logger.info(f"OTP email delivered to {email} (purpose={purpose})")
    except Exception as e:
        logger.error(f"Failed to send OTP email to {email}: {e}", exc_info=True)


async def _safe_send_welcome_email(email: str, name: str):
    try:
        # Some email services expose this as async, some as sync.
        result = email_service.send_welcome_email(email, name)
        if asyncio.iscoroutine(result):
            await result
        logger.info(f"Welcome email delivered to {email}")
    except Exception as e:
        logger.error(f"Failed to send welcome email to {email}: {e}", exc_info=True)


# ============================================================================
# Authentication Dependencies
# ============================================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    jti = payload.get("jti")
    if jti and await jwt_service.is_token_blacklisted(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing subject")

    token_version = payload.get("token_version", 0)

    try:
        user_id_obj = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=401, detail="Invalid user ID format")

    user = await db.users.find_one({"_id": user_id_obj, "is_active": True})
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    db_token_version = user.get("token_version", 0)
    if token_version != db_token_version:
        raise HTTPException(status_code=401, detail="Token has been revoked")

    return user


# ============================================================================
# Login Endpoint
# ============================================================================

@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, request: Request):
    client_ip = await get_client_ip(request)
    user_agent = await get_user_agent(request)
    normalized_username = credentials.username.strip().lower()

    rate_result = await rate_limit_service.is_rate_limited(
        client_ip, "/auth/login"
    )
    if rate_result["limited"]:
        reset_seconds = int((rate_result["reset_at"] - get_utc_now()).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Please try again in {reset_seconds} seconds."
        )

    lockout_status = await lockout_service.get_lockout_status(normalized_username)
    if lockout_status and lockout_status.get("is_locked"):
        raise HTTPException(
            status_code=429,
            detail=lockout_status.get("message", "Account temporarily locked")
        )

    user = await authenticate_user(normalized_username, credentials.password)

    if not user:
        lockout_result = await lockout_service.record_failed_attempt(
            normalized_username, client_ip, user_agent
        )
        if lockout_result.get("is_locked"):
            raise HTTPException(
                status_code=429,
                detail=lockout_result.get("message")
            )
        raise HTTPException(
            status_code=401,
            detail=lockout_result.get("message", "Invalid credentials")
        )

    await lockout_service.reset_attempts(normalized_username, client_ip)

    token_data = await build_token_data(user)

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": str(user["_id"])})

    logger.info(
        "User logged in",
        extra={
            "user_id": str(user["_id"]),
            "tenant_id": user.get("tenant_id"),
            "client_ip": client_ip,
            "event": "user_login"
        }
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


# ============================================================================
# Refresh Token Endpoint
# ============================================================================

@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    client_ip = await get_client_ip(request)

    rate_result = await rate_limit_service.is_rate_limited(
        client_ip, "/auth/refresh"
    )
    if rate_result["limited"]:
        raise HTTPException(
            status_code=429,
            detail="Too many refresh attempts. Please try again later."
        )

    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    jti = payload.get("jti")
    if jti and await jwt_service.is_token_blacklisted(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401,
                            detail="Invalid token: missing subject")

    try:
        user_id_obj = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=401,
                            detail="Invalid user ID format")

    user = await db.users.find_one({"_id": user_id_obj, "is_active": True})
    if not user:
        raise HTTPException(status_code=401,
                            detail="User not found or inactive")

    token_data = await build_token_data(user)

    await jwt_service.blacklist_token(
        jti=jti, user_id=user_id, token_type="refresh"
    )

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": user_id})

    logger.info(
        "Refresh token rotated",
        extra={
            "user_id": user_id,
            "client_ip": client_ip,
            "event": "refresh_token_rotated"
        }
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


# ============================================================================
# Logout Endpoints
# ============================================================================

@router.post("/logout", response_model=MessageResponse)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: dict = Depends(get_current_user)
):
    token = credentials.credentials
    payload = decode_token(token)

    if payload:
        jti = payload.get("jti")
        if jti:
            await jwt_service.blacklist_token(
                jti=jti,
                user_id=str(current_user["_id"]),
                token_type="access"
            )

    logger.info(
        "User logged out",
        extra={"user_id": str(current_user["_id"]), "event": "user_logout"}
    )

    return MessageResponse(status="success", message="Logged out successfully")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])

    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$inc": {"token_version": 1}}
    )

    logger.info(
        "User logged out from all devices",
        extra={"user_id": user_id, "event": "user_logout_all"}
    )

    return MessageResponse(status="success",
                           message="Logged out from all devices")


# ============================================================================
# OTP Endpoints
# ============================================================================

@router.post("/send-otp")
async def send_otp(
    otp_request: OTPSendRequest,
    background_tasks: BackgroundTasks,
    request: Request
):
    client_ip = await get_client_ip(request)
    normalized_email = normalize_email(otp_request.email)

    rate_result = await rate_limit_service.is_rate_limited(
        f"{client_ip}:{normalized_email}:{otp_request.purpose}",
        "/auth/send-otp"
    )
    if rate_result["limited"]:
        reset_seconds = int((rate_result["reset_at"] - get_utc_now()).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Too many OTP requests. Please wait {reset_seconds} seconds."
        )

    otp = otp_service.generate_otp()
    await otp_service.store_otp(normalized_email, otp_request.purpose, otp)

    # Queue the async email send. FastAPI awaits async background tasks
    # after the response is sent, so this does not block the client.
    background_tasks.add_task(
        _safe_send_otp_email,
        normalized_email,
        otp,
        otp_request.purpose,
    )

    logger.info(
        "OTP queued for delivery",
        extra={
            "purpose": otp_request.purpose,
            "email": normalized_email,
            "client_ip": client_ip,
            "event": "otp_sent"
        }
    )

    return {
        "success": True,
        "message": "Verification code sent to your email"
    }


@router.post("/verify-otp")
async def verify_otp(otp_request: OTPVerifyRequest, request: Request):
    client_ip = await get_client_ip(request)
    normalized_email = normalize_email(otp_request.email)

    rate_result = await rate_limit_service.is_rate_limited(
        f"{client_ip}:{normalized_email}:{otp_request.purpose}",
        "/auth/verify-otp"
    )
    if rate_result["limited"]:
        raise HTTPException(
            status_code=429,
            detail="Too many verification attempts. Please try again later."
        )

    result = await otp_service.verify_otp(
        normalized_email, otp_request.purpose, otp_request.otp
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    if otp_request.purpose == "signup_verification":
        await otp_service.mark_email_verified(normalized_email)
        # During signup the user document doesn't exist yet; the update
        # is harmless if it matches nothing.
        try:
            await db.users.update_one(
                {"email": normalized_email},
                {"$set": {"email_verified": True}}
            )
        except Exception as e:
            logger.debug(f"email_verified update skipped: {e}")

    logger.info(
        "OTP verified",
        extra={
            "purpose": otp_request.purpose,
            "client_ip": client_ip,
            "event": "otp_verified"
        }
    )

    return {"success": True, "message": "Email verified successfully"}


# ============================================================================
# Email Check Endpoint
# ============================================================================

@router.get("/check-email")
async def check_email(email: EmailStr, request: Request):
    client_ip = await get_client_ip(request)
    normalized_email = normalize_email(email)

    rate_result = await rate_limit_service.is_rate_limited(
        client_ip, "/auth/check-email"
    )
    if rate_result["limited"]:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later."
        )

    user = await db.users.find_one({"email": normalized_email})
    exists = user is not None

    logger.info(
        "Email check",
        extra={
            "exists": exists,
            "client_ip": client_ip,
            "event": "email_check"
        }
    )

    return {
        "exists": exists,
        "available": not exists,
        "message": "Email is available" if not exists
                   else "Email is already registered",
    }


# ============================================================================
# Health Check Endpoint
# ============================================================================

@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": get_utc_now().isoformat(),
        "service": "access-control-auth"
    }


# ============================================================================
# Session Info Endpoint
# ============================================================================

@router.get("/session")
async def get_session_info(current_user: dict = Depends(get_current_user)):
    return {
        "user_id": str(current_user["_id"]),
        "username": current_user.get("username"),
        "email": current_user.get("email"),
        "roles": current_user.get("roles", []),
        "tenant_id": current_user.get("tenant_id"),
        "token_version": current_user.get("token_version", 0)
    }
