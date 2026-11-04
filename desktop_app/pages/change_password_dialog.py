# pages/change_password_dialog.py
"""
Change-password dialog for a signed-in user.

Design notes
------------
- Uses DataService.change_password, which posts to
  /users/change-password on the backend (matching routes/users.py).
- The actual network call is dispatched on a worker thread via
  DataService.run_async() so the dialog never blocks the GUI.
- All inputs are ShadcnInput so they pick up the global theme,
  focus ring, and QSS cache automatically.
- The show/hide eye toggles are QToolButtons and are explicitly
  themed here because the global QSS does not cover QToolButton.
- Toasts are parented to the main window (not the dialog) so they
  position correctly and survive the dialog's close.
- Registers with ThemeManager for theme + appearance changes.

Sizing
------
The dialog is sized by Qt's natural layout (sizeHint). After the
layout has settled, it is centred over the parent and clamped to
the available screen geometry so it never leaves the work area.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

from PySide6.QtCore import Qt, Signal, QSize, QTimer, QRect
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from core.icon_manager import IconManager
from core.theme_manager import ThemeManager
from widgets.components import (
    ShadcnButton, ShadcnInput, ShadcnToast,
)
from widgets.password_strength_meter import PasswordStrengthMeter

logger = logging.getLogger(__name__)


# Password policy — single source of truth for both the live checklist
# and the pre-submit validation. Each entry is (rule_id, message, check).
_PASSWORD_RULES = (
    ("len",     "At least 8 characters long",
                lambda p: len(p) >= 8),
    ("upper",   "Contains at least one uppercase letter",
                lambda p: bool(re.search(r"[A-Z]", p))),
    ("lower",   "Contains at least one lowercase letter",
                lambda p: bool(re.search(r"[a-z]", p))),
    ("digit",   "Contains at least one number",
                lambda p: bool(re.search(r"[0-9]", p))),
    ("special", "Contains at least one special character",
                lambda p: bool(re.search(
                    r"""[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;'/`~]""", p))),
)


class _PasswordField(QWidget):
    """
    Composite widget: a ShadcnInput plus a themed show/hide toggle.
    """

    def __init__(self, placeholder: str, accessible_name: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._icon_manager = IconManager()
        self._theme_manager = ThemeManager()

        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(8)

        self.input = ShadcnInput(placeholder)
        self.input.setEchoMode(QLineEdit.EchoMode.Password)
        self.input.setAccessibleName(accessible_name)
        lo.addWidget(self.input, 1)

        self.toggle = QToolButton(self)
        self.toggle.setCheckable(True)
        self.toggle.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.toggle.setFixedSize(40, 40)
        self.toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggle.setAccessibleName(f"Show {accessible_name.lower()}")
        self.toggle.setToolTip("Show / hide password")
        self.toggle.toggled.connect(self._on_toggled)
        lo.addWidget(self.toggle)

        self._refresh_icon()
        self._apply_toggle_theme()

        self._theme_manager.register_widget(
            self,
            on_theme_changed=self._on_theme_changed,
        )

    # -- API -----------------------------------------------------------

    def text(self) -> str:
        return self.input.text()

    def clear(self):
        self.input.clear()

    def setFocus(self):  # type: ignore[override]
        self.input.setFocus()

    def echo_mode(self) -> QLineEdit.EchoMode:
        return self.input.echoMode()

    # -- Internals -----------------------------------------------------

    def _on_theme_changed(self, *_):
        self._apply_toggle_theme()
        self._refresh_icon()

    def _apply_toggle_theme(self):
        t = self._theme_manager.get_tokens()
        radius = t["radius"]
        ring = t.get("ring", t["primary"])

        self.toggle.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 2px solid transparent;
                border-radius: {radius};
                color: {t['foreground']};
                padding: 0;
            }}
            QToolButton:hover {{
                background: {t['secondary']};
                border-color: {t['border']};
            }}
            QToolButton:pressed {{
                background: {t['accent']};
            }}
            QToolButton:checked {{
                background: {t['secondary']};
                border-color: {t['border-strong']};
            }}
            QToolButton:focus {{
                border: 2px solid {ring};
            }}
            QToolButton:disabled {{
                background: {t['muted']};
            }}
        """)

    def _on_toggled(self, checked: bool):
        if checked:
            self.input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle.setAccessibleName(
                f"Hide {self.input.accessibleName().lower()}"
            )
        else:
            self.input.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle.setAccessibleName(
                f"Show {self.input.accessibleName().lower()}"
            )
        self._refresh_icon()

    def _refresh_icon(self):
        name = (
            "eye"
            if self.input.echoMode() == QLineEdit.EchoMode.Password
            else "eye_off"
        )
        try:
            icon = self._icon_manager.get_icon(name, size=QSize(18, 18))
            self.toggle.setIcon(QIcon(icon))
            self.toggle.setIconSize(QSize(18, 18))
        except Exception:
            self.toggle.setText("👁")


class ChangePasswordDialog(QDialog):
    """Enterprise change-password dialog."""

    password_changed = Signal()

    def __init__(self, user_id, data_service, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.data_service = data_service
        self._is_submitting = False

        self.theme_manager = ThemeManager()

        self.setWindowTitle("Change Password")
        self.setModal(True)

        # Let the layout dictate the size. Only impose a comfortable
        # minimum width. No fixed or minimum height, so the dialog
        # adapts to the environment font and density.
        self.setMinimumWidth(520)
        self.setSizeGripEnabled(False)

        self.setAccessibleName("Change password")

        self._build_ui()
        self._wire_signals()
        self._install_tab_order()

        self.theme_manager.register_widget(
            self,
            on_theme_changed=self._on_theme_changed,
            on_appearance_changed=self._on_theme_changed,
        )
        self._apply_styles()
        self._refresh_requirements("")

        # Defer centring until after Qt has laid out the dialog, so
        # self.size() reflects the real content size rather than the
        # 640x480 default.
        QTimer.singleShot(0, self._center_over_parent)

        QTimer.singleShot(0, self.current_field.setFocus)

    # ------------------------------------------------------------------
    # Sizing / positioning
    # ------------------------------------------------------------------

    def _center_over_parent(self):
        """
        Centre the dialog over its parent, or over the primary
        screen if no parent exists. The position is clamped so the
        dialog always fits inside the available screen geometry.
        """
        self.adjustSize()

        parent = self.parent()
        if parent is not None and hasattr(parent, "geometry"):
            target = parent.geometry()
        else:
            screen = QApplication.primaryScreen()
            target = screen.availableGeometry() if screen else QRect()

        if target.isNull():
            return

        # Clamp the dialog size to the available geometry (with a small
        # margin) so it can never extend off-screen.
        margin = 24
        max_w = max(360, target.width() - 2 * margin)
        max_h = max(400, target.height() - 2 * margin)
        w = min(self.width(), max_w)
        h = min(self.height(), max_h)
        if w != self.width() or h != self.height():
            self.resize(w, h)

        x = target.x() + (target.width() - w) // 2
        y = target.y() + (target.height() - h) // 2

        # Final safety clamp to the screen work area.
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            x = max(avail.left(), min(x, avail.right() - w))
            y = max(avail.top(), min(y, avail.bottom() - h))

        self.move(x, y)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(28, 24, 28, 24)

        self.title_label = QLabel("Change Password")
        layout.addWidget(self.title_label)

        self.desc_label = QLabel(
            "Enter your current password and choose a new strong password."
        )
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        layout.addSpacing(4)

        # -- Current password ----------------------------------------
        self.current_label = QLabel("Current Password")
        layout.addWidget(self.current_label)

        self.current_field = _PasswordField(
            "Enter your current password",
            "Current password",
        )
        layout.addWidget(self.current_field)

        layout.addSpacing(2)

        # -- New password --------------------------------------------
        self.new_label = QLabel("New Password")
        layout.addWidget(self.new_label)

        self.new_field = _PasswordField(
            "Enter your new password",
            "New password",
        )
        layout.addWidget(self.new_field)

        layout.addSpacing(2)

        self.strength_meter = PasswordStrengthMeter()
        self.strength_meter.setFixedHeight(6)
        layout.addWidget(self.strength_meter)

        self.strength_label = QLabel("Password strength")
        layout.addWidget(self.strength_label)

        layout.addSpacing(4)

        # -- Confirm password ----------------------------------------
        self.confirm_label = QLabel("Confirm New Password")
        layout.addWidget(self.confirm_label)

        self.confirm_field = _PasswordField(
            "Confirm your new password",
            "Confirm new password",
        )
        layout.addWidget(self.confirm_field)

        self.match_label = QLabel(" ")
        self.match_label.setMinimumHeight(16)
        layout.addWidget(self.match_label)

        layout.addSpacing(4)

        # -- Requirements card ---------------------------------------
        # Vertical policy is Minimum so the card is never squeezed
        # below its natural height. The stretch below absorbs the
        # remaining space instead.
        self.req_frame = QFrame()
        self.req_frame.setObjectName("passwordRequirements")
        self.req_frame.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum,
        )
        req_layout = QVBoxLayout(self.req_frame)
        req_layout.setContentsMargins(16, 14, 16, 14)
        req_layout.setSpacing(6)

        self.req_title = QLabel("Password Requirements")
        req_layout.addWidget(self.req_title)

        self.req_labels: list[tuple[str, QLabel]] = []
        for rule_id, message, _check in _PASSWORD_RULES:
            lbl = QLabel(f"●  {message}")
            lbl.setObjectName(f"req_{rule_id}")
            lbl.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
            )
            req_layout.addWidget(lbl)
            self.req_labels.append((rule_id, lbl))

        layout.addWidget(self.req_frame)
        layout.addStretch(1)

        # -- Buttons -------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.cancel_btn = ShadcnButton(
            "Cancel", variant="outline", size="default"
        )
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.save_btn = ShadcnButton(
            "Change Password", variant="default", size="default"
        )
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.change_password)
        btn_row.addWidget(self.save_btn)

        layout.addLayout(btn_row)

    def _wire_signals(self):
        self.new_field.input.textChanged.connect(
            self._on_new_password_changed
        )
        self.confirm_field.input.textChanged.connect(
            self._on_confirm_password_changed
        )
        self.strength_meter.strengthChanged.connect(
            self._update_strength_label
        )

    def _install_tab_order(self):
        QWidget.setTabOrder(
            self.current_field.input, self.current_field.toggle
        )
        QWidget.setTabOrder(
            self.current_field.toggle, self.new_field.input
        )
        QWidget.setTabOrder(self.new_field.input, self.new_field.toggle)
        QWidget.setTabOrder(
            self.new_field.toggle, self.confirm_field.input
        )
        QWidget.setTabOrder(
            self.confirm_field.input, self.confirm_field.toggle
        )
        QWidget.setTabOrder(self.confirm_field.toggle, self.cancel_btn)
        QWidget.setTabOrder(self.cancel_btn, self.save_btn)

    # ------------------------------------------------------------------
    # Live validation
    # ------------------------------------------------------------------

    def _on_new_password_changed(self, text: str):
        self.strength_meter.evaluate(text)
        self._refresh_requirements(text)
        if self.confirm_field.text():
            self._refresh_match_state()

    def _on_confirm_password_changed(self, _text: str):
        self._refresh_match_state()

    def _refresh_requirements(self, password: str):
        tokens = self.theme_manager.get_tokens()

        rules_by_id = {
            rule_id: (message, check)
            for rule_id, message, check in _PASSWORD_RULES
        }

        for rule_id, lbl in self.req_labels:
            message, check = rules_by_id[rule_id]
            passed = check(password)

            if passed:
                lbl.setText(f"✓  {message}")
                color = tokens["success"]
            else:
                lbl.setText(f"●  {message}")
                color = tokens["muted-foreground"]

            lbl.setStyleSheet(
                f"font-size: {tokens['font.caption']}px; "
                f"color: {color}; padding: 1px 0; "
                "background: transparent;"
            )

    def _refresh_match_state(self):
        tokens = self.theme_manager.get_tokens()
        password = self.new_field.text()
        confirm = self.confirm_field.text()

        if not confirm:
            self.match_label.setText(" ")
            return

        if password == confirm:
            self.match_label.setText("✓  Passwords match")
            color = tokens["success"]
        else:
            self.match_label.setText("✗  Passwords do not match")
            color = tokens["destructive"]

        self.match_label.setStyleSheet(
            f"font-size: {tokens['font.caption']}px; font-weight: 500; "
            f"color: {color}; background: transparent;"
        )

    def _update_strength_label(self, score: int):
        tokens = self.theme_manager.get_tokens()
        if not self.new_field.text():
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

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_password(self, password: str) -> Tuple[bool, str]:
        for _rule_id, message, check in _PASSWORD_RULES:
            if not check(password):
                return False, message
        return True, ""

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def change_password(self):
        if self._is_submitting:
            return

        current = self.current_field.text()
        new = self.new_field.text()
        confirm = self.confirm_field.text()

        if not current:
            self._toast(
                "Error",
                "Please enter your current password",
                variant="destructive",
            )
            self.current_field.setFocus()
            return

        if not new:
            self._toast(
                "Error",
                "Please enter a new password",
                variant="destructive",
            )
            self.new_field.setFocus()
            return

        if new != confirm:
            self._toast(
                "Error",
                "New passwords do not match",
                variant="destructive",
            )
            self.confirm_field.setFocus()
            return

        if new == current:
            self._toast(
                "Error",
                "New password must differ from your current password",
                variant="destructive",
            )
            self.new_field.setFocus()
            return

        valid, error = self._validate_password(new)
        if not valid:
            self._toast("Error", error, variant="destructive")
            self.new_field.setFocus()
            return

        self._set_submitting(True)

        self.data_service.run_async(
            lambda: self.data_service.change_password(
                self.user_id, current, new
            ),
            callback=self._on_change_success,
            error_callback=self._on_change_error,
        )

    def _set_submitting(self, submitting: bool):
        self._is_submitting = submitting
        self.save_btn.set_loading(submitting, "Changing…")
        self.cancel_btn.setEnabled(not submitting)
        self.current_field.input.setEnabled(not submitting)
        self.new_field.input.setEnabled(not submitting)
        self.confirm_field.input.setEnabled(not submitting)
        self.current_field.toggle.setEnabled(not submitting)
        self.new_field.toggle.setEnabled(not submitting)
        self.confirm_field.toggle.setEnabled(not submitting)

    def _on_change_success(self, result):
        try:
            success, message = result
        except (TypeError, ValueError):
            success, message = False, "Unexpected response from server"

        if success:
            self._toast(
                "Success",
                message or "Password changed successfully",
                variant="success",
            )
            self.password_changed.emit()
            self.accept()
        else:
            self._set_submitting(False)
            self._toast(
                "Error",
                message or "Failed to change password",
                variant="destructive",
            )

    def _on_change_error(self, error_message: str):
        self._set_submitting(False)
        logger.error(f"Password change error: {error_message}")
        self._toast(
            "Error",
            f"Failed to change password: {error_message}",
            variant="destructive",
        )

    # ------------------------------------------------------------------
    # Toast helper
    # ------------------------------------------------------------------

    def _toast(self, title: str, message: str, variant: str = "default"):
        target = self.parent() or self
        try:
            ShadcnToast(
                title,
                description=message,
                variant=variant,
                parent=target,
            )
        except Exception:
            logger.info(f"Toast suppressed: {title} — {message}")

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _on_theme_changed(self, *_):
        self._apply_styles()
        self._refresh_requirements(self.new_field.text())
        current_score = getattr(self.strength_meter, "score", 0)
        self._update_strength_label(current_score)
        self._refresh_match_state()

    def _apply_styles(self):
        tokens = self.theme_manager.get_tokens()

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {tokens['surface']};
                color: {tokens['foreground']};
            }}
        """)

        self.title_label.setStyleSheet(
            f"font-size: {tokens['font.h3']}px; font-weight: 700; "
            f"color: {tokens['foreground']}; background: transparent;"
        )
        self.desc_label.setStyleSheet(
            f"font-size: {tokens['font.small']}px; "
            f"color: {tokens['muted-foreground']}; "
            "background: transparent;"
        )
        for lbl in (
            self.current_label,
            self.new_label,
            self.confirm_label,
            self.req_title,
        ):
            lbl.setStyleSheet(
                f"font-size: {tokens['font.small']}px; font-weight: 600; "
                f"color: {tokens['foreground']}; background: transparent;"
            )
        self.strength_label.setStyleSheet(
            f"font-size: {tokens['font.caption']}px; "
            f"color: {tokens['muted-foreground']}; "
            "background: transparent;"
        )
        self.match_label.setStyleSheet(
            f"font-size: {tokens['font.caption']}px; "
            "background: transparent;"
        )
        self.req_frame.setStyleSheet(
            f"#passwordRequirements {{ "
            f"background: {tokens['muted']}; "
            f"border: 1px solid {tokens['border']}; "
            f"border-radius: {tokens['radius']}; }}"
        )

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not self._is_submitting
        ):
            self.change_password()
            event.accept()
            return
        super().keyPressEvent(event)
