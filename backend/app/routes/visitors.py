# backend/app/routes/visitors.py
"""
Visitor check-in / check-out / listing routes.

host_name handling
------------------
On check-in we resolve the host's display name from the users
collection (with an employees fallback) and store it on the visitor
document. That makes the visitor row self-contained: the host name
shown in the UI remains stable even if the user is later renamed or
deactivated.

On read, any row that is still missing host_name (created before this
behaviour was added) is enriched via a single batched lookup per
collection — not one query per visitor.
"""
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from ..config import db
from ..models.visitor import visitor_helper, resolve_host_name
from ..schemas.visitor import (
    VisitorCheckin, VisitorCheckout, VisitorResponse,
)
from ..services.audit_service import log_access
from .auth import get_current_user


router = APIRouter(prefix="/visitors", tags=["Visitors"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _enrich_host_names(visitors: list) -> list:
    """
    Fill in host_name for any visitor dict that is missing it.

    Batches the lookups so we run at most two queries (one for users,
    one for employees) regardless of how many visitors need fixing.
    Mutates the list in place and returns it for chaining.
    """
    to_resolve = []      # list of (visitor_dict, ObjectId)
    for v in visitors:
        if v.get("host_name"):
            continue
        hid = v.get("host_id")
        if not hid:
            v["host_name"] = "Unknown"
            continue
        try:
            to_resolve.append((v, ObjectId(str(hid))))
        except Exception:
            v["host_name"] = "Unknown"

    if not to_resolve:
        return visitors

    ids = [obj for _, obj in to_resolve]

    users_by_id = {}
    try:
        cursor = db.users.find({"_id": {"$in": ids}})
        async for u in cursor:
            users_by_id[u["_id"]] = (
                u.get("full_name") or u.get("username") or "Unknown"
            )
    except Exception:
        pass

    employees_by_id = {}
    try:
        cursor = db.employees.find({"_id": {"$in": ids}})
        async for e in cursor:
            employees_by_id[e["_id"]] = e.get("full_name") or "Unknown"
    except Exception:
        pass

    for v, obj in to_resolve:
        v["host_name"] = (
            users_by_id.get(obj)
            or employees_by_id.get(obj)
            or "Unknown"
        )

    return visitors


# ---------------------------------------------------------------------------
# Check-in
# ---------------------------------------------------------------------------

@router.post("/checkin", response_model=VisitorResponse)
async def checkin(
    visitor: VisitorCheckin,
    current_user=Depends(get_current_user),
):
    visitor_dict = visitor.dict()
    visitor_dict["check_in_time"] = datetime.utcnow().isoformat()
    visitor_dict["status"] = "inside"
    visitor_dict["tenant_id"] = current_user.get("tenant_id")

    # Resolve and store the host's display name now, so the visitor
    # record is self-contained and stays readable even if the host user
    # is later renamed or deactivated.
    visitor_dict["host_name"] = await resolve_host_name(
        visitor_dict.get("host_id")
    )

    result = await db.visitors.insert_one(visitor_dict)
    new_visitor = await db.visitors.find_one({"_id": result.inserted_id})

    await log_access(
        "visitor",
        str(result.inserted_id),
        "in",
        granted=True,
        verified_by=current_user["username"],
    )
    return visitor_helper(new_visitor)


# ---------------------------------------------------------------------------
# Check-out
# ---------------------------------------------------------------------------

@router.post("/checkout")
async def checkout(
    checkout: VisitorCheckout,
    current_user=Depends(get_current_user),
):
    tenant = current_user.get("tenant_id")
    try:
        obj_id = ObjectId(checkout.visitor_id)
    except Exception:
        raise HTTPException(404, "Invalid visitor ID")

    visitor = await db.visitors.find_one(
        {"_id": obj_id, "tenant_id": tenant}
    )
    if not visitor or visitor["status"] != "inside":
        raise HTTPException(404, "Active visitor not found")

    await db.visitors.update_one(
        {"_id": obj_id, "tenant_id": tenant},
        {
            "$set": {
                "check_out_time": datetime.utcnow().isoformat(),
                "status": "out",
            }
        },
    )
    await log_access(
        "visitor",
        checkout.visitor_id,
        "out",
        granted=True,
        verified_by=current_user["username"],
    )
    return {"status": "checked out"}


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@router.get("/active", response_model=list[VisitorResponse])
async def get_active_visitors(current_user=Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    cursor = db.visitors.find(
        {"tenant_id": tenant, "status": "inside"}
    )
    visitors = []
    async for v in cursor:
        visitors.append(visitor_helper(v))
    await _enrich_host_names(visitors)
    return visitors


@router.get("/history", response_model=list[VisitorResponse])
async def get_history(
    limit: int = 100,
    current_user=Depends(get_current_user),
):
    tenant = current_user.get("tenant_id")
    cursor = (
        db.visitors
        .find({"tenant_id": tenant})
        .sort("check_in_time", -1)
        .limit(limit)
    )
    visitors = []
    async for v in cursor:
        visitors.append(visitor_helper(v))
    await _enrich_host_names(visitors)
    return visitors
