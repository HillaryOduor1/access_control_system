from fastapi import APIRouter, Depends, HTTPException
from ..schemas.visitor import VisitorCheckin, VisitorCheckout, VisitorResponse
from ..config import db
from .auth import get_current_user
from ..models.visitor import visitor_helper
from ..services.audit_service import log_access
from datetime import datetime
from bson import ObjectId

router = APIRouter(prefix="/visitors", tags=["Visitors"])

@router.post("/checkin", response_model=VisitorResponse)
async def checkin(visitor: VisitorCheckin, current_user=Depends(get_current_user)):
    visitor_dict = visitor.dict()
    visitor_dict["check_in_time"] = datetime.utcnow().isoformat()
    visitor_dict["status"] = "inside"
    visitor_dict["tenant_id"] = current_user.get("tenant_id")  # add tenant
    result = await db.visitors.insert_one(visitor_dict)
    new_visitor = await db.visitors.find_one({"_id": result.inserted_id})
    await log_access("visitor", str(result.inserted_id), "in", granted=True, verified_by=current_user["username"])
    return visitor_helper(new_visitor)

@router.post("/checkout")
async def checkout(checkout: VisitorCheckout, current_user=Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    try:
        obj_id = ObjectId(checkout.visitor_id)
    except:
        raise HTTPException(404, "Invalid visitor ID")
    visitor = await db.visitors.find_one({"_id": obj_id, "tenant_id": tenant})
    if not visitor or visitor["status"] != "inside":
        raise HTTPException(404, "Active visitor not found")
    await db.visitors.update_one(
        {"_id": obj_id, "tenant_id": tenant},
        {"$set": {"check_out_time": datetime.utcnow().isoformat(), "status": "out"}}
    )
    await log_access("visitor", checkout.visitor_id, "out", granted=True, verified_by=current_user["username"])
    return {"status": "checked out"}

@router.get("/active", response_model=list[VisitorResponse])
async def get_active_visitors(current_user=Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    cursor = db.visitors.find({"tenant_id": tenant, "status": "inside"})
    visitors = []
    async for v in cursor:
        visitors.append(visitor_helper(v))
    return visitors

@router.get("/history", response_model=list[VisitorResponse])
async def get_history(limit: int = 100, current_user=Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    cursor = db.visitors.find({"tenant_id": tenant}).sort("check_in_time", -1).limit(limit)
    visitors = []
    async for v in cursor:
        visitors.append(visitor_helper(v))
    return visitors

    