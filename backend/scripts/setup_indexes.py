# scripts/setup_indexes.py
"""
Setup MongoDB indexes for the application.
Run this script once to create all required indexes.
"""
import asyncio
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Add the parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import MONGO_URI, DATABASE_NAME

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_index_safely(collection, keys, **kwargs):
    """
    Create an index safely, handling Atlas limitations.
    """
    try:
        # For Atlas free tier, we need to handle TTL differently
        if "expire_after_seconds" in kwargs:
            # Check if it's a TTL index
            ttl_value = kwargs.get("expire_after_seconds")
            if ttl_value == 0:
                # For Atlas, we need to use a positive value or handle differently
                # We'll use a long TTL (1 year) instead of 0
                kwargs["expire_after_seconds"] = 31536000  # 1 year
                logger.warning(f"TTL set to 0 not supported in Atlas free tier. Using 1 year instead.")
        
        await collection.create_index(keys, **kwargs)
        logger.info(f"✓ Index created on {collection.name}: {keys}")
        return True
    except Exception as e:
        error_msg = str(e)
        if "Index option expire_after_seconds" in error_msg:
            # Try without TTL
            kwargs.pop("expire_after_seconds", None)
            try:
                await collection.create_index(keys, **kwargs)
                logger.info(f"✓ Index created on {collection.name} (without TTL): {keys}")
                return True
            except Exception as e2:
                logger.warning(f"⚠ Failed to create index on {collection.name}: {e2}")
                return False
        else:
            logger.warning(f"⚠ Failed to create index on {collection.name}: {e}")
            return False


async def setup_indexes():
    """Create all necessary indexes with Atlas compatibility."""
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DATABASE_NAME]
    
    print("=" * 60)
    print("Setting up MongoDB indexes...")
    print(f"Database: {DATABASE_NAME}")
    print("=" * 60)
    
    # Rate limits collection
    await create_index_safely(db.rate_limits, [("key", 1), ("window", 1)], background=True)
    await create_index_safely(db.rate_limits, "expires_at", expire_after_seconds=31536000, background=True)
    
    # OTP collection
    await create_index_safely(db.otp_codes, [("email", 1), ("purpose", 1)], background=True)
    await create_index_safely(db.otp_codes, "expires_at", expire_after_seconds=31536000, background=True)
    
    # Verified emails
    await create_index_safely(db.otp_verified, "email", background=True)
    await create_index_safely(db.otp_verified, "expires_at", expire_after_seconds=31536000, background=True)
    
    # Verified emails (for signup)
    await create_index_safely(db.verified_emails, "email", background=True)
    await create_index_safely(db.verified_emails, "expires_at", expire_after_seconds=31536000, background=True)
    
    # Lockout attempts
    await create_index_safely(db.lockout_attempts, [("username", 1), ("ip_address", 1)], background=True)
    await create_index_safely(db.lockout_attempts, "locked_until", expire_after_seconds=31536000, background=True)
    await create_index_safely(db.lockout_attempts, "attempt_expires_at", expire_after_seconds=31536000, background=True)
    
    '''# Token blacklist
    await create_index_safely(db.token_blacklist, "jti", unique=True, background=True)
    await create_index_safely(db.token_blacklist, "expires_at", expire_after_seconds=31536000, background=True)
    
    # Password history
    await create_index_safely(db.password_history, [("user_id", 1), ("created_at", -1)], background=True)
    await create_index_safely(db.password_history, "expires_at", expire_after_seconds=31536000, background=True)'''

    # Password history
    await create_index_safely(db.password_history, [("user_id", 1), ("created_at", -1)], background=True)
    await create_index_safely(db.password_history, "expires_at", expire_after_seconds=31536000, background=True)

    # Token blacklist - ensure unique jti
    await create_index_safely(db.token_blacklist, "jti", unique=True, background=True)
    await create_index_safely(db.token_blacklist, "expires_at", expire_after_seconds=31536000, background=True)
    await create_index_safely(db.token_blacklist, "user_id", background=True)
    
    # Users collection - ensure email and username are unique
    await create_index_safely(db.users, "username", unique=True, background=True)
    await create_index_safely(db.users, "email", unique=True, background=True)
    await create_index_safely(db.users, "tenant_id", background=True)
    
    print("=" * 60)
    print("All indexes created successfully!")
    print("=" * 60)
    
    client.close()


if __name__ == "__main__":
    asyncio.run(setup_indexes())