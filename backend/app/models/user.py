from datetime import datetime
from typing import Optional, List

USER_COLLECTION = "users"

def user_helper(user) -> dict:
    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "email": user.get("email", ""),
        "full_name": user.get("full_name", ""),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "employee_number": user.get("employee_number", ""),
        "phone": user.get("phone", ""),
        "id_number": user.get("id_number", ""),
        "tenant_id": user.get("tenant_id", "default"),
        "roles": user.get("roles", []),
        "is_active": user.get("is_active", True),
        "created_at": user.get("created_at", datetime.utcnow()),
        "updated_at": user.get("updated_at", datetime.utcnow()),
    }
    
 