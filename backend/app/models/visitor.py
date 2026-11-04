# backend/app/models/visitor.py
"""
Visitor model helpers.

host_name resolution
--------------------
The desktop client's host dropdown is populated from the users
collection. Older rows may have host_id values that point at the
employees collection. resolve_host_name() checks users first and
falls back to employees so both shapes display correctly.
"""
from bson import ObjectId

from ..config import db


VISITOR_COLLECTION = "visitors"


async def resolve_host_name(host_id) -> str:
    """
    Resolve a single host_id to a display name.
    Returns "Unknown" when nothing can be found.
    """
    if not host_id:
        return "Unknown"
    try:
        obj_id = ObjectId(str(host_id))
    except Exception:
        return "Unknown"

    # Preferred: users collection.
    try:
        user = await db.users.find_one({"_id": obj_id})
        if user:
            return (user.get("full_name")
                    or user.get("username")
                    or "Unknown")
    except Exception:
        pass

    # Fallback: employees collection (legacy rows).
    try:
        emp = await db.employees.find_one({"_id": obj_id})
        if emp:
            return emp.get("full_name") or "Unknown"
    except Exception:
        pass

    return "Unknown"


def visitor_helper(visitor) -> dict:
    """Convert a MongoDB visitor document to the API response shape.

    host_name is passed through as stored. If it's missing (None), the
    route layer is responsible for enriching it via resolve_host_name
    before returning the response. This helper does NOT default the
    value to "Unknown" so the caller can tell the difference between
    "already resolved" and "needs a lookup".
    """
    return {
        "id": str(visitor["_id"]),
        "visitor_name": visitor.get("visitor_name", ""),
        "check_in_time": visitor.get("check_in_time"),
        "check_out_time": visitor.get("check_out_time"),
        "host_id": visitor.get("host_id"),
        "host_name": visitor.get("host_name"),
        "status": visitor.get("status", "inside"),
        "dynamic_fields": visitor.get("dynamic_fields", {}),
        "consent_gained": visitor.get("consent_gained", False),
    }
