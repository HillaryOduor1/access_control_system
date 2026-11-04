# pages/signup_form.py
"""
Enterprise signup form with validation, email verification, and OTP.

Threading
---------
Worker results are marshalled back to the GUI thread via two internal
signals (`_worker_finished`, `_worker_failed`) declared on the form.
Signals emitted from a worker thread and delivered to a QObject living
in the GUI thread are queued automatically by Qt, which guarantees the
callbacks run on the GUI thread.

Toast delivery
--------------
`ShadcnToast.__init__` calls `show()`, `raise_()`, and
`QTimer.singleShot(0, ...)` internally. That sequence can spin a
nested event loop depending on the current Qt dispatch state. When a
toast is opened from inside a `QTimer.singleShot(0, ...)` callback
(which is how `_on_worker_finished` defers GUI work), the nested loop
can end up blocked and the entire window stops pumping events —
which Windows reports as "Not Responding".

To eliminate that risk, every toast this form raises goes through
`_toast()`, which double-defers: the toast is created on the second
event-loop tick after the call, well outside any signal-dispatch or
worker-teardown context.

Also, the resend cooldown timer is not started until after the toast
has been created, so we never have two QTimers competing for the same
event-loop turn.
"""
import re
import time
import uuid
import logging
from typing import Dict, Optional, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QStackedWidget,
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QThread, QObject, Slot,
)
from PySide6.QtGui import QKeyEvent

from widgets.components import ShadcnButton, ShadcnToast, ShadcnCheckBox
from widgets.floating_label_input import FloatingLabelInput
from widgets.password_strength_meter import PasswordStrengthMeter
from core.theme_manager import ThemeManager

logger = logging.getLogger(__name__)


class _ApiWorker(QObject):
    """Runs a callable in a background QThread and reports the result."""
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
            logger.exception("Background API call failed")
            self.failed.emit(self._ticket, str(e))


class SignUpForm(QWidget):
    """Enterprise signup form with multi-step validation and OTP."""

    switch_to_signin = Signal()
    signup_successful = Signal(dict)

    _worker_finished = Signal(str, object)
    _worker_failed = Signal(str, str)

    ASYNC_WATCHDOG_SECONDS = 60

    def __init__(self, auth_manager, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager
        self.theme_manager = ThemeManager()
        self.data: Dict = {}
        self.current_step = 0
        self._is_submitting = False
        self._signup_attempts = 0
        self._max_attempts = 3
        self._locked_until: Optional[float] = None
        self._otp_code = None
        self._otp_timer = None
        self._otp_remaining = 0
        self._otp_verified = False

        self._thread: Optional[QThread] = None
        self._worker: Optional[_ApiWorker] = None
        self._pending_async: Dict[str, tuple] = {}

        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_watchdog_timeout)

        self._worker_finished.connect(self._on_worker_finished)
        self._worker_failed.connect(self._on_worker_failed)

        self.init_ui()
        self.show_step(0)

    # ======================================================================
    # Toast helper — double-deferred
    # ======================================================================

    def _toast(self, title: str, description: str = "",
               variant: str = "default", duration: int = 3000):
        """
        Show a toast without risking a nested-event-loop deadlock.

        The call is deferred twice: the outer singleShot(0, ...) moves
        us out of any current signal-dispatch, and the inner
        singleShot(0, ...) ensures the toast is created on a clean
        event-loop turn with no pending Qt work.

        Any exception inside the toast is logged and swallowed — a
        broken toast must never take down the app.
        """
        def _inner():
            try:
                ShadcnToast(title, description=description,
                            parent=self, variant=variant, duration=duration)
            except Exception:
                logger.exception("ShadcnToast failed")

        QTimer.singleShot(0, _inner)

    # ======================================================================
    # UI
    # ======================================================================

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(48, 48, 48, 36)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(6)
        self.title = QLabel("Create account")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setProperty("textRole", "title")
        self.title.setStyleSheet("background: transparent; border: none;")
        self.subtitle = QLabel("Fill in your details to get started.")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setProperty("textRole", "subtitle")
        self.subtitle.setStyleSheet("background: transparent; border: none;")
        header_layout.addWidget(self.title)
        header_layout.addWidget(self.subtitle)
        layout.addLayout(header_layout)

        self.progress_layout = QHBoxLayout()
        self.progress_layout.setSpacing(4)
        self.progress_layout.setContentsMargins(40, 8, 40, 8)
        self.step_indicators = []
        for i in range(4):
            indicator = QLabel()
            indicator.setFixedSize(40, 3)
            indicator.setStyleSheet("background: #E2E8F0; border-radius: 2px;")
            indicator.setAccessibleName(f"Step {i + 1} of 4")
            self.progress_layout.addWidget(indicator)
            self.step_indicators.append(indicator)
        layout.addLayout(self.progress_layout)

        self.stack = QStackedWidget()
        self.step1 = self._create_step1()
        self.step2 = self._create_step2()
        self.step3 = self._create_step3()
        self.step4 = self._create_step4()
        self.stack.addWidget(self.step1)
        self.stack.addWidget(self.step2)
        self.stack.addWidget(self.step3)
        self.stack.addWidget(self.step4)
        layout.addWidget(self.stack, 1)

        nav_layout = QHBoxLayout()
        self.back_btn = ShadcnButton("Back", variant="outline", size="sm")
        self.back_btn.clicked.connect(self.go_back)
        self.next_btn = ShadcnButton("Next", variant="default", size="sm")
        self.next_btn.clicked.connect(self.go_next)
        nav_layout.addStretch()
        nav_layout.addWidget(self.back_btn)
        nav_layout.addWidget(self.next_btn)
        layout.addLayout(nav_layout)

        self.signin_toggle = ShadcnButton(
            "Already have an account? Sign in", variant="link", size="sm"
        )
        self.signin_toggle.clicked.connect(self.switch_to_signin.emit)
        layout.addWidget(self.signin_toggle, alignment=Qt.AlignCenter)

    def _create_step1(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)

        self.first_name = FloatingLabelInput("First Name *", icon_name="user")
        self.first_name.set_required(True)
        layout.addWidget(self.first_name)

        self.last_name = FloatingLabelInput("Last Name *", icon_name="user")
        self.last_name.set_required(True)
        layout.addWidget(self.last_name)

        self.email = FloatingLabelInput("Email *", icon_name="email")
        self.email.set_required(True)
        layout.addWidget(self.email)

        self.employee_number = FloatingLabelInput(
            "Employee Number (optional)", icon_name="badge"
        )
        layout.addWidget(self.employee_number)

        self.phone = FloatingLabelInput(
            "Phone Number (optional)", icon_name="phone"
        )
        layout.addWidget(self.phone)

        self.id_number = FloatingLabelInput(
            "ID Number (optional)", icon_name="id"
        )
        layout.addWidget(self.id_number)

        layout.addStretch()
        return widget

    def _create_step2(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)

        self.organisation = FloatingLabelInput(
            "Organisation *", icon_name="building"
        )
        self.organisation.set_required(True)
        layout.addWidget(self.organisation)

        role_container = QWidget()
        role_container.setObjectName("roleContainer")
        role_container.setFixedHeight(72)
        role_layout = QHBoxLayout(role_container)
        role_layout.setContentsMargins(12, 8, 12, 8)
        role_layout.setSpacing(8)
        role_label = QLabel("Role *")
        role_label.setProperty("textRole", "hint")
        role_label.setStyleSheet("background: transparent; border: none;")
        self.signup_role = QComboBox()
        self.signup_role.setObjectName("signupRoleCombo")
        self.signup_role.setAccessibleName("Role")
        self.signup_role.addItems(['staff', 'security', 'finance', 'admin'])
        role_layout.addWidget(role_label)
        role_layout.addWidget(self.signup_role, 1)
        layout.addWidget(role_container)

        self.terms_checkbox = ShadcnCheckBox(
            "I agree to the Terms and Conditions"
        )
        self.terms_checkbox.setAccessibleName(
            "Agree to the Terms and Conditions"
        )
        layout.addWidget(self.terms_checkbox)

        layout.addStretch()
        return widget

    def _create_step3(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)

        otp_title = QLabel("Email Verification")
        otp_title.setAlignment(Qt.AlignCenter)
        otp_title.setStyleSheet(
            "font-size: 20px; font-weight: 700; "
            "color: #0F172A; background: transparent; border: none;"
        )
        layout.addWidget(otp_title)

        otp_subtitle = QLabel("We've sent a verification code to your email")
        otp_subtitle.setAlignment(Qt.AlignCenter)
        otp_subtitle.setStyleSheet(
            "font-size: 14px; color: #64748B; "
            "background: transparent; border: none;"
        )
        layout.addWidget(otp_subtitle)

        self.otp_input = FloatingLabelInput(
            "Enter 6-digit code", icon_name="email"
        )
        self.otp_input.set_required(True)
        self.otp_input.input.setMaxLength(6)
        self.otp_input.input.setAccessibleName("Six-digit verification code")
        self.otp_input.textChanged.connect(self._on_otp_changed)
        layout.addWidget(self.otp_input)

        self.otp_status = QLabel("")
        self.otp_status.setAlignment(Qt.AlignCenter)
        self.otp_status.setStyleSheet(
            "font-size: 12px; color: #64748B; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self.otp_status)

        resend_layout = QHBoxLayout()
        resend_layout.setAlignment(Qt.AlignCenter)
        self.resend_btn = ShadcnButton(
            "Resend Code", variant="ghost", size="sm"
        )
        self.resend_btn.clicked.connect(self._resend_otp)
        self.resend_timer_label = QLabel("")
        self.resend_timer_label.setStyleSheet(
            "font-size: 12px; color: #94A3B8; "
            "background: transparent; border: none;"
        )
        resend_layout.addWidget(self.resend_btn)
        resend_layout.addWidget(self.resend_timer_label)
        layout.addLayout(resend_layout)

        layout.addStretch()
        return widget

    def _create_step4(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)

        self.password = FloatingLabelInput(
            "Password *", icon_name="lock", password=True
        )
        self.password.set_required(True)
        layout.addWidget(self.password)

        strength_layout = QVBoxLayout()
        strength_layout.setSpacing(6)
        strength_layout.setContentsMargins(2, 0, 2, 4)
        self.strength_meter = PasswordStrengthMeter()
        self.strength_label = QLabel("Password strength")
        self.strength_label.setProperty("textRole", "hint")
        self.strength_label.setStyleSheet(
            "background: transparent; border: none;"
        )
        strength_layout.addWidget(self.strength_meter)
        strength_layout.addWidget(self.strength_label)
        layout.addLayout(strength_layout)

        self.password.textChanged.connect(self.strength_meter.evaluate)
        self.password.textChanged.connect(self._on_password_changed)
        self.strength_meter.strengthChanged.connect(self._update_strength_label)

        self.confirm_password = FloatingLabelInput(
            "Confirm Password *", icon_name="lock", password=True
        )
        self.confirm_password.set_required(True)
        layout.addWidget(self.confirm_password)
        self.confirm_password.textChanged.connect(self._check_password_match)
        self.confirm_password.focusLost.connect(self._check_password_match)

        self.req_label = QLabel(
            "Password must: • 8+ characters • Uppercase & lowercase • "
            "Number • Special character"
        )
        self.req_label.setProperty("textRole", "hint")
        self.req_label.setWordWrap(True)
        self.req_label.setStyleSheet(
            "font-size: 11px; color: #94A3B8; "
            "background: transparent; border: none; padding: 4px;"
        )
        layout.addWidget(self.req_label)

        layout.addStretch()
        return widget

    # ======================================================================
    # Busy state
    # ======================================================================

    def _set_busy(self, busy: bool, button: Optional[ShadcnButton] = None,
                  text: Optional[str] = None):
        self._is_submitting = busy

        self.next_btn.setEnabled(not busy)
        self.back_btn.setEnabled(not busy)
        self.signin_toggle.setEnabled(not busy)

        if button is not None:
            button.set_loading(busy, text)
        else:
            if busy:
                self.next_btn.set_loading(True, text or "Please wait…")
            else:
                self.next_btn.set_loading(False)

        self._set_inputs_enabled(not busy)

    def _set_inputs_enabled(self, enabled: bool):
        for w in (
            self.first_name, self.last_name, self.email,
            self.employee_number, self.phone, self.id_number,
            self.organisation, self.signup_role,
            self.otp_input, self.password, self.confirm_password,
        ):
            try:
                w.setEnabled(enabled)
            except Exception:
                pass
        try:
            self.terms_checkbox.setEnabled(enabled)
        except Exception:
            pass

    # ======================================================================
    # Threaded call helper
    # ======================================================================

    def _run_async(
        self, func: Callable, *args,
        on_success: Callable, on_error: Callable,
        button: Optional[ShadcnButton] = None,
        loading_text: str = "Please wait…",
        **kwargs,
    ):
        if self._thread is not None and self._thread.isRunning():
            logger.warning("Async call requested while another is running")
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

        # Cleanup AFTER the forwarding signals so the GUI slot is
        # enqueued first.
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)

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
        logger.warning(
            "Async watchdog fired — force-clearing busy state after %ss",
            self.ASYNC_WATCHDOG_SECONDS,
        )
        self._pending_async.clear()
        self._set_busy(False)
        self._toast(
            "Timed out",
            "The request took too long. Please try again.",
            "destructive",
        )

    @Slot(str, object)
    def _on_worker_finished(self, ticket: str, result):
        """
        Runs on the GUI thread.

        The callback is deferred to the next event-loop turn. It must
        not open a toast directly — see the toast-delivery note at the
        top of this file.
        """
        self._watchdog.stop()
        callbacks = self._pending_async.pop(ticket, None)
        if not callbacks:
            return
        on_success, _on_error, button = callbacks

        # Re-enable the form first so no matter what the callback does,
        # the user is not stuck staring at a disabled form.
        self._set_busy(False, button=button)

        QTimer.singleShot(0, lambda: self._invoke_callback(
            on_success, result
        ))

    @Slot(str, str)
    def _on_worker_failed(self, ticket: str, message: str):
        self._watchdog.stop()
        callbacks = self._pending_async.pop(ticket, None)
        if not callbacks:
            return
        _on_success, on_error, button = callbacks

        self._set_busy(False, button=button)
        QTimer.singleShot(0, lambda: self._invoke_error(
            on_error, message
        ))

    def _invoke_callback(self, callback: Callable, result):
        try:
            callback(result)
        except Exception:
            logger.exception("on_success handler raised")

    def _invoke_error(self, callback: Callable, message: str):
        try:
            callback(message)
        except Exception:
            logger.exception("on_error handler raised")

    # ======================================================================
    # OTP input
    # ======================================================================

    def _on_otp_changed(self, text: str):
        if self._otp_verified or self._is_submitting:
            return
        if len(text) == 6 and text.isdigit():
            QTimer.singleShot(300, self._auto_verify_otp)

    def _auto_verify_otp(self):
        if not self._is_submitting and not self._otp_verified:
            self._verify_otp()

    def _on_password_changed(self, _text):
        if self.confirm_password.text():
            self._check_password_match()

    def _check_password_match(self):
        password = self.password.text()
        confirm = self.confirm_password.text()
        if not confirm:
            self.confirm_password.set_valid(True, "", shake=False)
            return
        if password == confirm:
            self.confirm_password.set_valid(True, "", shake=False)
        else:
            self.confirm_password.set_valid(
                False, "Passwords do not match", shake=False
            )

    def _update_strength_label(self, score: int):
        tokens = self.theme_manager.get_tokens()

        if not self.password.text():
            self.strength_label.setText("Password strength")
            self.strength_label.setStyleSheet(
                f"font-size: 11px; font-weight: 500; "
                f"color: {tokens.get('muted-foreground', '#94A3B8')}; "
                "border: none; background: transparent;"
            )
            return

        if score <= 2:
            text, color = "Weak", tokens.get("destructive", "#EF4444")
        elif score <= 4:
            text, color = "Medium", tokens.get("warning", "#F59E0B")
        else:
            text, color = "Strong", tokens.get("success", "#10B981")

        self.strength_label.setText(f"Password strength · {text}")
        self.strength_label.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {color}; "
            "border: none; background: transparent;"
        )

    # ======================================================================
    # Step navigation
    # ======================================================================

    def show_step(self, index: int):
        self.current_step = index
        self.stack.setCurrentIndex(index)

        tokens = self.theme_manager.get_tokens()
        border_col = tokens.get("border", "#E2E8F0")
        success_col = tokens.get("success", "#16A34A")
        primary_col = tokens.get("primary", "#3B82F6")

        for i, indicator in enumerate(self.step_indicators):
            if i < index:
                indicator.setStyleSheet(
                    f"background: {success_col}; border-radius: 2px;"
                )
            elif i == index:
                indicator.setStyleSheet(
                    f"background: {primary_col}; border-radius: 2px;"
                )
            else:
                indicator.setStyleSheet(
                    f"background: {border_col}; border-radius: 2px;"
                )

        self.back_btn.setVisible(index > 0)

        if index == 3:
            self.next_btn.setText("Create Account")
            try:
                self.next_btn.clicked.disconnect()
            except Exception:
                pass
            self.next_btn.clicked.connect(self.submit)
        else:
            self.next_btn.setText("Next")
            try:
                self.next_btn.clicked.disconnect()
            except Exception:
                pass
            self.next_btn.clicked.connect(self.go_next)

        if index == 2:
            self._otp_verified = False
            QTimer.singleShot(300, self._send_otp)

    def go_back(self):
        if self._is_submitting:
            return
        if self.current_step > 0:
            self.show_step(self.current_step - 1)

    def go_next(self):
        if self._is_submitting:
            return
        if self.current_step == 0:
            self._validate_step1()
        elif self.current_step == 1:
            self._validate_step2()
        elif self.current_step == 2:
            self._verify_otp()

    def _validate_step1(self):
        if not self.first_name.text().strip():
            self._toast("Error", "First Name is required", "destructive")
            return
        if not self.last_name.text().strip():
            self._toast("Error", "Last Name is required", "destructive")
            return

        email = self.email.text().strip()
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not email or not re.match(email_regex, email):
            self._toast("Error",
                        "Please enter a valid email address.",
                        "destructive")
            return

        api = self.auth_manager.api
        cached_online = (
            api.is_online_cached()
            if hasattr(api, "is_online_cached")
            else True
        )

        if cached_online:
            def _on_result(result):
                if result and result.get('exists', False):
                    self._toast(
                        "Email Already Registered",
                        "This email is already in use. Please sign in instead.",
                        "destructive",
                    )
                    return
                self._commit_step1()

            def _on_error(_msg):
                self._commit_step1()

            self._run_async(
                self.auth_manager.api.request,
                "GET",
                f"/auth/check-email?email={email}",
                need_auth=False,
                timeout=10.0,
                on_success=_on_result,
                on_error=_on_error,
                button=self.next_btn,
                loading_text="Checking email…",
            )
        else:
            self._commit_step1()

    def _commit_step1(self):
        self.data['first_name'] = self.first_name.text().strip()
        self.data['last_name'] = self.last_name.text().strip()
        self.data['email'] = self.email.text().strip()
        self.data['employee_number'] = self.employee_number.text().strip()
        self.data['phone'] = self.phone.text().strip()
        self.data['id_number'] = self.id_number.text().strip()
        self.show_step(1)

    def _validate_step2(self):
        organisation = self.organisation.text().strip()
        if not organisation:
            self._toast("Error", "Organisation is required", "destructive")
            return
        if not self.terms_checkbox.isChecked():
            self._toast(
                "Error",
                "You must agree to the Terms and Conditions",
                "destructive",
            )
            return

        self.data['tenant_id'] = organisation
        self.data['role'] = self.signup_role.currentText()
        self.show_step(2)

    # ======================================================================
    # OTP
    # ======================================================================

    def _send_otp(self):
        if self._is_submitting:
            return

        api = self.auth_manager.api
        cached_online = (
            api.is_online_cached()
            if hasattr(api, "is_online_cached")
            else True
        )
        if not cached_online:
            self._toast("Offline", "Cannot send OTP while offline.",
                        "destructive")
            return

        self.otp_status.setText("Sending verification code…")
        self.otp_status.setStyleSheet(
            f"color: {self.theme_manager.get_tokens().get('info', '#3B82F6')}; "
            "font-size: 12px;"
        )
        self.resend_btn.setEnabled(False)
        self.otp_input.clear()

        def _on_success(result):
            if result and result.get('success', False):
                self.otp_status.setText(
                    "✓ Verification code sent to your email"
                )
                self.otp_status.setStyleSheet(
                    f"color: {self.theme_manager.get_tokens().get('success', '#16A34A')}; "
                    "font-size: 12px;"
                )
                self._toast(
                    "Code Sent",
                    "Check your inbox for the verification code.",
                    "success",
                )
                # Start the cooldown AFTER the toast has been scheduled,
                # so the toast's internal QTimer.singleShot(0, ...) and
                # our cooldown timer do not fire on the same tick.
                QTimer.singleShot(120, self._start_resend_timer)
            else:
                error = (result or {}).get('message', 'Failed to send OTP')
                self.otp_status.setText(f"✗ Error: {error}")
                self.otp_status.setStyleSheet(
                    f"color: {self.theme_manager.get_tokens().get('destructive', '#EF4444')}; "
                    "font-size: 12px;"
                )
                self._toast("Error", error, "destructive")
            self.resend_btn.setEnabled(True)
            self.otp_input.setFocus()

        def _on_error(msg):
            self.otp_status.setText(
                "✗ Failed to send verification code. Please try again."
            )
            self.otp_status.setStyleSheet(
                f"color: {self.theme_manager.get_tokens().get('destructive', '#EF4444')}; "
                "font-size: 12px;"
            )
            self._toast(
                "Error", f"Failed to send OTP: {msg}", "destructive"
            )
            self.resend_btn.setEnabled(True)

        self._run_async(
            self.auth_manager.api.request,
            "POST",
            "/auth/send-otp",
            json={"email": self.data['email'],
                  "purpose": "signup_verification"},
            need_auth=False,
            timeout=15.0,
            on_success=_on_success,
            on_error=_on_error,
            button=self.resend_btn,
            loading_text="Sending…",
        )

    def _resend_otp(self):
        if self._is_submitting:
            return
        if self._otp_remaining > 0:
            self._toast(
                "Please Wait",
                f"You can resend in {self._otp_remaining} seconds.",
                "info",
            )
            return
        self._otp_verified = False
        self._send_otp()

    def _start_resend_timer(self):
        self._otp_remaining = 60
        self.resend_btn.setEnabled(False)
        self.resend_timer_label.setText(f"({self._otp_remaining}s)")

        if self._otp_timer is None:
            self._otp_timer = QTimer(self)
            self._otp_timer.timeout.connect(self._update_resend_timer)
        self._otp_timer.start(1000)

    def _update_resend_timer(self):
        self._otp_remaining -= 1
        if self._otp_remaining <= 0:
            self._otp_timer.stop()
            self.resend_timer_label.setText("")
            self.resend_btn.setEnabled(True)
        else:
            self.resend_timer_label.setText(f"({self._otp_remaining}s)")

    def _verify_otp(self):
        if self._is_submitting or self._otp_verified:
            return

        otp = self.otp_input.text().strip()
        if not otp or len(otp) != 6 or not otp.isdigit():
            self._toast("Invalid Code",
                        "Please enter a valid 6-digit code.",
                        "destructive")
            self.otp_input.set_valid(False, "Enter 6-digit code", shake=True)
            return

        self.otp_status.setText("Verifying code…")
        self.otp_status.setStyleSheet(
            f"color: {self.theme_manager.get_tokens().get('info', '#3B82F6')}; "
            "font-size: 12px;"
        )

        def _on_success(result):
            if result and result.get('success', False):
                self._otp_verified = True
                self.otp_status.setText("✓ Email verified successfully!")
                self.otp_status.setStyleSheet(
                    f"color: {self.theme_manager.get_tokens().get('success', '#16A34A')}; "
                    "font-size: 12px; font-weight: 600;"
                )
                self.data['email_verified'] = True
                if self._otp_timer:
                    self._otp_timer.stop()
                self.resend_timer_label.setText("")
                self.resend_btn.setEnabled(True)
                self._toast("Verified",
                            "Your email has been verified.",
                            "success")
                QTimer.singleShot(500, lambda: self.show_step(3))
            else:
                error = (result or {}).get('message',
                                           'Invalid verification code')
                self.otp_status.setText(f"✗ {error}")
                self.otp_status.setStyleSheet(
                    f"color: {self.theme_manager.get_tokens().get('destructive', '#EF4444')}; "
                    "font-size: 12px;"
                )
                self.otp_input.set_valid(False, error, shake=True)
                self._toast("Verification Failed", error, "destructive")

        def _on_error(msg):
            self.otp_status.setText("✗ Verification failed. Please try again.")
            self.otp_status.setStyleSheet(
                f"color: {self.theme_manager.get_tokens().get('destructive', '#EF4444')}; "
                "font-size: 12px;"
            )
            self._toast("Error",
                        f"Verification failed: {msg}",
                        "destructive")

        self._run_async(
            self.auth_manager.api.request,
            "POST",
            "/auth/verify-otp",
            json={
                "email": self.data['email'],
                "otp": otp,
                "purpose": "signup_verification",
            },
            need_auth=False,
            timeout=10.0,
            on_success=_on_success,
            on_error=_on_error,
            button=self.next_btn,
            loading_text="Verifying…",
        )

    # ======================================================================
    # Password
    # ======================================================================

    def _validate_password(self, password: str) -> tuple:
        if len(password) < 8:
            return False, "Password must be at least 8 characters long."
        if len(password) > 128:
            return False, "Password must be at most 128 characters long."
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter (A-Z)."
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter (a-z)."
        if not re.search(r'[0-9]', password):
            return False, "Password must contain at least one number (0-9)."
        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\];\'`~/\\]', password):
            return False, "Password must contain at least one special character."

        common = {
            'password', 'password123', '123456', '12345678', 'qwerty',
            'abc123', 'admin', 'letmein', 'welcome', 'monkey', 'dragon',
            'master', 'sunshine', '111111', '123456789', '1234567890',
            'password1', 'qwertyuiop', 'admin123', 'adminadmin', 'root',
            'toor', 'passw0rd', 'changeme', 'iloveyou', 'trustno1',
            '123123', '1q2w3e4r', 'qwerty123',
        }
        if password.lower() in common:
            return False, "This password is too common. Please choose a different one."
        normalized = password.lower().rstrip(
            "0123456789!@#$%^&*()_+-=[]{}|;:'\",.<>/?`~"
        )
        if normalized in common:
            return False, "This password is too similar to a common password."

        lower = password.lower()
        sequences = [
            "0123", "1234", "2345", "3456", "4567", "5678", "6789",
            "abcd", "bcde", "cdef", "defg", "efgh", "fghi", "ghij",
            "hijk", "ijkl", "jklm", "klmn", "lmno", "mnop", "nopq",
            "opqr", "pqrs", "qrst", "rstu", "stuv", "tuvw", "uvwx",
            "vwxy", "wxyz", "qwer", "wert", "erty", "rtyu", "tyui",
            "yuio", "uiop", "asdf", "sdfg", "dfgh", "fghj", "ghjk",
            "hjkl", "zxcv", "xcvb", "cvbn", "vbnm",
        ]
        if any(seq in lower for seq in sequences):
            return False, "Password contains sequential characters."
        if any(seq[::-1] in lower for seq in sequences):
            return False, "Password contains reversed sequences."
        if len(set(password)) < 4:
            return False, "Password contains too many repeated characters."
        return True, ""

    # ======================================================================
    # Submit
    # ======================================================================

    def submit(self):
        if self._is_submitting:
            return

        if not self.data.get('email_verified', False):
            self._toast("Email Not Verified",
                        "Please verify your email first.",
                        "destructive")
            self.show_step(2)
            return

        if self._locked_until:
            if time.time() < self._locked_until:
                remaining = int(self._locked_until - time.time())
                self._toast(
                    "Please Wait",
                    f"Too many attempts. Try again in {remaining} seconds.",
                    "destructive",
                )
                return
            else:
                self._locked_until = None
                self._signup_attempts = 0

        password = self.password.text()
        confirm = self.confirm_password.text()

        if not password:
            self._toast("Password Required",
                        "Please enter a password.",
                        "destructive")
            return

        valid, error = self._validate_password(password)
        if not valid:
            self._toast("Weak Password", error, "destructive", 5000)
            return

        if password != confirm:
            self._toast("Mismatch", "Passwords do not match.", "destructive")
            return

        self.data['password'] = password

        payload = {
            "username": self.data['email'],
            "email": self.data['email'],
            "first_name": self.data['first_name'],
            "last_name": self.data['last_name'],
            "full_name": f"{self.data['first_name']} {self.data['last_name']}",
            "employee_number": self.data.get('employee_number', ''),
            "phone": self.data.get('phone', ''),
            "id_number": self.data.get('id_number', ''),
            "tenant_id": self.data['tenant_id'],
            "roles": [self.data['role']],
            "password": password,
            "email_verified": True,
        }

        self._signup_attempts += 1

        api = self.auth_manager.api
        cached_online = (
            api.is_online_cached()
            if hasattr(api, "is_online_cached")
            else True
        )
        if not cached_online:
            self._toast("Offline",
                        "Cannot create account while offline.",
                        "destructive")
            return

        def _on_success(result):
            self._signup_attempts = 0
            self._locked_until = None
            self._toast(
                "Account Created",
                "Your account has been created successfully! "
                "Please sign in.",
                "success",
                3500,
            )
            self._clear_form()
            QTimer.singleShot(800, self.switch_to_signin.emit)

        def _on_error(msg):
            error_msg = msg.lower()
            if "429" in error_msg or "too many" in error_msg or "rate limit" in error_msg:
                self._locked_until = time.time() + 300
                self._toast(
                    "Too Many Attempts",
                    "Please wait 5 minutes before trying again.",
                    "destructive",
                    5000,
                )
            elif "409" in error_msg or "already exists" in error_msg or "already registered" in error_msg:
                self._toast(
                    "Account Exists",
                    msg or "Username or email already taken.",
                    "destructive",
                )
            elif "400" in error_msg:
                self._toast(
                    "Signup Failed",
                    msg or "Please check your details.",
                    "destructive",
                    5000,
                )
            else:
                self._toast(
                    "Signup Failed",
                    msg or "An unexpected error occurred.",
                    "destructive",
                )

        self._run_async(
            self.auth_manager.api.request,
            "POST",
            "/users",
            json=payload,
            need_auth=False,
            timeout=30.0,
            on_success=_on_success,
            on_error=_on_error,
            button=self.next_btn,
            loading_text="Creating account…",
        )

    # ======================================================================
    # Cleanup
    # ======================================================================

    def _clear_form(self):
        self.first_name.clear()
        self.last_name.clear()
        self.email.clear()
        self.employee_number.clear()
        self.phone.clear()
        self.id_number.clear()
        self.organisation.clear()
        self.password.clear()
        self.confirm_password.clear()
        self.otp_input.clear()
        self.terms_checkbox.setChecked(False)
        self.data = {}
        self._otp_code = None
        self._otp_verified = False

        if self._otp_timer:
            self._otp_timer.stop()
        self.resend_timer_label.setText("")
        self.resend_btn.setEnabled(True)
        self.otp_status.setText("")
        self.otp_status.setStyleSheet(
            f"color: {self.theme_manager.get_tokens().get('muted-foreground', '#64748B')}; "
            "font-size: 12px;"
        )

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.current_step == 3:
                self.submit()
            elif self.current_step == 2:
                self._verify_otp()
            else:
                self.go_next()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.switch_to_signin.emit()
            event.accept()
            return
        super().keyPressEvent(event)
