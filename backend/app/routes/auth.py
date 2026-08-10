# 
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..schemas.auth import LoginRequest, TokenResponse
from ..services.auth_service import authenticate_user, create_access_token, create_refresh_token, decode_token
from ..services.rbac_service import get_permissions_for_roles
from ..config import db, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import timedelta
from bson import ObjectId

router = APIRouter(tags=["Authentication"])
security = HTTPBearer()

@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest):
    print(f"[DEBUG] login: username={credentials.username}")
    user = await authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    roles = user.get("roles", [])
    permissions = list(await get_permissions_for_roles(roles))
    
    access_token = create_access_token(
        data={
            "sub": str(user["_id"]),
            "username": user["username"],
            "full_name": user.get("full_name", user["username"]),
            "email": user.get("email", ""),
            "roles": roles,
            "permissions": permissions,
            "tenant_id": user.get("tenant_id", "default")
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(data={"sub": str(user["_id"])})
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@router.post("/refresh")
async def refresh(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    user_id = payload.get("sub")
    try:
        user_id_obj = ObjectId(user_id)
    except:
        raise HTTPException(status_code=401, detail="Invalid user ID")
    
    user = await db.users.find_one({"_id": user_id_obj})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    roles = user.get("roles", [])
    permissions = list(await get_permissions_for_roles(roles))
    new_access = create_access_token(
        data={
            "sub": user_id,
            "username": user["username"],
            "full_name": user.get("full_name", user["username"]),
            "email": user.get("email", ""),
            "roles": roles,
            "permissions": permissions,
            "tenant_id": user.get("tenant_id", "default")
        }
    )
    return {"access_token": new_access, "token_type": "bearer"}

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("sub")
    try:
        user_id_obj = ObjectId(user_id)
    except:
        raise HTTPException(status_code=401, detail="Invalid user ID")
    user = await db.users.find_one({"_id": user_id_obj})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

