# app/models/user.py
"""
User model helpers.

user_helper is now null-safe: it guarantees every key UserResponse
requires is present and non-null. Anything missing gets a sane default.
"""
from datetime import datetime, timezone


USER_COLLECTION = "users"


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def user_helper(user) -> dict:
    """Convert a MongoDB user document to the API response shape."""
    created = user.get("created_at") or get_utc_now()
    updated = user.get("updated_at") or created

    roles = user.get("roles")
    if roles is None:
        roles = []
    elif isinstance(roles, str):
        roles = [roles] if roles else []
    elif isinstance(roles, (list, tuple, set)):
        roles = [str(r) for r in roles if r]
    else:
        roles = []

    email = user.get("email")
    if email is not None:
        email = str(email).strip() or None

    return {
        "id": str(user.get("_id", "")),
        "username": str(user.get("username", "") or ""),
        "email": email,
        "full_name": str(user.get("full_name", "") or ""),
        "first_name": str(user.get("first_name", "") or ""),
        "last_name": str(user.get("last_name", "") or ""),
        "employee_number": str(user.get("employee_number", "") or ""),
        "phone": str(user.get("phone", "") or ""),
        "id_number": str(user.get("id_number", "") or ""),
        "tenant_id": str(user.get("tenant_id", "default") or "default"),
        "roles": roles,
        "is_active": bool(user.get("is_active", True)),
        "created_at": created,
        "updated_at": updated,
        "email_verified": bool(user.get("email_verified", False)),
    }
