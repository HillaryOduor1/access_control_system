# app/services/rate_limit_service.py
"""
MongoDB-based rate limiting service with manual cleanup.
"""
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from ..config import db, RATE_LIMIT

logger = logging.getLogger(__name__)


class RateLimitService:
    """
    MongoDB-based rate limiting service.
    """
    
    def __init__(self):
        self.collection = db.rate_limits
        self._cleanup_interval = 3600  # Clean up every hour
        self._last_cleanup = datetime.utcnow()
    
    def _get_limit_config(self, endpoint: str) -> Dict[str, int]:
        """Get rate limit configuration for an endpoint."""
        if endpoint in RATE_LIMIT:
            return RATE_LIMIT[endpoint]
        
        for key, config in RATE_LIMIT.items():
            if key != "default" and endpoint.startswith(key):
                return config
        
        return RATE_LIMIT.get("default", {"window": 60, "max_requests": 30})
    
    async def _cleanup_expired(self):
        """Clean up expired rate limit records."""
        now = datetime.utcnow()
        if (now - self._last_cleanup).total_seconds() > self._cleanup_interval:
            await self.collection.delete_many({
                "expires_at": {"$lt": now}
            })
            self._last_cleanup = now
    
    async def is_rate_limited(
        self,
        identifier: str,
        endpoint: str,
        limit_config: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Check if a request should be rate limited.
        """
        await self._cleanup_expired()
        
        if limit_config is None:
            limit_config = self._get_limit_config(endpoint)
        
        window = limit_config.get("window", 60)
        max_requests = limit_config.get("max_requests", 30)
        
        key = f"{endpoint}:{identifier}"
        now = datetime.utcnow()
        
        # Calculate window start
        window_start = now - timedelta(seconds=window)
        
        # Count requests in current window
        count = await self.collection.count_documents({
            "key": key,
            "created_at": {"$gte": window_start}
        })
        
        if count >= max_requests:
            # Get earliest request in current window for reset time
            earliest = await self.collection.find_one(
                {"key": key},
                sort=[("created_at", 1)]
            )
            reset_at = earliest["created_at"] + timedelta(seconds=window) if earliest else now + timedelta(seconds=window)
            
            return {
                "limited": True,
                "remaining": 0,
                "reset_at": reset_at,
                "limit": max_requests,
                "window": window
            }
        
        # Record this request
        await self.collection.insert_one({
            "key": key,
            "endpoint": endpoint,
            "identifier": identifier,
            "created_at": now,
            "expires_at": now + timedelta(seconds=window),
            "window": window
        })
        
        remaining = max_requests - count - 1
        
        return {
            "limited": False,
            "remaining": remaining,
            "reset_at": now + timedelta(seconds=window),
            "limit": max_requests,
            "window": window
        }
    
    async def clear_limits(self, identifier: str, endpoint: Optional[str] = None):
        """Clear rate limits for an identifier."""
        query = {"identifier": identifier}
        if endpoint:
            query["endpoint"] = endpoint
        
        await self.collection.delete_many(query)
    
    async def get_usage(self, identifier: str, endpoint: str) -> Dict[str, Any]:
        """Get current rate limit usage."""
        await self._cleanup_expired()
        
        limit_config = self._get_limit_config(endpoint)
        window = limit_config.get("window", 60)
        max_requests = limit_config.get("max_requests", 30)
        
        key = f"{endpoint}:{identifier}"
        window_start = datetime.utcnow() - timedelta(seconds=window)
        
        count = await self.collection.count_documents({
            "key": key,
            "created_at": {"$gte": window_start}
        })
        
        return {
            "used": count,
            "limit": max_requests,
            "remaining": max_requests - count,
            "window_seconds": window
        }


# Global instance
rate_limit_service = RateLimitService()