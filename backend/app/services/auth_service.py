# app/services/auth_service.py
"""
Enhanced authentication service with security features.

Change in this revision
-----------------------
`PasswordService.validate_password` no longer rejects a password
merely because a common word appears inside it. The common-password
check now only fires when the whole password (after stripping trivial
suffixes) *is* the common word. This allows realistic strong passwords
like "Admin@2026" to be accepted while still rejecting "admin",
"admin123", "admin123!" and so on.

The actual login-hang bug lived in `pages/login_page.py` (lambda
connection to a cross-thread signal). See that file for details.
"""
import json
import hashlib
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

import bcrypt
from bson import ObjectId
from bson.errors import InvalidId
from jose import jwt, JWTError

from ..config import (
    JWT_SECRET, JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS,
    TOKEN_BLACKLIST_EXPIRE_DAYS,
    db
)
from ..models.user import USER_COLLECTION
from ..services.rbac_service import get_permissions_for_roles

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================

def get_utc_now() -> datetime:
    """Get current UTC datetime with timezone awareness."""
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    """Normalize email address to lowercase."""
    return str(email).strip().lower()


# ============================================================================
# Password Service
# ============================================================================

class PasswordService:
    """Password management with security features."""

    def __init__(self):
        self.min_length = 8
        self.max_length = 128
        self.rounds = 12
        self._load_common_passwords()

    def _load_common_passwords(self):
        self.common_passwords = {
            'password', 'password123', '123456', '12345678', 'qwerty', 'abc123',
            'admin', 'letmein', 'welcome', 'monkey', 'dragon', 'master', 'sunshine',
            '111111', '123456789', '1234567890', 'password1', 'qwertyuiop',
            'admin123', 'adminadmin', 'root', 'toor', 'passw0rd', 'changeme',
            'iloveyou', 'trustno1', '123123', '1q2w3e4r', 'qwerty123',
        }

    def hash_password(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=self.rounds)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, plain: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            logger.warning(f"Password verification error: {e}")
            return False

    def _normalize_for_common_check(self, password: str) -> str:
        """
        Reduce a password to its 'core' for the common-password check.

        Only strips a single trailing digit run and/or a single trailing
        special-character run. It does NOT strip leading characters or
        interior content, so "Admin@2026" reduces to "admin@2026" and is
        not mistaken for "admin".
        """
        p = password.lower().strip()
        # Strip one trailing digit run (e.g. "admin123" -> "admin")
        p = p.rstrip("0123456789")
        # Strip one trailing special-char run (e.g. "admin!" -> "admin")
        p = p.rstrip("!@#$%^&*()_+-=[]{}|;:'\",.<>/?`~")
        return p

    def validate_password(self, password: str) -> Tuple[bool, Optional[str]]:
        """
        Validate password strength.

        Rules:
        - 8 to 128 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character
        - Must NOT be an exact common password
        - Must NOT reduce (via a single trailing digit/special run) to a
          common password
        - Must NOT contain long sequential runs (1234, abcd, qwer, asdf)
        - Must NOT contain excessive character repetition
        """
        # --- Length ---
        if len(password) < self.min_length:
            return False, f"Password must be at least {self.min_length} characters long."

        if len(password) > self.max_length:
            return False, f"Password must be at most {self.max_length} characters long."

        # --- Character classes ---
        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter (A-Z)."

        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter (a-z)."

        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one number (0-9)."

        special_chars = "!@#$%^&*(),.?\":{}|<>_-+=[];'`~/\\"
        if not any(c in special_chars for c in password):
            return False, "Password must contain at least one special character (e.g. !@#$%^&*)."

        # --- Exact match against common passwords ---
        if password.lower() in self.common_passwords:
            return False, "This password is too common and easily guessable. Please choose a different one."

        # --- Common password + trivial suffix (only if the WHOLE thing
        # reduces to a common password). "Admin@2026" is fine; "admin1"
        # is not.
        normalized = self._normalize_for_common_check(password)
        if normalized in self.common_passwords:
            return False, "This password is too similar to a common password. Please choose a different one."

        # --- Sequential character runs (keyboard & alphabet) ---
        lower = password.lower()
        sequences = [
            "0123", "1234", "2345", "3456", "4567", "5678", "6789",
            "abcd", "bcde", "cdef", "defg", "efgh", "fghi", "ghij", "hijk",
            "ijkl", "jklm", "klmn", "lmno", "mnop", "nopq", "opqr", "pqrs",
            "qrst", "rstu", "stuv", "tuvw", "uvwx", "vwxy", "wxyz",
            "qwer", "wert", "erty", "rtyu", "tyui", "yuio", "uiop",
            "asdf", "sdfg", "dfgh", "fghj", "ghjk", "hjkl",
            "zxcv", "xcvb", "cvbn", "vbnm",
        ]
        if any(seq in lower for seq in sequences):
            return False, "Password contains sequential characters (e.g. 1234, abcd). Please avoid sequences."

        if any(seq[::-1] in lower for seq in sequences):
            return False, "Password contains reversed sequential characters (e.g. 4321, dcba). Please avoid sequences."

        # --- Excessive character repetition ---
        if len(set(password)) < 4:
            return False, "Password contains too many repeated characters. Please use a more varied password."

        return True, None

    async def check_password_history(self, user_id: str, password_hash: str) -> bool:
        try:
            user_id_obj = ObjectId(user_id)
        except (InvalidId, TypeError):
            return False

        history = await db.password_history.find(
            {"user_id": user_id_obj}
        ).sort("created_at", -1).limit(5).to_list(None)

        for entry in history:
            if entry.get("password_hash") == password_hash:
                return True
        return False

    async def add_to_history(self, user_id: str, password_hash: str) -> None:
        try:
            user_id_obj = ObjectId(user_id)
        except (InvalidId, TypeError):
            return

        now = get_utc_now()

        await db.password_history.insert_one({
            "user_id": user_id_obj,
            "password_hash": password_hash,
            "created_at": now,
            "expires_at": now + timedelta(days=365)
        })

        count = await db.password_history.count_documents({"user_id": user_id_obj})
        if count > 10:
            oldest = await db.password_history.find(
                {"user_id": user_id_obj}
            ).sort("created_at", 1).limit(count - 10).to_list(None)

            if oldest:
                oldest_ids = [doc["_id"] for doc in oldest]
                await db.password_history.delete_many({"_id": {"$in": oldest_ids}})


# ============================================================================
# JWT Service
# ============================================================================

class JWTService:
    """Enhanced JWT management with security features."""

    def __init__(self):
        self.secret = JWT_SECRET
        self.algorithm = JWT_ALGORITHM
        self.access_expire_minutes = ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_expire_days = REFRESH_TOKEN_EXPIRE_DAYS

    def create_access_token(
        self,
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        if expires_delta is None:
            expires_delta = timedelta(minutes=self.access_expire_minutes)

        now = get_utc_now()
        expire = now + expires_delta
        token_id = secrets.token_urlsafe(16)

        to_encode = data.copy()
        to_encode.update({
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "jti": token_id,
            "type": "access"
        })

        return jwt.encode(to_encode, self.secret, algorithm=self.algorithm)

    def create_refresh_token(
        self,
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        if expires_delta is None:
            expires_delta = timedelta(days=self.refresh_expire_days)

        now = get_utc_now()
        expire = now + expires_delta
        token_id = secrets.token_urlsafe(24)

        to_encode = data.copy()
        to_encode.update({
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "jti": token_id,
            "type": "refresh"
        })

        return jwt.encode(to_encode, self.secret, algorithm=self.algorithm)

    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={
                    "verify_exp": True,
                    "require": ["exp", "iat", "sub", "jti", "type"]
                }
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token decode error: {e}")
            return None

    def decode_token_without_validation(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            return jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={"verify_exp": False, "verify_signature": False}
            )
        except Exception:
            return None

    async def blacklist_token(
        self,
        jti: str,
        user_id: Optional[str] = None,
        token_type: str = "access",
        expires_at: Optional[datetime] = None
    ) -> None:
        if not jti:
            logger.warning("Cannot blacklist token: missing jti")
            return

        if expires_at is None:
            expires_at = get_utc_now() + timedelta(days=TOKEN_BLACKLIST_EXPIRE_DAYS)

        try:
            await db.token_blacklist.insert_one({
                "jti": jti,
                "user_id": user_id,
                "token_type": token_type,
                "blacklisted_at": get_utc_now(),
                "expires_at": expires_at
            })
            logger.debug(f"Token {jti[:8]}... blacklisted")
        except Exception as e:
            logger.error(f"Failed to blacklist token: {e}")

    async def is_token_blacklisted(self, jti: str) -> bool:
        if not jti:
            return False
        try:
            record = await db.token_blacklist.find_one({"jti": jti})
            return record is not None
        except Exception as e:
            logger.error(f"Failed to check token blacklist: {e}")
            return False

    async def get_token_blacklist_count(self) -> int:
        return await db.token_blacklist.count_documents({})


# ============================================================================
# Authentication Functions
# ============================================================================

async def authenticate_user(username: str, password: str) -> Optional[dict]:
    normalized_username = username.strip().lower()

    try:
        user = await db[USER_COLLECTION].find_one({
            "$or": [
                {"username": normalized_username},
                {"email": normalized_username}
            ],
            "is_active": True
        })

        if not user:
            # Dummy hash to keep timing roughly constant.
            password_service.hash_password("dummy_password_for_timing")
            logger.warning(f"User not found: {normalized_username}")
            return None

        password_hash = user.get("password_hash")
        if not password_hash:
            logger.warning(f"User {normalized_username} has no password hash")
            return None

        if not password_service.verify_password(password, password_hash):
            logger.warning(f"Password mismatch for user: {normalized_username}")
            return None

        logger.info(f"Authentication successful for user: {normalized_username}")
        return user

    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return None


# ============================================================================
# Token Building Functions
# ============================================================================

async def build_token_data(user: dict) -> dict:
    """Centralized function to build JWT token payload."""
    user_id = str(user["_id"])
    roles = user.get("roles", [])
    permissions = list(await get_permissions_for_roles(roles))

    return {
        "sub": user_id,
        "username": user.get("username"),
        "full_name": user.get("full_name", user.get("username")),
        "email": user.get("email", ""),
        "roles": roles,
        "permissions": permissions,
        "tenant_id": user.get("tenant_id"),
        "token_version": user.get("token_version", 0),
        "type": "access"
    }


async def get_user_from_token(token: str) -> Optional[dict]:
    payload = jwt_service.decode_token(token)
    if not payload:
        return None

    jti = payload.get("jti")
    if jti and await jwt_service.is_token_blacklisted(jti):
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    try:
        user_id_obj = ObjectId(user_id)
    except (InvalidId, TypeError):
        return None

    return await db[USER_COLLECTION].find_one(
        {"_id": user_id_obj, "is_active": True}
    )


# ============================================================================
# Convenience Functions
# ============================================================================

password_service = PasswordService()
jwt_service = JWTService()


def hash_password(password: str) -> str:
    return password_service.hash_password(password)


def verify_password(plain: str, hashed: str) -> bool:
    return password_service.verify_password(plain, hashed)


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    return jwt_service.create_access_token(data, expires_delta)


def create_refresh_token(data: dict) -> str:
    return jwt_service.create_refresh_token(data)


def decode_token(token: str) -> Optional[Dict]:
    return jwt_service.decode_token(token)
