import sqlite3
import json
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

class DatabaseManager:
    def __init__(self):
        self.db_path = os.path.join(Config.DATA_DIR, "access_control.db")
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Users table
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            full_name TEXT,
            email TEXT,
            role TEXT,
            is_active INTEGER DEFAULT 1
        )''')

        # Employees table
        cursor.execute('''CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY,
            employee_id TEXT UNIQUE,
            full_name TEXT,
            role TEXT,
            badge_number TEXT,
            is_active INTEGER DEFAULT 1,
            dynamic_fields TEXT
        )''')

        # Visitors table
        cursor.execute('''CREATE TABLE IF NOT EXISTS visitors (
            id INTEGER PRIMARY KEY,
            visitor_name TEXT,
            check_in_time TEXT,
            check_out_time TEXT,
            host_id INTEGER,
            host_name TEXT,
            status TEXT,
            dynamic_fields TEXT,
            consent_gained INTEGER
        )''')

        # Access logs
        cursor.execute('''CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY,
            person_type TEXT,
            person_id INTEGER,
            direction TEXT,
            timestamp TEXT,
            granted INTEGER,
            reason TEXT,
            verified_by TEXT
        )''')

        # Custom fields config
        cursor.execute('''CREATE TABLE IF NOT EXISTS custom_fields (
            id INTEGER PRIMARY KEY,
            entity_type TEXT,
            field_name TEXT,
            label TEXT,
            data_type TEXT,
            required INTEGER,
            validation_regex TEXT,
            dropdown_options TEXT,
            display_order INTEGER,
            is_active INTEGER DEFAULT 1
        )''')

        # Role permissions
        cursor.execute('''CREATE TABLE IF NOT EXISTS role_permissions (
            role TEXT,
            permission TEXT
        )''')

        # Sync queue table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation TEXT NOT NULL,
                collection TEXT NOT NULL,
                doc_id TEXT,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                synced BOOLEAN DEFAULT 0
            )
        ''')

        # User cache table (added user_info column)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_cache (
                username TEXT PRIMARY KEY,
                token TEXT,
                permissions TEXT,
                user_info TEXT,
                updated_at TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

        self.create_default_permissions()
        self.create_default_users()

    # SYNC QUEUE METHODS
    def add_sync_operation(self, operation, collection, doc_id, data_dict):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sync_queue (operation, collection, doc_id, data, synced)
            VALUES (?, ?, ?, ?, 0)
        ''', (operation, collection, doc_id, json.dumps(data_dict)))
        conn.commit()
        conn.close()
        return cursor.lastrowid

    def get_pending_operations(self, limit=100):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT id, operation, collection, doc_id, data FROM sync_queue WHERE synced=0 LIMIT ?', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [{'id': r[0], 'operation': r[1], 'collection': r[2], 'doc_id': r[3], 'data': json.loads(r[4])} for r in rows]

    def mark_synced(self, operation_ids):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.executemany('UPDATE sync_queue SET synced=1 WHERE id=?', [(oid,) for oid in operation_ids])
        conn.commit()
        conn.close()

    # USER CACHE METHODS (updated)
    def _ensure_user_cache_column(self, column):
        """Ensure a column exists in user_cache table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(user_cache)")
        columns = [info[1] for info in cursor.fetchall()]
        conn.close()
        if column not in columns:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(f"ALTER TABLE user_cache ADD COLUMN {column} TEXT")
            conn.commit()
            conn.close()

    def save_user_credentials(self, username, token, permissions, user_info=None):
        self._ensure_user_cache_column("user_info")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('REPLACE INTO user_cache (username, token, permissions, user_info, updated_at) VALUES (?, ?, ?, ?, ?)',
                       (username, token, json.dumps(permissions), json.dumps(user_info) if user_info else "{}", datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_cached_user(self, username):
        self._ensure_user_cache_column("user_info")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT username, token, permissions, user_info, updated_at FROM user_cache WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                'username': row[0],
                'token': row[1],
                'permissions': json.loads(row[2]),
                'user_info': json.loads(row[3]) if row[3] else {},
                'updated_at': row[4]
            }
        return None

    # DEFAULT DATA 
    def create_default_permissions(self):
        perms = {
            'admin': list(Config.PERMISSIONS.keys()),
            'security': ['view_dashboard', 'manage_visitors', 'view_access_logs'],
            'regular': ['view_dashboard', 'view_visitors'],
            'finance': ['view_dashboard', 'view_reports'],
            'staff': ['view_dashboard', 'manage_visitors']
        }
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for role, perm_list in perms.items():
            for perm in perm_list:
                cursor.execute("INSERT OR IGNORE INTO role_permissions (role, permission) VALUES (?, ?)", (role, perm))
        conn.commit()
        conn.close()

    def create_default_users(self):
        users = [
            ('admin', 'Admin@123', 'System Administrator', 'admin@ict.go.ke', 'admin'),
            ('security', 'Security@123', 'Security Officer', 'security@ict.go.ke', 'security'),
            ('finance', 'Finance@123', 'Finance Officer', 'finance@ict.go.ke', 'finance'),
            ('staff', 'Staff@123', 'Staff Member', 'staff@ict.go.ke', 'staff')
        ]
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for username, pwd, fullname, email, role in users:
            hashed = generate_password_hash(pwd)
            cursor.execute("INSERT OR IGNORE INTO users (username, password, full_name, email, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                           (username, hashed, fullname, email, role))
        conn.commit()
        conn.close()

    # AUTHENTICATION 
    def authenticate_user(self, username, password):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, full_name, email, role, password FROM users WHERE username = ? AND is_active = 1", (username,))
        user = cursor.fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            return {
                'id': user['id'],
                'username': user['username'],
                'full_name': user['full_name'],
                'email': user['email'],
                'role': user['role']
            }
        return None

    def get_user_role_permissions(self, role):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT permission FROM role_permissions WHERE role = ?", (role,))
        perms = [row[0] for row in cursor.fetchall()]
        conn.close()
        return perms

    # EMPLOYEE METHODS 
    def get_employees(self, active_only=True):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if active_only:
            cursor.execute("SELECT * FROM employees WHERE is_active = 1")
        else:
            cursor.execute("SELECT * FROM employees")
        rows = cursor.fetchall()
        employees = []
        for r in rows:
            emp = dict(r)
            if emp['dynamic_fields']:
                emp['dynamic_fields'] = json.loads(emp['dynamic_fields'])
            else:
                emp['dynamic_fields'] = {}
            employees.append(emp)
        conn.close()
        return employees

    def get_employee_by_id(self, emp_id):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM employees WHERE id = ?", (emp_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            emp = dict(row)
            emp['dynamic_fields'] = json.loads(emp['dynamic_fields']) if emp['dynamic_fields'] else {}
            return emp
        return None

    def add_employee(self, employee_id, full_name, role, badge_number, dynamic_fields=None):
        dyn_json = json.dumps(dynamic_fields or {})
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO employees (employee_id, full_name, role, badge_number, dynamic_fields, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                       (employee_id, full_name, role, badge_number, dyn_json))
        conn.commit()
        conn.close()

    def update_employee(self, emp_id, full_name, role, badge_number, dynamic_fields, is_active):
        dyn_json = json.dumps(dynamic_fields or {})
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE employees SET full_name=?, role=?, badge_number=?, dynamic_fields=?, is_active=? WHERE id=?",
                       (full_name, role, badge_number, dyn_json, is_active, emp_id))
        conn.commit()
        conn.close()

    def deactivate_employee(self, emp_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE employees SET is_active=0 WHERE id=?", (emp_id,))
        conn.commit()
        conn.close()

    def get_employees_list_for_host(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name FROM employees WHERE is_active=1")
        rows = cursor.fetchall()
        conn.close()
        return rows

    # VISITOR METHODS
    def get_active_visitors(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM visitors WHERE status='inside'")
        rows = cursor.fetchall()
        visitors = []
        for r in rows:
            v = dict(r)
            if v['dynamic_fields']:
                v['dynamic_fields'] = json.loads(v['dynamic_fields'])
            visitors.append(v)
        conn.close()
        return visitors

    def check_in_visitor(self, name, host_id, dynamic_data, consent):
        host_name = None
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT full_name FROM employees WHERE id=?", (host_id,))
        row = cursor.fetchone()
        if row:
            host_name = row[0]
        dyn_json = json.dumps(dynamic_data)
        now = datetime.now().isoformat()
        cursor.execute("INSERT INTO visitors (visitor_name, check_in_time, host_id, host_name, status, dynamic_fields, consent_gained) VALUES (?,?,?,?,?,?,?)",
                       (name, now, host_id, host_name, 'inside', dyn_json, 1 if consent else 0))
        visitor_id = cursor.lastrowid
        # Log access
        cursor.execute("INSERT INTO access_logs (person_type, person_id, direction, timestamp, granted, verified_by) VALUES (?,?,?,?,?,?)",
                       ('visitor', visitor_id, 'in', now, 1, 'system'))
        conn.commit()
        conn.close()
        return visitor_id

    def check_out_visitor(self, visitor_id):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE visitors SET check_out_time=?, status='out' WHERE id=?", (now, visitor_id))
        cursor.execute("INSERT INTO access_logs (person_type, person_id, direction, timestamp, granted, verified_by) VALUES (?,?,?,?,?,?)",
                       ('visitor', visitor_id, 'out', now, 1, 'system'))
        conn.commit()
        conn.close()

    def get_visitor_history(self, limit=100):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, visitor_name, check_in_time, check_out_time, host_id, host_name, status FROM visitors ORDER BY check_in_time DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    # ACCESS LOGS 
    def get_access_logs(self, filters=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        query = "SELECT id, person_type, person_id, direction, timestamp, granted, reason, verified_by FROM access_logs"
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
        rows = cursor.fetchall()
        conn.close()
        return rows

    # CUSTOM FIELDS
    def get_custom_fields(self, entity_type, active_only=True):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if active_only:
            cursor.execute("SELECT * FROM custom_fields WHERE entity_type=? AND is_active=1 ORDER BY display_order", (entity_type,))
        else:
            cursor.execute("SELECT * FROM custom_fields WHERE entity_type=? ORDER BY display_order", (entity_type,))
        rows = cursor.fetchall()
        fields = [dict(r) for r in rows]
        conn.close()
        return fields

    def get_custom_field_by_id(self, entity_type, field_id):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM custom_fields WHERE entity_type=? AND id=?", (entity_type, field_id))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def save_custom_field(self, entity_type, field_id, data):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if field_id == -1:
            cursor.execute("""INSERT INTO custom_fields 
                (entity_type, field_name, label, data_type, required, validation_regex, dropdown_options, display_order, is_active)
                VALUES (?,?,?,?,?,?,?,?,1)""",
                (entity_type, data['field_name'], data['label'], data['data_type'],
                 data['required'], data['validation_regex'], data['dropdown_options'], data['display_order']))
        else:
            cursor.execute("""UPDATE custom_fields SET
                field_name=?, label=?, data_type=?, required=?, validation_regex=?, dropdown_options=?, display_order=?
                WHERE id=? AND entity_type=?""",
                (data['field_name'], data['label'], data['data_type'],
                 data['required'], data['validation_regex'], data['dropdown_options'],
                 data['display_order'], field_id, entity_type))
        conn.commit()
        conn.close()

    def delete_custom_field(self, entity_type, field_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM custom_fields WHERE entity_type=? AND id=?", (entity_type, field_id))
        conn.commit()
        conn.close()

    def purge_expired_visitors(self):
        cutoff = (datetime.now() - timedelta(days=Config.VISITOR_RETENTION_DAYS)).isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM visitors WHERE check_in_time < ? AND status='out'", (cutoff,))
        conn.commit()
        conn.close()

    def sync_data(self):
        # Placeholder for external sync
        pass
