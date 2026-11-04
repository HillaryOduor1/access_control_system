# core/data_service.py
"""
data service layer with async support and offline capability.
"""
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, Slot
import logging
import traceback
import time

logger = logging.getLogger(__name__)


class AsyncTask(QRunnable):
    """
    Async task runner for data operations with proper error handling.
    """

    def __init__(
        self,
        fn: Callable,
        callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
        *args,
        **kwargs
    ):
        super().__init__()
        self.fn = fn
        self.callback = callback
        self.error_callback = error_callback
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False

    def cancel(self):
        """Cancel the task if not yet started."""
        self._is_cancelled = True

    @Slot()
    def run(self):
        """Run the task and handle results/errors."""
        if self._is_cancelled:
            logger.debug("Async task cancelled")
            return

        try:
            result = self.fn(*self.args, **self.kwargs)
            if self.callback and not self._is_cancelled:
                try:
                    self.callback(result)
                except Exception as e:
                    logger.error(f"Error in callback: {e}")
        except Exception as e:
            logger.error(f"Async task failed: {e}\n{traceback.format_exc()}")
            if self.error_callback and not self._is_cancelled:
                try:
                    self.error_callback(str(e))
                except Exception as cb_error:
                    logger.error(f"Error in error callback: {cb_error}")


class DataService(QObject):
    """
    Data service layer with:
    - Async operations via QThreadPool
    - Online/offline support
    - Caching
    - Error handling
    """

    # Signals
    data_loaded = Signal(object)
    error_occurred = Signal(str)
    operation_completed = Signal(str, bool)  # operation_name, success

    def __init__(self, api_client, db_manager, sync_manager):
        super().__init__()
        self.api = api_client
        self.db = db_manager
        self.sync = sync_manager

        # Thread pool for async operations
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        max_threads = max(2, min(cpu_count * 2, 8))

        self._threadpool = QThreadPool()
        self._threadpool.setMaxThreadCount(max_threads)
        logger.info(f"DataService initialized with {max_threads} threads")

        # Cache for frequently accessed data
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, float] = {}
        self._default_ttl = 60  # seconds

        # Snapshot of connection state captured on the GUI thread so that
        # worker threads never have to call api.is_online() themselves.
        self._online_snapshot: bool = False
        try:
            api_client.connection_changed.connect(self._on_connection_changed)
        except Exception:
            pass
        # Prime the snapshot with the current value.
        try:
            self._online_snapshot = bool(api_client.is_online())
        except Exception:
            self._online_snapshot = False

    def _on_connection_changed(self, online: bool):
        """Record the latest connection state (runs on the GUI thread)."""
        self._online_snapshot = bool(online)

    def refresh_online_snapshot(self):
        """Re-read the current online state from the API client.

        Must be called from the GUI thread.
        """
        try:
            self._online_snapshot = bool(self.api.is_online())
        except Exception as e:
            logger.debug(f"refresh_online_snapshot failed: {e}")
            self._online_snapshot = False

    def _is_online(self) -> bool:
        """Return the last-known connection state.

        Safe to call from worker threads: this reads a plain Python bool
        that is updated on the GUI thread. It never touches Qt objects and
        never performs network I/O.
        """
        return self._online_snapshot

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached data if still valid."""
        if key in self._cache:
            if key in self._cache_ttl and time.time() < self._cache_ttl[key]:
                return self._cache[key]
            elif key not in self._cache_ttl:
                return self._cache[key]
        return None

    def _set_cache(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set cached data with optional TTL."""
        self._cache[key] = value
        if ttl is not None:
            self._cache_ttl[key] = time.time() + ttl

    def _clear_cache(self, key: Optional[str] = None):
        """Clear cache for a specific key or all."""
        if key:
            self._cache.pop(key, None)
            self._cache_ttl.pop(key, None)
        else:
            self._cache.clear()
            self._cache_ttl.clear()

    def run_async(
        self,
        fn: Callable,
        callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
        *args,
        **kwargs
    ):
        """
        Run a function asynchronously on a worker thread.
        """
        task = AsyncTask(fn, callback, error_callback, *args, **kwargs)
        self._threadpool.start(task)

    # VISITORS

    def get_active_visitors(self) -> List[Dict]:
        """Get active visitors (online or offline)."""
        try:
            if self._is_online():
                cache_key = "active_visitors"
                cached = self._get_cached(cache_key)
                if cached is not None:
                    return cached

                result = self.api.request("GET", "/visitors/active")
                self._set_cache(cache_key, result, ttl=30)
                return result
            else:
                return self.db.get_active_visitors()
        except Exception as e:
            logger.error(f"Error getting active visitors: {e}")
            return self.db.get_active_visitors()

    def get_active_visitors_async(self, callback: Optional[Callable] = None):
        """Get active visitors asynchronously."""
        self.run_async(
            self.get_active_visitors,
            callback=callback,
            error_callback=lambda e: self.error_occurred.emit(
                f"Failed to load visitors: {e}"
            )
        )

    def check_in_visitor(
        self,
        name: str,
        host_id: int,
        dynamic_data: Dict,
        consent: bool
    ) -> int:
        """Check in a visitor."""
        visitor_data = {
            "visitor_name": name,
            "host_id": str(host_id),
            "dynamic_fields": dynamic_data,
            "consent_gained": consent
        }

        try:
            if self._is_online():
                result = self.api.request(
                    "POST", "/visitors/checkin", json=visitor_data
                )
                visitor_id = result.get("id")
                self._clear_cache("active_visitors")
                self.operation_completed.emit("checkin", True)
                return visitor_id
            else:
                visitor_id = self.db.check_in_visitor(
                    name, host_id, dynamic_data, consent
                )
                self.db.add_sync_operation(
                    "CREATE", "visitors", str(visitor_id), visitor_data
                )
                self.operation_completed.emit("checkin", True)
                return visitor_id
        except Exception as e:
            logger.error(f"Error checking in visitor: {e}")
            self.error_occurred.emit(f"Check-in failed: {e}")
            raise

    def checkout_visitor(self, visitor_id: int) -> bool:
        """Check out a visitor."""
        try:
            if self._is_online():
                self.api.request(
                    "POST",
                    "/visitors/checkout",
                    json={"visitor_id": str(visitor_id)}
                )
                self._clear_cache("active_visitors")
                self.operation_completed.emit("checkout", True)
                return True
            else:
                self.db.check_out_visitor(visitor_id)
                self.db.add_sync_operation(
                    "UPDATE", "visitors", str(visitor_id), {"status": "out"}
                )
                self.operation_completed.emit("checkout", True)
                return True
        except Exception as e:
            logger.error(f"Error checking out visitor: {e}")
            self.error_occurred.emit(f"Check-out failed: {e}")
            raise

    def get_visitor_history(self, limit: int = 200) -> List[tuple]:
        """Get visitor history."""
        try:
            if self._is_online():
                data = self.api.request(
                    "GET", "/visitors/history", params={"limit": limit}
                )
                return [
                    (
                        v.get("id"),
                        v.get("visitor_name", ""),
                        v.get("check_in_time", ""),
                        v.get("check_out_time", ""),
                        v.get("host_name", ""),
                        v.get("status", "")
                    )
                    for v in data
                ]
            else:
                return self.db.get_visitor_history(limit)
        except Exception as e:
            logger.error(f"Error getting visitor history: {e}")
            return self.db.get_visitor_history(limit)

    # EMPLOYEES

    def get_employees(self, active_only: bool = True) -> List[Dict]:
        """Get employees."""
        try:
            if self._is_online():
                cache_key = f"employees_{active_only}"
                cached = self._get_cached(cache_key)
                if cached is not None:
                    return cached

                result = self.api.request(
                    "GET", "/employees", params={"active_only": active_only}
                )
                self._set_cache(cache_key, result, ttl=60)
                return result
            else:
                return self.db.get_employees(active_only)
        except Exception as e:
            logger.error(f"Error getting employees: {e}")
            return self.db.get_employees(active_only)

    def add_employee(
        self,
        employee_id: str,
        full_name: str,
        role: str,
        badge_number: str,
        dynamic_fields: Dict
    ) -> int:
        """Add a new employee."""
        emp_data = {
            "employee_id": employee_id,
            "full_name": full_name,
            "role": role,
            "badge_number": badge_number,
            "dynamic_fields": dynamic_fields
        }

        try:
            if self._is_online():
                result = self.api.request("POST", "/employees", json=emp_data)
                self._clear_cache("employees_")
                self.operation_completed.emit("add_employee", True)
                return result.get("id")
            else:
                emp_id = self.db.add_employee(
                    employee_id, full_name, role, badge_number, dynamic_fields
                )
                self.db.add_sync_operation(
                    "CREATE", "employees", str(emp_id), emp_data
                )
                self.operation_completed.emit("add_employee", True)
                return emp_id
        except Exception as e:
            logger.error(f"Error adding employee: {e}")
            self.error_occurred.emit(f"Failed to add employee: {e}")
            raise

    def update_employee(
        self,
        emp_id: int,
        full_name: str,
        role: str,
        badge_number: str,
        dynamic_fields: Dict,
        is_active: bool
    ):
        """Update an employee."""
        update_data = {
            "full_name": full_name,
            "role": role,
            "badge_number": badge_number,
            "dynamic_fields": dynamic_fields,
            "is_active": is_active
        }

        try:
            if self._is_online():
                self.api.request(
                    "PUT", f"/employees/{emp_id}", json=update_data
                )
                self._clear_cache("employees_")
                self.operation_completed.emit("update_employee", True)
            else:
                self.db.update_employee(
                    emp_id, full_name, role, badge_number,
                    dynamic_fields, is_active
                )
                self.db.add_sync_operation(
                    "UPDATE", "employees", str(emp_id), update_data
                )
                self.operation_completed.emit("update_employee", True)
        except Exception as e:
            logger.error(f"Error updating employee: {e}")
            self.error_occurred.emit(f"Failed to update employee: {e}")
            raise

    def deactivate_employee(self, emp_id: int):
        """Deactivate an employee."""
        try:
            if self._is_online():
                self.api.request("DELETE", f"/employees/{emp_id}")
                self._clear_cache("employees_")
                self.operation_completed.emit("deactivate_employee", True)
            else:
                self.db.deactivate_employee(emp_id)
                self.db.add_sync_operation(
                    "DELETE", "employees", str(emp_id), {}
                )
                self.operation_completed.emit("deactivate_employee", True)
        except Exception as e:
            logger.error(f"Error deactivating employee: {e}")
            self.error_occurred.emit(f"Failed to deactivate employee: {e}")
            raise

    def get_employees_list_for_host(self) -> List[tuple]:
        """Get employee list for host dropdown."""
        try:
            if self._is_online():
                cache_key = "employees_host_list"
                cached = self._get_cached(cache_key)
                if cached is not None:
                    return cached

                data = self.api.request(
                    "GET", "/employees", params={"active_only": True}
                )
                result = [(e.get("id"), e.get("full_name")) for e in data]
                self._set_cache(cache_key, result, ttl=60)
                return result
            else:
                return self.db.get_employees_list_for_host()
        except Exception as e:
            logger.error(f"Error getting employee list: {e}")
            return self.db.get_employees_list_for_host()

    # ACCESS LOGS

    def get_access_logs(self, filters: Optional[Dict] = None) -> List[tuple]:
        """Get access logs with filters."""
        try:
            if self._is_online():
                params = {}
                if filters:
                    if filters.get('person_type'):
                        params['person_type'] = filters['person_type']
                    if filters.get('direction'):
                        params['direction'] = filters['direction']
                    if filters.get('date_from'):
                        params['from_date'] = filters['date_from']
                    if filters.get('date_to'):
                        params['to_date'] = filters['date_to']

                data = self.api.request("GET", "/access-logs", params=params)
                return [
                    (
                        l.get("id"),
                        l.get("person_type", ""),
                        l.get("person_id"),
                        l.get("direction", ""),
                        l.get("timestamp", ""),
                        l.get("granted", False),
                        l.get("reason", ""),
                        l.get("verified_by", "")
                    )
                    for l in data
                ]
            else:
                return self.db.get_access_logs(filters)
        except Exception as e:
            logger.error(f"Error getting access logs: {e}")
            return self.db.get_access_logs(filters)

    # DASHBOARD

    def get_dashboard_stats_async(
        self,
        callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None
    ):
        """
        Get dashboard stats asynchronously.
        """
        self.run_async(
            self.get_dashboard_stats,
            callback=callback,
            error_callback=error_callback
        )

    def get_dashboard_stats(self) -> Dict:
        """Get dashboard stats - runs on worker thread."""
        start_time = time.time()

        try:
            if self._is_online():
                stats = self._get_dashboard_stats_online()
            else:
                stats = self._get_dashboard_stats_offline()

            elapsed = time.time() - start_time
            logger.debug(f"Dashboard stats loaded in {elapsed:.2f}s")
            return stats

        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {e}")
            return self._get_dashboard_stats_offline()

    def _get_dashboard_stats_online(self) -> Dict:
        """Get dashboard stats from online API."""
        active_visitors = len(self.api.request("GET", "/visitors/active"))

        employees = self.api.request(
            "GET", "/employees", params={"active_only": True}
        )
        active_employees = len(employees)

        today = datetime.now().date().isoformat()
        logs = self.api.request("GET", "/access-logs", params={
            "from_date": f"{today} 00:00:00",
            "to_date": f"{today} 23:59:59"
        })

        today_entries = sum(1 for log in logs if log.get("direction") == "in")
        today_checkouts = sum(
            1 for log in logs
            if log.get("direction") == "out" and log.get("granted", False)
        )
        recent_logs = logs[:10] if logs else []

        return {
            "active_visitors": active_visitors,
            "active_employees": active_employees,
            "today_entries": today_entries,
            "today_checkouts": today_checkouts,
            "recent_logs": recent_logs
        }

    def _get_dashboard_stats_offline(self) -> Dict:
        """Get dashboard stats from local database."""
        active_visitors = len(self.db.get_active_visitors())
        employees = self.db.get_employees(active_only=True)
        active_employees = len(employees)

        today = datetime.now().date().isoformat()
        logs = self.db.get_access_logs()

        today_entries = sum(
            1 for log in logs
            if log[4].startswith(today) and log[3] == 'in'
        )
        today_checkouts = sum(
            1 for log in logs
            if log[4].startswith(today) and log[3] == 'out' and log[5] == 1
        )
        recent_logs = logs[:10] if logs else []

        return {
            "active_visitors": active_visitors,
            "active_employees": active_employees,
            "today_entries": today_entries,
            "today_checkouts": today_checkouts,
            "recent_logs": recent_logs
        }

    # REPORTS

    def get_visitor_history_for_report(self, limit: int = 500) -> List[tuple]:
        """Get visitor history for reports."""
        return self.get_visitor_history(limit)

    # CUSTOM FIELDS

    def get_custom_fields(
        self, entity_type: str, active_only: bool = True
    ) -> List[Dict]:
        """Get custom fields configuration."""
        return self.db.get_custom_fields(entity_type, active_only)

    def save_custom_field(self, entity_type: str, field_id: int, data: Dict):
        """Save custom field configuration."""
        self.db.save_custom_field(entity_type, field_id, data)

    def delete_custom_field(self, entity_type: str, field_id: int):
        """Delete custom field configuration."""
        self.db.delete_custom_field(entity_type, field_id)

    # AUTHENTICATION
    # change_password posts to /users/change-password, matching the route
    # defined in app/routes/users.py.

    def change_password(
        self, user_id, current_password: str, new_password: str
    ) -> tuple:
        """Change password for the currently signed-in user."""
        try:
            if self._is_online():
                self.api.request(
                    "POST",
                    "/users/change-password",
                    json={
                        "current_password": current_password,
                        "new_password": new_password,
                    },
                )
                self.operation_completed.emit("change_password", True)
                return True, "Password changed successfully"
            else:
                return False, "Cannot change password while offline"
        except Exception as e:
            logger.error(f"Error changing password: {e}")
            return False, str(e)

    def update_profile(
        self, user_id: int, full_name: str, email: str
    ) -> tuple:
        """Update user profile."""
        try:
            if self._is_online():
                self.api.request(
                    "PUT", "/users/me",
                    json={"full_name": full_name, "email": email}
                )
                self.operation_completed.emit("update_profile", True)
                return True, "Profile updated successfully"
            else:
                return False, "Cannot update profile while offline"
        except Exception as e:
            logger.error(f"Error updating profile: {e}")
            return False, str(e)

    # PASSWORD RESET (forgot password flow)
    # Desktop-appropriate flow: OTP by email, no links. The dialog drives
    # each step and hands the returned reset_token to /complete.

    def request_password_reset(self, email: str) -> Dict:
        """Step 1: ask the backend to email a 6-digit code."""
        return self.api.request(
            "POST",
            "/auth/password/request",
            json={"email": email},
            need_auth=False,
            timeout=30.0,
        )

    def verify_password_reset_otp(self, email: str, otp: str) -> Dict:
        """Step 2: exchange the OTP for a single-use reset_token."""
        return self.api.request(
            "POST",
            "/auth/password/verify",
            json={"email": email, "otp": otp},
            need_auth=False,
            timeout=15.0,
        )

    def complete_password_reset(
        self, email: str, reset_token: str, new_password: str
    ) -> Dict:
        """Step 3: submit the reset_token and the new password."""
        return self.api.request(
            "POST",
            "/auth/password/complete",
            json={
                "email": email,
                "reset_token": reset_token,
                "new_password": new_password,
            },
            need_auth=False,
            timeout=30.0,
        )

    # USER MANAGEMENT
    # Two data sources are supported:
    #   - the API (server-side users, tenant-scoped or admin cross-tenant)
    #   - the local SQLite users table (built-in accounts + offline signups)
    #
    # get_all_users() merges both. get_all_users_across_tenants() calls
    # the admin endpoint and falls back to the tenant-scoped one.
    # get_user / update_user / deactivate_user dispatch by source so a
    # local row is edited locally and a server row is edited through
    # the API.

    def get_users(self) -> List[Dict]:
        """
        Return the server's tenant-scoped user list.

        Kept for backwards compatibility. Prefer get_all_users() when
        you want the merged API + local list.
        """
        if not self._is_online():
            return []
        return self.api.request("GET", "/users")

    def get_all_users(self) -> List[Dict]:
        """
        Return every user the app knows about.

        Strategy
        --------
        1. If online, fetch the tenant-scoped list from the API.
        2. Always fetch the local users table (built-in admin,
           security, finance, staff, and any locally created rows).
        3. Merge, deduplicating by username. API entries win when a
           username exists in both, because they have the server's
           canonical id and roles.

        This guarantees the Users page is never empty just because
        the tenant filter on the server excluded a row, or because
        the caller is offline.
        """
        api_users: List[Dict] = []

        if self._is_online():
            try:
                api_users = self.api.request("GET", "/users") or []
            except Exception as e:
                logger.warning(f"get_all_users: API fetch failed: {e}")
                api_users = []

        local_users: List[Dict] = []
        try:
            local_users = self.db.get_all_users() or []
        except Exception as e:
            logger.warning(f"get_all_users: local fetch failed: {e}")

        # Merge, keyed by lowercase username. API entries take
        # precedence so the server's id and roles are preserved.
        merged: Dict[str, Dict] = {}
        for u in local_users:
            key = (u.get("username") or "").lower()
            if key:
                u = dict(u)
                u.setdefault("source", "local")
                merged[key] = u
        for u in api_users:
            key = (u.get("username") or "").lower()
            if key:
                u = dict(u)
                u["source"] = "api"
                merged[key] = u

        result = list(merged.values())

        # Stable sort for display.
        result.sort(key=lambda x: (x.get("username") or "").lower())

        logger.info(
            f"get_all_users: {len(api_users)} from API, "
            f"{len(local_users)} local, {len(result)} merged"
        )
        return result

    def get_all_users_across_tenants(self) -> List[Dict]:
        """
        Admin-only: return users from every tenant.

        Calls GET /users/admin/all. If the endpoint is unavailable
        (older server, or the caller lacks permission), falls back
        to the tenant-scoped list and logs the reason.

        The result is always merged with the local users table so
        built-in accounts are visible even when the server call
        fails entirely.
        """
        api_users: List[Dict] = []

        if self._is_online():
            try:
                api_users = (
                    self.api.request("GET", "/users/admin/all") or []
                )
                for u in api_users:
                    u.setdefault("source", "api")
                logger.info(
                    f"get_all_users_across_tenants: fetched "
                    f"{len(api_users)} rows from /users/admin/all"
                )
            except Exception as e:
                logger.warning(
                    f"get_all_users_across_tenants: "
                    f"/users/admin/all unavailable ({e}); "
                    f"falling back to /users"
                )
                try:
                    api_users = self.api.request("GET", "/users") or []
                    for u in api_users:
                        u.setdefault("source", "api")
                except Exception as inner:
                    logger.warning(
                        f"get_all_users_across_tenants: tenant-scoped "
                        f"fallback also failed: {inner}"
                    )
                    api_users = []

        local_users: List[Dict] = []
        try:
            local_users = self.db.get_all_users() or []
        except Exception as e:
            logger.warning(
                f"get_all_users_across_tenants: local fetch failed: {e}"
            )

        # Merge by lowercase username, API wins.
        merged: Dict[str, Dict] = {}
        for u in local_users:
            key = (u.get("username") or "").lower()
            if key:
                u = dict(u)
                u.setdefault("source", "local")
                merged[key] = u
        for u in api_users:
            key = (u.get("username") or "").lower()
            if key:
                u = dict(u)
                u["source"] = "api"
                merged[key] = u

        result = list(merged.values())
        result.sort(key=lambda x: (
            (x.get("tenant_id") or ""),
            (x.get("username") or "").lower(),
        ))

        logger.info(
            f"get_all_users_across_tenants: {len(api_users)} from API, "
            f"{len(local_users)} local, {len(result)} merged"
        )
        return result

    def get_user(self, user_id) -> Optional[Dict]:
        """
        Return a single user.

        Tries the API first when online (the id is the server-side
        ObjectId), then falls back to the local table by integer id
        or username. This lets the Edit and Deactivate buttons work
        for users that exist only in one of the two stores.
        """
        if self._is_online():
            try:
                user = self.api.request("GET", f"/users/{user_id}")
                if user:
                    return user
            except Exception as e:
                logger.debug(f"get_user: API lookup failed: {e}")

        try:
            return self.db.get_local_user(user_id)
        except Exception as e:
            logger.warning(f"get_user: local lookup failed: {e}")
            return None

    def create_user(self, payload: Dict) -> Dict:
        """
        Create a user.

        When online, posts to the API so the new user lives on the
        server. When offline, inserts into the local users table with
        a securely hashed password.
        """
        if self._is_online():
            result = self.api.request("POST", "/users", json=payload)
            self.operation_completed.emit("create_user", True)
            return result

        self.db.create_local_user(payload)
        self.operation_completed.emit("create_user", True)
        return {"status": "created", "source": "local"}

    def update_user(self, user_id, payload: Dict) -> Dict:
        """
        Update a user.

        If the id belongs to the local users table, update it there;
        otherwise send to the API. Payload shape is the same for both
        because the local users table stores the same fields.
        """
        # Detect whether this id is a local user.
        local = None
        try:
            local = self.db.get_local_user(user_id)
        except Exception:
            local = None

        if local is not None:
            self.db.update_local_user(local["id"], payload)
            self.operation_completed.emit("update_user", True)
            return self.db.get_local_user(local["id"]) or payload

        result = self.api.request("PUT", f"/users/{user_id}", json=payload)
        self.operation_completed.emit("update_user", True)
        return result

    def deactivate_user(self, user_id) -> Dict:
        """
        Deactivate a user.

        Local users are flipped is_active=0 in the local table; server
        users are deactivated through DELETE /users/{id}.
        """
        local = None
        try:
            local = self.db.get_local_user(user_id)
        except Exception:
            local = None

        if local is not None:
            self.db.deactivate_local_user(local["id"])
            self.operation_completed.emit("deactivate_user", True)
            return {"status": "deactivated", "message": "User deactivated"}

        result = self.api.request("DELETE", f"/users/{user_id}")
        self.operation_completed.emit("deactivate_user", True)
        return result

    # UTILITY

    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()
        self._cache_ttl.clear()
        logger.debug("Cache cleared")

