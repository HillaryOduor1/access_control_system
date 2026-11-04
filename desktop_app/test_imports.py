"""
Bisection test: start from test_imports (which does NOT flicker), then
progressively add subsystems from the real app.

Flip ONE flag at a time, run, watch, report.

When the flicker appears, the last enabled flag is the cause.
"""
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer

# ----------------------------------------------------------------------
# FLAGS — flip ONE at a time, starting from all False
# ----------------------------------------------------------------------
ENABLE_APP_NAME = True          # app.setApplicationName + setOrganizationName
ENABLE_WINDOW_ICON = True       # app.setWindowIcon from icon.ico
ENABLE_LOGGING = True           # setup_logging + RotatingFileHandler
ENABLE_SPLASH = True            # show splash screen at startup
ENABLE_LOADER = True            # ApplicationLoader with 11 stages
ENABLE_MAIN_APP = False          # MainApp (the real one from core.app)
ENABLE_MAXIMIZED = True         # setWindowState(WindowMaximized)

# ----------------------------------------------------------------------
# Imports (always active — proven not to cause flicker)
# ----------------------------------------------------------------------
import core.theme_manager
import core.icon_manager
import core.api_client
import core.auth_manager
from config import Config
from core.theme_manager import ThemeManager
from database.db_manager import DatabaseManager
from core.api_client import APIClient
from core.auth_manager import AuthManager


class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test - Progressive Bisection")
        self.setGeometry(100, 100, 1200, 700)
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Test window"))
        self.setCentralWidget(w)


def main():
    app = QApplication(sys.argv)

    # ---- ENABLE_APP_NAME ----
    if ENABLE_APP_NAME:
        app.setApplicationName("ICT Authority Access Control")
        app.setOrganizationName("ICT Authority")

    # ---- ENABLE_LOGGING ----
    logger = None
    if ENABLE_LOGGING:
        from main import setup_logging
        logger = setup_logging(debug_mode=False)

    # ---- ENABLE_WINDOW_ICON ----
    if ENABLE_WINDOW_ICON:
        import os
        from utils.path_utils import resource_path
        from PySide6.QtGui import QIcon
        try:
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                app.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

    # ---- ENABLE_SPLASH + ENABLE_LOADER + ENABLE_MAIN_APP ----
    if ENABLE_MAIN_APP:
        # Full real pipeline
        from core.app import MainApp
        if ENABLE_SPLASH:
            from widgets.splash_screen import SplashScreen
            splash = SplashScreen()
            if logger:
                logger.info("Splash constructed")
        else:
            from widgets.splash_screen import SplashScreen
            splash = SplashScreen()  # constructed but never shown

        if ENABLE_LOADER:
            from main import ApplicationLoader
            loader = ApplicationLoader(app, splash)
            loader.start_loading()
        else:
            window = MainApp()
            window.show()

        sys.exit(app.exec())

    # ---- Simple window path ----
    window = TestWindow()
    if ENABLE_MAXIMIZED:
        window.setWindowState(Qt.WindowState.WindowMaximized)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()