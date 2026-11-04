# app/schemas/user.py
"""
User schemas.

email is intentionally typed as Optional[str] rather than EmailStr.
Real deployments contain users seeded without an email (admin-created
accounts, migrated rows), and a single empty string in the collection
would otherwise fail validation of the entire GET /users response.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    employee_number: Optional[str] = None
    phone: Optional[str] = None
    id_number: Optional[str] = None
    tenant_id: Optional[str] = None
    roles: List[str] = Field(default_factory=list)

    @field_validator("roles", mode="before")
    @classmethod
    def _coerce_roles(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, (list, tuple, set)):
            return [str(x) for x in v if x]
        return []

    @field_validator("email", mode="before")
    @classmethod
    def _coerce_email(cls, v):
        # Preserve None; convert everything else to a stripped string.
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class UserCreate(UserBase):
    password: str
    email_verified: bool = False


class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    employee_number: Optional[str] = None
    phone: Optional[str] = None
    id_number: Optional[str] = None
    tenant_id: Optional[str] = None
    roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
    email_verified: Optional[bool] = None


class UserInDB(UserBase):
    id: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    email_verified: bool = False


class UserResponse(UserInDB):
    pass
