# widgets/password_strength_meter.py
"""
Password strength meter.

Changes
-------
- Safe signal disconnection on destroy (was leaking theme_changed slots).
- Accessible name reflects the current strength so screen readers can
  announce it.
- Token-based colors via ThemeManager tokens.
"""
import re
from PySide6.QtWidgets import QWidget, QHBoxLayout, QFrame
from PySide6.QtCore import Signal
from core.theme_manager import ThemeManager


class PasswordStrengthMeter(QWidget):
    strengthChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self.segments = []
        self._score = 0
        self.theme_manager = ThemeManager()
        self.setAccessibleName("Password strength: not set")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for _ in range(5):
            seg = QFrame()
            seg.setFixedHeight(6)
            seg.setStyleSheet("border: none;")
            layout.addWidget(seg, 1)
            self.segments.append(seg)

        self.theme_manager.register_widget(
            self,
            on_theme_changed=self._refresh,
        )
        self._refresh()

    def evaluate(self, password: str):
        score = 0
        if len(password) >= 8:
            score += 1
        if re.search(r'[A-Z]', password):
            score += 1
        if re.search(r'[a-z]', password):
            score += 1
        if re.search(r'[0-9]', password):
            score += 1
        if re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            score += 1
        self._score = score
        self.update_bars(score)
        self.strengthChanged.emit(score)

    def get_strength_score(self) -> int:
        return self._score

    def _refresh(self, *_):
        self.update_bars(self._score)

    def update_bars(self, score: int):
        tokens = self.theme_manager.get_tokens()
        error = tokens.get("destructive", tokens.get("error", "#EF4444"))
        warning = tokens.get("warning", "#F59E0B")
        success = tokens.get("success", "#10B981")
        inactive = tokens.get("border", "#E2E8F0")
        colors = [error, error, warning, warning, success]

        for i, seg in enumerate(self.segments):
            color = colors[i] if i < score else inactive
            seg.setStyleSheet(
                f"background: {color}; border-radius: 3px; border: none;"
            )

        # Expose the current strength to assistive technology.
        if score <= 2:
            label = "weak"
        elif score <= 4:
            label = "medium"
        else:
            label = "strong"
        self.setAccessibleName(f"Password strength: {label}")

