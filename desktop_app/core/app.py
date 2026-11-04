# core/app.py
"""
Main application window and orchestration layer.

Update check is triggered once, quietly, after login succeeds.

Perf monitor
------------
MainApp accepts an optional PerfMonitor and stops it in closeEvent().
The monitor itself samples CPU / memory / threads / disk every 30s and
writes a PERF line to the application log. See core/perf_monitor.py.
"""
import logging
import time
from typing import Optional, Dict, List, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QApplication, QLabel
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QShortcut, QKeySequence

from config import Config

logger = logging.getLogger(__name__)


class MainApp(QMainWindow):
    logout_requested = Signal()
    connection_changed = Signal(bool)

    def __init__(self, perf_monitor=None):
        super().__init__()

        logger.info("MainApp: __init__ begin")

        self._is_closing = False
        self._is_logging_out = False
        self._ui_initialized = False
        self._is_shown = False
        self._is_transitioning = False

        # Owned by main.py; stopped in closeEvent.
        self._perf_monitor = perf_monitor

        self.current_user: Optional[Dict[str, Any]] = None
        self.permissions: List[str] = []
        self.main_central_widget: Optional[QWidget] = None
        self.pages: Dict[str, QWidget] = {}
        self.stack: Optional[QStackedWidget] = None
        self.sidebar = None
        self.header = None
        self.login_page: Optional[QWidget] = None
        self.sync_timer: Optional[QTimer] = None

        # Theme
        from core.theme_manager import ThemeManager
        self.theme_manager = ThemeManager()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self._on_theme_changed,
        )

        # Database + API + Auth
        from database.db_manager import DatabaseManager
        self.db = DatabaseManager()

        from core.api_client import APIClient
        from core.env_manager import EnvironmentManager
        self.env_manager = EnvironmentManager()
        self.api_client = APIClient(self.env_manager.get_base_url())
        self.env_manager.env_changed.connect(self._on_env_changed)

        from core.auth_manager import AuthManager
        self.auth_manager = AuthManager(self.api_client, self.db)

        # Services (lazy)
        self.sync_manager = None
        self.data_service = None

        # Root stack
        self.root_stack = QStackedWidget()
        self.root_stack.setObjectName("rootStack")
        self.setCentralWidget(self.root_stack)

        # Sizing
        self.setMinimumSize(Config.MIN_WIDTH, Config.MIN_HEIGHT)
        if Config.START_MAXIMIZED:
            self.setWindowState(Qt.WindowState.WindowMaximized)
        else:
            self.resize(Config.INITIAL_WIDTH, Config.INITIAL_HEIGHT)

        self._restore_window_geometry()

        # Login page
        self.show_login_page(show_window=False)

        # Global shortcuts
        self._register_global_shortcuts()

        logger.info("MainApp: __init__ end")

    # ==================================================================
    # GLOBAL SHORTCUTS
    # ==================================================================

    def _register_global_shortcuts(self):
        self._sc_toggle_theme = QShortcut(QKeySequence("Ctrl+Shift+T"), self)
        self._sc_toggle_theme.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_toggle_theme.activated.connect(self.toggle_theme)

        self._sc_focus_content = QShortcut(QKeySequence("Ctrl+Alt+M"), self)
        self._sc_focus_content.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_focus_content.activated.connect(self._focus_main_content)

        self._sc_refresh = QShortcut(QKeySequence("Ctrl+R"), self)
        self._sc_refresh.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_refresh.activated.connect(self._refresh_current_page)

    def _focus_main_content(self):
        if self.stack is None:
            return
        current = self.stack.currentWidget()
        if current is None:
            return
        target = current.focusWidget()
        if target is None:
            current.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _refresh_current_page(self):
        if self.stack is None:
            return
        current = self.stack.currentWidget()
        if current is None:
            return
        for method_name in ("refresh_data", "refresh_all", "refresh_table",
                            "refresh_logs", "refresh_users"):
            method = getattr(current, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception as e:
                    logger.error(f"MainApp: refresh via {method_name} failed: {e}")
                return

    # ==================================================================
    # WINDOW GEOMETRY
    # ==================================================================

    def _restore_window_geometry(self):
        from PySide6.QtCore import QSettings
        settings = QSettings("ICTAuthority", "AccessControl")
        geom = settings.value("window/geometry")
        state = settings.value("window/state")
        if geom is not None:
            try: self.restoreGeometry(geom)
            except Exception: pass
        if state is not None:
            try: self.restoreState(state)
            except Exception: pass

    def _save_window_geometry(self):
        from PySide6.QtCore import QSettings
        try:
            settings = QSettings("ICTAuthority", "AccessControl")
            settings.setValue("window/geometry", self.saveGeometry())
            settings.setValue("window/state", self.saveState())
            settings.sync()
        except Exception as e:
            logger.debug(f"MainApp: failed to save window geometry: {e}")

    # ==================================================================
    # SERVICE INITIALIZATION
    # ==================================================================

    def _lazy_init_services(self):
        if self._is_closing:
            return
        if self.sync_manager is None:
            logger.info("MainApp: initializing services...")
            try:
                from core.sync_manager import SyncManager
                from core.data_service import DataService

                _t = time.perf_counter()
                self.sync_manager = SyncManager(self.api_client, self.db)
                self.sync_manager.start()
                logger.info(f"INIT TIMING | SyncManager = "
                            f"{(time.perf_counter()-_t)*1000:.1f} ms")

                _t = time.perf_counter()
                self.data_service = DataService(
                    self.api_client, self.db, self.sync_manager
                )
                logger.info(f"INIT TIMING | DataService = "
                            f"{(time.perf_counter()-_t)*1000:.1f} ms")

                self.api_client.connection_changed.connect(
                    self._on_connection_changed
                )
                self._setup_auto_sync()
                logger.info("MainApp: services ready")
            except Exception as e:
                logger.error(f"MainApp: services failed: {e}")

    def _setup_auto_sync(self):
        if self._is_closing:
            return
        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self._auto_sync_check)
        self.sync_timer.start(Config.SYNC_INTERVAL_SECONDS * 1000)

    def _auto_sync_check(self):
        if self._is_closing or self._is_transitioning:
            return
        # Use the cached, non-blocking online check.
        if self.api_client.is_online_cached() and self.sync_manager:
            self.sync_manager.sync()

    def _on_connection_changed(self, online: bool):
        if self._is_closing or self._is_transitioning:
            return
        self.connection_changed.emit(online)
        if online and self.current_user:
            if self.sync_manager:
                self.sync_manager.sync()
            self._refresh_after_connection_change()
        elif not online:
            logger.debug("MainApp: app offline")

    def _refresh_after_connection_change(self):
        if self._is_closing or self._is_transitioning:
            return
        self._refresh_current_page()

    def _on_env_changed(self, new_url: str):
        if self._is_closing:
            return
        logger.info(f"MainApp: environment changed: {new_url}")
        self.api_client.set_base_url(new_url)
        if self.current_user and not self._is_transitioning:
            self._refresh_after_connection_change()

    def _show_toast(self, title, message, variant="default"):
        try:
            from widgets.components import ShadcnToast
            ShadcnToast(title, description=message,
                        variant=variant, parent=self)
        except Exception:
            logger.info(f"MainApp: toast suppressed '{title}': {message}")

    def _on_theme_changed(self, theme: str):
        if self._is_closing or self._is_transitioning:
            return
        if self.header and hasattr(self.header, "on_theme_changed"):
            self.header.on_theme_changed(theme)
        if self.sidebar and hasattr(self.sidebar, "on_theme_changed"):
            self.sidebar.on_theme_changed(theme)
        if self.stack:
            current = self.stack.currentWidget()
            if current and hasattr(current, "on_theme_changed"):
                try:
                    current.on_theme_changed(theme)
                except Exception:
                    pass

    # ==================================================================
    # LOGIN PAGE
    # ==================================================================

    def show_login_page(self, show_window: bool = True):
        logger.info("MainApp: show_login_page")

        if self._is_closing:
            return

        if self.login_page is not None:
            try:
                self.root_stack.removeWidget(self.login_page)
                self.login_page.setParent(None)
                self.login_page.deleteLater()
            except Exception:
                pass
            self.login_page = None

        from pages.login_page import LoginPage
        self.login_page = LoginPage(auth_manager=self.auth_manager)
        self.login_page.login_successful.connect(self.on_login_success)

        self.root_stack.insertWidget(0, self.login_page)
        self.root_stack.setCurrentIndex(0)
        self.setWindowTitle("Access Control - Login")

        if show_window and not self._is_shown:
            self.show()
            self.raise_()
            self.activateWindow()
            self._is_shown = True

    # ==================================================================
    # LOGIN SUCCESS
    # ==================================================================

    def on_login_success(self, user_info: Dict[str, Any]):
        _t_start = time.perf_counter()

        if self._is_closing or self._is_transitioning:
            return

        logger.info(
            f"MainApp: login success for "
            f"{user_info.get('username', 'unknown')}"
        )

        if self._ui_initialized and self.current_user:
            logger.warning("MainApp: UI already initialized, ignoring duplicate login")
            return

        self._is_transitioning = True

        try:
            from widgets.components import ShadcnToast
            ShadcnToast.suppress(True)
        except Exception:
            pass

        try:
            self.api_client.suspend_health_checks()
        except Exception:
            pass

        try:
            if self.auth_manager:
                self.permissions = (
                    list(self.auth_manager.permissions)
                    if self.auth_manager.permissions else []
                )
            else:
                self.permissions = ['view_dashboard']

            user_info.setdefault('id', user_info.get('username', 'User'))
            user_info.setdefault('full_name', user_info.get('username', 'User'))
            user_info.setdefault('email', '')
            user_info.setdefault('permissions', self.permissions)
            self.current_user = user_info

            _t = time.perf_counter()
            self._lazy_init_services()
            logger.info(f"LOGIN TIMING | _lazy_init_services = "
                        f"{(time.perf_counter()-_t)*1000:.1f} ms")

            _t = time.perf_counter()
            self.build_main_ui(user_info)
            logger.info(f"LOGIN TIMING | build_main_ui = "
                        f"{(time.perf_counter()-_t)*1000:.1f} ms")

            if self.main_central_widget is None:
                logger.error("MainApp: no central widget")
                return

            _t = time.perf_counter()
            if self.root_stack.indexOf(self.main_central_widget) < 0:
                self.root_stack.addWidget(self.main_central_widget)
            logger.info(f"LOGIN TIMING | addWidget = "
                        f"{(time.perf_counter()-_t)*1000:.1f} ms")

            _t = time.perf_counter()
            self.root_stack.setCurrentWidget(self.main_central_widget)
            logger.info(f"LOGIN TIMING | setCurrentWidget = "
                        f"{(time.perf_counter()-_t)*1000:.1f} ms")

            self.setWindowTitle(
                f"Access Control System - {user_info['full_name']}"
            )

            old_login = self.login_page
            self.login_page = None
            if old_login is not None:
                QTimer.singleShot(400, lambda w=old_login: w.deleteLater())

            if self.isVisible():
                self.raise_()
                self.activateWindow()

            self._ui_initialized = True
            logger.info("MainApp: dashboard displayed")
            logger.info(f"LOGIN TIMING | total = "
                        f"{(time.perf_counter()-_t_start)*1000:.1f} ms")
        finally:
            QTimer.singleShot(0, self._end_transition)

    def _end_transition(self):
        logger.info("MainApp: _end_transition")

        try:
            user_info = self.current_user or {}
            user_id = (
                user_info.get("id")
                or user_info.get("_id")
                or user_info.get("username")
            )
            self.theme_manager.set_user(str(user_id) if user_id else None)
        except Exception as e:
            logger.warning(f"MainApp: set_user failed: {e}")

        self._is_transitioning = False

        # Resume health checks. With the api_client fix, this method also
        # re-emits connection_changed with the real online state, which
        # triggers DataService._on_connection_changed and updates its
        # snapshot automatically.
        try:
            self.api_client.resume_health_checks()
        except Exception:
            pass

        # NOTE: Do NOT call refresh_online_snapshot() here — that method
        # performs a blocking network probe (api.is_online()) on the GUI
        # thread. The resume_health_checks() call above already triggers
        # a background re-emit of the real online state, and DataService
        # listens for connection_changed, so its snapshot updates itself.

        try:
            from widgets.components import ShadcnToast
            ShadcnToast.suppress(False)
        except Exception:
            pass

        if self.sidebar is not None and self.permissions:
            QTimer.singleShot(50, self._populate_sidebar)

        # Automatic update check — deferred, non-blocking, one-shot.
        QTimer.singleShot(2500, self._maybe_check_for_updates)

    def _maybe_check_for_updates(self):
        """Silently check for updates and prompt if a newer version exists."""
        if self._is_closing or not self._ui_initialized:
            return
        try:
            from core.update_checker import UpdateChecker
            checker = UpdateChecker()
            if not checker.should_auto_check_now():
                return

            info = checker.check_now()
            if not info:
                return

            from dialogs.update_dialog import UpdateDialog
            dlg = UpdateDialog(info, parent=self)
            dlg.exec()
        except Exception as e:
            # Never crash the app because of an update check.
            logger.warning(f"Update check failed: {e}")

    def _populate_sidebar(self):
        if self._is_closing:
            return
        try:
            if self.sidebar is not None:
                logger.info(f"MainApp: populating sidebar with "
                            f"{len(self.permissions)} permissions")
                self.sidebar.refresh_permissions(self.permissions)
        except Exception as e:
            logger.error(f"MainApp: sidebar populate failed: {e}")

    # ==================================================================
    # MAIN UI CONSTRUCTION
    # ==================================================================

    def build_main_ui(self, user_info):
        logger.info("MainApp: build_main_ui")

        if self._is_closing or self._ui_initialized:
            return

        from widgets.sidebar import Sidebar
        from widgets.header import Header

        central = QWidget()
        central.setObjectName("mainCentralWidget")
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = Sidebar([], user_info, self.theme_manager)
        self.sidebar.navigation_requested.connect(self.navigate)
        self.sidebar.toggled.connect(self._on_sidebar_toggled)
        main_layout.addWidget(self.sidebar)

        right = QWidget()
        right.setObjectName("mainRightPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.header = Header(
            user_info,
            self.theme_manager,
            sidebar_expanded=True,
            data_service=self.data_service,
        )
        self.header.menu_toggled.connect(self.sidebar.toggle_collapse)
        self.header.logout_requested.connect(self.logout)
        self.header.search_requested.connect(self.global_search)
        right_layout.addWidget(self.header)

        self.stack = QStackedWidget()
        self.stack.setObjectName("mainStack")
        self.pages = {}

        self._load_pages()

        right_layout.addWidget(self.stack)
        main_layout.addWidget(right, 1)

        self.main_central_widget = central
        logger.info("MainApp: build_main_ui done")

    def _load_pages(self):
        from pages.dashboard_page import DashboardPage
        from pages.visitors_page import VisitorsPage
        from pages.employees_page import EmployeesPage
        from pages.access_logs_page import AccessLogsPage
        from pages.field_config_page import FieldConfigPage
        from pages.report_page import ReportPage
        from pages.settings_page import SettingsPage

        logger.info(f"MainApp: loading pages with permissions: {self.permissions}")

        if 'view_dashboard' in self.permissions or not self.permissions:
            page = DashboardPage(self.current_user, self.permissions,
                                 self.data_service)
            if hasattr(page, 'navigate_requested'):
                page.navigate_requested.connect(self.navigate)
            self.pages['dashboard'] = page
            self.stack.addWidget(page)

        if self._has_permission(('manage_visitors', 'view_visitors')):
            page = VisitorsPage(self.current_user, self.permissions,
                                self.data_service)
            if hasattr(page, 'navigate_requested'):
                page.navigate_requested.connect(self.navigate)
            self.pages['visitors'] = page
            self.stack.addWidget(page)

        if self._has_permission(('manage_employees', 'view_employees')):
            page = EmployeesPage(self.current_user, self.permissions,
                                 self.data_service)
            if hasattr(page, 'navigate_requested'):
                page.navigate_requested.connect(self.navigate)
            self.pages['employees'] = page
            self.stack.addWidget(page)

        if 'view_access_logs' in self.permissions:
            page = AccessLogsPage(self.current_user, self.permissions,
                                  self.data_service)
            self.pages['access_logs'] = page
            self.stack.addWidget(page)

        if 'configure_fields' in self.permissions:
            page = FieldConfigPage(self.current_user, self.permissions,
                                   self.data_service)
            self.pages['field_config'] = page
            self.stack.addWidget(page)

        if 'view_reports' in self.permissions:
            page = ReportPage(self.current_user, self.permissions,
                              self.data_service)
            self.pages['reports'] = page
            self.stack.addWidget(page)

        if 'manage_settings' in self.permissions:
            page = SettingsPage(
                self.current_user,
                self.permissions,
                self.data_service,
                env_manager=self.env_manager,
                api_client=self.api_client,
            )
            self.pages['settings'] = page
            self.stack.addWidget(page)

        if 'manage_users' in self.permissions:
            from pages.user_management_page import UserManagementPage
            page = UserManagementPage(self.current_user, self.permissions,
                                      self.data_service)
            if hasattr(page, 'navigate_requested'):
                page.navigate_requested.connect(self.navigate)
            self.pages['users'] = page
            self.stack.addWidget(page)

        if self.stack.count() == 0:
            logger.warning("MainApp: no pages loaded — showing fallback")
            fallback = QLabel(
                "No permissions assigned.\nPlease contact your administrator."
            )
            fallback.setAlignment(Qt.AlignCenter)
            self.stack.addWidget(fallback)

        if 'dashboard' in self.pages:
            self.navigate('dashboard')
        elif self.pages:
            self.navigate(list(self.pages.keys())[0])

    def _has_permission(self, perm):
        if isinstance(perm, tuple):
            return any(p in self.permissions for p in perm)
        return perm in self.permissions

    def navigate(self, page_name: str):
        if self._is_closing:
            return
        if page_name == 'logout':
            self.logout()
            return
        if page_name in self.pages:
            self.stack.setCurrentWidget(self.pages[page_name])
            if self.sidebar:
                self.sidebar.set_active(page_name)
            if self.header:
                self.header.set_title(page_name.replace('_', ' ').title())

    def toggle_theme(self):
        if self._is_closing:
            return
        self.theme_manager.toggle_theme()

    def _on_sidebar_toggled(self, expanded: bool):
        if self._is_closing:
            return
        if self.header:
            self.header.set_sidebar_expanded(expanded)

    def global_search(self, text: str):
        if self._is_closing:
            return
        if self.stack and self.stack.currentWidget():
            if hasattr(self.stack.currentWidget(), 'filter_table'):
                self.stack.currentWidget().filter_table(text)

    # ==================================================================
    # LOGOUT
    # ==================================================================

    def logout(self):
        logger.info("MainApp: logout")
        if self._is_closing or self._is_logging_out:
            return
        self._is_logging_out = True
        self._is_transitioning = True

        try:
            from widgets.components import ShadcnToast
            ShadcnToast.suppress(True)
        except Exception:
            pass
        try:
            self.api_client.suspend_health_checks()
        except Exception:
            pass

        try:
            if self.auth_manager:
                try: self.auth_manager.logout()
                except Exception: pass
            if self.sync_manager:
                try: self.sync_manager.sync_now()
                except Exception: pass

            self.current_user = None
            self.permissions = []
            self._ui_initialized = False

            for name, page in list(self.pages.items()):
                if hasattr(page, 'cleanup'):
                    try: page.cleanup()
                    except Exception: pass
                page.setParent(None)
                page.deleteLater()
            self.pages.clear()

            if self.stack:
                self.stack.setParent(None)
                self.stack.deleteLater()
                self.stack = None

            if self.main_central_widget is not None:
                try:
                    self.root_stack.removeWidget(self.main_central_widget)
                except Exception:
                    pass
                self.main_central_widget.setParent(None)
                self.main_central_widget.deleteLater()
                self.main_central_widget = None

            self.show_login_page(show_window=False)

            try:
                self.theme_manager.set_user(None)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"MainApp: logout error: {e}")

        self._is_logging_out = False
        QTimer.singleShot(0, self._end_transition)

    # ==================================================================
    # MISC
    # ==================================================================

    def center_window(self):
        screen = QApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            self.move(geometry.center() - self.rect().center())

    def closeEvent(self, event):
        if self._is_closing:
            event.accept()
            return
        self._is_closing = True
        logger.info("MainApp: closing")

        self._save_window_geometry()

        # Stop the performance monitor first so no PERF line is written
        # while we are tearing down. Failure here is non-fatal.
        if self._perf_monitor is not None:
            try:
                self._perf_monitor.stop()
            except Exception as e:
                logger.debug(f"PerfMonitor stop failed: {e}")
            self._perf_monitor = None

        if self.sync_timer:
            try: self.sync_timer.stop()
            except Exception: pass
            self.sync_timer = None
        if self.sync_manager:
            try: self.sync_manager.stop()
            except Exception: pass
            self.sync_manager = None
        if self.api_client:
            try: self.api_client.shutdown()
            except Exception: pass
            self.api_client = None
        if self.db:
            try: self.db.close()
            except Exception: pass
            self.db = None

        self.pages.clear()
        self.stack = None
        self.main_central_widget = None
        event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self._is_shown = True
