import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

# Database
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "icta_db")

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Email Settings (for password reset)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@ictauthority.go.ke")
APP_NAME = os.getenv("APP_NAME", "ICT Authority Access Control")

# Database client
client = AsyncIOMotorClient(MONGO_URI)
db = client[DATABASE_NAME]

# Settings class for backwards compatibility
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

settings = Settings()
