from pydantic import BaseModel
from typing import List, Optional   # <-- add this

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    username: Optional[str] = None
    roles: List[str] = []
    permissions: List[str] = []