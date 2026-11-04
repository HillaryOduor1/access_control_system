# pages/profile_dialog.py
"""
Enterprise profile dialog with full theme awareness.

Changes in this revision
------------------------
- Registers with ThemeManager and applies tokens throughout.
- Accessible names on every input and on the avatar.
- Uses ShadcnButton and ShadcnInput.
"""
import re
import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QWidget,
)
from PySide6.QtCore import Qt, Signal, QTimer

from widgets.components import (
    ShadcnInput, ShadcnButton, ShadcnToast, ShadcnAvatar, ShadcnCaption,
)
from core.icon_manager import IconManager
from core.theme_manager import ThemeManager

logger = logging.getLogger(__name__)


class ProfileDialog(QDialog):
    """Enterprise profile dialog with theme awareness."""

    profile_updated = Signal(dict)

    def __init__(self, user_info: dict, data_service, parent=None):
        super().__init__(parent)
        self.user_info = user_info.copy()
        self.data_service = data_service
        self._is_saving = False
        self._original_data = user_info.copy()
        self.icon_manager = IconManager()
        self.theme_manager = ThemeManager()

        self.setWindowTitle("Profile Settings")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setAccessibleName("Profile settings")

        self.init_ui()

        self.theme_manager.register_widget(
            self,
            on_theme_changed=self._apply_styles,
        )
        self._apply_styles()

        if parent:
            parent_geo = parent.geometry()
            self.move(
                parent_geo.center().x() - self.width() // 2,
                parent_geo.center().y() - self.height() // 2,
            )

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(28, 24, 28, 24)

        # Header with avatar
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)

        full_name = self.user_info.get('full_name', 'User')
        self.avatar = ShadcnAvatar(fallback_text=full_name, size=56)
        header_layout.addWidget(self.avatar)

        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)

        self.name_label = QLabel(full_name)
        self.name_label.setStyleSheet("background: transparent; border: none;")
        info_layout.addWidget(self.name_label)

        role = self.user_info.get('role', 'Staff')
        self.role_label = QLabel(role.title())
        self.role_label.setStyleSheet("background: transparent; border: none;")
        info_layout.addWidget(self.role_label)

        header_layout.addWidget(info_widget)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Separator
        from widgets.components import ShadcnSeparator
        layout.addWidget(ShadcnSeparator())

        # Form
        form_layout = QFormLayout()
        form_layout.setSpacing(14)
        form_layout.setLabelAlignment(Qt.AlignRight)

        # Username (read-only)
        self.username_label = QLabel("Username")
        self.username_value = QLabel(self.user_info.get('username', ''))
        self.username_value.setAccessibleName(
            f"Username: {self.user_info.get('username', '')}"
        )
        form_layout.addRow(self.username_label, self.username_value)

        # Full Name
        self.full_name_input = ShadcnInput("Enter your full name")
        self.full_name_input.setAccessibleName("Full name")
        self.full_name_input.setText(self.user_info.get('full_name', ''))
        form_layout.addRow("Full Name:", self.full_name_input)

        # Email
        self.email_input = ShadcnInput("Enter your email")
        self.email_input.setAccessibleName("Email")
        self.email_input.setText(self.user_info.get('email', ''))
        form_layout.addRow("Email:", self.email_input)

        # Department
        self.department_input = ShadcnInput("Enter your department")
        self.department_input.setAccessibleName("Department")
        self.department_input.setText(self.user_info.get('department', ''))
        form_layout.addRow("Department:", self.department_input)

        # Phone
        self.phone_input = ShadcnInput("Enter your phone number")
        self.phone_input.setAccessibleName("Phone number")
        self.phone_input.setText(self.user_info.get('phone', ''))
        form_layout.addRow("Phone:", self.phone_input)

        layout.addLayout(form_layout)
        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        cancel_btn = ShadcnButton("Cancel", variant="outline", size="sm")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.save_btn = ShadcnButton("Save Changes", variant="default",
                                     size="sm")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save_profile)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

        QTimer.singleShot(0, self.full_name_input.setFocus)

    def _apply_styles(self, *_):
        tokens = self.theme_manager.get_tokens()

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {tokens['surface']};
                color: {tokens['foreground']};
            }}
            QLabel {{
                color: {tokens['foreground']};
                background: transparent;
            }}
        """)

        self.name_label.setStyleSheet(
            f"font-size: {tokens['font.h4']}px; font-weight: 600; "
            f"color: {tokens['foreground']}; "
            "background: transparent; border: none;"
        )
        self.role_label.setStyleSheet(
            f"font-size: {tokens['font.small']}px; "
            f"color: {tokens['muted-foreground']}; "
            "background: transparent; border: none;"
        )
        self.username_label.setStyleSheet(
            f"font-size: {tokens['font.small']}px; font-weight: 500; "
            f"color: {tokens['foreground']}; background: transparent;"
        )
        self.username_value.setStyleSheet(
            f"padding: 8px 12px; background: {tokens['muted']}; "
            f"border-radius: {tokens['radius']}; "
            f"color: {tokens['muted-foreground']};"
        )

    def validate_email(self, email: str) -> bool:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email.strip()))

    def save_profile(self):
        if self._is_saving:
            return

        full_name = self.full_name_input.text().strip()
        email = self.email_input.text().strip()
        department = self.department_input.text().strip()
        phone = self.phone_input.text().strip()

        if not full_name:
            ShadcnToast("Error", description="Full name is required",
                        parent=self, variant="destructive")
            return
        if not email:
            ShadcnToast("Error", description="Email is required",
                        parent=self, variant="destructive")
            return
        if not self.validate_email(email):
            ShadcnToast("Error",
                        description="Please enter a valid email address",
                        parent=self, variant="destructive")
            return

        self._is_saving = True
        self.save_btn.set_loading(True, "Saving…")

        try:
            if (full_name == self._original_data.get('full_name', '')
                    and email == self._original_data.get('email', '')
                    and department == self._original_data.get('department', '')
                    and phone == self._original_data.get('phone', '')):
                ShadcnToast("Info", description="No changes to save",
                            parent=self)
                self._is_saving = False
                self.save_btn.set_loading(False)
                return

            success, msg = self.data_service.update_profile(
                self.user_info.get('id'),
                full_name,
                email,
                department=department,
                phone=phone,
            )

            if success:
                self.user_info['full_name'] = full_name
                self.user_info['email'] = email
                self.user_info['department'] = department
                self.user_info['phone'] = phone

                ShadcnToast("Profile",
                            description="Profile updated successfully!",
                            parent=self, variant="success")
                self.profile_updated.emit(self.user_info)
                QTimer.singleShot(500, self.accept)
            else:
                ShadcnToast("Error", description=msg,
                            parent=self, variant="destructive")
                self._is_saving = False
                self.save_btn.set_loading(False)

        except Exception as e:
            logger.error(f"Profile update error: {e}")
            ShadcnToast("Error",
                        description=f"Failed to update profile: {e}",
                        parent=self, variant="destructive")
            self._is_saving = False
            self.save_btn.set_loading(False)

    def get_updated_info(self) -> dict:
        return self.user_info.copy()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.save_profile()
            event.accept()
            return
        super().keyPressEvent(event)
