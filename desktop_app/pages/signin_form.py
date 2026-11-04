# pages/signin_form.py
"""
Enterprise signin form with enhanced security features.

Changes in this revision
------------------------
- Removed the inline setStyleSheet() call that appended to the button's
  QSS. That append broke ShadcnButton's `_last_qss` cache: the appended
  rules were not reflected in the cache, so the next update_theme() call
  silently dropped them. Border radius and font weight are now set in
  ShadcnButton itself for `size="lg"`.
- `opacity: 0.6` in the disabled rule was a no-op (Qt QSS does not
  support `opacity`); it is replaced with muted colors.
- Accessible names are set on every input and the error label.
- A caps-lock indicator is shown when the password field has focus and
  Caps Lock is on.

Fix in this revision
--------------------
- `Qt.KeyboardModifier.CapsLock` does not exist in Qt. Qt exposes no
  Caps Lock modifier; Caps Lock is a toggle, not a modifier. Accessing
  that attribute raised `AttributeError: capslock` on every keypress in
  the password field, aborting the whole app. Replaced with a Windows
  API call to `GetKeyState(VK_CAPITAL)`.
"""
import ctypes
import time
from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, QTimer, QSettings, QEvent
from PySide6.QtGui import QIcon, QKeyEvent

from widgets.components import ShadcnButton, ShadcnToast, ShadcnCheckBox
from widgets.floating_label_input import FloatingLabelInput
from core.icon_manager import IconManager

import logging
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Caps Lock detection
#
# Qt has no Caps Lock modifier, so we ask Windows directly.
# VK_CAPITAL = 0x14. The low bit of GetKeyState() is 1 when the toggle
# is on. Falls back to False on non-Windows.
# ---------------------------------------------------------------------------
def _is_caps_lock_on() -> bool:
    try:
        return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
    except Exception:
        return False


class SignInForm(QWidget):
    """Enterprise signin form with enhanced security features."""

    login_successful = Signal(dict)
    switch_to_signup = Signal()
    login_requested = Signal(str, str, bool)   # username, password, remember
    reset_password_requested = Signal()

    MAX_ATTEMPTS = 5
    LOCKOUT_DURATION = 300  # 5 minutes

    def __init__(self, auth_manager, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager
        self.icon_manager = IconManager()
        self._settings = QSettings("ICTAuthority", "AccessControl")
        self._is_logging_in = False
        self._failed_attempts = 0
        self._lockout_until: Optional[float] = None

        self.init_ui()
        self._load_remembered_user()
        self._setup_security_events()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(18)
        layout.setContentsMargins(48, 48, 48, 36)

        # Header
        header = QVBoxLayout()
        header.setSpacing(6)
        title = QLabel("Sign in")
        title.setAlignment(Qt.AlignCenter)
        title.setProperty("textRole", "title")
        title.setStyleSheet("background: transparent; border: none;")
        subtitle = QLabel("Welcome back! Enter your details to continue.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setProperty("textRole", "subtitle")
        subtitle.setStyleSheet("background: transparent; border: none;")
        header.addWidget(title)
        header.addWidget(subtitle)
        layout.addLayout(header)
        layout.addSpacing(8)

        # Username
        self.login_username = FloatingLabelInput(
            "Username or email", icon_name="user"
        )
        self.login_username.input.setAccessibleName("Username or email")
        layout.addWidget(self.login_username)

        # Password
        self.login_password = FloatingLabelInput(
            "Password", icon_name="lock", password=True
        )
        self.login_password.input.setAccessibleName("Password")
        self.login_password.input.installEventFilter(self)
        layout.addWidget(self.login_password)

        # Caps lock indicator (hidden by default)
        self.caps_lock_label = QLabel("Caps Lock is on")
        self.caps_lock_label.setAlignment(Qt.AlignLeft)
        self.caps_lock_label.setStyleSheet(
            "color: #F59E0B; font-size: 11px; background: transparent;"
        )
        self.caps_lock_label.hide()
        layout.addWidget(self.caps_lock_label)

        # Remember me / forgot password
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(2, 0, 2, 0)

        self.remember_checkbox = ShadcnCheckBox("Remember me")
        self.remember_checkbox.setChecked(False)
        self.remember_checkbox.setToolTip(
            "Keep me signed in on this device. You can sign out at any time."
        )
        self.remember_checkbox.setAccessibleName("Remember me")
        row_layout.addWidget(self.remember_checkbox)

        row_layout.addStretch()

        self.forgot_btn = ShadcnButton(
            "Forgot password?", variant="link", size="sm"
        )
        self.forgot_btn.clicked.connect(self.reset_password_requested.emit)
        row_layout.addWidget(self.forgot_btn)

        layout.addLayout(row_layout)
        layout.addSpacing(4)

        # Login button — no inline QSS append.
        self.login_btn = ShadcnButton("Sign in", variant="default", size="lg")
        self.login_btn.setMinimumHeight(50)
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.clicked.connect(self.animate_login)
        layout.addWidget(self.login_btn)
        layout.addStretch()

        # Error label
        self.error_label = QLabel()
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #EF4444; font-size: 13px;")
        self.error_label.setAccessibleName("Sign in error")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        # Sign up toggle
        self.signup_toggle = ShadcnButton(
            "Don't have an account? Sign up", variant="link", size="sm"
        )
        self.signup_toggle.clicked.connect(self.switch_to_signup.emit)
        layout.addWidget(self.signup_toggle, alignment=Qt.AlignCenter)

    def _setup_security_events(self):
        self._clear_timer = QTimer()
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self._clear_password)
        self.installEventFilter(self)

    def _load_remembered_user(self):
        remembered = self._settings.value("remembered_username", "")
        remember_enabled = self._settings.value(
            "remember_me_enabled", False, type=bool
        )

        if remember_enabled and remembered:
            self.login_username.setText(remembered)
            self.remember_checkbox.setChecked(True)
            self.login_password.setFocus()

    def _save_remembered_user(self, username: str, remember: bool):
        if remember and username:
            self._settings.setValue("remembered_username", username)
            self._settings.setValue("remember_me_enabled", True)
        else:
            self._settings.setValue("remembered_username", "")
            self._settings.setValue("remember_me_enabled", False)

    def _check_lockout(self) -> bool:
        if self._lockout_until and time.time() < self._lockout_until:
            remaining = int(self._lockout_until - time.time())
            self._show_error(
                f"Account locked. Please wait {remaining} seconds."
            )
            return True
        elif self._lockout_until:
            self._lockout_until = None
            self._failed_attempts = 0
        return False

    def validate_signin(self) -> bool:
        valid = True
        username = self.login_username.text().strip()
        password = self.login_password.text().strip()

        if self._check_lockout():
            return False

        if not username:
            self.login_username.set_valid(False, "Username or email is required")
            valid = False
        else:
            self.login_username.set_valid(True)

        if not password:
            self.login_password.set_valid(False, "Password is required")
            valid = False
        else:
            self.login_password.set_valid(True)

        if not valid:
            self._hide_error()

        return valid

    def animate_login(self):
        if self._is_logging_in:
            return

        self._hide_error()

        if self._check_lockout():
            return

        if not self.validate_signin():
            return

        self.set_login_state(True, "Signing in…")

        username = self.login_username.text().strip()
        password = self.login_password.text().strip()
        remember = self.remember_checkbox.isChecked()

        self.login_password.clear()

        self.login_requested.emit(username, password, remember)

    def on_login_success(self, user_info: dict, remember_me: bool = False):
        username = self.login_username.text().strip()
        self._save_remembered_user(username, remember_me)
        self._failed_attempts = 0
        self._lockout_until = None
        self.set_login_state(False)
        self.login_successful.emit(user_info)

    def on_login_failed(self, message: Optional[str] = None):
        self._failed_attempts += 1

        if self._failed_attempts >= self.MAX_ATTEMPTS:
            self._lockout_until = time.time() + self.LOCKOUT_DURATION
            self._show_error(
                f"Account temporarily locked. Please wait "
                f"{self.LOCKOUT_DURATION // 60} minutes."
            )
            self.set_login_state(False)
            self.login_btn.setEnabled(False)
            QTimer.singleShot(
                self.LOCKOUT_DURATION * 1000, self._re_enable_login
            )
        else:
            remaining = self.MAX_ATTEMPTS - self._failed_attempts
            msg = message or "Invalid username or password."
            self._show_error(f"{msg} {remaining} attempts remaining.")
            self.set_login_state(False)

        self.login_password.clear()
        self.login_password.input.setText("")

    def _re_enable_login(self):
        self._lockout_until = None
        self._failed_attempts = 0
        self.login_btn.setEnabled(True)
        self._hide_error()

    def set_login_state(self, loading: bool, text: Optional[str] = None):
        self._is_logging_in = loading

        if loading:
            self.login_btn.set_loading(True, text or "Signing in…")
            self.login_username.setEnabled(False)
            self.login_password.setEnabled(False)
            self.remember_checkbox.setEnabled(False)
            self.forgot_btn.setEnabled(False)
            self.signup_toggle.setEnabled(False)
        else:
            self.login_btn.set_loading(False)
            self.login_username.setEnabled(True)
            self.login_password.setEnabled(True)
            self.remember_checkbox.setEnabled(True)
            self.forgot_btn.setEnabled(True)
            self.signup_toggle.setEnabled(True)
            self.login_btn.setCursor(Qt.PointingHandCursor)

    def _show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()

    def _hide_error(self):
        self.error_label.hide()

    def _clear_password(self):
        if not self._is_logging_in:
            self.login_password.clear()
            self.login_password.input.setText("")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.WindowDeactivate:
            self._clear_timer.start(30000)
        elif event.type() == QEvent.WindowActivate:
            self._clear_timer.stop()

        # Caps-lock tracking on the password field.
        # Qt has no Caps Lock modifier; ask Windows directly.
        if obj is self.login_password.input:
            if event.type() == QEvent.KeyPress:
                self.caps_lock_label.setVisible(_is_caps_lock_on())
            elif event.type() == QEvent.FocusIn:
                # Reflect current state the moment the field gains focus.
                self.caps_lock_label.setVisible(_is_caps_lock_on())
            elif event.type() == QEvent.FocusOut:
                self.caps_lock_label.hide()

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not self._is_logging_in and not self._check_lockout():
                self.animate_login()
            event.accept()
            return
        if event.key() == Qt.Key_Escape:
            # Esc no longer closes the application. Clear the password.
            self.login_password.clear()
            self.login_password.input.setText("")
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.login_password.clear()
        self.login_password.input.setText("")
        super().closeEvent(event)
