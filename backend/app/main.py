# app/main.py
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import (
    auth, users, employees, visitors, access_logs, sync,
    password_reset, updates, logs,
)

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger("app.services.email_service").setLevel(logging.INFO)
logging.getLogger("app.routes.auth").setLevel(logging.INFO)
logging.getLogger("app.routes.users").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

env = os.getenv("ENV", "development")
print("=" * 60)
print("APPLICATION STARTING")
print(f"Environment: {env}")
print(f"ENV from os.getenv: {os.getenv('ENV', 'NOT SET')}")
print("=" * 60)

app = FastAPI(title="Access Control API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth")
app.include_router(users.router)
app.include_router(employees.router)
app.include_router(visitors.router)
app.include_router(access_logs.router)
app.include_router(sync.router)
app.include_router(password_reset.router)
app.include_router(updates.router)   # GET  /updates/manifest
app.include_router(logs.router)      # POST /logs/upload


@app.get("/")
async def root():
    return {"message": "Access Control API is running"}


@app.get("/health")
async def health():
    return {"status": "ok"}

  