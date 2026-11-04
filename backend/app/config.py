# app/config.py
import os
import secrets
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load .env from the correct path
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
load_dotenv()

# Environment detection
ENV = os.getenv("ENV", "development")
IS_PRODUCTION = ENV == "production"


# ============================================================================
# JWT Security - Requires strong secret
# ============================================================================

def get_jwt_secret() -> str:
    """Get JWT secret with validation."""
    secret = os.getenv("JWT_SECRET")
    
    if IS_PRODUCTION:
        if not secret:
            raise ValueError(
                "JWT_SECRET environment variable is required in production. "
                "Generate one using: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        if len(secret) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 characters long. "
                "Generate one using: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        if secret in ["your-secret-key-change-this", "your-secret-key"]:
            raise ValueError(
                "Default JWT_SECRET detected in production! "
                "Generate a secure secret immediately."
            )
    else:
        if not secret or secret in ["your-secret-key-change-this", "your-secret-key"]:
            secret = secrets.token_urlsafe(32)
            print(f"⚠️  Using auto-generated JWT_SECRET for development: {secret[:8]}...")
            print("   Set JWT_SECRET in .env for consistent development sessions")
    
    return secret


# ============================================================================
# Database
# ============================================================================

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "icta_db")

# Database client
client = AsyncIOMotorClient(MONGO_URI)
db = client[DATABASE_NAME]


# ============================================================================
# JWT Settings
# ============================================================================

JWT_SECRET = get_jwt_secret()
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 15))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))
TOKEN_BLACKLIST_EXPIRE_DAYS = int(os.getenv("TOKEN_BLACKLIST_EXPIRE_DAYS", 7))


# ============================================================================
# Rate Limiting Settings
# ============================================================================

RATE_LIMIT = {
    "login": {"window": 60, "max_requests": 5},
    "send_otp": {"window": 60, "max_requests": 3},
    "verify_otp": {"window": 60, "max_requests": 5},
    "signup": {"window": 3600, "max_requests": 10},
    "refresh": {"window": 60, "max_requests": 10},
    "password_reset": {"window": 3600, "max_requests": 3},
    "default": {"window": 60, "max_requests": 30},
}


# ============================================================================
# Account Lockout Settings
# ============================================================================

MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", 5))
LOCKOUT_DURATION_MINUTES = int(os.getenv("LOCKOUT_DURATION_MINUTES", 15))
ATTEMPT_WINDOW_SECONDS = int(os.getenv("ATTEMPT_WINDOW_SECONDS", 3600))


# ============================================================================
# OTP Settings
# ============================================================================

OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", 10))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", 3))
OTP_LENGTH = int(os.getenv("OTP_LENGTH", 6))


# ============================================================================
# Email Settings
# ============================================================================

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@icta.go.ke")
APP_NAME = os.getenv("APP_NAME", "Access Control System")


# ============================================================================
# Security Headers
# ============================================================================

SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-XSS-Protection": "1; mode=block",
}

if IS_PRODUCTION:
    SECURITY_HEADERS["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


# ============================================================================
# CORS Settings
# ============================================================================

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else ["http://localhost:8000", "http://localhost:8080"]


# ============================================================================
# Print loaded configuration
# ============================================================================

print("=" * 60)
print("CONFIG LOADED")
print(f"ENV: {ENV}")
print(f"Database: {MONGO_URI}")
print(f"JWT Secret: {'*' * 8} (set)" if JWT_SECRET else "JWT Secret: NOT SET!")
print(f"Rate Limits: {RATE_LIMIT}")
print("=" * 60)


# Settings class for backward compatibility
class Settings:
    MONGO_URI = MONGO_URI
    DATABASE_NAME = DATABASE_NAME
    JWT_SECRET = JWT_SECRET
    JWT_ALGORITHM = JWT_ALGORITHM
    ACCESS_TOKEN_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_MINUTES
    REFRESH_TOKEN_EXPIRE_DAYS = REFRESH_TOKEN_EXPIRE_DAYS
    SMTP_HOST = SMTP_HOST
    SMTP_PORT = SMTP_PORT
    SMTP_USER = SMTP_USER
    SMTP_PASSWORD = SMTP_PASSWORD
    SMTP_FROM = SMTP_FROM
    APP_NAME = APP_NAME
    OTP_EXPIRY_MINUTES = OTP_EXPIRY_MINUTES
    OTP_MAX_ATTEMPTS = OTP_MAX_ATTEMPTS
    MAX_LOGIN_ATTEMPTS = MAX_LOGIN_ATTEMPTS
    LOCKOUT_DURATION_MINUTES = LOCKOUT_DURATION_MINUTES


settings = Settings()
