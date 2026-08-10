# widgets/floating_label_input.py
import os
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QLineEdit, QApplication
)
from PySide6.QtCore import Qt, Signal, QPoint, QPropertyAnimation, QEasingCurve, QRect, QSize, QEvent
from PySide6.QtGui import QColor, QCursor
from core.theme_manager import ThemeManager
from core.icon_manager import IconManager

class FloatingLabelInput(QWidget):
    textChanged = Signal(str)
    validChanged = Signal(bool)
    focusLost = Signal()

    def __init__(self, label: str, icon_name: str = None, password: bool = False, parent=None):
        super().__init__(parent)
        self.label_text = label
        self.icon_name = icon_name
        self.password = password
        self._valid = True
        self._error_msg = ""
        self._is_floating = False
        self._focused = False

        self.setFixedHeight(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.input_container = QFrame()
        self.input_container.setObjectName("inputContainer")
        self.input_container.setFixedHeight(52)
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(12, 0, 12, 0)
        input_layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border: none;")

        self.input = QLineEdit()
        self.input.setFrame(False)
        self.input.setPlaceholderText(" ")
        self.input.setMinimumHeight(52)
        self.input.setStyleSheet("""
            QLineEdit {
                border: none;
                background: transparent;
                background-color: transparent;
                font-size: 14px;
                padding: 0;
                margin: 0;
                outline: none;
            }
        """)
        if password:
            self.input.setEchoMode(QLineEdit.Password)
        self.input.textChanged.connect(self._on_text_changed)
        self.input.textChanged.connect(self.textChanged.emit)
        self.input.installEventFilter(self)

        self.eye_label = None
        if password:
            self.eye_label = QLabel()
            self.eye_label.setFixedSize(20, 20)
            self.eye_label.setAlignment(Qt.AlignCenter)
            self.eye_label.setStyleSheet("background: transparent; border: none; font-size: 16px;")
            self.eye_label.setCursor(QCursor(Qt.PointingHandCursor))
            self.eye_label.mousePressEvent = self._toggle_visibility

        input_layout.addWidget(self.icon_label)
        input_layout.addWidget(self.input, 1)
        if self.eye_label:
            input_layout.addWidget(self.eye_label)

        self.floating_label = QLabel(label)
        self.floating_label.setCursor(QCursor(Qt.IBeamCursor))
        self.floating_label.mousePressEvent = lambda e: self.input.setFocus()
        self.floating_label.setStyleSheet("background: transparent; border: none; font-weight: 500;")

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("font-size: 11px; padding-left: 4px; font-weight: 500; border: none; background: transparent;")

        layout.addWidget(self.input_container)
        layout.addWidget(self.error_label)

        self.floating_label.setParent(self.input_container)
        self._label_x = 40 if icon_name else 12
        self.floating_label.setGeometry(self._label_x, 6, 240, 20)
        self.floating_label.raise_()
        self.floating_label.show()

        self.theme_manager = ThemeManager()
        self.icon_manager = IconManager()
        self.update_icon()
        self.theme_manager.theme_changed.connect(self.update_icon)
        self.theme_manager.theme_changed.connect(self.update_theme_colors)

        self.float_anim = QPropertyAnimation(self.floating_label, b"geometry")
        self.float_anim.setDuration(160)
        self.float_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.update_floating_label()
        self.update_theme_colors()

    def eventFilter(self, obj, event):
        if obj is self.input:
            if event.type() == QEvent.FocusIn:
                self._focused = True
                self.update_floating_label()
                self._update_border(active=True)
            elif event.type() == QEvent.FocusOut:
                self._focused = False
                self.update_floating_label()
                self._update_border(active=False)
                self.focusLost.emit()
        return super().eventFilter(obj, event)

    def update_icon(self):
        if self.icon_name:
            icon = self.icon_manager.get_icon(self.icon_name, size=QSize(18, 18), state="default")
            pixmap = icon.pixmap(18, 18)
            if pixmap.isNull():
                self.icon_label.hide()
                self._label_x = 12
            else:
                self.icon_label.show()
                self.icon_label.setPixmap(pixmap)
                self._label_x = 40
        else:
            self._label_x = 12

        if self.eye_label:
            state = "eye_off" if self.input.echoMode() == QLineEdit.Normal else "eye"
            icon = self.icon_manager.get_icon(state, size=QSize(18, 18), state="default")
            pixmap = icon.pixmap(18, 18)
            if pixmap.isNull():
                if state == "eye":
                    self.eye_label.setText("👁")
                else:
                    self.eye_label.setText("🙈")
                self.eye_label.setStyleSheet("background: transparent; border: none; font-size: 16px;")
            else:
                self.eye_label.setPixmap(pixmap)
                self.eye_label.setText("")

        rect = self.floating_label.geometry()
        y = 0 if self._is_floating else 6
        rect.moveTo(self._label_x, y)
        self.floating_label.setGeometry(rect)
        self.floating_label.raise_()

    def _toggle_visibility(self, event):
        if self.input.echoMode() == QLineEdit.Password:
            self.input.setEchoMode(QLineEdit.Normal)
        else:
            self.input.setEchoMode(QLineEdit.Password)
        self.update_icon()

    def _on_text_changed(self, text):
        self.update_floating_label()
        if not self._valid:
            self.set_valid(True, "")

    def update_floating_label(self):
        has_text = bool(self.input.text())
        if has_text or self._focused:
            if not self._is_floating:
                self.float_anim.stop()
                end_rect = QRect(self._label_x, 0, self.floating_label.width(), 20)
                self.float_anim.setEndValue(end_rect)
                self.float_anim.start()
                font = self.floating_label.font()
                font.setPointSize(9)
                self.floating_label.setFont(font)
                self._is_floating = True
        else:
            if self._is_floating:
                self.float_anim.stop()
                end_rect = QRect(self._label_x, 6, self.floating_label.width(), 20)
                self.float_anim.setEndValue(end_rect)
                self.float_anim.start()
                font = self.floating_label.font()
                font.setPointSize(11)
                self.floating_label.setFont(font)
                self._is_floating = False
        self.floating_label.raise_()

    def update_theme_colors(self):
        is_dark = self.theme_manager.get_current_theme() == "dark"
        if is_dark:
            active_color = "#CBD5E1"
            inactive_color = "#F8FAFC"
        else:
            active_color = "#475569"
            inactive_color = "#0F172A"

        label_color = active_color if (self._is_floating or self._focused or self.input.text()) else inactive_color
        self.floating_label.setStyleSheet(f"background: transparent; border: none; color: {label_color}; font-weight: 500;")

        foreground = "#F8FAFC" if is_dark else "#0F172A"
        self.input.setStyleSheet(f"""
            QLineEdit {{
                border: none;
                background: transparent;
                background-color: transparent;
                font-size: 14px;
                padding: 0;
                margin: 0;
                color: {foreground};
                outline: none;
            }}
        """)
        self.error_label.setStyleSheet(
            f"color: {self.theme_manager.get_tokens().get('error', '#EF4444')}; font-size: 11px; padding-left: 4px; font-weight: 500; border: none; background: transparent;"
        )
        if self._valid:
            self._apply_valid_style(self.theme_manager.get_tokens())
        else:
            self._apply_invalid_style(self.theme_manager.get_tokens())

    def _update_border(self, active: bool):
        if not self._valid:
            return
        tokens = self.theme_manager.get_tokens()
        bg = tokens.get('background', '#FFFFFF')
        border = tokens.get('border', '#E2E8F0')
        primary = tokens.get('primary', '#006B3F')

        if active:
            border_color = primary
            border_width = "2px"
        else:
            border_color = border
            border_width = "1px"

        self.input_container.setStyleSheet(f"""
            QFrame#inputContainer {{
                background: {bg};
                border: {border_width} solid {border_color};
                border-radius: 12px;
            }}
        """)

    def _apply_valid_style(self, tokens):
        self.error_label.hide()
        self._update_border(self._focused)

    def _apply_invalid_style(self, tokens):
        error = tokens.get('error', '#EF4444')
        bg = tokens.get('background', '#FFFFFF')
        self.input_container.setStyleSheet(f"""
            QFrame#inputContainer {{
                background: {error}10;
                border: 2px solid {error};
                border-radius: 12px;
            }}
        """)
        self.error_label.show()

    def set_valid(self, valid: bool, error_msg: str = "", shake: bool = True):
        self._valid = valid
        self._error_msg = error_msg
        self.error_label.setText(error_msg)
        tokens = self.theme_manager.get_tokens()
        if valid:
            self._apply_valid_style(tokens)
        else:
            self._apply_invalid_style(tokens)
            if shake:
                self._shake()
        self.validChanged.emit(valid)

    def _shake(self):
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(200)
        orig = self.pos()
        anim.setKeyValueAt(0, orig)
        anim.setKeyValueAt(0.2, orig + QPoint(6, 0))
        anim.setKeyValueAt(0.4, orig - QPoint(6, 0))
        anim.setKeyValueAt(0.6, orig + QPoint(3, 0))
        anim.setKeyValueAt(0.8, orig - QPoint(3, 0))
        anim.setKeyValueAt(1, orig)
        anim.start()

    def text(self):
        return self.input.text()

    def clear(self):
        self.input.clear()
        self.set_valid(True)

    def setFocus(self):
        self.input.setFocus()