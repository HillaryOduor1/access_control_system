from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime

class VisitorBase(BaseModel):
    visitor_name: str
    host_id: Optional[str] = None
    host_name: Optional[str] = None
    dynamic_fields: Optional[Dict] = {}
    consent_gained: bool = False

class VisitorCheckin(VisitorBase):
    pass

class VisitorCheckout(BaseModel):
    visitor_id: str

class VisitorResponse(VisitorBase):
    id: str
    check_in_time: datetime
    check_out_time: Optional[datetime] = None
    status: str