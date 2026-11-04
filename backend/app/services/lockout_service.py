# app/services/lockout_service.py
"""
MongoDB-based account lockout service with manual cleanup.
"""
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from ..config import db, MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES, ATTEMPT_WINDOW_SECONDS

logger = logging.getLogger(__name__)


class AccountLockoutService:
    """
    MongoDB-based account lockout with manual cleanup.
    """
    
    def __init__(self):
        self.collection = db.lockout_attempts
        self.max_attempts = MAX_LOGIN_ATTEMPTS
        self.lockout_duration = LOCKOUT_DURATION_MINUTES * 60
        self.window_seconds = ATTEMPT_WINDOW_SECONDS
        self._cleanup_interval = 3600
        self._last_cleanup = datetime.utcnow()
    
    async def _cleanup_expired(self):
        """Clean up expired lockout records."""
        now = datetime.utcnow()
        if (now - self._last_cleanup).total_seconds() > self._cleanup_interval:
            await self.collection.delete_many({
                "$or": [
                    {"locked_until": {"$lt": now}},
                    {"attempt_expires_at": {"$lt": now}}
                ]
            })
            self._last_cleanup = now
    
    async def get_lockout_status(self, username: str) -> Optional[Dict[str, Any]]:
        """Get current lockout status for a user."""
        await self._cleanup_expired()
        
        # Check if user is locked
        lockout = await self.collection.find_one({
            "username": username,
            "locked_until": {"$gt": datetime.utcnow()},
            "is_locked": True
        })
        
        if lockout:
            remaining_seconds = int((lockout["locked_until"] - datetime.utcnow()).total_seconds())
            return {
                "is_locked": True,
                "remaining_seconds": remaining_seconds,
                "message": f"Account locked. Try again in {remaining_seconds//60} minutes."
            }
        
        # Get current attempts
        attempts = await self.collection.find({
            "username": username,
            "created_at": {"$gte": datetime.utcnow() - timedelta(seconds=self.window_seconds)},
            "is_locked": False
        }).to_list(None)
        
        return {
            "is_locked": False,
            "attempts": len(attempts),
            "remaining_attempts": self.max_attempts - len(attempts)
        }
    
    async def record_failed_attempt(
        self,
        username: str,
        ip_address: str,
        user_agent: str = None
    ) -> Dict[str, Any]:
        """Record a failed login attempt."""
        await self._cleanup_expired()
        
        now = datetime.utcnow()
        
        # Check if already locked
        existing_lockout = await self.collection.find_one({
            "username": username,
            "locked_until": {"$gt": now},
            "is_locked": True
        })
        
        if existing_lockout:
            remaining_seconds = int((existing_lockout["locked_until"] - now).total_seconds())
            return {
                "is_locked": True,
                "reason": "user_locked",
                "remaining_seconds": remaining_seconds,
                "message": f"Account locked. Try again in {remaining_seconds//60} minutes."
            }
        
        # Check IP-based lockout
        ip_lockout = await self.collection.find_one({
            "ip_address": ip_address,
            "locked_until": {"$gt": now},
            "is_locked": True,
            "is_ip_lockout": True
        })
        
        if ip_lockout:
            remaining_seconds = int((ip_lockout["locked_until"] - now).total_seconds())
            return {
                "is_locked": True,
                "reason": "ip_locked",
                "remaining_seconds": remaining_seconds,
                "message": f"Too many attempts from this IP. Please wait {remaining_seconds//60} minutes."
            }
        
        # Count recent attempts
        user_attempts = await self.collection.count_documents({
            "username": username,
            "created_at": {"$gte": now - timedelta(seconds=self.window_seconds)},
            "is_locked": False
        })
        
        ip_attempts = await self.collection.count_documents({
            "ip_address": ip_address,
            "created_at": {"$gte": now - timedelta(seconds=self.window_seconds)},
            "is_locked": False
        })
        
        # Record the attempt
        await self.collection.insert_one({
            "username": username,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "created_at": now,
            "attempt_expires_at": now + timedelta(seconds=self.window_seconds),
            "is_locked": False,
            "is_ip_lockout": False,
            "locked_until": None
        })
        
        # Check if user should be locked
        if user_attempts + 1 >= self.max_attempts:
            locked_until = now + timedelta(seconds=self.lockout_duration)
            
            await self.collection.insert_one({
                "username": username,
                "ip_address": ip_address,
                "created_at": now,
                "attempt_expires_at": None,
                "is_locked": True,
                "is_ip_lockout": False,
                "locked_until": locked_until
            })
            
            return {
                "is_locked": True,
                "reason": "user_locked",
                "remaining_seconds": self.lockout_duration,
                "message": f"Account locked due to multiple failed attempts. Try again in {LOCKOUT_DURATION_MINUTES} minutes."
            }
        
        # Check IP-based lockout
        if ip_attempts + 1 >= self.max_attempts * 2:
            locked_until = now + timedelta(seconds=300)
            
            await self.collection.insert_one({
                "username": username,
                "ip_address": ip_address,
                "created_at": now,
                "attempt_expires_at": None,
                "is_locked": True,
                "is_ip_lockout": True,
                "locked_until": locked_until
            })
            
            return {
                "is_locked": True,
                "reason": "ip_locked",
                "remaining_seconds": 300,
                "message": "Too many attempts from this IP. Please wait 5 minutes."
            }
        
        remaining = self.max_attempts - (user_attempts + 1)
        return {
            "is_locked": False,
            "remaining_attempts": remaining,
            "message": f"{remaining} attempts remaining"
        }
    
    async def reset_attempts(self, username: str, ip_address: str) -> None:
        """Reset attempts on successful login."""
        await self.collection.delete_many({
            "$or": [
                {"username": username, "is_locked": False},
                {"ip_address": ip_address, "is_locked": False}
            ]
        })
        
        await self.collection.delete_many({
            "$or": [
                {"username": username, "is_locked": True},
                {"ip_address": ip_address, "is_locked": True}
            ]
        })


# Global instance
lockout_service = AccountLockoutService()