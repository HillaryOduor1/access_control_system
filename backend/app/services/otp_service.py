# app/services/otp_service.py
"""
MongoDB-based OTP service with manual expiration handling.
"""
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from ..config import db, OTP_EXPIRY_MINUTES, OTP_MAX_ATTEMPTS, OTP_LENGTH

logger = logging.getLogger(__name__)


def get_utc_now() -> datetime:
    """Get current UTC datetime with timezone awareness."""
    return datetime.now(timezone.utc)


class OTPService:
    """
    MongoDB-based OTP service with manual expiration.
    """
    
    def __init__(self):
        self.collection = db.otp_codes
        self.otp_ttl = OTP_EXPIRY_MINUTES * 60
        self.max_attempts = OTP_MAX_ATTEMPTS
        self.otp_length = OTP_LENGTH
    
    def generate_otp(self) -> str:
        """Generate cryptographically secure OTP."""
        return ''.join([str(secrets.randbelow(10)) for _ in range(self.otp_length)])
    
    async def store_otp(
        self,
        email: str,
        purpose: str,
        otp: str,
        expiry_minutes: int = None
    ) -> bool:
        """Store OTP in MongoDB with expiration."""
        if expiry_minutes is None:
            expiry_minutes = OTP_EXPIRY_MINUTES
        
        now = get_utc_now()
        expires_at = now + timedelta(minutes=expiry_minutes)
        
        # Delete any existing OTP for this email/purpose
        await self.collection.delete_many({
            "email": email,
            "purpose": purpose
        })
        
        # Store new OTP
        await self.collection.insert_one({
            "email": email,
            "purpose": purpose,
            "otp": otp,
            "attempts": 0,
            "created_at": now,
            "expires_at": expires_at,
            "verified": False
        })
        
        logger.info(f"OTP stored for {email} with purpose {purpose}")
        return True
    
    async def verify_otp(
        self,
        email: str,
        purpose: str,
        otp: str
    ) -> Dict[str, Any]:
        """Verify OTP with attempt tracking."""
        # Clean up expired OTPs first
        await self._cleanup_expired()
        
        # Find OTP record
        record = await self.collection.find_one({
            "email": email,
            "purpose": purpose
        })
        
        if not record:
            return {
                "success": False,
                "message": "No verification code found. Please request a new one."
            }
        
        # Check if already verified
        if record.get("verified", False):
            await self.collection.delete_one({"_id": record["_id"]})
            return {
                "success": False,
                "message": "This code has already been used. Please request a new one."
            }
        
        # Check expiration
        expires_at = record["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if expires_at < get_utc_now():
            await self.collection.delete_one({"_id": record["_id"]})
            return {
                "success": False,
                "message": "Verification code has expired. Please request a new one."
            }
        
        # Check attempts
        attempts = record.get("attempts", 0)
        if attempts >= self.max_attempts:
            await self.collection.delete_one({"_id": record["_id"]})
            return {
                "success": False,
                "message": "Too many failed attempts. Please request a new code."
            }
        
        # Verify OTP
        if record["otp"] != otp:
            await self.collection.update_one(
                {"_id": record["_id"]},
                {"$inc": {"attempts": 1}}
            )
            remaining = self.max_attempts - (attempts + 1)
            return {
                "success": False,
                "message": f"Invalid verification code. {remaining} attempts remaining."
            }
        
        # Success - mark as verified
        await self.collection.update_one(
            {"_id": record["_id"]},
            {"$set": {"verified": True}}
        )
        
        # Store verification record (expires after 24 hours)
        now = get_utc_now()
        await db.otp_verified.insert_one({
            "email": email,
            "purpose": purpose,
            "verified_at": now,
            "expires_at": now + timedelta(days=1)
        })
        
        # Delete the OTP
        await self.collection.delete_one({"_id": record["_id"]})
        
        logger.info(f"OTP verified successfully for {email} with purpose {purpose}")
        return {
            "success": True,
            "message": "Verification code verified successfully"
        }
    
    async def _cleanup_expired(self):
        """Clean up expired OTP records."""
        await self.collection.delete_many({
            "expires_at": {"$lt": get_utc_now()}
        })
    
    async def is_rate_limited(self, email: str, purpose: str) -> bool:
        """Check if user has exceeded rate limit for OTP requests."""
        one_minute_ago = get_utc_now() - timedelta(minutes=1)
        count = await self.collection.count_documents({
            "email": email,
            "purpose": purpose,
            "created_at": {"$gte": one_minute_ago}
        })
        return count >= 3
    
    async def get_verification_status(self, email: str, purpose: str) -> bool:
        """Check if email was previously verified."""
        await self._cleanup_expired_verified()
        record = await db.otp_verified.find_one({
            "email": email,
            "purpose": purpose,
            "expires_at": {"$gt": get_utc_now()}
        })
        return record is not None
    
    async def _cleanup_expired_verified(self):
        """Clean up expired verification records."""
        await db.otp_verified.delete_many({
            "expires_at": {"$lt": get_utc_now()}
        })
    
    async def mark_email_verified(self, email: str):
        """Mark an email as verified for signup."""
        now = get_utc_now()
        await db.verified_emails.update_one(
            {"email": email},
            {"$set": {
                "verified": True,
                "verified_at": now,
                "expires_at": now + timedelta(days=365)
            }},
            upsert=True
        )


# Global instance
otp_service = OTPService()

