from pydantic import BaseModel
from typing import Optional, Dict

class EmployeeBase(BaseModel):
    employee_id: str
    full_name: str
    role: Optional[str] = None
    badge_number: Optional[str] = None
    dynamic_fields: Optional[Dict] = {}

class EmployeeCreate(EmployeeBase):
    pass

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    badge_number: Optional[str] = None
    is_active: Optional[bool] = None
    dynamic_fields: Optional[Dict] = None

class EmployeeResponse(EmployeeBase):
    id: str
    is_active: bool