# pages/base_page.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFrame
from PySide6.QtCore import Qt, Signal
from core.theme_manager import ThemeManager
from widgets.components import ShadcnToast, ShadcnAlertDialog

class BasePage(QWidget):
    navigate_requested = Signal(str)
    show_notification = Signal(str, str)

    def __init__(self, user_info=None, permissions=None, page_id=""):
        super().__init__()
        self.user_info = user_info or {'full_name': 'User', 'role': 'staff', 'id': 1}
        self.permissions = permissions or []
        self.page_id = page_id
        self.theme_manager = ThemeManager()

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Make scroll area viewport transparent to inherit main window background
        self.scroll.viewport().setStyleSheet("background-color: transparent;")

        self.content_widget = QWidget()
        self.content_widget.setObjectName("basePageContent")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(24, 24, 24, 24)
        self.content_layout.setSpacing(20)

        self.scroll.setWidget(self.content_widget)
        self._layout.addWidget(self.scroll)

        self.init_ui()

    def init_ui(self):
        pass

    def layout(self):
        return self.content_layout

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def has_any_permission(self, permissions_list: list) -> bool:
        return any(p in self.permissions for p in permissions_list)

    def show_error(self, message: str, duration: int = 3000):
        ShadcnToast(message, description="", duration=duration, parent=self)
        self.show_notification.emit(message, "error")

    def show_success(self, message: str, duration: int = 3000):
        ShadcnToast(message, description="", duration=duration, parent=self)
        self.show_notification.emit(message, "success")

    def show_warning(self, message: str, duration: int = 3000):
        ShadcnToast(message, description="", duration=duration, parent=self)
        self.show_notification.emit(message, "warning")

    def show_info(self, message: str, duration: int = 3000):
        ShadcnToast(message, description="", duration=duration, parent=self)
        self.show_notification.emit(message, "info")

    def confirm_action(self, title: str, message: str) -> bool:
        dialog = ShadcnAlertDialog(title, message, cancel_text="Cancel", action_text="Continue", parent=self)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def alert(self, title: str, message: str):
        ShadcnToast(title, description=message, duration=3000, parent=self)

    def get_theme_tokens(self):
        return self.theme_manager.get_tokens()

    def refresh_styles(self):
        self.style().unpolish(self)
        self.style().polish(self)
