from ..config import db
from ..models.role import ROLE_COLLECTION

async def get_permissions_for_roles(roles: list) -> set:
    perms = set()
    cursor = db[ROLE_COLLECTION].find({"name": {"$in": roles}})
    async for role in cursor:
        perms.update(role.get("permissions", []))
    return perms

async def user_has_permission(user, permission: str) -> bool:
    roles = user.get("roles", [])
    perms = await get_permissions_for_roles(roles)
    return permission in perms