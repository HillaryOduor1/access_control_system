# app/routes/password_reset.py
"""
Password reset routes for the desktop client.

Flow
----
1. POST /auth/password/request   { email }
     -> Generates a 6-digit OTP, stores it under purpose
        "password_reset", emails the code. Always returns the same
        generic response (no email enumeration).

2. POST /auth/password/verify    { email, otp }
     -> Validates the OTP. On success returns a short-lived
        `reset_token` (single-use, 15 min TTL) that the client
        presents when setting the new password.

3. POST /auth/password/complete  { email, reset_token, new_password }
     -> Validates the reset_token, checks password policy and
        history, updates the hash, bumps token_version (kills all
        existing sessions), sends a confirmation email.

The desktop client never receives a URL and never has to open a
browser. The whole flow is completed inside the app.
"""
import secrets
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from pydantic import BaseModel, EmailStr, Field

from ..config import db
from ..services.email_service import email_service
from ..services.auth_service import password_service
from ..services.otp_service import otp_service
from ..services.rate_limit_service import rate_limit_service
from .auth import get_client_ip, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/password", tags=["Password Reset"])

RESET_TOKEN_TTL_MINUTES = 15
OTP_PURPOSE = "password_reset"


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return str(email).strip().lower()


# ============================================================================
# Pydantic Models
# ============================================================================

class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)


class PasswordResetCompleteRequest(BaseModel):
    email: EmailStr
    reset_token: str = Field(..., min_length=16)
    new_password: str = Field(..., min_length=8, max_length=128)


# ============================================================================
# Helpers
# ============================================================================

def generate_reset_token() -> str:
    """Cryptographically strong single-use token."""
    return secrets.token_urlsafe(32)


async def store_reset_token(email: str, token: str) -> None:
    """Persist a fresh reset token, invalidating any previous ones."""
    now = get_utc_now()
    expires_at = now + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

    await db.password_reset_tokens.delete_many({"email": email})
    await db.password_reset_tokens.insert_one({
        "email": email,
        "token": token,
        "created_at": now,
        "expires_at": expires_at,
        "used": False,
    })


async def find_valid_reset_token(email: str, token: str):
    now = get_utc_now()
    return await db.password_reset_tokens.find_one({
        "email": email,
        "token": token,
        "expires_at": {"$gt": now},
        "used": False,
    })


async def mark_token_used(email: str, token: str) -> None:
    await db.password_reset_tokens.update_one(
        {"email": email, "token": token},
        {"$set": {"used": True, "used_at": get_utc_now()}},
    )


async def _safe_send_reset_otp(email: str, otp: str) -> None:
    try:
        result = email_service.send_password_reset_otp(email, otp)
        # Support both sync and async implementations
        if hasattr(result, "__await__"):
            await result
        logger.info(f"Password-reset OTP email queued for {email}")
    except Exception as e:
        logger.error(f"Failed to send reset OTP to {email}: {e}", exc_info=True)


async def _safe_send_reset_confirmation(email: str) -> None:
    try:
        result = email_service.send_password_changed_confirmation(email)
        if hasattr(result, "__await__"):
            await result
        logger.info(f"Password-changed confirmation queued for {email}")
    except Exception as e:
        logger.error(f"Failed to send confirmation to {email}: {e}", exc_info=True)


# ============================================================================
# Step 1 — Request a reset code
# ============================================================================

@router.post("/request")
async def request_password_reset(
    request_data: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Send a 6-digit verification code to the user's email.

    Always returns the same response — we do not reveal whether the
    email is registered (prevents account enumeration).
    """
    client_ip = await get_client_ip(request)
    email = normalize_email(request_data.email)

    rate_result = await rate_limit_service.is_rate_limited(
        f"{client_ip}:{email}", "/auth/password/request"
    )
    if rate_result["limited"]:
        reset_seconds = int(
            (rate_result["reset_at"] - get_utc_now()).total_seconds()
        )
        raise HTTPException(
            status_code=429,
            detail=f"Too many password reset requests. "
                   f"Please try again in {reset_seconds} seconds.",
        )

    user = await db.users.find_one({"email": email})

    if user:
        otp = otp_service.generate_otp()
        await otp_service.store_otp(email, OTP_PURPOSE, otp)
        background_tasks.add_task(_safe_send_reset_otp, email, otp)

        logger.info(
            "Password reset OTP issued",
            extra={"email": email, "client_ip": client_ip,
                   "event": "password_reset_requested"},
        )
    else:
        # Burn the same amount of time so timing can't be used to
        # probe which emails exist.
        _ = otp_service.generate_otp()
        logger.info(
            "Password reset requested for non-existent email",
            extra={"email": email, "client_ip": client_ip,
                   "event": "password_reset_nonexistent"},
        )

    return {
        "status": "success",
        "message": "If an account exists with this email, a "
                   "verification code has been sent.",
    }


# ============================================================================
# Step 2 — Verify the code, hand back a reset token
# ============================================================================

@router.post("/verify")
async def verify_reset_otp(
    request_data: PasswordResetVerifyRequest,
    request: Request,
):
    """
    Exchange a valid OTP for a short-lived reset token.

    The reset token is what the client will present when it submits
    the new password. It is single-use and expires after 15 minutes.
    """
    client_ip = await get_client_ip(request)
    email = normalize_email(request_data.email)

    rate_result = await rate_limit_service.is_rate_limited(
        f"{client_ip}:{email}", "/auth/password/verify"
    )
    if rate_result["limited"]:
        raise HTTPException(
            status_code=429,
            detail="Too many verification attempts. Please try again later.",
        )

    result = await otp_service.verify_otp(email, OTP_PURPOSE, request_data.otp)
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "Invalid or expired code"),
        )

    # Only issue a token if the account actually exists. If it doesn't,
    # return the same error a wrong OTP would have produced so we don't
    # leak existence via this step either.
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=400,
                            detail="Invalid or expired code")

    reset_token = generate_reset_token()
    await store_reset_token(email, reset_token)

    logger.info(
        "Password reset OTP verified",
        extra={"email": email, "client_ip": client_ip,
               "event": "password_reset_verified"},
    )

    return {
        "status": "success",
        "message": "Code verified",
        "reset_token": reset_token,
        "expires_in": RESET_TOKEN_TTL_MINUTES * 60,
    }


# ============================================================================
# Step 3 — Complete the reset
# ============================================================================

@router.post("/complete")
async def complete_password_reset(
    request_data: PasswordResetCompleteRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    client_ip = await get_client_ip(request)
    email = normalize_email(request_data.email)

    rate_result = await rate_limit_service.is_rate_limited(
        f"{client_ip}:{email}", "/auth/password/complete"
    )
    if rate_result["limited"]:
        raise HTTPException(
            status_code=429,
            detail="Too many reset attempts. Please try again later.",
        )

    record = await find_valid_reset_token(email, request_data.reset_token)
    if not record:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired reset token. Please start over.",
        )

    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=400,
                            detail="Invalid or expired reset token.")

    is_valid, error = password_service.validate_password(
        request_data.new_password
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    user_id = str(user["_id"])
    new_hash = password_service.hash_password(request_data.new_password)

    if await password_service.check_password_history(user_id, new_hash):
        raise HTTPException(
            status_code=400,
            detail="You have used this password recently. "
                   "Please choose a different password.",
        )

    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "password_hash": new_hash,
                "updated_at": get_utc_now(),
            },
            # Invalidate every existing session for this account.
            "$inc": {"token_version": 1},
        },
    )
    await password_service.add_to_history(user_id, new_hash)
    await mark_token_used(email, request_data.reset_token)

    background_tasks.add_task(_safe_send_reset_confirmation, email)

    logger.info(
        "Password reset completed",
        extra={"user_id": user_id, "email": email, "client_ip": client_ip,
               "event": "password_reset_completed"},
    )

    return {
        "status": "success",
        "message": "Password has been reset successfully. "
                   "Please log in with your new password.",
    }


# ============================================================================
# Admin — purge expired tokens
# ============================================================================

@router.post("/cleanup")
async def cleanup_expired_tokens(
    current_user: dict = Depends(get_current_user),
):
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(status_code=403,
                            detail="Admin access required")

    now = get_utc_now()
    result = await db.password_reset_tokens.delete_many({
        "$or": [
            {"expires_at": {"$lt": now}},
            {"used": True,
             "used_at": {"$lt": now - timedelta(hours=24)}},
        ]
    })

    return {
        "status": "success",
        "message": f"Cleaned up {result.deleted_count} expired tokens",
    }
