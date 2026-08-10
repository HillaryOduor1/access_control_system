"""
Enterprise-grade UI component library.All components are theme-aware and connect to ThemeManager automatically.
"""
from __future__ import annotations

import math
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QSizePolicy, QDialog, QDialogButtonBox, QMenu, QMenuBar, QApplication,
    QSpacerItem, QAbstractItemView, QGraphicsOpacityEffect, QTextEdit,
    QCheckBox, QRadioButton, QButtonGroup, QComboBox,
)
from PySide6.QtCore import (
    Qt, Signal, QSize, QPropertyAnimation, QEasingCurve, QTimer,
    QPoint, QRect, QRectF, QEvent,
)
from PySide6.QtGui import (
    QFont, QColor, QPalette, QIcon, QPixmap, QPainter, QBrush, QPen,
    QCursor, QFontMetrics, QPainterPath,
)

from core.icon_manager import IconManager
from core.theme_manager import ThemeManager

# Internal helpers

def _theme() -> ThemeManager:
    return ThemeManager()


def _tok() -> dict:
    return ThemeManager().get_tokens()


def _apply_scrollbar_style(widget: QWidget, tokens: dict):
    """Apply the ghost thin scrollbar style to any scroll-bearing widget."""
    widget.setStyleSheet(widget.styleSheet() + f"""
        QScrollBar:vertical {{
            background: transparent;
            width: 4px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {tokens["border"]};
            border-radius: 2px;
            min-height: 36px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {tokens["border-strong"]};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 4px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {tokens["border"]};
            border-radius: 2px;
            min-width: 36px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {tokens["border-strong"]}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """)

# ShadcnButton

class ShadcnButton(QPushButton):
    """
    Multi-variant push button.Variants: default | destructive | outline | secondary | ghost | link | icon
    Sizes:    sm | default | lg
    """

    def __init__(
        self,
        text: str = "",
        variant: str = "default",
        size: str = "default",
        icon: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        self.variant = variant
        self.size = size
        self.icon_name = icon
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.theme_manager = _theme()
        self.update_theme()
        if icon:
            self.setIcon(IconManager().get_icon(icon, size=self._icon_size(), state="default"))
            self.setIconSize(self._icon_size())
        self.theme_manager.theme_changed.connect(self.update_theme)

    # public so sidebar can call it explicitly after restoring its stylesheet
    def update_theme(self):
        # Nav buttons inside the sidebar own their own stylesheet — skip.
        if self.property("class") == "nav-button":
            self.setStyleSheet("")
            return

        t = self.theme_manager.get_tokens()
        r = t["radius"]
        r_sm = t["radius-sm"]

        # ── variant styles ──
        if self.variant == "default":
            base  = f"background:{t['primary']}; color:{t['primary-foreground']}; border:none;"
            hover = f"background:{t['primary-hover']};"
            press = f"background:{t['primary-hover']}; opacity:0.9;"
        elif self.variant == "destructive":
            base  = f"background:{t['destructive']}; color:{t['destructive-foreground']}; border:none;"
            hover = f"background:{t['destructive-hover']};"
            press = f"background:{t['destructive-hover']};"
        elif self.variant == "outline":
            base  = f"background:transparent; color:{t['foreground']}; border:1px solid {t['border']};"
            hover = f"background:{t['secondary']}; border-color:{t['border-strong']};"
            press = f"background:{t['accent']};"
        elif self.variant == "secondary":
            base  = f"background:{t['secondary']}; color:{t['secondary-foreground']}; border:none;"
            hover = f"background:{t['accent']};"
            press = f"background:{t['surface-active']};"
        elif self.variant == "ghost":
            base  = f"background:transparent; color:{t['foreground']}; border:none;"
            hover = f"background:{t['secondary']};"
            press = f"background:{t['accent']};"
        elif self.variant == "link":
            base  = f"background:transparent; color:{t['primary']}; border:none; text-decoration:underline;"
            hover = f"color:{t['primary-hover']};"
            press = f"color:{t['primary-hover']};"
        else:
            base = hover = press = ""

        # ── size ──
        if self.size == "sm":
            padding, fsize, height = "0 11px", "12px", "30px"
        elif self.size == "lg":
            padding, fsize, height = "0 22px", "15px", "44px"
        elif self.size == "icon":
            padding, fsize, height = "0", "14px", "36px"
        else:
            padding, fsize, height = "0 15px", "13px", "36px"

        # Icon-only buttons get a fixed square
        icon_only = bool(self.icon_name and not self.text())
        if icon_only or self.variant == "icon":
            sq = {"sm": 28, "lg": 42, "icon": 36}.get(self.size, 36)
            self.setFixedSize(sq, sq)
            padding = "0"

        checked_bg = (
            t["primary-subtle"] if self.variant == "ghost"
            else t["secondary"]
        )
        checked_fg = t["primary"] if self.variant == "ghost" else t["foreground"]

        self.setStyleSheet(f"""
            QPushButton {{
                {base}
                padding: {padding};
                height: {height};
                font-size: {fsize};
                font-weight: 500;
                border-radius: {r};
                text-align: center;
            }}
            QPushButton:hover {{ {hover} }}
            QPushButton:pressed {{ {press} }}
            QPushButton:checked {{
                background: {checked_bg};
                color: {checked_fg};
            }}
            QPushButton:disabled {{ opacity: 0.45; }}
        """)

        if self.icon_name:
            self.setIcon(
                IconManager().get_icon(self.icon_name, size=self._icon_size(), state="default")
            )

    def _icon_size(self) -> QSize:
        return {"sm": QSize(14, 14), "lg": QSize(20, 20)}.get(self.size, QSize(16, 16))

# ShadcnInput

class ShadcnInput(QLineEdit):
    """Single-line text input with theme-aware styling."""

    def __init__(self, placeholder: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {t["input"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius"]};
                padding: 7px 11px;
                font-size: 13px;
                color: {t["foreground"]};
                selection-background-color: {t["primary"]};
                selection-color: {t["primary-foreground"]};
            }}
            QLineEdit:focus {{
                border: 1.5px solid {t["ring"]};
                background-color: {t["surface"]};
            }}
            QLineEdit::placeholder {{ color: {t["muted-foreground"]}; }}
            QLineEdit:disabled {{
                background-color: {t["muted"]};
                color: {t["muted-foreground"]};
            }}
        """)

# ShadcnTextArea

class ShadcnTextArea(QTextEdit):
    """Multi-line text area."""

    def __init__(self, placeholder: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: {t["input"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius"]};
                padding: 9px 11px;
                font-size: 13px;
                color: {t["foreground"]};
                selection-background-color: {t["primary"]};
            }}
            QTextEdit:focus {{ border: 1.5px solid {t["ring"]}; }}
        """)

# ShadcnComboBox

class ShadcnComboBox(QComboBox):
    """Themed combo box / select."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {t["input"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius"]};
                padding: 7px 32px 7px 11px;
                font-size: 13px;
                color: {t["foreground"]};
            }}
            QComboBox:focus {{ border: 1.5px solid {t["ring"]}; }}
            QComboBox::drop-down {{
                border: none;
                width: 28px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                width: 12px; height: 12px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {t["popover"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius"]};
                selection-background-color: {t["secondary"]};
                selection-color: {t["foreground"]};
                padding: 4px;
                font-size: 13px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 12px;
                border-radius: {t["radius-sm"]};
                min-height: 28px;
            }}
        """)

# ShadcnCheckBox

class ShadcnCheckBox(QCheckBox):
    """Themed checkbox."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            QCheckBox {{
                font-size: 13px;
                color: {t["foreground"]};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1.5px solid {t["border-strong"]};
                border-radius: {t["radius-sm"]};
                background: {t["input"]};
            }}
            QCheckBox::indicator:checked {{
                background: {t["primary"]};
                border-color: {t["primary"]};
            }}
            QCheckBox::indicator:hover {{
                border-color: {t["ring"]};
            }}
            QCheckBox:disabled {{ color: {t["muted-foreground"]}; opacity: 0.6; }}
        """)

# ShadcnRadioButton

class ShadcnRadioButton(QRadioButton):
    """Themed radio button."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            QRadioButton {{
                font-size: 13px;
                color: {t["foreground"]};
                spacing: 8px;
            }}
            QRadioButton::indicator {{
                width: 16px;
                height: 16px;
                border: 1.5px solid {t["border-strong"]};
                border-radius: 8px;
                background: {t["input"]};
            }}
            QRadioButton::indicator:checked {{
                background: {t["primary"]};
                border-color: {t["primary"]};
            }}
            QRadioButton::indicator:hover {{ border-color: {t["ring"]}; }}
        """)


# ShadcnLabel / ShadcnCaption / ShadcnHeading

class ShadcnLabel(QLabel):
    """Form field label — medium weight, 13 px."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {t['foreground']};"
        )


class ShadcnCaption(QLabel):
    """Small helper / caption text — 11 px muted."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(
            f"font-size: 11px; color: {t['muted-foreground']}; background: transparent;"
        )


class ShadcnHeading(QLabel):
    """
    Section heading.
    level: 1=24px/600  2=18px/600  3=15px/600  4=13px/600
    """

    _SIZES = {1: ("22px", "600"), 2: ("17px", "600"), 3: ("14px", "600"), 4: ("13px", "600")}

    def __init__(self, text: str = "", level: int = 2, parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.level = max(1, min(4, level))
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        fsize, fweight = self._SIZES[self.level]
        self.setStyleSheet(
            f"font-size: {fsize}; font-weight: {fweight}; color: {t['foreground']}; background: transparent;"
        )


# ShadcnSeparator

class ShadcnSeparator(QFrame):
    """1 px hairline separator, horizontal or vertical."""

    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Horizontal,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        if orientation == Qt.Orientation.Horizontal:
            self.setFrameShape(QFrame.Shape.HLine)
            self.setFixedHeight(1)
        else:
            self.setFrameShape(QFrame.Shape.VLine)
            self.setFixedWidth(1)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"background-color: {t['border']}; border: none;")

# ShadcnCard

class ShadcnCard(QFrame):
    """
    Elevated card container with optional header / content / footer sections.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ShadcnCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._header = None
        self._content = None
        self._footer = None
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            #ShadcnCard {{
                background-color: {t["surface"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius-lg"]};
            }}
        """)

    def _swap(self, attr: str, widget: QWidget):
        old = getattr(self, attr)
        if old:
            self._layout.removeWidget(old)
            old.deleteLater()
        setattr(self, attr, widget)
        # Maintain order: header → content → footer
        self._layout.addWidget(widget)

    def set_header(self, widget: QWidget):  self._swap("_header", widget)
    def set_content(self, widget: QWidget): self._swap("_content", widget)
    def set_footer(self, widget: QWidget):  self._swap("_footer", widget)


class CardHeader(QWidget):
    def __init__(self, title: str = "", description: str = "",
                 action: Optional[QWidget] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme_manager = _theme()
        lo = QHBoxLayout(self)
        lo.setContentsMargins(20, 18, 20, 10)
        text_lo = QVBoxLayout()
        self.title_lbl = ShadcnHeading(title, level=3)
        text_lo.addWidget(self.title_lbl)
        if description:
            self.desc_lbl = ShadcnCaption(description)
            text_lo.addWidget(self.desc_lbl)
        lo.addLayout(text_lo, 1)
        if action:
            lo.addWidget(action)
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        pass  # children handle themselves


class CardContent(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 4, 20, 20)
        self.main_layout.setSpacing(14)

    def addWidget(self, w: QWidget): self.main_layout.addWidget(w)
    # Back-compat alias
    layout = property(lambda self: self.main_layout)


class CardFooter(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme_manager = _theme()
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(20, 12, 20, 18)
        self.main_layout.setSpacing(10)
        self.setObjectName("cardFooter")
        self.theme_manager.theme_changed.connect(self.update_theme)
        self.update_theme()

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"#cardFooter {{ border-top: 1px solid {t['border']}; }}")

    def addWidget(self, w: QWidget): self.main_layout.addWidget(w)
    layout = property(lambda self: self.main_layout)


# ShadcnAvatar

class ShadcnAvatar(QFrame):
    """
    Circular avatar — shows image if provided, else coloured initials.
    """

    # Deterministic accent colours for initials
    _PALETTE = [
        ("#dbeafe", "#1d4ed8"), ("#dcfce7", "#15803d"), ("#fce7f3", "#9d174d"),
        ("#fef3c7", "#92400e"), ("#ede9fe", "#5b21b6"), ("#ffedd5", "#9a3412"),
        ("#cffafe", "#164e63"), ("#f0fdf4", "#166534"),
    ]

    def __init__(self, image_path: Optional[str] = None, fallback_text: str = "",
                 size: int = 32, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.avatar_size = size
        self.image_path = image_path
        self.fallback_text = fallback_text
        self.setFixedSize(size, size)
        self.theme_manager = _theme()
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(self.label)
        self._set_content()
        self.theme_manager.theme_changed.connect(self._set_content)

    def _pick_colour(self) -> tuple[str, str]:
        idx = sum(ord(c) for c in self.fallback_text) % len(self._PALETTE)
        return self._PALETTE[idx]

    def _set_content(self):
        if self.image_path:
            pix = QPixmap(self.image_path)
            if not pix.isNull():
                pix = pix.scaled(
                    self.avatar_size, self.avatar_size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.setStyleSheet(
                    f"border-radius: {self.avatar_size // 2}px; background: transparent;"
                )
                self.label.setPixmap(pix)
                self.label.setScaledContents(True)
                return
        bg, fg = self._pick_colour()
        initials = (self.fallback_text[:2]).upper() if self.fallback_text else "?"
        fsize = max(9, self.avatar_size // 3)
        self.setStyleSheet(
            f"border-radius: {self.avatar_size // 2}px; background: {bg};"
        )
        self.label.setStyleSheet(
            f"font-size: {fsize}px; font-weight: 600; color: {fg}; background: transparent;"
        )
        self.label.setText(initials)
        self.label.setPixmap(QPixmap())

# ShadcnBadge

class ShadcnBadge(QLabel):
    """
    Inline status badge / pill.
    Variants: default | secondary | destructive | outline | success | warning | info
    """

    def __init__(self, text: str = "", variant: str = "default",
                 parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.variant = variant
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        v = self.variant
        pairs = {
            "default":     (t["primary"],            t["primary-foreground"]),
            "secondary":   (t["secondary"],           t["secondary-foreground"]),
            "destructive": (t["destructive-subtle"],  t["destructive"]),
            "outline":     ("transparent",            t["foreground"]),
            "success":     (t["success-subtle"],      t["success-foreground"]),
            "warning":     (t["warning-subtle"],      t["warning-foreground"]),
            "info":        (t["info-subtle"],         t["info-foreground"]),
        }
        bg, fg = pairs.get(v, pairs["default"])
        border = (f"border: 1px solid {t['border']};" if v == "outline"
                  else f"border: 1px solid {bg};")
        self.setStyleSheet(f"""
            background: {bg};
            color: {fg};
            {border}
            border-radius: 99px;
            padding: 2px 9px;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.02em;
        """)

# ShadcnAlert

class ShadcnAlert(QFrame):
    """
    Inline alert banner.
    Variants: default | destructive | success | warning | info
    """

    def __init__(self, title: str, description: str = "",
                 variant: str = "default", icon_name: Optional[str] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ShadcnAlert")
        self.title_text = title
        self.desc_text = description
        self.alert_variant = variant
        self.icon_name = icon_name

        lo = QHBoxLayout(self)
        lo.setContentsMargins(14, 12, 14, 12)
        lo.setSpacing(12)
        lo.setAlignment(Qt.AlignTop)

        if icon_name:
            self.icon_lbl = QLabel()
            self.icon_lbl.setFixedSize(18, 18)
            lo.addWidget(self.icon_lbl, 0, Qt.AlignTop)

        text_lo = QVBoxLayout()
        text_lo.setSpacing(3)
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("alertTitle")
        text_lo.addWidget(self.title_lbl)
        if description:
            self.desc_lbl = QLabel(description)
            self.desc_lbl.setWordWrap(True)
            self.desc_lbl.setObjectName("alertDesc")
            text_lo.addWidget(self.desc_lbl)
        lo.addLayout(text_lo, 1)

        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        v = self.alert_variant
        configs = {
            "default":     (t["surface"],            t["border"],            t["foreground"]),
            "destructive": (t["destructive-subtle"],  t["destructive"],       t["destructive"]),
            "success":     (t["success-subtle"],      t["success"],           t["success-foreground"]),
            "warning":     (t["warning-subtle"],      t["warning"],           t["warning-foreground"]),
            "info":        (t["info-subtle"],         t["info"],              t["info-foreground"]),
        }
        bg, border_col, accent = configs.get(v, configs["default"])
        self.setStyleSheet(f"""
            #ShadcnAlert {{
                background: {bg};
                border: 1px solid {border_col};
                border-left: 3px solid {accent};
                border-radius: {t["radius"]};
            }}
            #alertTitle {{
                font-size: 13px;
                font-weight: 600;
                color: {accent};
            }}
            #alertDesc {{
                font-size: 12px;
                color: {t["foreground-secondary"]};
            }}
        """)
        if self.icon_name and hasattr(self, "icon_lbl"):
            icon = IconManager().get_icon(self.icon_name, size=QSize(18, 18), state="active")
            self.icon_lbl.setPixmap(icon.pixmap(18, 18))


# ShadcnAlertDialog

class ShadcnAlertDialog(QDialog):
    """Modal confirmation dialog."""

    def __init__(self, title: str, description: str,
                 cancel_text: str = "Cancel", action_text: str = "Continue",
                 destructive: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setObjectName("ShadcnAlertDialog")
        self.setFixedWidth(420)

        lo = QVBoxLayout(self)
        lo.setContentsMargins(24, 24, 24, 20)
        lo.setSpacing(14)

        self.title_lbl = ShadcnHeading(title, level=3)
        lo.addWidget(self.title_lbl)

        self.desc_lbl = ShadcnCaption(description)
        lo.addWidget(self.desc_lbl)

        lo.addSpacing(4)
        btn_lo = QHBoxLayout()
        btn_lo.setSpacing(8)
        btn_lo.addStretch()
        self.cancel_btn = ShadcnButton(cancel_text, variant="outline", size="sm")
        self.cancel_btn.clicked.connect(self.reject)
        btn_lo.addWidget(self.cancel_btn)
        variant = "destructive" if destructive else "default"
        self.action_btn = ShadcnButton(action_text, variant=variant, size="sm")
        self.action_btn.clicked.connect(self.accept)
        btn_lo.addWidget(self.action_btn)
        lo.addLayout(btn_lo)

        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            #ShadcnAlertDialog {{
                background: {t["surface"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius-xl"]};
            }}
        """)

# ShadcnDataTable

class ShadcnDataTable(QTableWidget):
    """
    Enterprise data table with alternating rows, ghost scrollbars,
    and column-resize support.
    """

    def __init__(self, columns: List[str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(True)
        hdr.setHighlightSections(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(44)
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {t["surface"]};
                alternate-background-color: {t["muted"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius-lg"]};
                gridline-color: transparent;
                font-size: 13px;
                color: {t["foreground"]};
                outline: none;
            }}
            QTableWidget::item {{
                padding: 0 14px;
                border-bottom: 1px solid {t["border"]};
                color: {t["foreground"]};
            }}
            QTableWidget::item:selected {{
                background: {t["primary-subtle"]};
                color: {t["primary"]};
            }}
            QTableWidget::item:hover {{
                background: {t["surface-hover"]};
            }}
            QHeaderView::section {{
                background: {t["muted"]};
                color: {t["muted-foreground"]};
                padding: 0 14px;
                height: 38px;
                border: none;
                border-bottom: 1px solid {t["border"]};
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }}
            QHeaderView::section:first {{
                border-top-left-radius: {t["radius-lg"]};
            }}
            QHeaderView::section:last {{
                border-top-right-radius: {t["radius-lg"]};
            }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {t["border"]}; border-radius: 2px; min-height: 32px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {t["border-strong"]}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: transparent; height: 4px; margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {t["border"]}; border-radius: 2px; min-width: 32px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {t["border-strong"]}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        """)

    def populate(self, data: list, empty_message: str = "No records found"):
        self.setRowCount(0)
        if not data:
            self.setRowCount(1)
            item = QTableWidgetItem(empty_message)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            t = _tok()
            item.setForeground(QColor(t["muted-foreground"]))
            for col in range(self.columnCount()):
                self.setItem(0, col, QTableWidgetItem("") if col else item)
            return
        self.setRowCount(len(data))
        for row, row_data in enumerate(data):
            for col, val in enumerate(row_data):
                self.setItem(row, col, QTableWidgetItem(str(val)))

# ShadcnSkeleton

class ShadcnSkeleton(QFrame):
    """Pulsing placeholder while content loads."""

    def __init__(self, width: int = 120, height: int = 18,
                 rounded: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._rounded = rounded
        self._state = False
        self.theme_manager = _theme()
        self.update_theme()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self._timer.start(700)
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        r = "99px" if self._rounded else t["radius"]
        self._style_a = f"background:{t['muted']}; border-radius:{r}; border:none;"
        self._style_b = f"background:{t['border']}; border-radius:{r}; border:none;"
        self.setStyleSheet(self._style_a)

    def _pulse(self):
        self._state = not self._state
        self.setStyleSheet(self._style_b if self._state else self._style_a)

# ShadcnToast

class ShadcnToast(QFrame):
    """
    Transient notification that auto-dismisses.
    Variants: default | success | destructive | warning | info
    """

    def __init__(self, message: str, description: str = "",
                 variant: str = "default", duration: int = 3500,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setObjectName("ShadcnToast")
        self.toast_variant = variant

        lo = QHBoxLayout(self)
        lo.setContentsMargins(14, 12, 14, 12)
        lo.setSpacing(10)

        # Accent dot
        dot = QLabel()
        dot.setFixedSize(8, 8)
        t = _tok()
        colours = {
            "success":     t["success"],
            "destructive": t["destructive"],
            "warning":     t["warning"],
            "info":        t["info"],
        }
        dot_col = colours.get(variant, t["primary"])
        dot.setStyleSheet(f"background:{dot_col}; border-radius:4px;")
        lo.addWidget(dot, 0, Qt.AlignTop | Qt.AlignVCenter)

        text_lo = QVBoxLayout()
        text_lo.setSpacing(2)
        msg_lbl = QLabel(message)
        msg_lbl.setObjectName("toastMsg")
        text_lo.addWidget(msg_lbl)
        if description:
            desc_lbl = QLabel(description)
            desc_lbl.setObjectName("toastDesc")
            desc_lbl.setWordWrap(True)
            text_lo.addWidget(desc_lbl)
        lo.addLayout(text_lo, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(18, 18)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.clicked.connect(self.close)
        lo.addWidget(close_btn, 0, Qt.AlignTop)

        self.setFixedWidth(340)
        self.theme_manager = _theme()
        self.update_theme()
        self.move(self._position())
        self.show()
        QTimer.singleShot(duration, self.close)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            #ShadcnToast {{
                background: {t["surface"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius-lg"]};
            }}
            #toastMsg {{
                font-size: 13px;
                font-weight: 500;
                color: {t["foreground"]};
                background: transparent;
            }}
            #toastDesc {{
                font-size: 12px;
                color: {t["muted-foreground"]};
                background: transparent;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                color: {t["muted-foreground"]};
                font-size: 11px;
                border-radius: 4px;
                padding: 0;
            }}
            QPushButton:hover {{ background: {t["secondary"]}; }}
        """)

    def _position(self) -> QPoint:
        screen = QApplication.primaryScreen().availableGeometry()
        return QPoint(screen.right() - self.width() - 20,
                      screen.bottom() - self.height() - 20)

# ShadcnSheet

class ShadcnSheet(QDialog):
    """Slide-in side panel / drawer."""

    def __init__(self, title: str, description: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setObjectName("ShadcnSheet")
        self.setFixedWidth(420)

        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setObjectName("sheetHeader")
        hdr.setFixedHeight(58)
        hdr_lo = QHBoxLayout(hdr)
        hdr_lo.setContentsMargins(22, 0, 16, 0)
        hdr_lo.setSpacing(10)
        self.title_lbl = ShadcnHeading(title, level=3)
        hdr_lo.addWidget(self.title_lbl)
        hdr_lo.addStretch()
        close_btn = ShadcnButton("✕", variant="ghost", size="sm")
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self.close)
        hdr_lo.addWidget(close_btn)
        lo.addWidget(hdr)

        sep = ShadcnSeparator()
        lo.addWidget(sep)

        # Scroll content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(22, 18, 22, 18)
        self.content_layout.setSpacing(14)
        if description:
            self.content_layout.addWidget(ShadcnCaption(description))
        scroll.setWidget(self.content_widget)
        lo.addWidget(scroll, 1)

        # Footer
        self.footer = QWidget()
        self.footer.setObjectName("sheetFooter")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(22, 14, 22, 18)
        self.footer_layout.setSpacing(8)
        lo.addWidget(self.footer)

        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            #ShadcnSheet {{
                background: {t["surface"]};
                border-left: 1px solid {t["border"]};
            }}
            #sheetHeader {{
                background: {t["surface"]};
            }}
            #sheetFooter {{
                background: {t["surface"]};
                border-top: 1px solid {t["border"]};
            }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {t["border"]}; border-radius: 2px; min-height: 32px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def add_widget(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def add_button(self, button: QWidget):
        self.footer_layout.addWidget(button)

# ShadcnPagination

class ShadcnPagination(QWidget):
    page_changed = Signal(int)

    def __init__(self, total_pages: int = 1, current: int = 1,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.total = total_pages
        self.current = current
        self._btn_lo = QHBoxLayout(self)
        self._btn_lo.setSpacing(4)
        self._btn_lo.setContentsMargins(0, 0, 0, 0)
        self._page_btns: List[ShadcnButton] = []

        self.prev_btn = ShadcnButton("← Prev", variant="outline", size="sm")
        self.prev_btn.clicked.connect(self._prev)
        self.next_btn = ShadcnButton("Next →", variant="outline", size="sm")
        self.next_btn.clicked.connect(self._next)

        self._btn_lo.addWidget(self.prev_btn)
        self._render_pages()
        self._btn_lo.addWidget(self.next_btn)

        self.theme_manager = _theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def _render_pages(self):
        for b in self._page_btns:
            self._btn_lo.removeWidget(b)
            b.deleteLater()
        self._page_btns.clear()

        start = max(1, self.current - 2)
        end = min(self.total, self.current + 2)
        insert_at = 1

        for p in range(start, end + 1):
            v = "default" if p == self.current else "outline"
            btn = ShadcnButton(str(p), variant=v, size="sm")
            btn.setFixedWidth(34)
            btn.clicked.connect(lambda _=False, page=p: self._goto(page))
            self._btn_lo.insertWidget(insert_at, btn)
            self._page_btns.append(btn)
            insert_at += 1

        self.prev_btn.setEnabled(self.current > 1)
        self.next_btn.setEnabled(self.current < self.total)

    def _goto(self, page: int):
        if 1 <= page <= self.total:
            self.current = page
            self._render_pages()
            self.page_changed.emit(self.current)

    def _prev(self): self._goto(self.current - 1)
    def _next(self): self._goto(self.current + 1)

    def update_theme(self):
        for b in [self.prev_btn, self.next_btn, *self._page_btns]:
            b.update_theme()

# ShadcnField / ShadcnFieldGroup

class ShadcnField(QWidget):
    """
    Labelled form field wrapper.
    orientation: "vertical" (label above) | "horizontal" (label left)
    """

    def __init__(self, label: str = "", description: str = "", error: str = "",
                 orientation: str = "vertical", required: bool = False,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme_manager = _theme()
        self._error = error

        if orientation == "vertical":
            lo = QVBoxLayout(self)
            lo.setContentsMargins(0, 0, 0, 0)
            lo.setSpacing(5)
        else:
            lo = QHBoxLayout(self)
            lo.setContentsMargins(0, 0, 0, 0)
            lo.setSpacing(12)
            lo.setAlignment(Qt.AlignVCenter)

        if label:
            lbl_text = f"{label} <span style='color:#ef4444'>*</span>" if required else label
            self.label_w = ShadcnLabel()
            self.label_w.setText(lbl_text)
            if orientation == "horizontal":
                self.label_w.setFixedWidth(130)
            lo.addWidget(self.label_w)

        self.input_container = QWidget()
        self.input_lo = QVBoxLayout(self.input_container)
        self.input_lo.setContentsMargins(0, 0, 0, 0)
        self.input_lo.setSpacing(4)
        lo.addWidget(self.input_container, 1)

        if description:
            self.desc_w = ShadcnCaption(description)
            self.input_lo.addWidget(self.desc_w)

        if error:
            self.error_w = ShadcnCaption(error)
            t = self.theme_manager.get_tokens()
            self.error_w.setStyleSheet(f"font-size:11px; color:{t['destructive']};")
            self.input_lo.addWidget(self.error_w)
        else:
            self.error_w = None

        self.theme_manager.theme_changed.connect(self.update_theme)

    def set_input(self, widget: QWidget):
        # Insert before description/error labels
        self.input_lo.insertWidget(0, widget)

    def set_error(self, msg: str):
        t = self.theme_manager.get_tokens()
        if self.error_w:
            self.error_w.setText(msg)
        elif msg:
            self.error_w = ShadcnCaption(msg)
            self.error_w.setStyleSheet(f"font-size:11px; color:{t['destructive']};")
            self.input_lo.addWidget(self.error_w)

    def update_theme(self):
        if self.error_w:
            t = self.theme_manager.get_tokens()
            self.error_w.setStyleSheet(f"font-size:11px; color:{t['destructive']};")


class ShadcnFieldGroup(QWidget):
    """Groups multiple ShadcnField widgets with consistent spacing."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(16)

    def add_field(self, field: QWidget):
        self.main_layout.addWidget(field)

# ShadcnItem (list row)

class ShadcnItem(QFrame):
    """
    Single-row list item with title, optional description, and action area.
    """
    clicked = Signal()

    def __init__(self, title: str, description: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ShadcnItem")
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        lo = QHBoxLayout(self)
        lo.setContentsMargins(14, 10, 14, 10)
        lo.setSpacing(10)

        text_lo = QVBoxLayout()
        text_lo.setSpacing(2)
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("itemTitle")
        text_lo.addWidget(self.title_lbl)
        if description:
            self.desc_lbl = QLabel(description)
            self.desc_lbl.setObjectName("itemDesc")
            text_lo.addWidget(self.desc_lbl)
        lo.addLayout(text_lo, 1)

        self.action_lo = QHBoxLayout()
        self.action_lo.setSpacing(6)
        lo.addLayout(self.action_lo)

        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            #ShadcnItem {{
                background: {t["surface"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius"]};
            }}
            #ShadcnItem:hover {{ background: {t["surface-hover"]}; }}
            #itemTitle {{
                font-size: 13px;
                font-weight: 500;
                color: {t["foreground"]};
                background: transparent;
            }}
            #itemDesc {{
                font-size: 12px;
                color: {t["muted-foreground"]};
                background: transparent;
            }}
        """)

    def add_action(self, widget: QWidget):
        self.action_lo.addWidget(widget)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

# ShadcnMenubar / ShadcnNavigationMenu

class ShadcnMenubar(QMenuBar):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"""
            QMenuBar {{
                background: {t["surface"]};
                border-bottom: 1px solid {t["border"]};
                padding: 2px 8px;
                font-size: 13px;
                color: {t["foreground"]};
            }}
            QMenuBar::item {{
                background: transparent;
                padding: 5px 10px;
                border-radius: {t["radius-sm"]};
            }}
            QMenuBar::item:selected {{ background: {t["secondary"]}; }}
            QMenu {{
                background: {t["popover"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius"]};
                padding: 4px;
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 6px 22px 6px 12px;
                border-radius: {t["radius-sm"]};
                color: {t["foreground"]};
            }}
            QMenu::item:selected {{ background: {t["secondary"]}; }}
            QMenu::separator {{ height:1px; background:{t["border"]}; margin:4px 8px; }}
        """)


class ShadcnNavigationMenu(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(12, 6, 12, 6)
        lo.setSpacing(4)
        self.theme_manager = _theme()
        self.update_theme()
        self.theme_manager.theme_changed.connect(self.update_theme)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        self.setStyleSheet(f"background:{t['surface']}; border-bottom:1px solid {t['border']};")

    def add_item(self, text: str, callback):
        btn = ShadcnButton(text, variant="ghost", size="sm")
        btn.clicked.connect(callback)
        self.layout().addWidget(btn)
