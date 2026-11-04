# pages/base_page.py
"""
Base page with a scrollable content area.

Changes in this revision
------------------------
- Uses tokens for the background, foreground, and scrollbar.
- Accessible name on the scroll area.
- Removed redundant viewport stylesheet (content_widget already paints
  the background).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QDialog, QApplication
)
from PySide6.QtCore import Qt, Signal

from core.theme_manager import ThemeManager
from widgets.components import ShadcnToast, ShadcnAlertDialog


class BasePage(QWidget):
    navigate_requested = Signal(str)
    show_notification = Signal(str, str)

    def __init__(self, user_info=None, permissions=None, page_id=""):
        super().__init__()
        self.user_info = user_info or {
            'full_name': 'User', 'role': 'staff', 'id': 1
        }
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
        self.scroll.setAccessibleName("Page content")

        self.content_widget = QWidget()
        self.content_widget.setObjectName("basePageContent")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(24, 24, 24, 24)
        self.content_layout.setSpacing(20)

        self.scroll.setWidget(self.content_widget)
        self._layout.addWidget(self.scroll)

        self.theme_manager.register_widget(
            self,
            on_theme_changed=self._on_theme_changed,
            on_appearance_changed=self._on_appearance_changed,
        )

        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        pass

    def layout(self):
        return self.content_layout

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def has_any_permission(self, permissions_list: list) -> bool:
        return any(p in self.permissions for p in permissions_list)

    def show_error(self, message: str, duration: int = 3000):
        ShadcnToast(message, description="", duration=duration,
                    parent=self, variant="destructive")
        self.show_notification.emit(message, "error")

    def show_success(self, message: str, duration: int = 3000):
        ShadcnToast(message, description="", duration=duration,
                    parent=self, variant="success")
        self.show_notification.emit(message, "success")

    def show_warning(self, message: str, duration: int = 3000):
        ShadcnToast(message, description="", duration=duration,
                    parent=self, variant="warning")
        self.show_notification.emit(message, "warning")

    def show_info(self, message: str, duration: int = 3000):
        ShadcnToast(message, description="", duration=duration,
                    parent=self, variant="info")
        self.show_notification.emit(message, "info")

    def confirm_action(self, title: str, message: str) -> bool:
        dialog = ShadcnAlertDialog(
            title, message, cancel_text="Cancel",
            action_text="Continue", parent=self
        )
        return dialog.exec() == QDialog.DialogCode.Accepted

    def alert(self, title: str, message: str):
        ShadcnToast(title, description=message, duration=3000, parent=self)

    def get_theme_tokens(self):
        return self.theme_manager.get_tokens()

    def refresh_styles(self):
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def apply_theme(self):
        tokens = self.theme_manager.get_tokens()
        bg = tokens.get('background', '#F8FAFC')
        fg = tokens.get('foreground', '#0F172A')

        self.content_widget.setStyleSheet(f"""
            #basePageContent {{
                background-color: {bg};
                color: {fg};
            }}
        """)

        sb_size = tokens.get("scrollbar_size", 10)
        sb_radius = tokens.get("scrollbar_radius", 5)
        sb_track = tokens.get("scrollbar_track",
                              tokens.get("muted", "#F1F5F9"))
        sb_handle = tokens.get("scrollbar_handle",
                               tokens.get("border-strong", "#94A3B8"))
        sb_handle_hover = tokens.get(
            "scrollbar_handle_hover",
            tokens.get("foreground-secondary", "#64748B"),
        )

        self.scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {bg}; border: none; }}
            QScrollBar:vertical {{
                background: {sb_track};
                width: {sb_size}px;
                border: none;
                border-radius: {sb_radius}px;
            }}
            QScrollBar::handle:vertical {{
                background: {sb_handle};
                border-radius: {sb_radius}px;
                min-height: 36px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {sb_handle_hover};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{ background: transparent; }}
            QScrollBar:horizontal {{
                background: {sb_track};
                height: {sb_size}px;
                border: none;
                border-radius: {sb_radius}px;
            }}
            QScrollBar::handle:horizontal {{
                background: {sb_handle};
                border-radius: {sb_radius}px;
                min-width: 36px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {sb_handle_hover};
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{ width: 0; }}
        """)

        self.refresh_styles()

    def _on_theme_changed(self, *_):
        self.apply_theme()

    def _on_appearance_changed(self, *_):
        self.apply_theme()

    def update_theme(self):
        self.apply_theme()

    def cleanup(self):
        pass

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_theme()
