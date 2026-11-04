# app/routes/users.py
"""
Enhanced user management routes with security features.

Fixes in this revision
----------------------
- Every 400/409/500 branch now logs *why* it fired, so the client's
  generic "400 Bad Request" can be traced back to the exact validation
  step in the backend log.
- create_user returns 409 (not 400) for duplicate username/email so
  the client can distinguish "already exists" from "bad payload".
- Added GET /users/admin/all for cross-tenant user listing. The
  permission check accepts any of the standard admin signals
  (manage_users permission, role == 'admin', 'admin' in roles,
  is_superuser, is_admin) so it works regardless of how the JWT
  or DB document was minted. When the check denies, it logs the
  exact signals it saw so the mismatch is easy to trace.
- The /users/admin/all route is declared BEFORE /{user_id} so the
  literal path wins the match.
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from bson.errors import InvalidId
import logging
import traceback

from ..schemas.user import UserCreate, UserUpdate, UserResponse
from ..config import db
from .auth import get_current_user, get_client_ip, get_user_agent
from ..models.user import user_helper
from ..services.auth_service import password_service, jwt_service
from ..services.rate_limit_service import rate_limit_service
from ..services.otp_service import otp_service
from ..services.email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_admin(current_user: dict) -> tuple:
    """
    Decide whether the caller is an admin.

    Returns (is_admin, signals) where `signals` is a dict of the
    values that were inspected. Callers log `signals` when denying
    so the mismatch is easy to trace.

    Accepts any of the standard admin signals so the check works
    regardless of how the token or DB document was minted:
      - permissions list contains 'manage_users'
      - role == 'admin'
      - roles list contains 'admin'
      - is_superuser truthy
      - is_admin truthy
    """
    permissions = set(current_user.get("permissions") or [])
    role = str(current_user.get("role") or "").lower()
    roles = current_user.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    roles_lower = {str(r).lower() for r in roles}

    signals = {
        "permissions": sorted(permissions),
        "role": role,
        "roles": sorted(roles_lower),
        "is_superuser": bool(current_user.get("is_superuser")),
        "is_admin": bool(current_user.get("is_admin")),
    }

    is_admin = (
        "manage_users" in permissions
        or role == "admin"
        or "admin" in roles_lower
        or signals["is_superuser"]
        or signals["is_admin"]
    )
    return is_admin, signals


# ============================================================================
# Create User (Signup)
# ============================================================================
@router.post("", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Create a new user account with security validations."""
    try:
        client_ip = await get_client_ip(request)

        logger.info(f"Received signup request from {client_ip}")
        logger.info(
            f"User data: username={user_data.username!r}, "
            f"email={user_data.email!r}, tenant={user_data.tenant_id!r}, "
            f"roles={user_data.roles!r}, email_verified={user_data.email_verified}"
        )

        # STEP 1: Rate limiting
        try:
            rate_result = await rate_limit_service.is_rate_limited(
                client_ip, "/users"
            )
            if rate_result["limited"]:
                reset_seconds = int(
                    (rate_result["reset_at"] - get_utc_now()).total_seconds()
                )
                logger.warning(
                    f"Signup rejected: rate-limited (reset in {reset_seconds}s)"
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many signup attempts. "
                           f"Please try again in {reset_seconds} seconds.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Rate limit check crashed: {e}")
            logger.error(traceback.format_exc())

        # STEP 2: Required field validation
        missing = []
        if not user_data.username:   missing.append("username")
        if not user_data.email:      missing.append("email")
        if not user_data.first_name: missing.append("first_name")
        if not user_data.last_name:  missing.append("last_name")
        if not user_data.tenant_id:  missing.append("tenant_id")
        if not user_data.roles:      missing.append("roles")
        if not user_data.password:   missing.append("password")

        if missing:
            logger.warning(
                f"Signup rejected: missing required fields {missing}"
            )
            raise HTTPException(
                400, f"Missing required fields: {', '.join(missing)}"
            )

        # STEP 3: Email verification check
        if not user_data.email_verified:
            try:
                is_verified = await otp_service.get_verification_status(
                    user_data.email, "signup_verification"
                )
                if not is_verified:
                    logger.warning(
                        f"Signup rejected: email {user_data.email!r} "
                        f"is not marked verified in OTP service"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail="Email must be verified before creating "
                               "account. Please verify your email first.",
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"OTP verification check crashed: {e}")
                logger.error(traceback.format_exc())
                raise HTTPException(
                    400, f"Email verification check failed: {e}"
                )

        # STEP 4: Duplicate checks (409 Conflict, not 400)
        existing_username = await db.users.find_one(
            {"username": user_data.username}
        )
        if existing_username:
            logger.warning(
                f"Signup rejected: username {user_data.username!r} "
                f"already exists (id={existing_username.get('_id')})"
            )
            raise HTTPException(409, "Username already exists")

        if user_data.email:
            existing_email = await db.users.find_one(
                {"email": user_data.email}
            )
            if existing_email:
                logger.warning(
                    f"Signup rejected: email {user_data.email!r} "
                    f"already registered (id={existing_email.get('_id')})"
                )
                raise HTTPException(409, "Email already registered")

        # STEP 5: Password strength
        is_valid, error = password_service.validate_password(user_data.password)
        if not is_valid:
            logger.warning(f"Signup rejected: weak password ({error})")
            raise HTTPException(400, error)

        # STEP 6: Build user document
        try:
            user_dict = user_data.model_dump()
        except AttributeError:
            user_dict = user_data.dict()

        password = user_dict.pop("password")
        user_dict["password_hash"] = password_service.hash_password(password)
        user_dict["is_active"] = True
        now = get_utc_now()
        user_dict["created_at"] = now
        user_dict["updated_at"] = now
        user_dict["email_verified"] = True
        user_dict["token_version"] = 0

        # STEP 7: Insert
        try:
            result = await db.users.insert_one(user_dict)
        except Exception as e:
            logger.error(f"MongoDB insert failed: {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(500, f"Database error: {e}")

        new_user = await db.users.find_one({"_id": result.inserted_id})
        if not new_user:
            raise HTTPException(500, "User created but could not be retrieved")

        logger.info(
            f"Signup succeeded: user {user_data.username!r} "
            f"id={result.inserted_id}"
        )

        # STEP 8: Password history
        try:
            await password_service.add_to_history(
                str(result.inserted_id), user_dict["password_hash"]
            )
        except Exception as e:
            logger.warning(f"Failed to add password history (non-fatal): {e}")

        # STEP 9: Welcome email
        try:
            from .auth import _safe_send_welcome_email
            background_tasks.add_task(
                _safe_send_welcome_email,
                user_data.email,
                user_data.full_name
                or f"{user_data.first_name} {user_data.last_name}",
            )
        except Exception as e:
            logger.warning(f"Failed to queue welcome email (non-fatal): {e}")

        # STEP 10: Response
        try:
            return user_helper(new_user)
        except Exception as e:
            logger.error(f"user_helper failed: {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(500, f"Response serialization error: {e}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"UNHANDLED EXCEPTION in create_user: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(500, f"Unexpected error: {e}")


# ============================================================================
# Get Users (tenant-scoped)
# ============================================================================
@router.get("", response_model=list[UserResponse])
async def get_users(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    tenant = current_user.get("tenant_id")
    if not tenant:
        full = await db.users.find_one({"_id": current_user.get("_id")})
        if full:
            tenant = full.get("tenant_id")

    logger.info(f"GET /users: tenant={tenant!r}")

    query = {"tenant_id": tenant} if tenant else {}

    users: list[dict] = []
    skipped = 0
    cursor = db.users.find(query)
    async for u in cursor:
        try:
            users.append(user_helper(u))
        except Exception as e:
            skipped += 1
            logger.warning(
                f"Skipping user {u.get('_id')} — user_helper raised: {e}"
            )

    logger.info(f"GET /users: returning {len(users)} users (skipped {skipped})")
    return users


# ============================================================================
# Get All Users (Admin, cross-tenant)
#
# Declared BEFORE /{user_id} so the literal path 'admin' is not
# captured by the dynamic segment.
# ============================================================================
@router.get("/admin/all", response_model=list[UserResponse])
async def get_all_users_admin(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Return every user across every tenant.

    Restricted to admins. The check accepts any of the standard
    admin signals (see _is_admin). When the check denies, the exact
    signals the backend saw are logged so the client/server shape
    mismatch is easy to trace.
    """
    is_admin, signals = _is_admin(current_user)

    if not is_admin:
        logger.warning(
            f"GET /users/admin/all denied for "
            f"{current_user.get('username')!r}: {signals}"
        )
        raise HTTPException(
            403,
            "You do not have permission to list users across tenants",
        )

    logger.info(
        f"GET /users/admin/all requested by "
        f"{current_user.get('username')!r}"
    )

    users: list[dict] = []
    skipped = 0
    cursor = db.users.find({})
    async for u in cursor:
        try:
            users.append(user_helper(u))
        except Exception as e:
            skipped += 1
            logger.warning(
                f"Skipping user {u.get('_id')} — user_helper raised: {e}"
            )

    logger.info(
        f"GET /users/admin/all: returning {len(users)} users "
        f"(skipped {skipped})"
    )
    return users


# ============================================================================
# Debug — count raw documents
# ============================================================================
@router.get("/debug/count")
async def debug_count(current_user: dict = Depends(get_current_user)):
    total = await db.users.count_documents({})
    tenants = await db.users.distinct("tenant_id")
    return {
        "total_users": total,
        "distinct_tenants": [str(t) for t in tenants],
        "current_user_tenant": current_user.get("tenant_id"),
        "current_user_id": str(current_user.get("_id", "")),
    }


# ============================================================================
# Get Current User
# ============================================================================
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return user_helper(current_user)


# ============================================================================
# Update Current User
# ============================================================================
@router.put("/me", response_model=UserResponse)
async def update_me(
    update: UserUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    user_id = current_user["_id"]
    client_ip = await get_client_ip(request)

    update_dict = {
        k: v for k, v in update.dict(exclude_unset=True).items() if v is not None
    }

    if "password" in update_dict:
        password = update_dict.pop("password")
        is_valid, error = password_service.validate_password(password)
        if not is_valid:
            raise HTTPException(400, error)
        password_hash = password_service.hash_password(password)
        if await password_service.check_password_history(str(user_id),
                                                         password_hash):
            raise HTTPException(
                400,
                "You have used this password recently. "
                "Please choose a different password.",
            )
        update_dict["password_hash"] = password_hash
        background_tasks.add_task(
            password_service.add_to_history, str(user_id), password_hash
        )

    await db.users.update_one({"_id": user_id}, {"$set": update_dict})
    updated = await db.users.find_one({"_id": user_id})

    logger.info(
        "User profile updated",
        extra={"user_id": str(user_id), "client_ip": client_ip,
               "event": "user_updated"},
    )
    return user_helper(updated)


# ============================================================================
# Get User by ID
# ============================================================================
@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    tenant = current_user.get("tenant_id")
    try:
        obj_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(404, "Invalid user ID")
    user = await db.users.find_one({"_id": obj_id, "tenant_id": tenant})
    if not user:
        raise HTTPException(404, "User not found")
    return user_helper(user)


# ============================================================================
# Update User by ID
# ============================================================================
@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    update: UserUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    tenant = current_user.get("tenant_id")
    client_ip = await get_client_ip(request)

    try:
        obj_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(404, "Invalid user ID")

    update_dict = {
        k: v for k, v in update.dict(exclude_unset=True).items() if v is not None
    }

    if "password" in update_dict:
        password = update_dict.pop("password")
        is_valid, error = password_service.validate_password(password)
        if not is_valid:
            raise HTTPException(400, error)
        password_hash = password_service.hash_password(password)
        if await password_service.check_password_history(user_id,
                                                         password_hash):
            raise HTTPException(
                400,
                "You have used this password recently. "
                "Please choose a different password.",
            )
        update_dict["password_hash"] = password_hash
        background_tasks.add_task(
            password_service.add_to_history, user_id, password_hash
        )

    result = await db.users.update_one(
        {"_id": obj_id, "tenant_id": tenant}, {"$set": update_dict}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "User not found")

    updated = await db.users.find_one({"_id": obj_id})
    logger.info(
        "User updated by admin",
        extra={"user_id": user_id, "admin_id": str(current_user["_id"]),
               "client_ip": client_ip, "event": "user_updated_by_admin"},
    )
    return user_helper(updated)


# ============================================================================
# Deactivate User
# ============================================================================
@router.delete("/{user_id}")
async def deactivate_user(
    user_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    tenant = current_user.get("tenant_id")
    client_ip = await get_client_ip(request)

    try:
        obj_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(404, "Invalid user ID")

    if str(obj_id) == str(current_user["_id"]):
        raise HTTPException(400, "You cannot deactivate your own account")

    result = await db.users.update_one(
        {"_id": obj_id, "tenant_id": tenant}, {"$set": {"is_active": False}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "User not found")

    logger.info(
        "User deactivated",
        extra={"user_id": user_id, "admin_id": str(current_user["_id"]),
               "client_ip": client_ip, "event": "user_deactivated"},
    )
    return {"status": "deactivated", "message": "User deactivated successfully"}


# ============================================================================
# Reactivate User
# ============================================================================
@router.post("/{user_id}/reactivate")
async def reactivate_user(
    user_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    tenant = current_user.get("tenant_id")
    client_ip = await get_client_ip(request)

    try:
        obj_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(404, "Invalid user ID")

    result = await db.users.update_one(
        {"_id": obj_id, "tenant_id": tenant}, {"$set": {"is_active": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "User not found")

    logger.info(
        "User reactivated",
        extra={"user_id": user_id, "admin_id": str(current_user["_id"]),
               "client_ip": client_ip, "event": "user_reactivated"},
    )
    return {"status": "reactivated",
            "message": "User reactivated successfully"}


# ============================================================================
# Change Password (Self)
# ============================================================================
@router.post("/change-password")
async def change_password(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    body = await request.json()
    current_password = body.get("current_password")
    new_password = body.get("new_password")

    if not current_password or not new_password:
        raise HTTPException(400,
                            "Current password and new password are required")

    client_ip = await get_client_ip(request)
    user_id = current_user["_id"]

    if not password_service.verify_password(
        current_password, current_user["password_hash"]
    ):
        raise HTTPException(400, "Current password is incorrect")

    is_valid, error = password_service.validate_password(new_password)
    if not is_valid:
        raise HTTPException(400, error)

    new_hash = password_service.hash_password(new_password)
    if await password_service.check_password_history(str(user_id), new_hash):
        raise HTTPException(
            400,
            "You have used this password recently. "
            "Please choose a different password.",
        )

    await db.users.update_one(
        {"_id": user_id}, {"$set": {"password_hash": new_hash}}
    )
    await password_service.add_to_history(str(user_id), new_hash)
    await db.users.update_one(
        {"_id": user_id}, {"$inc": {"token_version": 1}}
    )

    logger.info(
        "Password changed",
        extra={"user_id": str(user_id), "client_ip": client_ip,
               "event": "password_changed"},
    )
    return {"status": "success", "message": "Password changed successfully"}


# ============================================================================
# Get User Statistics
# ============================================================================
@router.get("/stats")
async def get_user_stats(current_user: dict = Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    total = await db.users.count_documents({"tenant_id": tenant})
    active = await db.users.count_documents(
        {"tenant_id": tenant, "is_active": True}
    )
    inactive = total - active

    roles_pipeline = [
        {"$match": {"tenant_id": tenant}},
        {"$unwind": "$roles"},
        {"$group": {"_id": "$roles", "count": {"$sum": 1}}},
    ]
    role_distribution = await db.users.aggregate(roles_pipeline).to_list(None)

    return {
        "total_users": total,
        "active_users": active,
        "inactive_users": inactive,
        "role_distribution": [
            {"role": item["_id"], "count": item["count"]}
            for item in role_distribution
        ],
    }
