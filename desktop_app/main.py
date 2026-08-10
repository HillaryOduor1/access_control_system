import sys
import os
import importlib
import logging
from datetime import datetime
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QThread, Signal, QObject
from core.app import MainApp
from widgets.splash_screen import SplashScreen
from database.db_manager import DatabaseManager
from utils.path_utils import resource_path

# LOGGING SETUP – writes logs to ./logs/ during development,or ~/.ictaccess/logs/ when frozen.

def setup_logging():
    # Determine log directory
    frozen = getattr(sys, 'frozen', False)
    if frozen:
        log_dir = os.path.join(os.path.expanduser("~"), ".ictaccess", "logs")
    else:
        log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"app_{datetime.now().strftime('%Y%m%d')}.log")

    # Build handlers – only add StreamHandler if stdout exists
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

    # Clean old logs (keep 7 days)
    try:
        now = datetime.now().timestamp()
        for f in os.listdir(log_dir):
            if f.startswith("app_") and f.endswith(".log"):
                file_path = os.path.join(log_dir, f)
                if os.path.getmtime(file_path) < now - (7 * 86400):
                    os.remove(file_path)
    except Exception:
        pass

    # Catch uncaught exceptions – logs to file and (if available) console
    def excepthook(exc_type, exc_value, exc_tb):
        logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = excepthook

    logging.info("=" * 60)
    logging.info("Application started")
    logging.info(f"Log directory: {log_dir}")
    logging.info("=" * 60)

# Worker for splash‑screen loading

class Worker(QObject):
    progress_updated = Signal(int, str)
    loading_finished = Signal(object)

    def __init__(self):
        super().__init__()
        self.modules = [
            ("database.db_manager", "Connecting to database...", 5),
            ("core.theme_manager", "Loading theme engine...", 15),
            ("core.icon_manager", "Loading icon assets...", 25),
            ("pages.login_page", "Loading login module...", 35),
            ("pages.dashboard_page", "Loading dashboard...", 45),
            ("pages.visitors_page", "Loading visitor management...", 55),
            ("pages.employees_page", "Loading employee management...", 65),
            ("pages.access_logs_page", "Loading access logs...", 70),
            ("pages.field_config_page", "Loading field config...", 75),
            ("pages.report_page", "Loading reports...", 80),
            ("pages.settings_page", "Loading settings...", 85),
            ("widgets.sidebar", "Building sidebar...", 90),
            ("widgets.header", "Building header...", 92),
            ("widgets.components", "Loading UI components...", 95),
            ("core.app", "Finalizing...", 98),
        ]
        self.db = None

    def run(self):
        self.db = DatabaseManager()
        for module, msg, progress in self.modules:
            self.progress_updated.emit(progress, msg)
            try:
                importlib.import_module(module)
            except ImportError as e:
                logging.warning(f"Module import failed: {module} - {e}")
            self.thread().msleep(30)

        self.progress_updated.emit(99, "Creating default users...")
        self.db.create_default_users()
        self.loading_finished.emit(None)

    def create_main_window(self):
        return MainApp()

# Loader thread

class LoaderThread(QThread):
    progress = Signal(int, str)
    finished = Signal(object)

    def __init__(self):
        super().__init__()
        self.worker = Worker()
        self.worker.moveToThread(self)
        self.worker.progress_updated.connect(self.progress)
        self.worker.loading_finished.connect(self.finished)
        self.started.connect(self.worker.run)

    def create_main_window(self):
        return self.worker.create_main_window()

# Main entry point

def main():
    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("ICT Authority Access Control")
    app.setOrganizationName("ICTAuthority")

    splash = SplashScreen()
    splash.show()
    app.processEvents()

    loader = LoaderThread()
    main_window = None

    def on_progress(percent, msg):
        splash.update_progress(percent, msg)
        app.processEvents()

    def on_finished():
        nonlocal main_window
        splash.update_progress(100, "Starting application...")
        main_window = loader.create_main_window()
        splash.finish(main_window)
        main_window.show()
        logging.info("Main window shown")

    loader.progress.connect(on_progress)
    loader.finished.connect(on_finished)
    loader.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
