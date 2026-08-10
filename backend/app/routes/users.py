from fastapi import APIRouter, Depends, HTTPException
from ..schemas.user import UserCreate, UserUpdate, UserResponse
from ..config import db
from .auth import get_current_user
from ..models.user import user_helper
from datetime import datetime
from ..services.auth_service import hash_password

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("", response_model=UserResponse)
async def create_user(user_data: UserCreate):
    # Check if user already exists
    existing = await db.users.find_one({"username": user_data.username})
    if existing:
        raise HTTPException(400, "Username already exists")
    
    # Ensure tenant_id is provided (mandatory)
    if not user_data.tenant_id:
        raise HTTPException(400, "Organisation (tenant_id) is required")
    
    user_dict = user_data.dict()
    user_dict["password_hash"] = hash_password(user_dict.pop("password"))
    user_dict["is_active"] = True
    user_dict["created_at"] = datetime.utcnow()
    
    result = await db.users.insert_one(user_dict)
    new_user = await db.users.find_one({"_id": result.inserted_id})
    return user_helper(new_user)

@router.get("", response_model=list[UserResponse])
async def get_users(current_user=Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    query = {"tenant_id": tenant}
    cursor = db.users.find(query)
    users = []
    async for u in cursor:
        users.append(user_helper(u))
    return users

@router.get("/me", response_model=UserResponse)
async def get_me(current_user=Depends(get_current_user)):
    return user_helper(current_user)

@router.put("/me", response_model=UserResponse)
async def update_me(update: UserUpdate, current_user=Depends(get_current_user)):
    await db.users.update_one({"_id": current_user["_id"]}, {"$set": update.dict(exclude_unset=True)})
    updated = await db.users.find_one({"_id": current_user["_id"]})
    return user_helper(updated)

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, current_user=Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(404, "Invalid user ID")
    user = await db.users.find_one({"_id": obj_id, "tenant_id": tenant})
    if not user:
        raise HTTPException(404, "User not found")
    return user_helper(user)

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, update: UserUpdate, current_user=Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(404, "Invalid user ID")
    update_dict = {k: v for k, v in update.dict().items() if v is not None}
    if update_dict.get("password"):
        update_dict["password_hash"] = hash_password(update_dict.pop("password"))
    result = await db.users.update_one({"_id": obj_id, "tenant_id": tenant}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(404, "User not found")
    updated = await db.users.find_one({"_id": obj_id})
    return user_helper(updated)

@router.delete("/{user_id}")
async def deactivate_user(user_id: str, current_user=Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(404, "Invalid user ID")
    result = await db.users.update_one({"_id": obj_id, "tenant_id": tenant}, {"$set": {"is_active": False}})
    if result.matched_count == 0:
        raise HTTPException(404, "User not found")
    return {"status": "deactivated"}

    