from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QApplication, QLabel
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from widgets.sidebar import Sidebar
from widgets.header import Header
from core.theme_manager import ThemeManager
from pages.dashboard_page import DashboardPage
from pages.visitors_page import VisitorsPage
from pages.employees_page import EmployeesPage
from pages.access_logs_page import AccessLogsPage
from pages.field_config_page import FieldConfigPage
from pages.report_page import ReportPage
from pages.settings_page import SettingsPage
from database.db_manager import DatabaseManager
from config import Config
from widgets.components import (
    ShadcnButton, ShadcnInput, ShadcnDataTable,
    ShadcnCard, ShadcnAlert, ShadcnBadge
)
from core.api_client import APIClient
from core.auth_manager import AuthManager
from core.data_service import DataService
from core.sync_manager import SyncManager

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.theme_manager = ThemeManager()
        self.theme_manager.theme_changed.connect(self._on_theme_changed)
        self.db = DatabaseManager()
        self.api_client = APIClient()
        self.sync_manager = SyncManager(self.api_client, self.db)
        self.sync_manager.start()
        self.data_service = DataService(self.api_client, self.db, self.sync_manager)
        self.auth_manager = AuthManager(self.api_client, self.db)
        self.current_user = None
        self.permissions = []
        self.main_central_widget = None
        self.theme_manager.theme_changed.connect(self.apply_theme)
        self.show_login_page()

    def _on_theme_changed(self):
        self.apply_theme()
        for widget in self.findChildren(QWidget):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.update()

    def show_login_page(self):
        from pages.login_page import LoginPage
        self.login_page = LoginPage(auth_manager=self.auth_manager)
        self.login_page.login_successful.connect(self.on_login_success)
        self.setCentralWidget(self.login_page)
        self.setWindowTitle("ICT Authority Access Control - Login")
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)
        self.center_window()
        self.show()
        self.raise_()
        self.activateWindow()

    def on_login_success(self, user_info):
        print(f"[DEBUG] on_login_success: user_info received = {user_info}")
        if not user_info.get('id') and self.auth_manager.current_user:
            user_info['id'] = self.auth_manager.current_user.get('id')
        if not user_info.get('full_name'):
            user_info['full_name'] = user_info.get('username', 'User')
        if not user_info.get('email'):
            user_info['email'] = ''

        self.permissions = list(self.auth_manager.permissions)
        print(f"[DEBUG] on_login_success: self.permissions after reading from auth_manager = {self.permissions}")

        self.current_user = user_info
        self.build_main_ui(user_info)
        current_geometry = self.geometry()
        self.login_page.hide()
        self.setCentralWidget(self.main_central_widget)
        self.setGeometry(current_geometry)
        self.show()
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()
        self.setWindowOpacity(0.0)
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(400)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.fade_anim.start()
        QTimer.singleShot(500, lambda: self.setWindowOpacity(1.0))
        QTimer.singleShot(600, self.login_page.deleteLater)

    def build_main_ui(self, user_info):
        self.setWindowTitle(f"ICT Authority Access Control - {user_info['full_name']}")
        self.setMinimumSize(Config.MIN_WIDTH, Config.MIN_HEIGHT)
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        #self.sidebar = Sidebar(self.permissions, user_info, self.theme_manager)
        #self.sidebar.navigation_requested.connect(self.navigate)
        #main_layout.addWidget(self.sidebar)
        self.sidebar = Sidebar(self.permissions, user_info, self.theme_manager)
        self.sidebar.navigation_requested.connect(self.navigate)
        # Connect toggle signal to header
        self.sidebar.toggled.connect(self._on_sidebar_toggled)   # <-- add this
        main_layout.addWidget(self.sidebar)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        #self.header = Header(user_info, self.theme_manager)
        #self.header.menu_toggled.connect(self.sidebar.toggle_collapse)
        self.header = Header(user_info, self.theme_manager, sidebar_expanded=True)  # pass initial state
        self.header.menu_toggled.connect(self.sidebar.toggle_collapse)
        
        #self.header.theme_toggled.connect(self.toggle_theme)
        self.header.logout_requested.connect(self.logout)
        self.header.search_requested.connect(self.global_search)
        right_layout.addWidget(self.header)

        self.stack = QStackedWidget()
        self.pages = {}

        if 'view_dashboard' in self.permissions:
            self.pages['dashboard'] = DashboardPage(user_info, self.permissions, self.data_service)
            self.pages['dashboard'].navigate_requested.connect(self.navigate)
            self.stack.addWidget(self.pages['dashboard'])

        if 'manage_visitors' in self.permissions or 'view_visitors' in self.permissions:
            self.pages['visitors'] = VisitorsPage(user_info, self.permissions, self.data_service)
            self.pages['visitors'].navigate_requested.connect(self.navigate)
            self.stack.addWidget(self.pages['visitors'])

        if 'manage_employees' in self.permissions or 'view_employees' in self.permissions:
            self.pages['employees'] = EmployeesPage(user_info, self.permissions, self.data_service)
            self.pages['employees'].navigate_requested.connect(self.navigate)
            self.stack.addWidget(self.pages['employees'])

        if 'view_access_logs' in self.permissions:
            self.pages['access_logs'] = AccessLogsPage(user_info, self.permissions, self.data_service)
            self.stack.addWidget(self.pages['access_logs'])

        if 'configure_fields' in self.permissions:
            self.pages['field_config'] = FieldConfigPage(user_info, self.permissions, self.data_service)
            self.stack.addWidget(self.pages['field_config'])

        if 'view_reports' in self.permissions:
            self.pages['reports'] = ReportPage(user_info, self.permissions, self.data_service)
            self.stack.addWidget(self.pages['reports'])

        if 'manage_settings' in self.permissions:
            self.pages['settings'] = SettingsPage(user_info, self.permissions, self.data_service)
            self.stack.addWidget(self.pages['settings'])
        
        if 'manage_users' in self.permissions:
            from pages.user_management_page import UserManagementPage
            self.pages['users'] = UserManagementPage(user_info, self.permissions, self.data_service)
            self.pages['users'].navigate_requested.connect(self.navigate)
            self.stack.addWidget(self.pages['users'])

        if self.stack.count() == 0:
            fallback_widget = QWidget()
            fallback_layout = QVBoxLayout(fallback_widget)
            fallback_layout.setAlignment(Qt.AlignCenter)
            msg = QLabel("No permissions assigned. Please contact your administrator.")
            msg.setStyleSheet("font-size: 18px; color: #64748B; padding: 40px;")
            fallback_layout.addWidget(msg)
            self.stack.addWidget(fallback_widget)

        right_layout.addWidget(self.stack)
        main_layout.addWidget(right_panel, 1)
        self.apply_theme()
        self.navigate('dashboard')
        self.main_central_widget = central

    def navigate(self, page_name):
        if page_name == 'logout':
            self.logout()
            return
        if page_name == 'dashboard' and 'dashboard' not in self.pages:
            if self.stack.count() > 0:
                first_widget = self.stack.widget(0)
                for key, widget in self.pages.items():
                    if widget is first_widget:
                        page_name = key
                        break
                else:
                    self.stack.setCurrentIndex(0)
                    self.sidebar.set_active(list(self.pages.keys())[0] if self.pages else '')
                    return
        if page_name in self.pages:
            self.stack.setCurrentWidget(self.pages[page_name])
            self.sidebar.set_active(page_name)
            self.header.set_title(page_name.replace('_', ' ').title())

    def toggle_theme(self):
        self.theme_manager.toggle_theme()

    def _on_sidebar_toggled(self, expanded):
        self.header.set_sidebar_expanded(expanded)
    
    def apply_theme(self):
        stylesheet = self.theme_manager.get_stylesheet()
        self.setStyleSheet(stylesheet)
        # Refresh all widgets that have update_theme method
        for widget in self.findChildren(QWidget):
            if hasattr(widget, "update_theme"):
                try:
                    widget.update_theme()
                except Exception:
                    pass
        self.update()

    def global_search(self, text):
        if hasattr(self.stack.currentWidget(), 'filter_table'):
            self.stack.currentWidget().filter_table(text)

    def logout(self):
        self.current_user = None
        self.permissions = []
        if self.main_central_widget:
            self.main_central_widget.deleteLater()
            self.main_central_widget = None
        self.show_login_page()

    def center_window(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())
