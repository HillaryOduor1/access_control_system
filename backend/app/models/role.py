ROLE_COLLECTION = "roles"

def role_helper(role) -> dict:
    return {
        "name": role["name"],
        "permissions": role.get("permissions", []),
    }