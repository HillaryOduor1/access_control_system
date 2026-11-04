# dialogs/forgot_password_dialog.py
"""
Forgot-password dialog for the desktop client.

Three-step flow, all inside the app:

    1. Enter email        -> POST /auth/password/request
    2. Enter 6-digit OTP  -> POST /auth/password/verify
                             (returns a single-use reset_token)
    3. Set new password   -> POST /auth/password/complete

The whole flow runs on worker QThreads. The GUI is never blocked.
A per-call watchdog guarantees the form can never get stuck in a
"loading" state if a worker dies without emitting a result.

Positioning
-----------
The dialog is centered on the primary screen (not on its parent
widget). Centering on the parent placed the dialog wherever the
login page happened to be inside the window, which looked offset.
The centering is re-run on every showEvent so it stays correct if
the user moves the app window between invocations.

Sizing
------
The dialog uses a fixed width (400 px) and a fixed height (360 px).
The stack of three steps is bounded by that height; longer content
(such as the password step) fits inside without making the dialog
grow when the user advances from one step to the next.
"""
import re
import time
import uuid
import logging
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QWidget, QStackedWidget, QFrame, QProgressBar, QApplication,
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QThread, QObject, Slot,
)
from PySide6.QtGui import QKeyEvent, QGuiApplication

from widgets.components import (
    ShadcnButton, ShadcnInput, ShadcnToast,
)
from widgets.floating_label_input import FloatingLabelInput
from widgets.password_strength_meter import PasswordStrengthMeter
from core.theme_manager import ThemeManager

logger = logging.getLogger(__name__)


class _ApiWorker(QObject):
    """Runs a single callable in a background thread."""
    finished = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, func: Callable, ticket: str, *args, **kwargs):
        super().__init__()
        self._func = func
        self._ticket = ticket
        self._args = args
        self._kwargs = kwargs

    @Slot()
    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
            self.finished.emit(self._ticket, result)
        except Exception as e:
            logger.exception("Forgot-password worker failed")
            self.failed.emit(self._ticket, str(e))


class ForgotPasswordDialog(QDialog):
    """Desktop-appropriate password reset: code by email, no links."""

    password_reset_complete = Signal()

    _worker_finished = Signal(str, object)
    _worker_failed = Signal(str, str)

    ASYNC_WATCHDOG_SECONDS = 45
    OTP_RESEND_COOLDOWN = 60

    # Compact fixed geometry.
    DIALOG_WIDTH = 400
    DIALOG_HEIGHT = 360

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.theme_manager = ThemeManager()

        self._is_submitting = False
        self._thread: Optional[QThread] = None
        self._worker: Optional[_ApiWorker] = None
        self._pending_async: dict[str, tuple] = {}

        # Flow state
        self._email: str = ""
        self._reset_token: str = ""
        self._otp_timer: Optional[QTimer] = None
        self._otp_remaining: int = 0

        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_watchdog_timeout)

        self._worker_finished.connect(self._on_worker_finished)
        self._worker_failed.connect(self._on_worker_failed)

        self.setWindowTitle("Reset Password")
        self.setModal(True)
        self.setFixedSize(self.DIALOG_WIDTH, self.DIALOG_HEIGHT)
        self.setAccessibleName("Reset password")

        self._init_ui()
        self.show_step(0)

        self.theme_manager.register_widget(
            self, on_theme_changed=self._apply_styles,
        )
        self._apply_styles()

    # ------------------------------------------------------------------
    # Centering
    # ------------------------------------------------------------------

    def _center_on_screen(self):
        screen = None
        if self.parent() is not None:
            try:
                screen = self.parent().screen()
            except Exception:
                screen = None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_screen)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 18, 20, 16)

        header = QVBoxLayout()
        header.setSpacing(2)

        self.title_label = QLabel("Reset Password")
        self.title_label.setStyleSheet("background: transparent; border: none;")
        header.addWidget(self.title_label)

        self.subtitle_label = QLabel(
            "We'll email you a 6-digit verification code."
        )
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet(
            "background: transparent; border: none;"
        )
        header.addWidget(self.subtitle_label)
        layout.addLayout(header)

        layout.addSpacing(2)

        self.stack = QStackedWidget()

        # Step 1 — email
        step0 = QWidget()
        s0 = QVBoxLayout(step0)
        s0.setContentsMargins(0, 0, 0, 0)
        s0.setSpacing(8)

        self.email_label = QLabel("Email Address")
        self.email_label.setStyleSheet(
            "background: transparent; border: none;"
        )
        s0.addWidget(self.email_label)

        self.email_input = ShadcnInput("you@example.com")
        self.email_input.setAccessibleName("Email address")
        self.email_input.returnPressed.connect(self.send_code)
        s0.addWidget(self.email_input)
        s0.addStretch()

        self.send_code_btn = ShadcnButton(
            "Send Verification Code", variant="default", size="lg"
        )
        self.send_code_btn.setMinimumHeight(38)
        self.send_code_btn.clicked.connect(self.send_code)
        s0.addWidget(self.send_code_btn)
        self.stack.addWidget(step0)

        # Step 2 — OTP
        step1 = QWidget()
        s1 = QVBoxLayout(step1)
        s1.setContentsMargins(0, 0, 0, 0)
        s1.setSpacing(8)

        self.otp_hint = QLabel("")
        self.otp_hint.setWordWrap(True)
        self.otp_hint.setStyleSheet(
            "background: transparent; border: none;"
        )
        s1.addWidget(self.otp_hint)

        self.otp_input = ShadcnInput("6-digit code")
        self.otp_input.setAccessibleName("Six-digit verification code")
        self.otp_input.setMaxLength(6)
        self.otp_input.returnPressed.connect(self.verify_code)
        s1.addWidget(self.otp_input)

        self.otp_timer_label = QLabel("")
        self.otp_timer_label.setStyleSheet(
            "background: transparent; border: none;"
        )
        s1.addWidget(self.otp_timer_label)

        resend_row = QHBoxLayout()
        resend_row.addStretch()
        self.resend_btn = ShadcnButton(
            "Resend code", variant="link", size="sm"
        )
        self.resend_btn.clicked.connect(self.send_code)
        resend_row.addWidget(self.resend_btn)
        s1.addLayout(resend_row)

        s1.addStretch()

        self.verify_btn = ShadcnButton(
            "Verify Code", variant="default", size="lg"
        )
        self.verify_btn.setMinimumHeight(38)
        self.verify_btn.clicked.connect(self.verify_code)
        s1.addWidget(self.verify_btn)
        self.stack.addWidget(step1)

        # Step 3 — new password
        step2 = QWidget()
        s2 = QVBoxLayout(step2)
        s2.setContentsMargins(0, 0, 0, 0)
        s2.setSpacing(6)

        info = QLabel("Create a new password for your account.")
        info.setWordWrap(True)
        info.setStyleSheet("background: transparent; border: none;")
        s2.addWidget(info)

        self.new_password = FloatingLabelInput(
            "New Password *", icon_name="lock", password=True
        )
        self.new_password.set_required(True)
        self.new_password.textChanged.connect(self._on_password_changed)
        s2.addWidget(self.new_password)

        self.strength_meter = PasswordStrengthMeter()
        self.strength_label = QLabel("Password strength")
        self.strength_label.setStyleSheet(
            "background: transparent; border: none;"
        )
        s2.addWidget(self.strength_meter)
        s2.addWidget(self.strength_label)

        self.confirm_password = FloatingLabelInput(
            "Confirm Password *", icon_name="lock", password=True
        )
        self.confirm_password.set_required(True)
        self.confirm_password.textChanged.connect(self._check_password_match)
        s2.addWidget(self.confirm_password)

        self.match_label = QLabel("")
        self.match_label.setStyleSheet(
            "background: transparent; border: none;"
        )
        s2.addWidget(self.match_label)
        s2.addStretch()

        self.reset_btn = ShadcnButton(
            "Reset Password", variant="default", size="lg"
        )
        self.reset_btn.setMinimumHeight(38)
        self.reset_btn.clicked.connect(self.complete_reset)
        self.reset_btn.setEnabled(False)
        s2.addWidget(self.reset_btn)

        self.new_password.textChanged.connect(
            self.strength_meter.evaluate
        )
        self.strength_meter.strengthChanged.connect(
            self._update_strength_label
        )
        self.stack.addWidget(step2)

        layout.addWidget(self.stack, 1)

        # Progress + error
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        # Footer
        footer = QHBoxLayout()
        self.back_btn = ShadcnButton("← Back", variant="outline", size="sm")
        self.back_btn.clicked.connect(self._go_back)
        self.back_btn.hide()
        footer.addWidget(self.back_btn)

        footer.addStretch()

        self.cancel_btn = ShadcnButton("Cancel", variant="ghost", size="sm")
        self.cancel_btn.clicked.connect(self.reject)
        footer.addWidget(self.cancel_btn)

        layout.addLayout(footer)

    def _apply_styles(self, *_):
        t = self.theme_manager.get_tokens()

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t["surface"]};
                color: {t["foreground"]};
            }}
        """)
        self.title_label.setStyleSheet(
            f"font-size: {t['font.h3']}px; font-weight: 700; "
            f"color: {t['foreground']}; background: transparent;"
        )
        self.subtitle_label.setStyleSheet(
            f"font-size: {t['font.caption']}px; color: {t['muted-foreground']}; "
            "background: transparent;"
        )
        self.email_label.setStyleSheet(
            f"font-size: {t['font.caption']}px; font-weight: 500; "
            f"color: {t['foreground']}; background: transparent;"
        )
        self.otp_hint.setStyleSheet(
            f"font-size: {t['font.caption']}px; color: {t['muted-foreground']}; "
            "background: transparent;"
        )
        self.otp_timer_label.setStyleSheet(
            f"font-size: {t['font.caption']}px; "
            f"color: {t['muted-foreground']}; background: transparent;"
        )
        self.error_label.setStyleSheet(
            f"color: {t['destructive']}; font-size: {t['font.caption']}px; "
            "background: transparent;"
        )
        self.strength_label.setStyleSheet(
            f"font-size: {t['font.caption']}px; "
            f"color: {t['muted-foreground']}; background: transparent;"
        )
        self.match_label.setStyleSheet(
            f"font-size: {t['font.caption']}px; background: transparent;"
        )
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background: {t["muted"]};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {t["primary"]};
                border-radius: 2px;
            }}
        """)

    # ------------------------------------------------------------------
    # Step navigation
    # ------------------------------------------------------------------

    def show_step(self, index: int):
        self.stack.setCurrentIndex(index)
        self.back_btn.setVisible(index == 1)
        self.error_label.hide()
        self.progress_bar.hide()

        if index == 0:
            self.subtitle_label.setText(
                "We'll email you a 6-digit verification code."
            )
            QTimer.singleShot(0, self.email_input.setFocus)
        elif index == 1:
            self.subtitle_label.setText(
                "Enter the 6-digit code sent to your email."
            )
            self.otp_hint.setText(
                f"Code sent to {self._email}. Check your inbox — and the "
                "spam folder just in case."
            )
            self.otp_input.clear()
            QTimer.singleShot(0, self.otp_input.setFocus)
            self._start_otp_cooldown()
        elif index == 2:
            self.subtitle_label.setText(
                "Choose a strong new password."
            )
            QTimer.singleShot(0, self.new_password.input.setFocus)

    def _go_back(self):
        if self._is_submitting:
            return
        idx = self.stack.currentIndex()
        if idx > 0:
            self.show_step(idx - 1)

    # ------------------------------------------------------------------
    # Async plumbing
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool, button=None, text: str = "Please wait…"):
        self._is_submitting = busy
        for b in (self.send_code_btn, self.verify_btn, self.reset_btn,
                  self.back_btn, self.cancel_btn, self.resend_btn):
            try:
                b.setEnabled(not busy)
            except Exception:
                pass
        if button is not None:
            button.set_loading(busy, text)
        if busy:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.show()
        else:
            self.progress_bar.hide()
            self.progress_bar.setRange(0, 100)

    def _run_async(self, func, *args, on_success, on_error,
                   button=None, loading_text="Please wait…", **kwargs):
        if self._thread is not None and self._thread.isRunning():
            logger.warning("Async call already in flight")
            return

        self._set_busy(True, button=button, text=loading_text)
        self._watchdog.start(self.ASYNC_WATCHDOG_SECONDS * 1000)

        ticket = uuid.uuid4().hex
        self._pending_async[ticket] = (on_success, on_error, button)

        thread = QThread()
        worker = _ApiWorker(func, ticket, *args, **kwargs)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._worker_finished)
        worker.failed.connect(self._worker_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_thread_refs)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _clear_thread_refs(self):
        self._thread = None
        self._worker = None

    @Slot()
    def _on_watchdog_timeout(self):
        if not self._is_submitting:
            return
        logger.warning("Forgot-password watchdog fired")
        self._pending_async.clear()
        self._set_busy(False)
        self._show_error(
            "The request took too long. Please check your connection "
            "and try again."
        )

    @Slot(str, object)
    def _on_worker_finished(self, ticket: str, result):
        self._watchdog.stop()
        cb = self._pending_async.pop(ticket, None)
        if not cb:
            return
        on_success, _on_err, button = cb
        self._set_busy(False, button=button)
        try:
            on_success(result)
        except Exception as e:
            logger.exception("on_success raised")
            self._show_error(str(e))

    @Slot(str, str)
    def _on_worker_failed(self, ticket: str, message: str):
        self._watchdog.stop()
        cb = self._pending_async.pop(ticket, None)
        if not cb:
            return
        _on_ok, on_err, button = cb
        self._set_busy(False, button=button)
        try:
            on_err(message)
        except Exception as e:
            logger.exception("on_error raised")
            self._show_error(str(e))

    # ------------------------------------------------------------------
    # Step 1 — send code
    # ------------------------------------------------------------------

    def send_code(self):
        if self._is_submitting:
            return
        email = self.email_input.text().strip()
        if not email or not re.match(
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email
        ):
            self._show_error("Please enter a valid email address.")
            return

        self._email = email
        self._hide_error()

        def _on_ok(_result):
            self.show_step(1)

        def _on_err(msg):
            low = msg.lower()
            if "429" in low:
                self._show_error(
                    "Too many requests. Please wait a few minutes."
                )
            else:
                # Do not leak whether the email exists
                self.show_step(1)

        self._run_async(
            self.api_client.request,
            "POST",
            "/auth/password/request",
            json={"email": email},
            need_auth=False,
            timeout=30.0,
            on_success=_on_ok,
            on_error=_on_err,
            button=self.send_code_btn,
            loading_text="Sending code…",
        )

    # ------------------------------------------------------------------
    # Step 2 — verify code
    # ------------------------------------------------------------------

    def verify_code(self):
        if self._is_submitting:
            return
        otp = self.otp_input.text().strip()
        if len(otp) != 6 or not otp.isdigit():
            self._show_error("Please enter the 6-digit code.")
            return
        self._hide_error()

        def _on_ok(result):
            token = (result or {}).get("reset_token")
            if not token:
                self._show_error(
                    "Invalid or expired code. Please try again."
                )
                return
            self._reset_token = token
            self.show_step(2)

        def _on_err(msg):
            low = msg.lower()
            if "429" in low:
                self._show_error(
                    "Too many attempts. Please wait before trying again."
                )
            else:
                self._show_error(
                    "Invalid or expired code. Please try again."
                )

        self._run_async(
            self.api_client.request,
            "POST",
            "/auth/password/verify",
            json={"email": self._email, "otp": otp},
            need_auth=False,
            timeout=15.0,
            on_success=_on_ok,
            on_error=_on_err,
            button=self.verify_btn,
            loading_text="Verifying…",
        )

    def _start_otp_cooldown(self):
        self._otp_remaining = self.OTP_RESEND_COOLDOWN
        self.resend_btn.setEnabled(False)
        self.otp_timer_label.setText(
            f"Didn't get it? You can resend in {self._otp_remaining}s"
        )
        if self._otp_timer is None:
            self._otp_timer = QTimer(self)
            self._otp_timer.timeout.connect(self._tick_cooldown)
        self._otp_timer.start(1000)

    def _tick_cooldown(self):
        self._otp_remaining -= 1
        if self._otp_remaining <= 0:
            self._otp_timer.stop()
            self.otp_timer_label.setText("")
            self.resend_btn.setEnabled(True)
        else:
            self.otp_timer_label.setText(
                f"Didn't get it? You can resend in "
                f"{self._otp_remaining}s"
            )

    # ------------------------------------------------------------------
    # Step 3 — new password
    # ------------------------------------------------------------------

    def _on_password_changed(self, _):
        self._check_password_match()

    def _check_password_match(self):
        p = self.new_password.text()
        c = self.confirm_password.text()
        tokens = self.theme_manager.get_tokens()
        if not c:
            self.match_label.setText("")
            self.reset_btn.setEnabled(False)
            return
        if p == c and self._password_is_strong(p):
            self.match_label.setText("✓ Passwords match")
            self.match_label.setStyleSheet(
                f"font-size: {tokens['font.caption']}px; "
                f"color: {tokens['success']}; background: transparent;"
            )
            self.reset_btn.setEnabled(True)
        else:
            self.match_label.setText("✗ Passwords do not match")
            self.match_label.setStyleSheet(
                f"font-size: {tokens['font.caption']}px; "
                f"color: {tokens['destructive']}; background: transparent;"
            )
            self.reset_btn.setEnabled(False)

    def _password_is_strong(self, p: str) -> bool:
        return (
            len(p) >= 8
            and re.search(r'[A-Z]', p) is not None
            and re.search(r'[a-z]', p) is not None
            and re.search(r'[0-9]', p) is not None
            and re.search(r'[!@#$%^&*(),.?":{}|<>]', p) is not None
        )

    def _update_strength_label(self, score: int):
        tokens = self.theme_manager.get_tokens()
        p = self.new_password.text()
        if not p:
            self.strength_label.setText("Password strength")
            self.strength_label.setStyleSheet(
                f"font-size: {tokens['font.caption']}px; "
                f"color: {tokens['muted-foreground']}; "
                "background: transparent;"
            )
            return
        if score <= 2:
            text, color = "Weak", tokens["destructive"]
        elif score <= 4:
            text, color = "Medium", tokens["warning"]
        else:
            text, color = "Strong", tokens["success"]
        self.strength_label.setText(f"Password strength · {text}")
        self.strength_label.setStyleSheet(
            f"font-size: {tokens['font.caption']}px; font-weight: 600; "
            f"color: {color}; background: transparent;"
        )

    def complete_reset(self):
        if self._is_submitting:
            return
        p = self.new_password.text()
        c = self.confirm_password.text()
        if p != c:
            self._show_error("Passwords do not match.")
            return
        if not self._password_is_strong(p):
            self._show_error(
                "Password must be 8+ characters and include upper, "
                "lower, number and special character."
            )
            return
        self._hide_error()

        def _on_ok(_result):
            ShadcnToast(
                "Password reset",
                description="Your password has been updated. "
                            "Please sign in with the new password.",
                parent=self, variant="success", duration=4000,
            )
            self.password_reset_complete.emit()
            QTimer.singleShot(600, self.accept)

        def _on_err(msg):
            low = msg.lower()
            if "expired" in low or "invalid" in low:
                self._show_error(
                    "Your reset session expired. Please start over."
                )
                self.show_step(0)
            elif "recently" in low or "history" in low:
                self._show_error(
                    "You've used this password recently. "
                    "Please choose a different one."
                )
            elif "429" in low:
                self._show_error(
                    "Too many attempts. Please wait before trying again."
                )
            else:
                self._show_error(msg or "Could not reset password.")

        self._run_async(
            self.api_client.request,
            "POST",
            "/auth/password/complete",
            json={
                "email": self._email,
                "reset_token": self._reset_token,
                "new_password": p,
            },
            need_auth=False,
            timeout=30.0,
            on_success=_on_ok,
            on_error=_on_err,
            button=self.reset_btn,
            loading_text="Resetting…",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()

    def _hide_error(self):
        self.error_label.hide()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            idx = self.stack.currentIndex()
            if idx == 0:
                self.send_code()
            elif idx == 1:
                self.verify_code()
            elif idx == 2:
                if self.reset_btn.isEnabled():
                    self.complete_reset()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._otp_timer:
            self._otp_timer.stop()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)
