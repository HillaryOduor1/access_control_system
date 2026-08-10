from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
class AccessLogBase(BaseModel):
    person_type: str  # 'visitor' or 'employee'
    person_id: str
    direction: str    # 'in' or 'out'
    granted: bool = True
    reason: Optional[str] = None
    verified_by: Optional[str] = "system"

class AccessLogCreate(AccessLogBase):
    timestamp: Optional[datetime] = None

class AccessLogResponse(AccessLogBase):
    id: str
    timestamp: datetime