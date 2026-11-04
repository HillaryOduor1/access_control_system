# widgets/dashboard.py
"""
Dashboard card widget.

Fixes
-----
- Was importing from `utils.icon_manager`, which does not exist.
  Changed to `core.icon_manager` (though this file doesn't actually
  use IconManager, so the import is removed).
- Was using hardcoded hex colors (`#9CA3AF`) that ignored the theme.
  Now uses ThemeManager tokens and subscribes to theme/appearance
  changes so the card recolors when the user toggles theme.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

from core.theme_manager import ThemeManager


class DashboardCard(QWidget):
    """A simple labelled value card that respects the active theme."""

    def __init__(self, title: str, value: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("dashboard-card")

        self._theme_manager = ThemeManager()

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        self._title_lbl = QLabel(title)
        self._title_lbl.setObjectName("dashboard-card-title")

        self._value_lbl = QLabel(value)
        self._value_lbl.setObjectName("dashboard-card-value")

        layout.addWidget(self._title_lbl)
        layout.addWidget(self._value_lbl)

        self._apply_theme()

        self._theme_manager.register_widget(
            self,
            on_theme_changed=self._on_theme_changed,
            on_appearance_changed=self._on_appearance_changed,
        )

    def _apply_theme(self):
        t = self._theme_manager.get_tokens()
        base = t.get("font_size", 13)

        # Card body
        self.setStyleSheet(f"""
            #dashboard-card {{
                background-color: {t['surface']};
                border: 1px solid {t['border']};
                border-radius: {t['radius-lg']};
            }}
            #dashboard-card-title {{
                color: {t['muted-foreground']};
                font-size: {max(11, base - 1)}px;
                background: transparent;
            }}
            #dashboard-card-value {{
                color: {t['foreground']};
                font-size: {base + 11}px;
                font-weight: 700;
                background: transparent;
            }}
        """)

    def _on_theme_changed(self, *_):
        self._apply_theme()

    def _on_appearance_changed(self, *_):
        self._apply_theme()

    def set_value(self, value: str):
        self._value_lbl.setText(str(value))

    def set_title(self, title: str):
        self._title_lbl.setText(title)

    def on_theme_changed(self, theme: str):
        """Public hook kept for compatibility with MainApp._on_theme_changed."""
        self._apply_theme()

