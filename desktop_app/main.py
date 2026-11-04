# main.py
"""
Enterprise-grade application entry point.
"""
import sys
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer, Qt

from core.app import MainApp
from widgets.splash_screen import SplashScreen
from utils.path_utils import resource_path


# LOGGING SETUP

class LoggingConfig:
    DEV_LOG_LEVEL = logging.DEBUG
    PROD_LOG_LEVEL = logging.INFO

    DEBUG_MODULES = [
        'core.auth_manager',
        'core.sync_manager',
        'database.db_manager',
    ]

    SUPPRESS_MODULES = [
        'httpx', 'httpcore', 'urllib3',
        'keyring', 'keyrings',
        'asyncio', 'PIL', 'matplotlib',
        'jose', 'pymongo', 'motor', 'cryptography',
    ]

    MAX_LOG_SIZE = 50 * 1024 * 1024
    BACKUP_COUNT = 5
    RETENTION_DAYS = 30

    @classmethod
    def get_log_dir(cls) -> Path:
        frozen = getattr(sys, 'frozen', False)
        if frozen:
            if sys.platform == "win32":
                base = Path(os.environ.get("APPDATA", "~"))
            elif sys.platform == "darwin":
                base = Path.home() / "Library" / "Application Support"
            else:
                base = Path.home() / ".local" / "share"
            return base / "ICTAuthority" / "AccessControl" / "logs"
        else:
            return Path(os.getcwd()) / "logs"

    @classmethod
    def get_log_file(cls) -> Path:
        log_dir = cls.get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log"

    @classmethod
    def is_production(cls) -> bool:
        return getattr(sys, 'frozen', False)


def setup_logging(debug_mode: bool = False) -> logging.Logger:
    is_prod = LoggingConfig.is_production()
    root_level = logging.DEBUG if debug_mode else logging.INFO
    root_logger = logging.getLogger()
    root_logger.setLevel(root_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    log_file = LoggingConfig.get_log_file()
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=LoggingConfig.MAX_LOG_SIZE,
        backupCount=LoggingConfig.BACKUP_COUNT,
        encoding='utf-8'
    )
    file_level = logging.DEBUG if debug_mode else logging.INFO
    file_handler.setLevel(file_level)

    console_handler = None
    if sys.stdout is not None and (debug_mode or not is_prod):
        console_handler = logging.StreamHandler(sys.stdout)
        console_level = logging.DEBUG if debug_mode else logging.INFO
        console_handler.setLevel(console_level)

    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    if console_handler:
        console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    if console_handler:
        root_logger.addHandler(console_handler)

    for lib in LoggingConfig.SUPPRESS_MODULES:
        logging.getLogger(lib).setLevel(logging.WARNING)

    if is_prod and not debug_mode:
        for mod in LoggingConfig.DEBUG_MODULES:
            try:
                logging.getLogger(mod).setLevel(logging.DEBUG)
            except Exception:
                pass

    try:
        log_dir = LoggingConfig.get_log_dir()
        now = datetime.now().timestamp()
        retention_seconds = LoggingConfig.RETENTION_DAYS * 86400
        for f in log_dir.glob("app_*.log"):
            try:
                if f.stat().st_mtime < now - retention_seconds:
                    f.unlink()
            except Exception:
                pass
    except Exception:
        pass

    def excepthook(exc_type, exc_value, exc_tb):
        error_msg = f"Uncaught exception: {exc_type.__name__}: {exc_value}"
        root_logger.error(error_msg, exc_info=(exc_type, exc_value, exc_tb))
        try:
            app = QApplication.instance()
            if app and not app.closingDown():
                msg = QMessageBox()
                msg.setWindowFlags(
                    Qt.WindowType.Dialog |
                    Qt.WindowType.WindowStaysOnTopHint |
                    Qt.WindowType.FramelessWindowHint
                )
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setWindowTitle("Application Error")
                msg.setText(
                    f"An unexpected error occurred:\n\n"
                    f"{exc_type.__name__}: {exc_value}\n\n"
                    "The error has been logged. Please restart the application."
                )
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                screen = app.primaryScreen()
                if screen:
                    geom = screen.availableGeometry()
                    msg.move(
                        geom.center().x() - msg.width() // 2,
                        geom.center().y() - msg.height() // 2
                    )
                msg.exec()
        except Exception:
            if sys.stderr:
                sys.stderr.write(f"FATAL: {error_msg}\n")

    sys.excepthook = excepthook

    logger = logging.getLogger(__name__)
    logger.info("=" * 70)
    logger.info("APPLICATION STARTING")
    logger.info(f"   Mode: {'PRODUCTION' if is_prod else 'DEVELOPMENT'}")
    logger.info(f"   Debug: {'ON' if debug_mode else 'OFF'}")
    logger.info(f"   Log directory: {LoggingConfig.get_log_dir()}")
    logger.info(f"   Log file: {log_file}")

    # Log the update checker configuration so support can confirm what URL the client will query. The actual check runs after login.
    try:
        from core.update_checker import UPDATE_MANIFEST_URL
        logger.info(f"   Update manifest: {UPDATE_MANIFEST_URL}")
    except Exception:
        logger.info("   Update manifest: (not configured)")
    try:
        from core.log_uploader import LOG_UPLOAD_URL
        logger.info(f"   Log upload URL: {LOG_UPLOAD_URL}")
    except Exception:
        logger.info("   Log upload URL: (not configured)")

    logger.info("=" * 70)

    return root_logger


# APPLICATION LOADER

class ApplicationLoader:
    def __init__(self, app: QApplication, splash: SplashScreen,
                 perf_monitor=None):
        self.app = app
        self.splash = splash
        self.perf_monitor = perf_monitor
        self.main_window: Optional[MainApp] = None
        self.logger = logging.getLogger(__name__)

        self.stages = [
            ("init", "Initializing core services...", 5),
            ("theme", "Loading theme manager...", 10),
            ("database", "Connecting to database...", 20),
            ("api", "Setting up API client...", 30),
            ("auth", "Initializing authentication...", 40),
            ("icons", "Loading icon assets...", 50),
            ("ui_components", "Building UI components...", 60),
            ("pages", "Loading pages...", 75),
            ("widgets", "Building widgets...", 85),
            ("app", "Creating main window...", 95),
            ("ready", "Ready!", 100),
        ]

        self.current_stage = 0
        self._is_loading = False
        self._has_error = False
        self._is_finished = False

    def start_loading(self):
        if self._is_loading:
            return
        self._is_loading = True
        self.logger.info("Starting application loading sequence...")
        QTimer.singleShot(50, self._load_next_stage)

    def _load_next_stage(self):
        if self.current_stage >= len(self.stages):
            self._finish_loading()
            return

        stage_id, description, progress = self.stages[self.current_stage]
        self.current_stage += 1

        self.splash.update_progress(progress, description)
        self.app.processEvents()

        try:
            self._execute_stage(stage_id)
        except Exception as e:
            self.logger.error(f"Error in stage '{stage_id}': {e}")
            self._has_error = True

        QTimer.singleShot(20, self._load_next_stage)

    def _execute_stage(self, stage_id: str):
        if stage_id == "init":
            import core.theme_manager
            import database.db_manager
            import core.api_client
            import core.auth_manager

        elif stage_id == "theme":
            from core.theme_manager import ThemeManager
            tm = ThemeManager()
            tm.apply_current_theme()
            self.logger.info(f"Theme applied: {tm.get_current_theme()}")

        elif stage_id == "database":
            from database.db_manager import DatabaseManager
            db = DatabaseManager()
            if hasattr(db, 'needs_initialization') and db.needs_initialization():
                db.create_default_permissions()
                db.create_default_users()

        elif stage_id == "api":
            from core.api_client import APIClient
            from core.env_manager import EnvironmentManager
            env = EnvironmentManager()
            APIClient(env.get_base_url())

        elif stage_id == "auth":
            from core.auth_manager import AuthManager  # noqa: F401
            from core.api_client import APIClient       # noqa: F401
            from database.db_manager import DatabaseManager  # noqa: F401

        elif stage_id == "icons":
            from core.icon_manager import IconManager
            manager = IconManager()
            try:
                manager.preload_icons()
            except Exception:
                pass

        elif stage_id == "ui_components":
            from widgets.components import (
                ShadcnButton, ShadcnInput, ShadcnCard,
                ShadcnDataTable, ShadcnToast
            )

        elif stage_id == "pages":
            import pages.login_page
            import pages.dashboard_page
            import pages.visitors_page
            import pages.employees_page
            import pages.access_logs_page
            import pages.settings_page

        elif stage_id == "widgets":
            import widgets.sidebar
            import widgets.header
            import widgets.floating_label_input

        elif stage_id == "app":
            # Pass the perf monitor through so MainApp can stop it cleanly when the window closes.
            self.main_window = MainApp(perf_monitor=self.perf_monitor)

        elif stage_id == "ready":
            pass

    def _finish_loading(self):
        if self._is_finished:
            return

        self._is_finished = True
        self.logger.info("Loading complete, showing main window...")

        if self._has_error:
            self.logger.warning(
                "Loading completed with errors - some features may be limited"
            )

        if self.main_window is None:
            self.logger.error("Main window was not created! Creating fallback...")
            try:
                self.main_window = MainApp(perf_monitor=self.perf_monitor)
            except Exception as e:
                self.logger.critical(f"Failed to create main window: {e}")
                QMessageBox.critical(
                    None,
                    "Application Error",
                    f"Failed to start application:\n\n{str(e)}\n\n"
                    "Please check the log file for details.",
                    QMessageBox.StandardButton.Ok
                )
                sys.exit(1)

        self.splash.update_progress(100, "Ready!")
        self.app.processEvents()

        QTimer.singleShot(50, self._transition_to_main)

    def _transition_to_main(self):
        try:
            if self.main_window:
                self.main_window.show()
                self.main_window.raise_()
                self.main_window.activateWindow()
                self.app.processEvents()

            if hasattr(self.splash, 'finish_with_animation'):
                self.splash.finish_with_animation(self.main_window)
            else:
                self.splash.close()
                self.splash.deleteLater()

            self.logger.info("Application started successfully")

        except Exception as e:
            self.logger.error(f"Error during splash transition: {e}")
            try:
                if self.main_window:
                    self.main_window.show()
                self.splash.close()
            except Exception:
                pass

        self._is_loading = False


# MAIN ENTRY POINT

def main():
    debug_mode = (
        "--debug" in sys.argv
        or os.environ.get("APP_DEBUG", "").lower() == "true"
    )

    logger = setup_logging(debug_mode=debug_mode)

    # Performance monitor — samples CPU / memory / threads / disk every 30s and writes a PERF line to the application log. Disabled automatically if psutil is not installed.
    
    perf_monitor = None
    try:
        from core.perf_monitor import PerfMonitor
        perf_monitor = PerfMonitor(interval_seconds=30)
        perf_monitor.start()
    except Exception as e:
        logger.warning(f"PerfMonitor not started: {e}")

    if "--watch-windows" in sys.argv:
        try:
            from utils.window_watcher import start_window_watcher
            start_window_watcher(
                logger,
                poll_seconds=0.25,
                duration_seconds=60.0,
            )
        except Exception as e:
            logger.error(f"Failed to start window watcher: {e}")

    try:
        try:
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        except AttributeError:
            try:
                QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
            except AttributeError:
                pass
            try:
                QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
            except AttributeError:
                pass

        app = QApplication(sys.argv)
        app.setApplicationName("Access Control System")
        app.setOrganizationName("ICTAuthority")

        try:
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                from PySide6.QtGui import QIcon
                app.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

        splash = SplashScreen()
        splash.show()
        app.processEvents()

        loader = ApplicationLoader(app, splash, perf_monitor=perf_monitor)
        loader.start_loading()

        exit_code = app.exec()

        # Stop the perf monitor if the app exits without the main window having run closeEvent (e.g. sys.exit() called).
        if perf_monitor is not None:
            try:
                perf_monitor.stop()
            except Exception:
                pass

        logger.info(f"Application exited with code: {exit_code}")
        sys.exit(exit_code)

    except KeyboardInterrupt:
        if perf_monitor is not None:
            try:
                perf_monitor.stop()
            except Exception:
                pass
        logger.info("Application terminated by user")
        sys.exit(0)
    except Exception as e:
        if perf_monitor is not None:
            try:
                perf_monitor.stop()
            except Exception:
                pass
        logger.critical(f"Fatal error in main: {e}", exc_info=True)
        try:
            QMessageBox.critical(
                None,
                "Fatal Error",
                f"Application failed to start:\n\n{str(e)}\n\n"
                "Please check the log file for details.",
                QMessageBox.StandardButton.Ok
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
