# config.py
"""
Enterprise-grade configuration management for ICT Authority Access Control.

The configuration is designed for:
- Dynamic screen/work-area sizing
- Windows taskbar awareness
- Multi-monitor environments
- PyInstaller/frozen deployments
- User-specific application data
- Theme and asset management
- Secure configuration storage
- Reduced motion accessibility support
"""

import base64
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet


logger = logging.getLogger(__name__)

# Application Paths

@dataclass
class AppPaths:
    """Application path management for enterprise deployment."""

    @staticmethod
    def get_base_dir() -> Path:
        """Get the base directory of the application."""

        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent

        return Path(__file__).parent

    @staticmethod
    def get_user_data_dir() -> Path:
        """Get platform-specific user data directory."""

        if sys.platform == "win32":
            base = Path(
                os.environ.get(
                    "APPDATA",
                    os.path.expanduser("~"),
                )
            )

        elif sys.platform == "darwin":
            base = (
                Path.home()
                / "Library"
                / "Application Support"
            )

        else:
            base = (
                Path.home()
                / ".local"
                / "share"
            )

        return (
            base
            / "ICTAuthority"
            / "AccessControl"
        )

    @staticmethod
    def get_user_config_dir() -> Path:
        """Get platform-specific user configuration directory."""

        if sys.platform == "win32":
            base = Path(
                os.environ.get(
                    "APPDATA",
                    os.path.expanduser("~"),
                )
            )

        elif sys.platform == "darwin":
            base = (
                Path.home()
                / "Library"
                / "Preferences"
            )

        else:
            base = (
                Path.home()
                / ".config"
            )

        return (
            base
            / "ICTAuthority"
            / "AccessControl"
        )

    @staticmethod
    def get_cache_dir() -> Path:
        """Get platform-specific cache directory."""

        if sys.platform == "win32":
            base = Path(
                os.environ.get(
                    "LOCALAPPDATA",
                    os.path.expanduser("~"),
                )
            )

        elif sys.platform == "darwin":
            base = (
                Path.home()
                / "Library"
                / "Caches"
            )

        else:
            base = (
                Path.home()
                / ".cache"
            )

        return (
            base
            / "ICTAuthority"
            / "AccessControl"
        )

    @staticmethod
    def get_log_dir() -> Path:
        """Get application log directory."""

        if getattr(sys, "frozen", False):
            return (
                AppPaths.get_user_data_dir()
                / "logs"
            )

        return (
            Path(__file__).parent
            / "logs"
        )

    @staticmethod
    def get_assets_dir() -> Path:
        """Get application assets directory."""

        if getattr(sys, "frozen", False):

            base = Path(
                sys.executable
            ).parent

            internal = base / "_internal"

            if internal.exists():
                return internal / "assets"

            return base / "assets"

        return (
            Path(__file__).parent
            / "assets"
        )

    @staticmethod
    def get_theme_dir() -> Path:
        """Get application themes directory."""

        if getattr(sys, "frozen", False):

            base = Path(
                sys.executable
            ).parent

            internal = base / "_internal"

            if internal.exists():
                return internal / "themes"

            return base / "themes"

        return (
            Path(__file__).parent
            / "themes"
        )

    @staticmethod
    def ensure_directories():
        """Create all required application directories."""

        directories = [
            AppPaths.get_user_data_dir(),
            AppPaths.get_user_config_dir(),
            AppPaths.get_cache_dir(),
            AppPaths.get_log_dir(),
        ]

        for directory in directories:
            try:
                directory.mkdir(
                    parents=True,
                    exist_ok=True,
                )
            except Exception as exc:
                logger.error(
                    "Failed to create directory %s: %s",
                    directory,
                    exc,
                )


# Secure Configuration

class SecureConfig:
    """
    Secure configuration storage.

    Sensitive values are encrypted using Fernet.

    NOTE:
    For high-security production deployments, OS credential/keychain
    storage should ultimately be preferred over an application-managed
    encryption key file.
    """

    def __init__(self):

        self._key: Optional[bytes] = None
        self._fernet: Optional[Fernet] = None

        self._config_file = (
            AppPaths.get_user_config_dir()
            / "secure_config.json"
        )

        self._config_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._load_or_create_key()

    # Encryption key

    def _load_or_create_key(self):
        """Load an existing encryption key or generate one."""

        key_file = (
            AppPaths.get_user_config_dir()
            / "encryption.key"
        )

        try:

            if key_file.exists():

                with open(
                    key_file,
                    "rb",
                ) as file:

                    self._key = file.read()

                logger.debug(
                    "Loaded existing encryption key"
                )

            else:

                self._key = (
                    Fernet.generate_key()
                )

                with open(
                    key_file,
                    "wb",
                ) as file:

                    file.write(
                        self._key
                    )

                try:
                    os.chmod(
                        key_file,
                        0o600,
                    )
                except Exception:
                    pass

                logger.info(
                    "Generated new encryption key"
                )

            self._fernet = Fernet(
                self._key
            )

        except Exception as exc:

            logger.warning(
                "Failed to load/create encryption key: %s",
                exc,
            )

            self._create_fallback_key()

    def _create_fallback_key(self):
        """Create a deterministic fallback encryption key.

        NOTE: This fallback derives a key from local machine identifiers
        and is weaker than the primary key file. When it is used, a
        warning is logged so the deployment can be audited.
        """

        import hashlib
        import socket

        try:

            machine_id = hashlib.sha256(
                (
                    os.environ.get(
                        "USER",
                        "",
                    )
                    + os.environ.get(
                        "USERNAME",
                        "",
                    )
                    + os.environ.get(
                        "COMPUTERNAME",
                        "",
                    )
                    + socket.gethostname()
                ).encode()
            ).hexdigest()

            self._key = (
                base64.urlsafe_b64encode(
                    machine_id[:32]
                    .encode()
                    .ljust(
                        32,
                        b"_",
                    )
                )
            )

            self._fernet = Fernet(
                self._key
            )

            logger.warning(
                "Using fallback encryption key — this is weaker than "
                "the primary key file and should be investigated."
            )

        except Exception as exc:

            logger.error(
                "Failed to create fallback key: %s",
                exc,
            )

            self._fernet = None

    def get_encryption_key(
        self,
    ) -> Optional[bytes]:
        """Return the current encryption key."""

        return self._key

    def encrypt(
        self,
        value: str,
    ) -> str:
        """Encrypt a string value."""

        if not self._fernet:

            logger.warning(
                "Encryption unavailable"
            )

            return value

        try:

            return (
                self._fernet
                .encrypt(
                    value.encode()
                )
                .decode()
            )

        except Exception as exc:

            logger.error(
                "Encryption failed: %s",
                exc,
            )

            return value

    def decrypt(
        self,
        encrypted: str,
    ) -> str:
        """Decrypt an encrypted string."""

        if not self._fernet:
            return encrypted

        try:

            return (
                self._fernet
                .decrypt(
                    encrypted.encode()
                )
                .decode()
            )

        except Exception as exc:

            logger.error(
                "Decryption failed: %s",
                exc,
            )

            return encrypted

    def get_config(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """Retrieve a configuration value."""

        try:

            if not self._config_file.exists():
                return default

            with open(
                self._config_file,
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(file)

            value = data.get(
                key,
                default,
            )

            if (
                isinstance(value, str)
                and value.startswith("enc:")
            ):
                return self.decrypt(
                    value[4:]
                )

            return value

        except Exception as exc:

            logger.error(
                "Failed to get config '%s': %s",
                key,
                exc,
            )

            return default

    def set_config(
        self,
        key: str,
        value: Any,
    ):
        """Store a configuration value."""

        try:

            data = {}

            if self._config_file.exists():

                with open(
                    self._config_file,
                    "r",
                    encoding="utf-8",
                ) as file:

                    data = json.load(file)

            sensitive_keys = {
                "api_key",
                "secret_token",
                "password",
                "refresh_token",
            }

            if key in sensitive_keys:

                data[key] = (
                    "enc:"
                    + self.encrypt(
                        str(value)
                    )
                )

            else:

                data[key] = value

            temp_file = (
                self._config_file.with_suffix(
                    ".tmp"
                )
            )

            with open(
                temp_file,
                "w",
                encoding="utf-8",
            ) as file:

                json.dump(
                    data,
                    file,
                    indent=2,
                )

            # Atomic replacement where supported.
            temp_file.replace(
                self._config_file
            )

            logger.debug(
                "Configuration saved: %s",
                key,
            )

        except Exception as exc:

            logger.error(
                "Failed to set config '%s': %s",
                key,
                exc,
            )


# Application Configuration

class Config:
    """
    Enterprise application configuration.

    Screen sizing intentionally does NOT define a fixed application height.
    The main window should use the operating system's available screen
    geometry so that the Windows taskbar remains visible.
    """

    # Application

    WINDOW_TITLE = (
        "Authority Access Control"
    )
    '''Layout: shared shell geometry,The header and the sidebar's top block must have the same height so their bottom separators form a single continuous line across the top of the application window.'''
    TOPBAR_HEIGHT = 52

    # Minimum usable dimensions.
    # These are NOT the startup dimensions.
    MIN_WIDTH = 1000
    MIN_HEIGHT = 650

    # Legacy/default dimensions retained as sensible fallback values.
    INITIAL_WIDTH = 1100
    INITIAL_HEIGHT = 700

    # Start application using available desktop/work area.
    START_MAXIMIZED = True

    # Do NOT use Qt's true fullscreen mode.
    # showFullScreen() can cover the Windows taskbar.
    USE_TRUE_FULLSCREEN = False

    # Respect operating system work area.
    RESPECT_SYSTEM_WORK_AREA = True

    # Reduced motion
    '''When True, animation durations are forced to 0. This is a global,default; users can override it per-account via the Settings page,("Reduce visual effects" checkbox), which persists to the user's,appearance preferences. Components consult,ThemeManager.is_reduced_effects() at animation time.The presence of this attribute keeps any legacy callers that read.Config.REDUCED_MOTION working. New code should prefer the ThemeManager method.'''
    REDUCED_MOTION = False

    # Spacing scale (px)
    # A small subset of the token spacing scale, exposed on Config for
    # callers that do not have a ThemeManager instance handy. Prefer the
    # tokens from ThemeManager.get_tokens() where possible.
    SPACE_1 = 4
    SPACE_2 = 8
    SPACE_3 = 12
    SPACE_4 = 16
    SPACE_5 = 20
    SPACE_6 = 24
    SPACE_8 = 32
    SPACE_10 = 40

    # Default content margin for top-level pages.
    PAGE_MARGIN = 24

    # Sidebar
    
    SIDEBAR_EXPANDED = 248
    SIDEBAR_COLLAPSED = 68
    SIDEBAR_ANIMATION_DURATION = 220

    # Automatically collapse below this application width.
    SIDEBAR_AUTO_COLLAPSE_AT = 1100

    # Data retention
    
    VISITOR_RETENTION_DAYS = 30
    LOG_RETENTION_DAYS = 30

    # Synchronization
    
    SYNC_INTERVAL_SECONDS = 120
    SYNC_RETRY_MAX = 3
    SYNC_RETRY_DELAY_SECONDS = 30

    # API
    
    API_TIMEOUT_SECONDS = 30
    API_MAX_RETRIES = 3
    API_RETRY_BACKOFF = 1.0

    # Sensitive fields
    
    SENSITIVE_FIELDS = [
        "phone",
        "emergency_phone",
        "national_id",
        "license_plate",
        "passport_number",
    ]

    # Permissions
    
    PERMISSIONS: Dict[str, str] = {
        "view_dashboard":
            "View Dashboard",

        "manage_visitors":
            "Manage Visitors (check in/out)",

        "view_visitors":
            "View Visitor List",

        "manage_employees":
            "Manage Employees",

        "view_employees":
            "View Employees",

        "view_access_logs":
            "View Access Logs",

        "configure_fields":
            "Configure Dynamic Fields",

        "view_reports":
            "View Reports",

        "manage_settings":
            "Manage Settings",

        "manage_users":
            "Manage Users",
    }

    # Paths
    
    @classmethod
    def get_data_dir(cls) -> Path:
        """Get application data directory."""

        return (
            AppPaths.get_user_data_dir()
        )

    @classmethod
    def get_assets_dir(cls) -> Path:
        """Get application assets directory."""

        return (
            AppPaths.get_assets_dir()
        )

    @classmethod
    def get_theme_dir(cls) -> Path:
        """Get application themes directory."""

        return (
            AppPaths.get_theme_dir()
        )

    @classmethod
    def get_icons_dir(cls) -> Path:
        """Get application icon directory."""

        return (
            cls.get_assets_dir()
            / "icons"
        )

    @classmethod
    def get_log_dir(cls) -> Path:
        """Get application log directory."""

        return (
            AppPaths.get_log_dir()
        )

    @classmethod
    def get_secure_config(
        cls,
    ) -> SecureConfig:
        """Return a secure configuration instance."""

        return SecureConfig()

    @classmethod
    def get_data_file(cls) -> Path:
        """Get application data file."""

        return (
            cls.get_data_dir()
            / "app_data.json"
        )

    @classmethod
    def get_db_path(cls) -> Path:
        """Get main database path."""

        return (
            cls.get_data_dir()
            / "school_management.db"
        )

    @classmethod
    def get_access_control_db_path(
        cls,
    ) -> Path:
        """Get access-control database path."""

        return (
            cls.get_data_dir()
            / "access_control.db"
        )

    # Screen / Work Area Helpers
    
    @classmethod
    def get_available_geometry(cls):
        """
        Get the available screen geometry (excludes taskbar/docks).

        Returns:
            QRect: Available screen geometry or None if QApplication not running
        """
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtGui import QScreen

            app = QApplication.instance()
            if app is None:
                return None

            screen = app.primaryScreen()
            if screen is None:
                return None

            # Get available geometry (excludes taskbar, docks, etc.)
            return screen.availableGeometry()

        except ImportError:
            logger.warning("PySide6 not available for screen geometry")
            return None
        except Exception as exc:
            logger.error("Failed to get available geometry: %s", exc)
            return None

    @classmethod
    def get_screen_size(cls):
        """
        Get the full screen size.

        Returns:
            tuple: (width, height) or None if QApplication not running
        """
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                return None

            screen = app.primaryScreen()
            if screen is None:
                return None

            geometry = screen.geometry()
            return (geometry.width(), geometry.height())

        except ImportError:
            return None
        except Exception as exc:
            logger.error("Failed to get screen size: %s", exc)
            return None

    @classmethod
    def get_available_size(cls):
        """
        Get the available size (work area, excludes taskbar).

        Returns:
            tuple: (width, height) or None if QApplication not running
        """
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                return None

            screen = app.primaryScreen()
            if screen is None:
                return None

            geometry = screen.availableGeometry()
            return (geometry.width(), geometry.height())

        except ImportError:
            return None
        except Exception as exc:
            logger.error("Failed to get available size: %s", exc)
            return None

    @classmethod
    def get_window_geometry_for_startup(cls):
        """
        Get the recommended window geometry for application startup.

        Returns:
            tuple: (x, y, width, height) or None
        """
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                return None

            screen = app.primaryScreen()
            if screen is None:
                return None

            geometry = screen.availableGeometry()

            # Use 85% of available width, 90% of available height
            # with the window centered in the available work area.
            width = int(geometry.width() * 0.85)
            height = int(geometry.height() * 0.90)

            # Ensure minimum dimensions
            width = max(width, cls.MIN_WIDTH)
            height = max(height, cls.MIN_HEIGHT)

            x = geometry.x() + (geometry.width() - width) // 2
            y = geometry.y() + (geometry.height() - height) // 2

            return (x, y, width, height)

        except ImportError:
            return None
        except Exception as exc:
            logger.error("Failed to get startup geometry: %s", exc)
            return None

    @classmethod
    def get_sidebar_dimensions(cls) -> Dict[str, int]:
        """
        Get sidebar dimensions from configuration.

        Returns:
            dict: Contains 'expanded', 'collapsed', 'auto_collapse_at'
        """
        return {
            "expanded": cls.SIDEBAR_EXPANDED,
            "collapsed": cls.SIDEBAR_COLLAPSED,
            "auto_collapse_at": cls.SIDEBAR_AUTO_COLLAPSE_AT,
        }

    # Environment
    
    @classmethod
    def is_development(cls) -> bool:
        """Return True when running from source."""

        return not getattr(
            sys,
            "frozen",
            False,
        )

    @classmethod
    def is_frozen(cls) -> bool:
        """Return True when running as a frozen executable."""

        return getattr(
            sys,
            "frozen",
            False,
        )

    # Initialization
    
    @classmethod
    def ensure_directories(cls):
        """Ensure application directories and defaults exist."""

        AppPaths.ensure_directories()

        # Asset directories.
        cls.get_icons_dir().mkdir(
            parents=True,
            exist_ok=True,
        )

        # Default application configuration.
        config_file = (
            cls.get_data_dir()
            / "app_data.json"
        )

        if not config_file.exists():

            try:

                default_config = {
                    "version": "2.0.0",
                    "theme": "light",
                    "environment": "production",
                    "first_run": True,
                    "window": {
                        "startup_mode": "maximized",
                        "respect_work_area": True,
                    },
                    "installed_at":
                        datetime.now().isoformat(),
                }

                temp_file = (
                    config_file.with_suffix(
                        ".tmp"
                    )
                )

                with open(
                    temp_file,
                    "w",
                    encoding="utf-8",
                ) as file:

                    json.dump(
                        default_config,
                        file,
                        indent=2,
                    )

                temp_file.replace(
                    config_file
                )

                logger.info(
                    "Created default application configuration"
                )

            except Exception as exc:

                logger.error(
                    "Failed to create default configuration: %s",
                    exc,
                )


# Initialize configuration directories

Config.ensure_directories()

