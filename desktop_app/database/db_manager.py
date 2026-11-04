# database/db_manager.py
"""
Enterprise-grade database manager with connection pooling, migrations, and security.

Idempotency contract
--------------------
DatabaseManager() is safe to construct multiple times. The first
construction performs the full schema setup; subsequent constructions
short-circuit the expensive work (migrations, default permission inserts,
index creation) by inspecting the schema_version table.

This matters because MainApp owns ONE DatabaseManager, and every page
receives it via DataService. Pages MUST NOT construct their own
DatabaseManager — doing so on the GUI thread will block for several
seconds and (during the login -> dashboard transition) cause the main
window to be composited in an unresponsive state.
"""
import sqlite3
import json
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager
import threading
import hashlib
import secrets

from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

logger = logging.getLogger(__name__)


# Bump this whenever a new migration is added in _run_migrations().
CURRENT_SCHEMA_VERSION = 1


class DatabaseManager:
    """
    Enterprise database manager with:
    - Connection pooling (thread-safe)
    - Transaction support
    - Migration system
    - Secure credential storage
    - Audit logging

    Idempotent construction: repeated DatabaseManager() calls are cheap
    after the first successful initialization.
    """

    def __init__(self):
        # Use user data directory, not project directory
        self.db_path = Config.get_access_control_db_path()

        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._local = threading.local()
        self._initialized = False

        # Initialize database (idempotent)
        self.init_db()
        self._initialized = True

        logger.info(f"Database initialized at: {self.db_path}")

    # CONNECTION MANAGEMENT

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get a thread-local database connection.
        Returns a connection for the current thread.
        """
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self._local.conn.execute("PRAGMA foreign_keys = ON")
            # Enable WAL mode for better concurrency
            self._local.conn.execute("PRAGMA journal_mode = WAL")
            # NORMAL synchronous reduces fsync stalls on Windows. WAL is
            # still durable across application crashes (only an OS-level
            # crash with an unstable power supply risks the last commit).
            self._local.conn.execute("PRAGMA synchronous = NORMAL")
            # Larger cache reduces I/O on read-heavy operations.
            self._local.conn.execute("PRAGMA cache_size = -8000")  # ~8 MB

        return self._local.conn

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION")
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    # SCHEMA INITIALIZATION (IDEMPOTENT)
    
    def init_db(self):
        """
        Initialize database schema with migrations.

        On the FIRST run this creates all tables, applies migrations,
        seeds default permissions/users, and creates indexes.

        On SUBSEQUENT runs, everything short-circuits:
          - CREATE TABLE IF NOT EXISTS is a no-op (SQLite skips instantly)
          - Migrations check schema_version and skip
          - Default seeding checks row counts and skips
          - Index creation checks schema_version and skips

        This means DatabaseManager() is safe to construct many times
        without incurring multi-second I/O.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Enable foreign keys
            cursor.execute("PRAGMA foreign_keys = ON")

            # ====== VERSION TABLE (must exist before migrations check it) ======
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

            # Fast path: if the schema is already at the current version,
            # skip all remaining schema work. This is the hot path taken by
            # every DatabaseManager() constructed after the first one.
            cursor.execute("SELECT MAX(version) FROM schema_version")
            row = cursor.fetchone()
            current_version = row[0] if row and row[0] is not None else 0

            if current_version >= CURRENT_SCHEMA_VERSION:
                # Everything below has already been applied.
                return

            # USERS 
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    email TEXT,
                    role TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    password_changed_at TIMESTAMP,
                    failed_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP
                )
            """)

            # EMPLOYEES
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT,
                    badge_number TEXT UNIQUE,
                    is_active INTEGER DEFAULT 1,
                    dynamic_fields TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # VISITORS 
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS visitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    visitor_name TEXT NOT NULL,
                    check_in_time TIMESTAMP NOT NULL,
                    check_out_time TIMESTAMP,
                    host_id INTEGER,
                    host_name TEXT,
                    status TEXT DEFAULT 'inside',
                    dynamic_fields TEXT,
                    consent_gained INTEGER DEFAULT 0,
                    badge_printed INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (host_id) REFERENCES employees(id)
                )
            """)

            # ACCESS LOGS
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS access_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_type TEXT NOT NULL,
                    person_id INTEGER NOT NULL,
                    direction TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    granted INTEGER DEFAULT 1,
                    reason TEXT,
                    verified_by TEXT,
                    device_id TEXT
                )
            """)

            # CUSTOM FIELDS 
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS custom_fields (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    label TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    required INTEGER DEFAULT 0,
                    validation_regex TEXT,
                    dropdown_options TEXT,
                    display_order INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ROLE PERMISSIONS
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS role_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(role, permission)
                )
            """)

            # SYNC QUEUE 
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT NOT NULL,
                    collection TEXT NOT NULL,
                    doc_id TEXT,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    synced INTEGER DEFAULT 0,
                    sync_attempts INTEGER DEFAULT 0,
                    last_sync_attempt TIMESTAMP
                )
            """)

            # USER CACHE 
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_cache (
                    username TEXT PRIMARY KEY,
                    token TEXT,
                    permissions TEXT,
                    user_info TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # AUDIT LOG
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    action TEXT NOT NULL,
                    details TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

            # Run migrations (writes to schema_version)
            self._run_migrations()

            # Create default data if needed (self-guarding)
            self.create_default_permissions()
            self.create_default_users()

            # Indexes (one-time)
            self._create_indexes()

            # Mark this schema version as fully applied.
            cursor.execute(
                "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                (CURRENT_SCHEMA_VERSION,)
            )
            conn.commit()

        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise

    def _run_migrations(self):
        """Run database migrations. Idempotent: skips already-applied versions."""
        migrations = [
            {
                "version": 1,
                "description": "Initial schema",
                "sql": []
            },
            # Add future migrations here as {"version": N, ...}
        ]

        conn = self._get_connection()
        cursor = conn.cursor()

        # Get current version
        cursor.execute("SELECT MAX(version) FROM schema_version")
        result = cursor.fetchone()
        current_version = result[0] if result and result[0] else 0

        for migration in migrations:
            if migration["version"] <= current_version:
                continue

            logger.info(
                f"Running migration {migration['version']}: "
                f"{migration['description']}"
            )

            try:
                for sql in migration["sql"]:
                    cursor.execute(sql)
                cursor.execute(
                    "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                    (migration["version"],)
                )
                conn.commit()
            except Exception as e:
                logger.error(f"Migration {migration['version']} failed: {e}")
                conn.rollback()
                raise

        conn.commit()

    def _create_indexes(self):
        """Create indexes for performance. Idempotent (IF NOT EXISTS)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_visitors_status ON visitors(status)",
            "CREATE INDEX IF NOT EXISTS idx_visitors_checkin ON visitors(check_in_time)",
            "CREATE INDEX IF NOT EXISTS idx_access_logs_timestamp ON access_logs(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_access_logs_person ON access_logs(person_type, person_id)",
            "CREATE INDEX IF NOT EXISTS idx_employees_active ON employees(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
            "CREATE INDEX IF NOT EXISTS idx_sync_queue_synced ON sync_queue(synced)",
        ]

        for sql in indexes:
            try:
                cursor.execute(sql)
            except Exception as e:
                logger.warning(f"Failed to create index: {e}")

        conn.commit()

    # SECURE USER MANAGEMENT

    def create_default_users(self):
        """
        Create default users with secure random passwords.

        Self-guarding: returns immediately if any user already exists.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]

        if count > 0:
            return

        # Generate secure passwords
        admin_password = self._generate_secure_password()
        security_password = self._generate_secure_password()
        finance_password = self._generate_secure_password()
        staff_password = self._generate_secure_password()

        default_passwords = {
            'admin': admin_password,
            'security': security_password,
            'finance': finance_password,
            'staff': staff_password,
        }

        # Log passwords (first run only)
        logger.warning("=" * 60)
        logger.warning("DEFAULT USER PASSWORDS GENERATED (FIRST RUN ONLY)")
        logger.warning("Please change these immediately after login!")
        for user, pwd in default_passwords.items():
            logger.warning(f"  {user}: {pwd}")
        logger.warning("=" * 60)

        users = [
            ('admin', admin_password, 'System Administrator', 'admin@ict.go.ke', 'admin'),
            ('security', security_password, 'Security Officer', 'security@ict.go.ke', 'security'),
            ('finance', finance_password, 'Finance Officer', 'finance@ict.go.ke', 'finance'),
            ('staff', staff_password, 'Staff Member', 'staff@ict.go.ke', 'staff')
        ]

        for username, pwd, fullname, email, role in users:
            hashed = generate_password_hash(pwd)
            cursor.execute("""
                INSERT INTO users (username, password, full_name, email, role, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (username, hashed, fullname, email, role))

        conn.commit()
        logger.info(f"Default users created: {[u[0] for u in users]}")

    def _generate_secure_password(self) -> str:
        """Generate a secure random password."""
        import string
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(16))


    # AUDIT LOGGING

    def log_audit_event(
        self,
        user_id: Optional[int],
        username: Optional[str],
        action: str,
        details: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Log an audit event."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_log (user_id, username, action, details, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                username,
                action,
                json.dumps(details) if details else None,
                ip_address,
                user_agent
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")

    # SYNC QUEUE METHODS

    def add_sync_operation(self, operation: str, collection: str, doc_id: str, data_dict: Dict) -> int:
        """Add an operation to the sync queue."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sync_queue (operation, collection, doc_id, data, synced)
            VALUES (?, ?, ?, ?, 0)
        """, (operation, collection, doc_id, json.dumps(data_dict)))
        conn.commit()
        return cursor.lastrowid

    def get_pending_operations(self, limit: int = 100) -> List[Dict]:
        """Get pending sync operations."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, operation, collection, doc_id, data, sync_attempts
            FROM sync_queue WHERE synced=0 ORDER BY created_at LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()

        return [
            {
                'id': r['id'],
                'operation': r['operation'],
                'collection': r['collection'],
                'doc_id': r['doc_id'],
                'data': json.loads(r['data']),
                'sync_attempts': r['sync_attempts']
            }
            for r in rows
        ]

    def mark_synced(self, operation_ids: List[int]):
        """Mark operations as synced."""
        if not operation_ids:
            return

        conn = self._get_connection()
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(operation_ids))
        cursor.execute(
            f"UPDATE sync_queue SET synced=1, sync_attempts=sync_attempts+1 WHERE id IN ({placeholders})",
            operation_ids
        )
        conn.commit()

    def increment_sync_attempts(self, operation_ids: List[int]):
        """Increment sync attempt count for operations."""
        if not operation_ids:
            return

        conn = self._get_connection()
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(operation_ids))
        cursor.execute(
            f"UPDATE sync_queue SET sync_attempts=sync_attempts+1, last_sync_attempt=CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
            operation_ids
        )
        conn.commit()

    def clear_synced_operations(self, days: int = 7):
        """Clear old synced operations."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute("DELETE FROM sync_queue WHERE synced=1 AND created_at < ?", (cutoff,))
        conn.commit()
        return cursor.rowcount

    # USER CACHE METHODS

    def save_user_credentials(self, username: str, token: str, permissions: List[str], user_info: Dict):
        """Save user credentials for offline use."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_cache (username, token, permissions, user_info, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            username,
            token,
            json.dumps(permissions),
            json.dumps(user_info),
            datetime.now().isoformat()
        ))
        conn.commit()

    def get_cached_user(self, username: str) -> Optional[Dict]:
        """Get cached user credentials."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT username, token, permissions, user_info, updated_at
            FROM user_cache WHERE username = ?
        """, (username,))
        row = cursor.fetchone()

        if row:
            return {
                'username': row['username'],
                'token': row['token'],
                'permissions': json.loads(row['permissions']),
                'user_info': json.loads(row['user_info']) if row['user_info'] else {},
                'updated_at': row['updated_at']
            }
        return None

    def clear_user_credentials(self, username: Optional[str] = None):
        """Clear cached user credentials."""
        conn = self._get_connection()
        cursor = conn.cursor()
        if username:
            cursor.execute("DELETE FROM user_cache WHERE username = ?", (username,))
        else:
            cursor.execute("DELETE FROM user_cache")
        conn.commit()

    # AUTHENTICATION

    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        """
        Authenticate a user against the local database.

        Returns:
            User info dict or None if authentication fails
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Check lockout
        cursor.execute("""
            SELECT locked_until, failed_attempts
            FROM users WHERE username = ?
        """, (username,))
        lock_row = cursor.fetchone()

        if lock_row and lock_row['locked_until']:
            lock_time = datetime.fromisoformat(lock_row['locked_until'])
            if lock_time > datetime.now():
                logger.warning(f"User {username} is locked until {lock_time}")
                return None
            else:
                cursor.execute(
                    "UPDATE users SET locked_until = NULL, failed_attempts = 0 WHERE username = ?",
                    (username,)
                )
                conn.commit()

        # Get user
        cursor.execute("""
            SELECT id, username, full_name, email, role, password, is_active
            FROM users WHERE username = ?
        """, (username,))
        user = cursor.fetchone()

        if not user or not user['is_active']:
            return None

        # Verify password
        if check_password_hash(user['password'], password):
            cursor.execute("""
                UPDATE users SET
                    failed_attempts = 0,
                    last_login = CURRENT_TIMESTAMP,
                    locked_until = NULL
                WHERE id = ?
            """, (user['id'],))
            conn.commit()

            return {
                'id': user['id'],
                'username': user['username'],
                'full_name': user['full_name'],
                'email': user['email'],
                'role': user['role']
            }
        else:
            cursor.execute("""
                UPDATE users SET
                    failed_attempts = failed_attempts + 1
                WHERE id = ?
            """, (user['id'],))
            conn.commit()

            cursor.execute("SELECT failed_attempts FROM users WHERE id = ?", (user['id'],))
            attempts = cursor.fetchone()
            if attempts and attempts['failed_attempts'] >= 5:
                lock_until = (datetime.now() + timedelta(minutes=30)).isoformat()
                cursor.execute(
                    "UPDATE users SET locked_until = ? WHERE id = ?",
                    (lock_until, user['id'])
                )
                conn.commit()
                logger.warning(f"User {username} locked for 30 minutes (too many failed attempts)")

            return None

    def get_user_role_permissions(self, role: str) -> List[str]:
        """Get permissions for a specific role from database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT permission FROM role_permissions WHERE role = ?", (role,))
        perms = [row['permission'] for row in cursor.fetchall()]
        logger.debug(f"get_user_role_permissions for role '{role}': {perms}")
        return perms
    
    def get_all_users(self) -> List[Dict]:
        """
        Return every row in the local users table.

        Columns mirror what the server returns so the UI can render
        both sources with the same row-building code:

            id, username, full_name, email, role, is_active,
            created_at, updated_at, last_login
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, full_name, email, role, is_active,
                   created_at, updated_at, last_login
            FROM users
            ORDER BY username COLLATE NOCASE
        """)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def get_local_user(self, user_id) -> Optional[Dict]:
        """
        Return one row from the local users table by id or username.

        The id may be either the integer primary key or the username
        string, since the API and the local DB use different shapes.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Try integer id first.
        try:
            int_id = int(user_id)
            cursor.execute("""
                SELECT id, username, full_name, email, role, is_active,
                       created_at, updated_at, last_login
                FROM users WHERE id = ?
            """, (int_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
        except (TypeError, ValueError):
            pass

        # Fall back to username lookup.
        cursor.execute("""
            SELECT id, username, full_name, email, role, is_active,
                   created_at, updated_at, last_login
            FROM users WHERE username = ?
        """, (str(user_id),))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def create_local_user(self, payload: Dict) -> int:
        """
        Insert a row into the local users table.

        Password must be supplied in `payload['password']`. It is
        hashed with werkzeug before storage, matching what
        create_default_users uses.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        password = payload.get("password") or self._generate_secure_password()
        hashed = generate_password_hash(password)

        roles = payload.get("roles") or []
        if isinstance(roles, str):
            roles = [roles]
        primary_role = roles[0] if roles else "staff"

        cursor.execute("""
            INSERT INTO users
            (username, password, full_name, email, role, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            payload.get("username", ""),
            hashed,
            payload.get("full_name", ""),
            payload.get("email", ""),
            primary_role,
            1 if payload.get("is_active", True) else 0,
        ))
        conn.commit()
        return cursor.lastrowid

    def update_local_user(self, local_id: int, payload: Dict):
        """Update a row in the local users table."""
        conn = self._get_connection()
        cursor = conn.cursor()

        fields = []
        params = []
        for column in ("username", "full_name", "email", "role", "is_active"):
            if column in payload:
                fields.append(f"{column} = ?")
                value = payload[column]
                if column == "is_active":
                    value = 1 if value else 0
                params.append(value)

        # Password is stored separately because it needs hashing.
        if payload.get("password"):
            fields.append("password = ?")
            params.append(generate_password_hash(payload["password"]))

        if not fields:
            return

        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(local_id)

        cursor.execute(
            f"UPDATE users SET {', '.join(fields)} WHERE id = ?",
            params
        )
        conn.commit()

    def deactivate_local_user(self, local_id: int):
        """Flip is_active=0 for a row in the local users table."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_active = 0, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (local_id,)
        )
        conn.commit()

    def create_default_permissions(self):
        """
        Create default permissions for all roles.

        Self-guarding: returns immediately if role_permissions already
        contains rows. This makes the method safe to call from any code
        path — including repeated DatabaseManager() constructions — with
        no write I/O on subsequent calls.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Fast path — no rows written if anything already exists.
        cursor.execute("SELECT COUNT(*) FROM role_permissions")
        if cursor.fetchone()[0] > 0:
            return

        permissions = {
            'admin': [
                'view_dashboard', 'manage_visitors', 'view_visitors',
                'manage_employees', 'view_employees', 'view_access_logs',
                'configure_fields', 'view_reports', 'manage_settings',
                'manage_users'
            ],
            'security': ['view_dashboard', 'manage_visitors', 'view_access_logs'],
            'regular': ['view_dashboard', 'view_visitors'],
            'finance': ['view_dashboard', 'view_reports'],
            'staff': ['view_dashboard', 'manage_visitors', 'view_visitors']
        }

        for role, perm_list in permissions.items():
            for perm in perm_list:
                cursor.execute(
                    "INSERT OR IGNORE INTO role_permissions (role, permission) VALUES (?, ?)",
                    (role, perm)
                )
        conn.commit()
        logger.info(f"Default permissions created for roles: {list(permissions.keys())}")

    def needs_initialization(self) -> bool:
        """Check if the database needs initial data."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            count = cursor.fetchone()[0]
            return count == 0
        except Exception:
            return True

    # EMPLOYEE METHODS

    def get_employees(self, active_only: bool = True) -> List[Dict]:
        """Get all employees."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if active_only:
            cursor.execute("SELECT * FROM employees WHERE is_active = 1")
        else:
            cursor.execute("SELECT * FROM employees")

        rows = cursor.fetchall()
        employees = []
        for r in rows:
            emp = dict(r)
            if emp.get('dynamic_fields'):
                emp['dynamic_fields'] = json.loads(emp['dynamic_fields'])
            else:
                emp['dynamic_fields'] = {}
            employees.append(emp)
        return employees

    def get_employee_by_id(self, emp_id: int) -> Optional[Dict]:
        """Get employee by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM employees WHERE id = ?", (emp_id,))
        row = cursor.fetchone()

        if row:
            emp = dict(row)
            if emp.get('dynamic_fields'):
                emp['dynamic_fields'] = json.loads(emp['dynamic_fields'])
            else:
                emp['dynamic_fields'] = {}
            return emp
        return None

    def add_employee(
        self,
        employee_id: str,
        full_name: str,
        role: str,
        badge_number: str,
        dynamic_fields: Optional[Dict] = None
    ) -> int:
        """Add a new employee."""
        dyn_json = json.dumps(dynamic_fields or {})
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO employees (employee_id, full_name, role, badge_number, dynamic_fields, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (employee_id, full_name, role, badge_number, dyn_json))
        conn.commit()
        return cursor.lastrowid

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
        dyn_json = json.dumps(dynamic_fields or {})
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE employees SET
                full_name = ?,
                role = ?,
                badge_number = ?,
                dynamic_fields = ?,
                is_active = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (full_name, role, badge_number, dyn_json, is_active, emp_id))
        conn.commit()

    def deactivate_employee(self, emp_id: int):
        """Deactivate an employee."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE employees SET is_active=0, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (emp_id,)
        )
        conn.commit()

    def get_employees_list_for_host(self) -> List[Tuple[int, str]]:
        """Get employee list for host dropdown."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name FROM employees WHERE is_active=1 ORDER BY full_name")
        return cursor.fetchall()

    # VISITOR METHODS

    def get_active_visitors(self) -> List[Dict]:
        """Get currently active visitors."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM visitors WHERE status='inside'")
        rows = cursor.fetchall()

        visitors = []
        for r in rows:
            v = dict(r)
            if v.get('dynamic_fields'):
                v['dynamic_fields'] = json.loads(v['dynamic_fields'])
            visitors.append(v)
        return visitors

    def check_in_visitor(
        self,
        name: str,
        host_id: int,
        dynamic_data: Dict,
        consent: bool
    ) -> int:
        """Check in a visitor."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT full_name FROM employees WHERE id=?", (host_id,))
        row = cursor.fetchone()
        host_name = row['full_name'] if row else None

        dyn_json = json.dumps(dynamic_data)
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO visitors (visitor_name, check_in_time, host_id, host_name, status, dynamic_fields, consent_gained)
            VALUES (?, ?, ?, ?, 'inside', ?, ?)
        """, (name, now, host_id, host_name, dyn_json, 1 if consent else 0))

        visitor_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO access_logs (person_type, person_id, direction, timestamp, granted, verified_by)
            VALUES ('visitor', ?, 'in', ?, 1, 'system')
        """, (visitor_id, now))

        conn.commit()
        return visitor_id

    def check_out_visitor(self, visitor_id: int):
        """Check out a visitor."""
        now = datetime.now().isoformat()
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE visitors SET check_out_time=?, status='out' WHERE id=?",
            (now, visitor_id)
        )
        cursor.execute("""
            INSERT INTO access_logs (person_type, person_id, direction, timestamp, granted, verified_by)
            VALUES ('visitor', ?, 'out', ?, 1, 'system')
        """, (visitor_id, now))

        conn.commit()

    def get_visitor_history(self, limit: int = 100) -> List[Tuple]:
        """Get visitor history."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, visitor_name, check_in_time, check_out_time, host_id, host_name, status
            FROM visitors ORDER BY check_in_time DESC LIMIT ?
        """, (limit,))
        return cursor.fetchall()

    # ACCESS LOG METHODS

    def get_access_logs(self, filters: Optional[Dict] = None) -> List[Tuple]:
        """Get access logs with optional filters."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
            SELECT id, person_type, person_id, direction, timestamp, granted, reason, verified_by
            FROM access_logs
        """
        params = []
        conditions = []

        if filters:
            if filters.get('person_type'):
                conditions.append("person_type=?")
                params.append(filters['person_type'])
            if filters.get('direction'):
                conditions.append("direction=?")
                params.append(filters['direction'])
            if filters.get('date_from'):
                conditions.append("timestamp>=?")
                params.append(filters['date_from'])
            if filters.get('date_to'):
                conditions.append("timestamp<=?")
                params.append(filters['date_to'])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT 500"

        cursor.execute(query, params)
        return cursor.fetchall()

    def add_access_log(
        self,
        person_type: str,
        person_id: int,
        direction: str,
        granted: bool = True,
        reason: str = "",
        verified_by: str = ""
    ):
        """Add an access log entry."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO access_logs (person_type, person_id, direction, granted, reason, verified_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (person_type, person_id, direction, 1 if granted else 0, reason, verified_by))
        conn.commit()

    # CUSTOM FIELD METHODS

    def get_custom_fields(self, entity_type: str, active_only: bool = True) -> List[Dict]:
        """Get custom fields configuration."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if active_only:
            cursor.execute("""
                SELECT * FROM custom_fields
                WHERE entity_type=? AND is_active=1
                ORDER BY display_order
            """, (entity_type,))
        else:
            cursor.execute("""
                SELECT * FROM custom_fields
                WHERE entity_type=?
                ORDER BY display_order
            """, (entity_type,))

        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def get_custom_field_by_id(self, entity_type: str, field_id: int) -> Optional[Dict]:
        """Get a custom field by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM custom_fields WHERE entity_type=? AND id=?",
            (entity_type, field_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def save_custom_field(self, entity_type: str, field_id: int, data: Dict):
        """Save a custom field configuration."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if field_id == -1:
            cursor.execute("""
                INSERT INTO custom_fields
                (entity_type, field_name, label, data_type, required, validation_regex, dropdown_options, display_order, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                entity_type,
                data['field_name'],
                data['label'],
                data['data_type'],
                data.get('required', 0),
                data.get('validation_regex', ''),
                data.get('dropdown_options', ''),
                data.get('display_order', 0)
            ))
        else:
            cursor.execute("""
                UPDATE custom_fields SET
                    field_name = ?,
                    label = ?,
                    data_type = ?,
                    required = ?,
                    validation_regex = ?,
                    dropdown_options = ?,
                    display_order = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND entity_type = ?
            """, (
                data['field_name'],
                data['label'],
                data['data_type'],
                data.get('required', 0),
                data.get('validation_regex', ''),
                data.get('dropdown_options', ''),
                data.get('display_order', 0),
                field_id,
                entity_type
            ))

        conn.commit()

    def delete_custom_field(self, entity_type: str, field_id: int):
        """Delete a custom field."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM custom_fields WHERE entity_type=? AND id=?",
            (entity_type, field_id)
        )
        conn.commit()

    # UTILITY METHODS

    def purge_expired_visitors(self):
        """Purge expired visitor records."""
        cutoff = (datetime.now() - timedelta(days=Config.VISITOR_RETENTION_DAYS)).isoformat()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM visitors WHERE check_in_time < ? AND status='out'",
            (cutoff,)
        )
        conn.commit()

    def vacuum(self):
        """Optimize database."""
        conn = self._get_connection()
        conn.execute("VACUUM")
        logger.info("Database vacuumed")

    def close(self):
        """Close database connection."""
        if hasattr(self._local, 'conn') and self._local.conn:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
            logger.debug("Database connection closed")


