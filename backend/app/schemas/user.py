from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    employee_number: Optional[str] = None
    phone: Optional[str] = None
    id_number: Optional[str] = None
    tenant_id: Optional[str] = None
    roles: List[str] = []

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    employee_number: Optional[str] = None
    phone: Optional[str] = None
    id_number: Optional[str] = None
    tenant_id: Optional[str] = None
    roles: Optional[List[str]] = None
    is_active: Optional[bool] = None

class UserInDB(UserBase):
    id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

class UserResponse(UserInDB):
    pass
    
    