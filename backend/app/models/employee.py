EMPLOYEE_COLLECTION = "employees"

def employee_helper(emp) -> dict:
    return {
        "id": str(emp["_id"]),
        "employee_id": emp["employee_id"],
        "full_name": emp["full_name"],
        "role": emp.get("role", ""),
        "badge_number": emp.get("badge_number", ""),
        "is_active": emp.get("is_active", True),
        "dynamic_fields": emp.get("dynamic_fields", {}),
        "created_at": emp.get("created_at"),
    }