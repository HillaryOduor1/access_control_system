import os
from cryptography.fernet import Fernet

class Config:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    ASSETS_DIR = os.path.join(BASE_DIR, "assets")
    ICONS_DIR = os.path.join(ASSETS_DIR, "icons")

    # Ensure directories exist
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(ICONS_DIR, exist_ok=True)

    DATA_FILE = os.path.join(DATA_DIR, "app_data.json")
    THEMES_DIR = os.path.join(BASE_DIR, "themes")

    WINDOW_TITLE = "ICT Authority Access Control"
    MIN_WIDTH = 1000
    MIN_HEIGHT = 700
    INITIAL_WIDTH = 1100
    INITIAL_HEIGHT = 700

    # Sidebar
    SIDEBAR_EXPANDED = 260
    SIDEBAR_COLLAPSED = 72
    SIDEBAR_ANIMATION_DURATION = 300  # ms

    # GDPR / Retention
    VISITOR_RETENTION_DAYS = 30

    # Encryption
    KEY_FILE = os.path.join(DATA_DIR, "secret.key")
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            ENCRYPTION_KEY = f.read().decode()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        ENCRYPTION_KEY = key.decode()

    SENSITIVE_FIELDS = ['phone', 'emergency_phone', 'national_id', 'license_plate']

    # Permissions (matching DB)
    PERMISSIONS = {
        'view_dashboard': 'View Dashboard',
        'manage_visitors': 'Manage Visitors (check in/out)',
        'view_visitors': 'View Visitor List',
        'manage_employees': 'Manage Employees',
        'view_employees': 'View Employees',
        'view_access_logs': 'View Access Logs',
        'configure_fields': 'Configure Dynamic Fields',
        'view_reports': 'View Reports',
        'manage_settings': 'Manage Settings',
    }

    # Design tokens (will be overridden by theme manager)
    THEME_TOKENS = {
        "light": {
            "bg_primary": "#F8FAFC",
            "bg_secondary": "#FFFFFF",
            "bg_elevated": "#FFFFFF",
            "surface": "#FFFFFF",
            "surface_hover": "#F1F5F9",
            "border": "#E2E8F0",
            "text_primary": "#0F172A",
            "text_secondary": "#64748B",
            "text_muted": "#94A3B8",
            "text_on_primary": "#FFFFFF",
            "primary": "#006B3F",
            "primary_hover": "#005633",
            "accent": "#D62828",
            "success": "#10B981",
            "warning": "#F59E0B",
            "error": "#EF4444",
            "info": "#3B82F6",
        },
        "dark": {
            "bg_primary": "#0B1220",
            "bg_secondary": "#111827",
            "bg_elevated": "#1E293B",
            "surface": "#1E293B",
            "surface_hover": "#334155",
            "border": "#334155",
            "text_primary": "#F8FAFC",
            "text_secondary": "#94A3B8",
            "text_muted": "#64748B",
            "text_on_primary": "#FFFFFF",
            "primary": "#006B3F",
            "primary_hover": "#008C52",
            "accent": "#D62828",
            "success": "#10B981",
            "warning": "#F59E0B",
            "error": "#EF4444",
            "info": "#3B82F6",
        }
    }
