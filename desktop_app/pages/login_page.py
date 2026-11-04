# pages/login_page.py
"""
Enterprise login page with background threading, accessibility,
and silent session restoration ("remember me").

Critical fix in this revision
-----------------------------
`_handle_login` used to connect `worker.success` to a `lambda`. Lambdas
have no thread affinity, so Qt delivered them with DirectConnection —
which meant the slot ran on the *worker* thread and touched GUI widgets
from there. That is undefined behaviour: sometimes it worked, sometimes
the app hung at "Signing in…". The success signal is now connected to a
proper @Slot method (which auto-queues to the GUI thread), and the
`remember_me` flag travels inside the emitted dict instead of through a
lambda.
"""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QStackedWidget, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThread, QObject, Slot, QTimer
from PySide6.QtGui import QPixmap, QKeyEvent

from pages.signin_form import SignInForm
from pages.signup_form import SignUpForm
from widgets.floating_label_input import FloatingLabelInput
from core.theme_manager import ThemeManager
from core.icon_manager import IconManager
from utils.path_utils import resource_path
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Workers
# ============================================================================

class LoginWorker(QObject):
    """Worker for login authentication in a background thread."""

    # Emits a single dict so all cross-thread data travels together.
    # Payload: {"user_info": {...}, "remember_me": bool}
    success = Signal(dict)
    error = Signal(str)
    finished = Signal()

    def __init__(self, username: str, password: str,
                 remember_me: bool, auth_manager):
        super().__init__()
        self.username = username
        self.password = password
        self.remember_me = remember_me
        self.auth_manager = auth_manager

    @Slot()
    def run(self):
        try:
            logger.debug(f"Login attempt for: {self.username}")
            result = self.auth_manager.login(
                self.username, self.password, remember_me=self.remember_me
            )
            if result:
                user_info = self.auth_manager.current_user
                if user_info:
                    if ('permissions' not in user_info
                            or not user_info['permissions']):
                        user_info['permissions'] = list(
                            self.auth_manager.permissions
                        )
                    logger.info(f"Login successful for: {self.username}")
                    self.success.emit({
                        "user_info": user_info,
                        "remember_me": self.remember_me,
                    })
                else:
                    self.error.emit("User information not found")
            else:
                self.error.emit("Invalid username or password")
        except Exception as e:
            logger.error(f"Login error: {e}")
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class SessionRestoreWorker(QObject):
    """Attempts to silently restore a session using a stored refresh token."""

    success = Signal(dict)
    finished = Signal()

    def __init__(self, auth_manager):
        super().__init__()
        self.auth_manager = auth_manager

    @Slot()
    def run(self):
        try:
            user_info = self.auth_manager.try_restore_session()
            if user_info:
                if not user_info.get("permissions"):
                    user_info["permissions"] = list(
                        self.auth_manager.permissions
                    )
                self.success.emit(user_info)
        except Exception as e:
            logger.error(f"Session restore error: {e}")
        finally:
            self.finished.emit()


# ============================================================================
# Login Page
# ============================================================================

class LoginPage(QWidget):
    """
    Enterprise login page with:
    - Background authentication
    - Silent session restoration ("remember me")
    - Theme-aware styling
    - DPI scaling
    - Keyboard shortcuts
    """

    login_successful = Signal(dict)
    _login_in_progress = False

    def __init__(self, auth_manager=None, parent=None):
        super().__init__(parent)

        if auth_manager is None:
            from core.api_client import APIClient
            from database.db_manager import DatabaseManager
            from core.auth_manager import AuthManager
            self.auth_manager = AuthManager(APIClient(), DatabaseManager())
        else:
            self.auth_manager = auth_manager

        self.theme_manager = ThemeManager()
        self.icon_manager = IconManager()
        self.mode = "signin"
        self._login_thread = None
        self._login_worker = None
        self._restore_thread = None
        self._restore_worker = None
        self._is_transitioning = False
        # Remember which remember_me the current login attempt used so the
        # success slot can save the setting without a lambda.
        self._pending_remember_me = False

        self.init_ui()
        self.show_signin()
        self.apply_theme()
        self.setFocusPolicy(Qt.StrongFocus)

        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.apply_theme,
        )

        QTimer.singleShot(0, self._attempt_session_restore)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # LEFT PANEL — Branding
        self.left_panel = QFrame()
        self.left_panel.setObjectName("leftPanel")

        self.bg_label = QLabel(self.left_panel)
        self.bg_label.setScaledContents(True)
        self.bg_label.setAccessibleName("")
        self.set_background_image()

        self.overlay = QFrame(self.left_panel)
        self.overlay.setObjectName("overlay")
        self.overlay.setStyleSheet("""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(0,0,0,0.88),
                stop:1 rgba(0,0,0,0.78)
            );
            border: none;
        """)

        self.left_text = QLabel(self.left_panel)
        self.left_text.setAlignment(Qt.AlignCenter)
        self.left_text.setWordWrap(True)
        self.left_text.setStyleSheet(
            "font-size: 42px; font-weight: 800; "
            "color: white; background: transparent; border: none;"
        )

        self.left_subtitle = QLabel(self.left_panel)
        self.left_subtitle.setAlignment(Qt.AlignCenter)
        self.left_subtitle.setStyleSheet(
            "font-size: 16px; font-weight: 400; "
            "color: rgba(255,255,255,0.85); "
            "background: transparent; border: none;"
        )
        self.left_subtitle.setText("Access Control System")

        self.version_label = QLabel(self.left_panel)
        self.version_label.setAlignment(Qt.AlignCenter)
        self.version_label.setStyleSheet(
            "font-size: 12px; color: rgba(255,255,255,0.4); "
            "background: transparent; border: none;"
        )
        self.version_label.setText("v2.0.0")

        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setAlignment(Qt.AlignCenter)
        left_layout.setSpacing(16)
        left_layout.addStretch()
        left_layout.addWidget(self.left_text, alignment=Qt.AlignCenter)
        left_layout.addWidget(self.left_subtitle, alignment=Qt.AlignCenter)
        left_layout.addWidget(self.version_label, alignment=Qt.AlignCenter)
        left_layout.addStretch()

        main_layout.addWidget(self.left_panel, 1)

        # RIGHT PANEL — Forms
        self.right_panel = QFrame()
        self.right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setAlignment(Qt.AlignCenter)
        right_layout.setContentsMargins(40, 40, 40, 40)

        self.form_container = QFrame(self.right_panel)
        self.form_container.setMinimumWidth(400)
        self.form_container.setMaximumWidth(480)
        self.form_container.setMinimumHeight(520)
        self.form_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )

        container_layout = QVBoxLayout(self.form_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.stack = QStackedWidget()

        self.signin_form = SignInForm(self.auth_manager)
        self.signin_form.login_requested.connect(self._handle_login)
        self.signin_form.switch_to_signup.connect(self.switch_to_signup)
        self.signin_form.reset_password_requested.connect(
            self._show_reset_password
        )

        self.signup_form = SignUpForm(self.auth_manager)
        self.signup_form.switch_to_signin.connect(self.switch_to_signin)

        self.stack.addWidget(self.signin_form)
        self.stack.addWidget(self.signup_form)

        container_layout.addWidget(self.stack)
        right_layout.addWidget(self.form_container, alignment=Qt.AlignCenter)

        main_layout.addWidget(self.right_panel, 1)

        self.left_text.setText("Welcome Back")

    # ------------------------------------------------------------------
    # Session restore
    # ------------------------------------------------------------------

    def _attempt_session_restore(self):
        if self._is_transitioning:
            return
        if not self.auth_manager.has_persisted_session():
            logger.debug("No persisted session — showing login form normally")
            return

        logger.info("Persisted session found — attempting silent restore")
        self.signin_form.set_login_state(True, "Restoring session…")

        self._restore_thread = QThread(self)
        self._restore_worker = SessionRestoreWorker(self.auth_manager)
        self._restore_worker.moveToThread(self._restore_thread)

        self._restore_thread.started.connect(self._restore_worker.run)
        # Both of these are bound methods on a QObject living in the GUI
        # thread, so Qt auto-queues them.
        self._restore_worker.success.connect(self._on_restore_success)
        self._restore_worker.finished.connect(self._on_restore_finished)
        self._restore_worker.finished.connect(self._restore_thread.quit)
        self._restore_worker.finished.connect(
            self._restore_worker.deleteLater
        )
        self._restore_thread.finished.connect(
            self._restore_thread.deleteLater
        )

        self._restore_thread.start()

    @Slot(dict)
    def _on_restore_success(self, user_info: dict):
        logger.info("Silent session restore succeeded")
        self._is_transitioning = True
        self.signin_form.on_login_success(user_info, remember_me=True)
        self.login_successful.emit(user_info)

    @Slot()
    def _on_restore_finished(self):
        if (self.signin_form._is_logging_in
                and not self._is_transitioning):
            self.signin_form.set_login_state(False)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def _handle_login(self, username: str, password: str,
                      remember_me: bool = False):
        if LoginPage._login_in_progress or self._is_transitioning:
            logger.warning("Login already in progress")
            return

        LoginPage._login_in_progress = True
        self._pending_remember_me = remember_me
        self.signin_form.set_login_state(True, "Signing in…")

        self._login_thread = QThread()
        self._login_worker = LoginWorker(
            username, password, remember_me, self.auth_manager
        )
        self._login_worker.moveToThread(self._login_thread)

        self._login_thread.started.connect(self._login_worker.run)
        # Connected to a @Slot method on `self` — a QObject living in the
        # GUI thread — so Qt auto-queues this signal. NO LAMBDA.
        self._login_worker.success.connect(self._on_login_success)
        self._login_worker.error.connect(self._on_login_error)
        self._login_worker.finished.connect(self._on_login_finished)
        self._login_worker.finished.connect(self._login_thread.quit)
        self._login_worker.finished.connect(
            self._login_worker.deleteLater
        )
        self._login_thread.finished.connect(
            self._login_thread.deleteLater
        )

        self._login_thread.start()

    @Slot(dict)
    def _on_login_success(self, payload: dict):
        """Runs on the GUI thread (auto-queued)."""
        user_info = payload.get("user_info") or {}
        remember_me = payload.get("remember_me", False)

        logger.info(
            f"Login successful for: {user_info.get('username', 'unknown')}"
        )
        if 'permissions' not in user_info or not user_info['permissions']:
            user_info['permissions'] = list(self.auth_manager.permissions)

        self._is_transitioning = True
        self.signin_form.on_login_success(user_info, remember_me)
        self.login_successful.emit(user_info)

    @Slot(str)
    def _on_login_error(self, error_msg: str):
        self.signin_form.on_login_failed(error_msg)
        LoginPage._login_in_progress = False

    @Slot()
    def _on_login_finished(self):
        if not getattr(self, '_is_transitioning', False):
            LoginPage._login_in_progress = False

    def _show_reset_password(self):
        try:
            from dialogs.forgot_password_dialog import ForgotPasswordDialog
            dialog = ForgotPasswordDialog(self.auth_manager.api, self)
            dialog.exec()
        except ImportError as e:
            logger.error(f"Could not import reset password dialog: {e}")
            from widgets.components import ShadcnToast
            ShadcnToast(
                "Info",
                description="Password reset is not available offline.",
                parent=self,
            )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def show_signin(self):
        self.mode = "signin"
        self.stack.setCurrentWidget(self.signin_form)
        self.left_text.setText("Welcome Back")
        QTimer.singleShot(100, self.signin_form.setFocus)

    def show_signup(self):
        self.mode = "signup"
        self.stack.setCurrentWidget(self.signup_form)
        self.left_text.setText("Create Account")
        QTimer.singleShot(100, self.signup_form.setFocus)

    def switch_to_signup(self):
        if self.mode == "signin":
            self.show_signup()

    def switch_to_signin(self):
        if self.mode == "signup":
            self.show_signin()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def set_background_image(self):
        image_path = resource_path("assets/images/icta1.jpg")
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                self.bg_label.setPixmap(pixmap)
            else:
                self.bg_label.setStyleSheet(
                    "background-color: #2c3e50; border: none;"
                )
        else:
            logger.warning(f"Background image not found: {image_path}")
            self.bg_label.setStyleSheet(
                "background-color: #2c3e50; border: none;"
            )

    def update_logo(self):
        pass

    def apply_theme(self):
        if self._is_transitioning:
            return

        tokens = self.theme_manager.get_tokens()
        is_dark = self.theme_manager.get_current_theme() == "dark"

        right_bg = tokens.get("background", "#F8FAFC" if not is_dark else "#0B1220")
        self.right_panel.setStyleSheet(
            f"#rightPanel {{ background-color: {right_bg}; border: none; }}"
        )

        form_bg = tokens.get("surface", "#FFFFFF" if not is_dark else "#1E293B")
        form_border = tokens.get("border", "#E2E8F0" if not is_dark else "#334155")
        self.form_container.setStyleSheet(f"""
            QFrame {{
                background-color: {form_bg};
                border-radius: 20px;
                border: 1px solid {form_border};
            }}
        """)

        text_color = tokens.get("foreground", "#0F172A")
        subtext_color = tokens.get("muted-foreground", "#64748B")
        hint_color = tokens.get("muted-foreground", "#94A3B8")

        for lbl in self.findChildren(QLabel):
            role = lbl.property("textRole")
            if role == "title":
                lbl.setStyleSheet(
                    f"font-size: 26px; font-weight: 700; "
                    f"background: transparent; border: none; "
                    f"color: {text_color};"
                )
            elif role == "subtitle":
                lbl.setStyleSheet(
                    f"font-size: 13px; background: transparent; "
                    f"border: none; color: {subtext_color};"
                )
            elif role == "hint":
                lbl.setStyleSheet(
                    f"font-size: 11px; font-weight: 500; "
                    f"background: transparent; border: none; "
                    f"color: {hint_color};"
                )

        for child in self.findChildren(FloatingLabelInput):
            child.update_icon()
            child.update_theme_colors()

        if hasattr(self.signup_form, 'signup_role'):
            radius = tokens.get("radius", "6px")
            self.signup_form.signup_role.setStyleSheet(f"""
                QComboBox#signupRoleCombo {{
                    background-color: {form_bg};
                    border: 1px solid {form_border};
                    border-radius: {radius};
                    padding: 8px 12px;
                    color: {text_color};
                    min-height: 30px;
                }}
                QComboBox#signupRoleCombo:focus {{
                    border: 2px solid {tokens["ring"]};
                }}
                QComboBox#signupRoleCombo::drop-down {{
                    border: none;
                    width: 20px;
                }}
                QComboBox#signupRoleCombo QAbstractItemView {{
                    background-color: {form_bg};
                    color: {text_color};
                    border: 1px solid {form_border};
                    selection-background-color: {tokens['primary']};
                    selection-color: {tokens['primary-foreground']};
                }}
            """)

        role_container = self.signup_form.findChild(QWidget, "roleContainer")
        if role_container:
            self.signup_form_role_container_style = f"""
                QWidget#roleContainer {{
                    background: {form_bg};
                    border: 1px solid {form_border};
                    border-radius: {tokens.get('radius', '6px')};
                }}
            """
            role_container.setStyleSheet(
                self.signup_form_role_container_style
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.bg_label.setGeometry(self.left_panel.rect())
        self.overlay.setGeometry(self.left_panel.rect())
        fw = self.form_container.width()
        fh = self.form_container.height()
        self.form_container.move(
            (self.right_panel.width() - fw) // 2,
            (self.right_panel.height() - fh) // 2,
        )

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            if self.mode == "signin":
                self.signin_form.login_password.clear()
                self.signin_form.login_password.input.setText("")
            elif self.mode == "signup":
                try:
                    self.signup_form.password.clear()
                    self.signup_form.confirm_password.clear()
                except Exception:
                    pass
            event.accept()
            return
        super().keyPressEvent(event)

