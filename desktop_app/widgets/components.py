# widgets/components.py
"""
Enterprise-grade UI component library.

Performance
-----------
Every theme-aware widget caches the QSS string it last applied. When
update_theme() is called and the computed string is identical to the
cached one, the widget returns immediately without calling
setStyleSheet().

Accessibility
-------------
Every component sets an accessible name and (where useful) description.
Focus rings are drawn via the `ring` token so keyboard users can see
where focus is. Icon-only buttons get their tooltip promoted to an
accessible name.

Reduced motion
--------------
Animations consult ThemeManager.is_reduced_effects() and set their
duration to 0 when the user has asked to reduce visual effects.

Spinner spacing
---------------
ShadcnButton positions the loading spinner + text pair as a single
centered group. The gap scales with the length of the loading label
so short labels stay tight and long labels stay airy.
"""
from __future__ import annotations

import math
from typing import Optional, List, Sequence

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QSizePolicy, QDialog, QDialogButtonBox, QMenu, QMenuBar, QApplication,
    QSpacerItem, QAbstractItemView, QGraphicsOpacityEffect, QTextEdit,
    QCheckBox, QRadioButton, QButtonGroup, QComboBox, QStyle,
)
from PySide6.QtCore import (
    Qt, Signal, QSize, QPropertyAnimation, QEasingCurve, QTimer,
    QPoint, QRect, QRectF, QEvent, QObject,
)
from PySide6.QtGui import (
    QFont, QColor, QPalette, QIcon, QPixmap, QPainter, QBrush, QPen,
    QCursor, QFontMetrics, QPainterPath, QKeyEvent,
)

from core.icon_manager import IconManager
from core.theme_manager import ThemeManager
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _theme() -> ThemeManager:
    return ThemeManager()


def _tok() -> dict:
    return ThemeManager().get_tokens()


def _apply_qss(widget: QWidget, key: str, builder) -> None:
    """Apply cached QSS to a widget, skipping setStyleSheet when unchanged."""
    tm = ThemeManager()
    qss = tm.get_qss(key, builder)

    last = getattr(widget, "_last_qss", None)
    if last == qss:
        return

    widget.setStyleSheet(qss)
    widget._last_qss = qss


def _reduced_motion() -> bool:
    try:
        return ThemeManager().is_reduced_effects()
    except Exception:
        return False


# =============================================================================
# LOADING SPINNER
# =============================================================================

class ShadcnLoadingSpinner(QWidget):
    _SIZE_MAP = {"sm": 16, "default": 20, "lg": 28}

    def __init__(self, size: str = "default",
                 color: Optional[str] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._px = self._SIZE_MAP.get(size, 20)
        self.setFixedSize(self._px, self._px)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._angle = 0
        self._color_override = color
        self._theme_manager = _theme()
        self._color = self._resolve_color()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._interval_ms = 16
        self.hide()

        self._theme_manager.register_widget(
            self,
            on_theme_changed=self._on_theme_changed,
        )

    def start(self):
        if not self._timer.isActive():
            self._angle = 0
            if not _reduced_motion():
                self._timer.start(self._interval_ms)
        self.show()
        self.raise_()
        self.update()

    def stop(self):
        self._timer.stop()
        self.hide()

    def is_running(self) -> bool:
        return self._timer.isActive()

    def set_color(self, color: str):
        self._color_override = color
        self._color = self._resolve_color()
        self.update()

    def _resolve_color(self) -> str:
        if self._color_override:
            return self._color_override
        return self._theme_manager.get_tokens().get("primary-foreground", "#FFFFFF")

    def _on_theme_changed(self, *_):
        self._color = self._resolve_color()
        self.update()

    def _advance(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen_width = max(2.0, self._px / 8.0)
        rect = QRectF(
            pen_width / 2 + 1, pen_width / 2 + 1,
            self._px - pen_width - 2, self._px - pen_width - 2,
        )
        track_pen = QPen(QColor(self._color))
        track_pen.setWidthF(pen_width)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        c = QColor(self._color); c.setAlpha(60)
        track_pen.setColor(c)
        p.setPen(track_pen)
        p.drawArc(rect, 0, 360 * 16)

        arc_pen = QPen(QColor(self._color))
        arc_pen.setWidthF(pen_width)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arc_pen)
        p.drawArc(rect, int(-self._angle * 16), int(-280 * 16))
        p.end()


'''
# =============================================================================
# SHADCN BUTTON
# =============================================================================

class ShadcnButton(QPushButton):
    """
    Enterprise button with variants, sizes, inline loading, and focus ring.

    Spinner layout
    --------------
    When loading, the button shows  [spinner]  [gap]  [text]  as a single
    horizontally-centered group. The gap scales with the length of the
    loading label: short labels ("Send", "Save") get the minimum gap;
    longer labels get extra breathing room.

    Positioning runs on three successive event-loop ticks after the
    loading state is set, because Qt may not have applied the new text
    or font metrics on the very first tick.
    """

    # Minimum horizontal gap between the spinner and the text.
    SPINNER_TEXT_GAP = 16
    # Additional gap per character of the loading label beyond 8 chars.
    SPINNER_TEXT_GAP_PER_CHAR = 0.6
    # Symmetric inset reserved on both sides of the group.
    MIN_SIDE_INSET = 14

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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._is_loading = False
        self._loading_text: Optional[str] = None
        self._original_text = text
        self._spinner: Optional[ShadcnLoadingSpinner] = None
        self._last_qss: Optional[str] = None

        self.theme_manager = _theme()
        self.update_theme()

        if icon:
            self.setIcon(IconManager().get_icon(icon, size=self._icon_size(), state="default"))
            self.setIconSize(self._icon_size())

        self._refresh_accessibility()

        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    # ------------------------------------------------------------------
    # Accessibility
    # ------------------------------------------------------------------

    def _refresh_accessibility(self):
        name = (self.text() or "").strip()
        if not name and self.icon_name:
            name = self.icon_name.replace("_", " ").title()
        if not name:
            name = "Button"
        self.setAccessibleName(name)

        tip = self.toolTip()
        if tip:
            self.setAccessibleDescription(tip)

    def setToolTip(self, tip: str):  # type: ignore[override]
        super().setToolTip(tip)
        if tip:
            self.setAccessibleDescription(tip)

    def setText(self, text: str):  # type: ignore[override]
        super().setText(text)
        self._refresh_accessibility()
        if getattr(self, "_is_loading", False):
            self._position_spinner()

    # ------------------------------------------------------------------
    # Loading state
    # ------------------------------------------------------------------

    def set_loading(self, loading: bool, text: Optional[str] = None):
        if loading == self._is_loading:
            return
        self._is_loading = loading

        if loading:
            if self._loading_text is None:
                self._original_text = self.text()
            self._loading_text = text if text is not None else self._original_text

            if self._spinner is None:
                self._spinner = ShadcnLoadingSpinner(size="sm", parent=self)
                self._spinner.set_color(self._spinner_color())
                self._spinner.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
                )
                self.setIcon(QIcon())

            self.setText(self._loading_text)
            self._spinner.start()

            # Position on three successive ticks.
            self._position_spinner()
            QTimer.singleShot(0, self._position_spinner)
            QTimer.singleShot(16, self._position_spinner)

            self.setEnabled(True)
        else:
            if self._spinner is not None:
                self._spinner.stop()
            self.setText(self._original_text)
            self._loading_text = None
            if self.icon_name:
                self.setIcon(IconManager().get_icon(self.icon_name,
                                                     size=self._icon_size(),
                                                     state="default"))
            self.setEnabled(True)

    def is_loading(self) -> bool:
        return self._is_loading

    def mousePressEvent(self, event):
        if self._is_loading:
            event.ignore()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if self._is_loading and event.key() in (Qt.Key.Key_Space,
                                                Qt.Key.Key_Return,
                                                Qt.Key.Key_Enter):
            event.ignore()
            return
        super().keyPressEvent(event)

    def _spinner_color(self) -> str:
        t = self.theme_manager.get_tokens()
        if self.variant in ("default", "destructive"):
            return t.get("primary-foreground", "#FFFFFF")
        return t.get("foreground", "#0F172A")

    def _gap_for_text(self, text: str) -> int:
        base = self.SPINNER_TEXT_GAP
        extra_chars = max(0, len(text) - 8)
        return int(base + extra_chars * self.SPINNER_TEXT_GAP_PER_CHAR)

    def _position_spinner(self):
        spinner = getattr(self, "_spinner", None)
        if spinner is None or not spinner.isVisible():
            return

        s = spinner.size()
        text = self.text()
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(text)
        gap = self._gap_for_text(text)

        total_w = s.width() + gap + text_w

        avail = self.width()
        if total_w + 2 * self.MIN_SIDE_INSET >= avail:
            group_x = self.MIN_SIDE_INSET
        else:
            group_x = (avail - total_w) // 2

        y = (self.height() - s.height()) // 2
        spinner.move(group_x, y)
        spinner.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_is_loading", False):
            self._position_spinner()

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def update_theme(self):
        if self.property("class") == "nav-button":
            if self._last_qss != "":
                self.setStyleSheet("")
                self._last_qss = ""
            return

        t = self.theme_manager.get_tokens()
        r = t["radius"]
        ring = t.get("ring", t["primary"])

        key = f"btn|{self.variant}|{self.size}|{self.text()}|{bool(self.icon_name)}"

        def build():
            if self.variant == "default":
                base = f"background:{t['primary']}; color:{t['primary-foreground']};"
                hover = f"background:{t['primary-hover']};"
                press = f"background:{t['primary-hover']};"
            elif self.variant == "destructive":
                base = f"background:{t['destructive']}; color:{t['destructive-foreground']};"
                hover = f"background:{t['destructive-hover']};"
                press = f"background:{t['destructive-hover']};"
            elif self.variant == "outline":
                base = f"background:transparent; color:{t['foreground']};"
                hover = f"background:{t['secondary']}; border-color:{t['border-strong']};"
                press = f"background:{t['accent']};"
            elif self.variant == "secondary":
                base = f"background:{t['secondary']}; color:{t['secondary-foreground']};"
                hover = f"background:{t['accent']};"
                press = f"background:{t['surface-active']};"
            elif self.variant == "ghost":
                base = f"background:transparent; color:{t['foreground']};"
                hover = f"background:{t['secondary']};"
                press = f"background:{t['accent']};"
            elif self.variant == "link":
                base = f"background:transparent; color:{t['primary']};"
                hover = f"color:{t['primary-hover']};"
                press = f"color:{t['primary-hover']};"
            else:
                base = hover = press = ""

            font_size = t.get("font_size", 13)

            if self.size == "sm":
                padding, fsize, height = "0 11px", f"{max(10, font_size - 1)}px", "28px"
            elif self.size == "lg":
                padding, fsize, height = "0 22px", f"{font_size + 2}px", "42px"
            elif self.size == "icon":
                padding, fsize, height = "0", f"{font_size}px", "34px"
            else:
                padding, fsize, height = "0 15px", f"{font_size}px", "34px"

            icon_only = bool(self.icon_name and not self.text())
            if icon_only or self.variant == "icon":
                sq = {"sm": 28, "lg": 42, "icon": 34}.get(self.size, 34)
                self.setFixedSize(sq, sq)
                padding = "0"

            checked_bg = t["primary-subtle"] if self.variant == "ghost" else t["secondary"]
            checked_fg = t["primary"] if self.variant == "ghost" else t["foreground"]

            border_base = "border: 2px solid transparent;"
            if self.variant == "outline":
                border_base = f"border: 1px solid {t['border']};"

            return f"""
                QPushButton {{
                    {base}
                    {border_base}
                    padding: {padding};
                    min-height: {height};
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
                QPushButton:focus {{
                    border: 2px solid {ring};
                }}
                QPushButton:disabled {{
                    background: {t['muted']};
                    color: {t['muted-foreground']};
                }}
            """

        _apply_qss(self, key, build)

        if self.icon_name and not getattr(self, "_is_loading", False):
            self.setIcon(IconManager().get_icon(self.icon_name,
                                                size=self._icon_size(),
                                                state="default"))

        spinner = getattr(self, "_spinner", None)
        if spinner is not None:
            spinner.set_color(self._spinner_color())

    def _icon_size(self) -> QSize:
        return {"sm": QSize(14, 14), "lg": QSize(20, 20)}.get(self.size, QSize(16, 16))'''

class ShadcnButton(QPushButton):
    """
    Enterprise button with variants, sizes, inline loading, and focus ring.

    Loading state
    -------------
    While loading, the button shows a single horizontal group:

        [ spinner ]  8px  [ loading text ]

    The group is a child QWidget with a QHBoxLayout. The spinner and
    label are children of that layout, so the layout guarantees they
    can never overlap, regardless of the loading text length or the
    button width.

    Width reservation
    -----------------
    When loading starts, the button raises its minimum width so the
    parent layout gives it enough room to display the full loading
    group. When loading ends, the minimum width is dropped and
    updateGeometry() tells the parent layout to shrink the button
    back to its natural size. This is what allows a small button
    ("Next") to grow into "Checking email…" and then shrink back
    without either clipping the loading text or leaving a permanent
    gap after the loading state ends.

    If the parent window is too narrow to honour the reservation, the
    label is elided with "…" and the group is pinned to MIN_SIDE_INSET
    so the spinner never overlaps the text.
    """

    # Distance between the spinner and the loading text.
    SPINNER_TEXT_GAP = 8

    # Minimum horizontal breathing room between the loading group and
    # the button edges.
    MIN_SIDE_INSET = 14

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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._is_loading = False
        self._loading_text: Optional[str] = None
        self._original_text = text
        self._full_loading_text: Optional[str] = None  # un-elided
        self._spinner: Optional[ShadcnLoadingSpinner] = None
        self._loading_label: Optional[QLabel] = None
        self._loading_group: Optional[QWidget] = None
        self._loading_layout: Optional[QHBoxLayout] = None
        self._last_qss: Optional[str] = None

        self.theme_manager = _theme()
        self.update_theme()

        if icon:
            self.setIcon(IconManager().get_icon(
                icon, size=self._icon_size(), state="default"
            ))
            self.setIconSize(self._icon_size())

        self._refresh_accessibility()

        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    # ------------------------------------------------------------------
    # Accessibility
    # ------------------------------------------------------------------

    def _refresh_accessibility(self):
        name = (self.text() or "").strip()
        if not name and self._loading_text:
            name = self._loading_text.strip()
        if not name and self.icon_name:
            name = self.icon_name.replace("_", " ").title()
        if not name:
            name = "Button"
        self.setAccessibleName(name)

        tip = self.toolTip()
        if tip:
            self.setAccessibleDescription(tip)

    def setToolTip(self, tip: str):  # type: ignore[override]
        super().setToolTip(tip)
        if tip:
            self.setAccessibleDescription(tip)

    def setText(self, text: str):  # type: ignore[override]
        if self._is_loading:
            # Keep the pending original text; do not touch the visible
            # loading label.
            self._original_text = text
            return
        super().setText(text)
        self._original_text = text
        self._refresh_accessibility()

    # ------------------------------------------------------------------
    # Loading state
    # ------------------------------------------------------------------

    def set_loading(self, loading: bool, text: Optional[str] = None):
        """
        Enable or disable the loading state.

        Calling set_loading(True, "...") while already loading updates
        the visible loading message and re-reserves width if the new
        message is longer.
        """
        # Update loading text while already loading.
        if loading and self._is_loading:
            if text is not None:
                self._loading_text = text
                self._full_loading_text = text
                self._apply_loading_label_text()
                self._refresh_accessibility()
                self._update_size_hint_for_loading()
                self._position_loading_group()
            return

        if loading == self._is_loading:
            return

        self._is_loading = loading

        if loading:
            self._start_loading(text)
        else:
            self._stop_loading()

    def _start_loading(self, text: Optional[str]):
        # Preserve the normal button text.
        self._original_text = self.text()

        # Determine loading text.
        self._loading_text = text if text is not None else self._original_text
        self._full_loading_text = self._loading_text

        # Hide QPushButton's built-in text and clear the icon.
        super().setText("")
        self.setIcon(QIcon())

        # Create the loading group once.
        if self._loading_group is None:
            self._loading_group = QWidget(self)
            self._loading_group.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
            self._loading_layout = QHBoxLayout(self._loading_group)
            self._loading_layout.setContentsMargins(0, 0, 0, 0)
            self._loading_layout.setSpacing(self.SPINNER_TEXT_GAP)
            self._loading_layout.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            # Spinner first, then label.
            self._spinner = ShadcnLoadingSpinner(
                size="sm", parent=self._loading_group
            )
            self._spinner.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
            self._loading_layout.addWidget(
                self._spinner, 0, Qt.AlignmentFlag.AlignVCenter
            )

            self._loading_label = QLabel(self._loading_group)
            self._loading_label.setAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            self._loading_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
            self._loading_label.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
            )
            self._loading_layout.addWidget(
                self._loading_label, 0, Qt.AlignmentFlag.AlignVCenter
            )

        # Apply styling and text.
        self._style_loading_label()
        self._apply_loading_label_text()
        self._spinner.set_color(self._spinner_color())

        # Reserve enough width for the loading group.
        self._update_size_hint_for_loading()

        self._loading_group.show()
        self._loading_group.raise_()
        self._spinner.start()

        self._position_loading_group()
        self._refresh_accessibility()
        self.setEnabled(True)

    def _stop_loading(self):
        if self._spinner is not None:
            self._spinner.stop()

        if self._loading_group is not None:
            self._loading_group.hide()

        if self._loading_label is not None:
            self._loading_label.setText("")

        self._loading_text = None
        self._full_loading_text = None

        # Drop the reserved width so the button can shrink back.
        self.setMinimumWidth(0)

        super().setText(self._original_text)
        self._refresh_accessibility()

        if self.icon_name:
            self.setIcon(IconManager().get_icon(
                self.icon_name,
                size=self._icon_size(),
                state="default",
            ))
            self.setIconSize(self._icon_size())

        # Ask the layout to re-evaluate our size hint.
        self.updateGeometry()
        self.setEnabled(True)

    def is_loading(self) -> bool:
        return self._is_loading

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if self._is_loading:
            event.ignore()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if self._is_loading and event.key() in (
            Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter
        ):
            event.ignore()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Loading label text + sizing
    # ------------------------------------------------------------------

    def _apply_loading_label_text(self):
        """
        Set the label text to the full (un-elided) loading string.
        Elision happens later in _position_loading_group if there is
        not enough room.
        """
        if self._loading_label is None or self._full_loading_text is None:
            return
        self._loading_label.setText(self._full_loading_text)
        self._loading_label.adjustSize()

    def _elide_label_if_needed(self, available_for_label: int):
        """
        Elide the loading label if the full text won't fit in the
        space left over after the spinner and the gap.
        """
        if self._loading_label is None or self._full_loading_text is None:
            return

        fm = QFontMetrics(self._loading_label.font())
        full_w = fm.horizontalAdvance(self._full_loading_text)

        if full_w <= available_for_label:
            if self._loading_label.text() != self._full_loading_text:
                self._loading_label.setText(self._full_loading_text)
                self._loading_label.adjustSize()
            return

        elided = fm.elidedText(
            self._full_loading_text,
            Qt.TextElideMode.ElideRight,
            max(0, available_for_label),
        )
        if self._loading_label.text() != elided:
            self._loading_label.setText(elided)
            self._loading_label.adjustSize()

    # ------------------------------------------------------------------
    # Loading group geometry
    # ------------------------------------------------------------------

    def _spinner_color(self) -> str:
        t = self.theme_manager.get_tokens()
        if self.variant in ("default", "destructive"):
            return t.get("primary-foreground", "#FFFFFF")
        return t.get("foreground", "#0F172A")

    def _style_loading_label(self):
        if self._loading_label is None:
            return
        t = self.theme_manager.get_tokens()

        if self.variant in ("default", "destructive"):
            color = t.get("primary-foreground", "#FFFFFF")
        elif self.variant == "link":
            color = t.get("primary", "#006B3F")
        else:
            color = t.get("foreground", "#0F172A")

        font_size = t.get("font_size", 13)
        if self.size == "sm":
            font_size = max(10, font_size - 1)
        elif self.size == "lg":
            font_size = font_size + 2

        self._loading_label.setStyleSheet(
            f"QLabel {{ "
            f"color: {color}; "
            f"font-size: {font_size}px; "
            f"font-weight: 500; "
            f"background: transparent; "
            f"border: none; "
            f"padding: 0; "
            f"margin: 0; "
            f"}}"
        )

    def _update_size_hint_for_loading(self):
        """
        Reserve enough width to show the full loading group.

        Called on start and on every loading-text update. Never
        shrinks below the button's current minimum width, only raises
        it while loading is active. _stop_loading resets the minimum
        back to 0.
        """
        if not self._full_loading_text:
            return

        # Measure the label with the current styling.
        if self._loading_label is not None:
            self._loading_label.setText(self._full_loading_text)
            self._loading_label.adjustSize()
            label_w = self._loading_label.sizeHint().width()
        else:
            fm = QFontMetrics(self.font())
            label_w = fm.horizontalAdvance(self._full_loading_text)

        spinner_w = self._spinner.width() if self._spinner else 16
        gap = self.SPINNER_TEXT_GAP
        horizontal_padding = 2 * self.MIN_SIDE_INSET

        required = spinner_w + gap + label_w + horizontal_padding

        # Only ever increase the minimum width; never shrink it here.
        if required > self.minimumWidth():
            self.setMinimumWidth(required)

        # Tell the parent layout that our size hint has changed.
        self.updateGeometry()

    def _position_loading_group(self):
        """
        Size and center the loading group.

        Steps:
          1. Ensure the label has measured against its current text.
          2. Query the layout's total size hint.
          3. If the group fits inside the button, size it exactly and
             center it. The label keeps its full text.
          4. If it does not fit, elide the label to the space left
             over after the spinner and the gap, and pin the group to
             MIN_SIDE_INSET on the left.
        """
        group = self._loading_group
        layout = self._loading_layout
        spinner = self._spinner
        label = self._loading_label

        if group is None or layout is None or spinner is None or label is None:
            return
        if not self._is_loading:
            return

        # Make sure the label has measured against its current text.
        label.adjustSize()

        # Force the layout to compute fresh geometry.
        layout.invalidate()
        layout.activate()

        natural = layout.sizeHint()

        avail_w = self.width()
        inner_w = max(0, avail_w - 2 * self.MIN_SIDE_INSET)
        spinner_w = spinner.width()
        gap = self.SPINNER_TEXT_GAP

        max_label_w = max(0, inner_w - spinner_w - gap)

        if natural.width() <= inner_w:
            # Full text fits.
            if label.text() != (self._full_loading_text or ""):
                label.setText(self._full_loading_text or "")
                label.adjustSize()

            layout.invalidate()
            layout.activate()
            natural = layout.sizeHint()

            group_w = natural.width()
            group_h = natural.height()
        else:
            # Elide the label to fit and recompute.
            self._elide_label_if_needed(max_label_w)

            layout.invalidate()
            layout.activate()
            natural = layout.sizeHint()

            group_w = min(natural.width(), inner_w)
            group_h = natural.height()

        # Position the group.
        x = max(self.MIN_SIDE_INSET, (avail_w - group_w) // 2)
        y = max(0, (self.height() - group_h) // 2)

        # Use setGeometry so the layout can flow inside the group rect.
        group.setGeometry(x, y, group_w, group_h)
        group.raise_()

    # ------------------------------------------------------------------
    # Resize
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._is_loading:
            self._position_loading_group()

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def update_theme(self):
        if self.property("class") == "nav-button":
            if self._last_qss != "":
                self.setStyleSheet("")
                self._last_qss = ""
            return

        t = self.theme_manager.get_tokens()
        r = t["radius"]
        ring = t.get("ring", t["primary"])

        key = f"btn|{self.variant}|{self.size}|{self.text()}|{bool(self.icon_name)}"

        def build():
            if self.variant == "default":
                base = f"background:{t['primary']}; color:{t['primary-foreground']};"
                hover = f"background:{t['primary-hover']};"
                press = f"background:{t['primary-hover']};"
            elif self.variant == "destructive":
                base = f"background:{t['destructive']}; color:{t['destructive-foreground']};"
                hover = f"background:{t['destructive-hover']};"
                press = f"background:{t['destructive-hover']};"
            elif self.variant == "outline":
                base = f"background:transparent; color:{t['foreground']};"
                hover = f"background:{t['secondary']}; border-color:{t['border-strong']};"
                press = f"background:{t['accent']};"
            elif self.variant == "secondary":
                base = f"background:{t['secondary']}; color:{t['secondary-foreground']};"
                hover = f"background:{t['accent']};"
                press = f"background:{t['surface-active']};"
            elif self.variant == "ghost":
                base = f"background:transparent; color:{t['foreground']};"
                hover = f"background:{t['secondary']};"
                press = f"background:{t['accent']};"
            elif self.variant == "link":
                base = f"background:transparent; color:{t['primary']};"
                hover = f"color:{t['primary-hover']};"
                press = f"color:{t['primary-hover']};"
            else:
                base = hover = press = ""

            font_size = t.get("font_size", 13)
            if self.size == "sm":
                padding, fsize, height = "0 11px", f"{max(10, font_size - 1)}px", "28px"
            elif self.size == "lg":
                padding, fsize, height = "0 22px", f"{font_size + 2}px", "42px"
            elif self.size == "icon":
                padding, fsize, height = "0", f"{font_size}px", "34px"
            else:
                padding, fsize, height = "0 15px", f"{font_size}px", "34px"

            icon_only = bool(self.icon_name and not self.text())
            if icon_only or self.variant == "icon":
                sq = {"sm": 28, "lg": 42, "icon": 34}.get(self.size, 34)
                self.setFixedSize(sq, sq)
                padding = "0"

            checked_bg = t["primary-subtle"] if self.variant == "ghost" else t["secondary"]
            checked_fg = t["primary"] if self.variant == "ghost" else t["foreground"]

            border_base = "border: 2px solid transparent;"
            if self.variant == "outline":
                border_base = f"border: 1px solid {t['border']};"

            return f"""
                QPushButton {{
                    {base}
                    {border_base}
                    padding: {padding};
                    min-height: {height};
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
                QPushButton:focus {{
                    border: 2px solid {ring};
                }}
                QPushButton:disabled {{
                    background: {t['muted']};
                    color: {t['muted-foreground']};
                }}
            """

        _apply_qss(self, key, build)

        if self.icon_name and not self._is_loading:
            self.setIcon(IconManager().get_icon(
                self.icon_name, size=self._icon_size(), state="default"
            ))

        if self._is_loading:
            if self._loading_label is not None:
                self._style_loading_label()
            if self._spinner is not None:
                self._spinner.set_color(self._spinner_color())
            self._position_loading_group()

    def _icon_size(self) -> QSize:
        return {"sm": QSize(14, 14), "lg": QSize(20, 20)}.get(
            self.size, QSize(16, 16)
        )

# =============================================================================
# SHADCN INPUT
# =============================================================================

class ShadcnInput(QLineEdit):
    def __init__(self, placeholder: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def setPlaceholderText(self, text: str):  # type: ignore[override]
        super().setPlaceholderText(text)
        if not self.accessibleName():
            self.setAccessibleName(text or "Input")

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "input"

        def build():
            return f"""
                QLineEdit {{
                    background-color: {t["input"]};
                    border: 1px solid {t["border"]};
                    border-radius: {t["radius"]};
                    padding: {t["padding_vertical"]}px {t["padding_horizontal"]}px;
                    color: {t["foreground"]};
                    selection-background-color: {t["primary"]};
                    selection-color: {t["primary-foreground"]};
                }}
                QLineEdit:hover {{
                    border-color: {t["border-strong"]};
                }}
                QLineEdit:focus {{
                    border: 2px solid {t["ring"]};
                    background-color: {t["surface"]};
                }}
                QLineEdit:disabled {{
                    background-color: {t["muted"]};
                    color: {t["muted-foreground"]};
                }}
            """

        _apply_qss(self, key, build)


# =============================================================================
# SHADCN TEXT AREA
# =============================================================================

class ShadcnTextArea(QTextEdit):
    def __init__(self, placeholder: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "textarea"

        def build():
            return f"""
                QTextEdit {{
                    background-color: {t["input"]};
                    border: 1px solid {t["border"]};
                    border-radius: {t["radius"]};
                    padding: {t["padding_vertical"]}px {t["padding_horizontal"]}px;
                    color: {t["foreground"]};
                    selection-background-color: {t["primary"]};
                    selection-color: {t["primary-foreground"]};
                }}
                QTextEdit:hover {{ border-color: {t["border-strong"]}; }}
                QTextEdit:focus {{ border: 2px solid {t["ring"]}; }}
                QTextEdit:disabled {{
                    background-color: {t["muted"]};
                    color: {t["muted-foreground"]};
                }}
            """

        _apply_qss(self, key, build)


# =============================================================================
# SHADCN COMBOBOX
# =============================================================================

class ShadcnComboBox(QComboBox):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "combobox"

        def build():
            return f"""
                QComboBox {{
                    background-color: {t["input"]};
                    border: 1px solid {t["border"]};
                    border-radius: {t["radius"]};
                    padding: {t["padding_vertical"]}px 32px {t["padding_vertical"]}px {t["padding_horizontal"]}px;
                    color: {t["foreground"]};
                }}
                QComboBox:hover {{ border-color: {t["border-strong"]}; }}
                QComboBox:focus {{ border: 2px solid {t["ring"]}; }}
                QComboBox:disabled {{
                    background-color: {t["muted"]};
                    color: {t["muted-foreground"]};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 28px;
                    subcontrol-origin: padding;
                    subcontrol-position: center right;
                }}
                QComboBox QAbstractItemView {{
                    background-color: {t["popover"]};
                    border: 1px solid {t["border"]};
                    border-radius: {t["radius"]};
                    selection-background-color: {t["secondary"]};
                    selection-color: {t["foreground"]};
                    padding: 4px;
                    outline: none;
                }}
                QComboBox QAbstractItemView::item {{
                    padding: 6px 12px;
                    border-radius: {t["radius-sm"]};
                    min-height: 28px;
                }}
                QComboBox QAbstractItemView::item:selected:focus,
                QComboBox QAbstractItemView::item:selected:active {{
                    background-color: {t["primary-subtle"]};
                    color: {t["primary"]};
                    border: 1px solid {t["ring"]};
                }}
            """

        _apply_qss(self, key, build)


# =============================================================================
# SHADCN CHECKBOX / RADIO
# =============================================================================

class ShadcnCheckBox(QCheckBox):
    check_toggled = Signal(bool)

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )
        super().toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool):
        self.check_toggled.emit(checked)

    def setText(self, text: str):  # type: ignore[override]
        super().setText(text)
        if not self.accessibleName():
            self.setAccessibleName(text or "Checkbox")

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "checkbox"

        def build():
            return f"""
                QCheckBox {{
                    color: {t["foreground"]};
                    spacing: 8px;
                }}
                QCheckBox:focus {{ color: {t["ring"]}; }}
                QCheckBox::indicator {{
                    width: 16px;
                    height: 16px;
                    border: 1.5px solid {t["border-strong"]};
                    border-radius: {t["radius-sm"]};
                    background: {t["input"]};
                }}
                QCheckBox::indicator:hover {{ border-color: {t["ring"]}; }}
                QCheckBox::indicator:focus {{ border: 2px solid {t["ring"]}; }}
                QCheckBox::indicator:checked {{
                    background: {t["primary"]};
                    border-color: {t["primary"]};
                }}
                QCheckBox:disabled {{ color: {t["muted-foreground"]}; }}
            """

        _apply_qss(self, key, build)

    def set_checked(self, checked: bool):
        self.setChecked(checked)

    def is_checked(self) -> bool:
        return self.isChecked()


class ShadcnRadioButton(QRadioButton):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def setText(self, text: str):  # type: ignore[override]
        super().setText(text)
        if not self.accessibleName():
            self.setAccessibleName(text or "Option")

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "radio"

        def build():
            return f"""
                QRadioButton {{
                    color: {t["foreground"]};
                    spacing: 8px;
                }}
                QRadioButton:focus {{ color: {t["ring"]}; }}
                QRadioButton::indicator {{
                    width: 16px; height: 16px;
                    border: 1.5px solid {t["border-strong"]};
                    border-radius: 8px;
                    background: {t["input"]};
                }}
                QRadioButton::indicator:hover {{ border-color: {t["ring"]}; }}
                QRadioButton::indicator:focus {{ border: 2px solid {t["ring"]}; }}
                QRadioButton::indicator:checked {{
                    background: {t["primary"]};
                    border-color: {t["primary"]};
                }}
                QRadioButton:disabled {{ color: {t["muted-foreground"]}; }}
            """

        _apply_qss(self, key, build)


# =============================================================================
# LABEL / CAPTION / HEADING
# =============================================================================

class ShadcnLabel(QLabel):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "label"

        def build():
            return f"font-weight: 500; color: {t['foreground']}; background: transparent;"

        _apply_qss(self, key, build)


class ShadcnCaption(QLabel):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        base = max(9, t.get("font_size", 13) - 2)
        key = "caption"

        def build():
            return (
                f"font-size: {base}px; color: {t['muted-foreground']}; "
                "background: transparent;"
            )

        _apply_qss(self, key, build)


class ShadcnHeading(QLabel):
    _SIZES = {1: 9, 2: 5, 3: 2, 4: 0}

    def __init__(self, text: str = "", level: int = 2,
                 parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.level = max(1, min(4, level))
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        base_size = t.get("font_size", 13)
        delta = self._SIZES[self.level]
        size = base_size + delta
        weight = "650" if self.level <= 2 else "600"
        key = f"heading|{self.level}"

        def build():
            return (
                f"font-size: {size}px; font-weight: {weight}; "
                f"color: {t['foreground']}; background: transparent;"
            )

        _apply_qss(self, key, build)


# =============================================================================
# SEPARATOR
# =============================================================================

class ShadcnSeparator(QFrame):
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
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "separator"

        def build():
            return f"background-color: {t['border']}; border: none;"

        _apply_qss(self, key, build)


# =============================================================================
# CARD
# =============================================================================

class ShadcnCard(QFrame):
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
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "card"

        def build():
            return f"""
                #ShadcnCard {{
                    background-color: {t["surface"]};
                    border: 1px solid {t["border"]};
                    border-radius: {t["radius-lg"]};
                }}
            """

        _apply_qss(self, key, build)

    def _swap(self, attr: str, widget: QWidget):
        old = getattr(self, attr)
        if old:
            self._layout.removeWidget(old)
            old.deleteLater()
        setattr(self, attr, widget)
        self._layout.addWidget(widget)

    def set_header(self, widget: QWidget):
        self._swap("_header", widget)

    def set_content(self, widget: QWidget):
        self._swap("_content", widget)

    def set_footer(self, widget: QWidget):
        self._swap("_footer", widget)


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

    def update_theme(self):
        pass


class CardContent(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 4, 20, 20)
        self.main_layout.setSpacing(14)

    def addWidget(self, w: QWidget):
        self.main_layout.addWidget(w)

    @property
    def layout(self):
        return self.main_layout


class CardFooter(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(20, 12, 20, 18)
        self.main_layout.setSpacing(10)
        self.setObjectName("cardFooter")
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "cardfooter"

        def build():
            return f"#cardFooter {{ border-top: 1px solid {t['border']}; }}"

        _apply_qss(self, key, build)

    def addWidget(self, w: QWidget):
        self.main_layout.addWidget(w)

    @property
    def layout(self):
        return self.main_layout


# =============================================================================
# AVATAR
# =============================================================================

class ShadcnAvatar(QFrame):
    def __init__(self, image_path: Optional[str] = None,
                 fallback_text: str = "", size: int = 32,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.avatar_size = size
        self.image_path = image_path
        self.fallback_text = fallback_text
        self.setFixedSize(size, size)
        self.setAccessibleName(fallback_text or "Avatar")
        self.theme_manager = _theme()
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(self.label)
        self._set_content()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self._set_content,
        )

    def _get_theme_colors(self) -> tuple:
        if self.theme_manager.is_dark():
            palette = [
                ("#1a2a3a", "#60A5FA"), ("#1a2a1a", "#34D399"),
                ("#2a1a2a", "#F472B6"), ("#2a1a0a", "#FBBF24"),
                ("#1a1a2a", "#A78BFA"), ("#2a1a0a", "#FB923C"),
                ("#0a2a2a", "#22D3EE"), ("#1a2a1a", "#4ADE80"),
            ]
        else:
            palette = [
                ("#dbeafe", "#1d4ed8"), ("#dcfce7", "#15803d"),
                ("#fce7f3", "#9d174d"), ("#fef3c7", "#92400e"),
                ("#ede9fe", "#5b21b6"), ("#ffedd5", "#9a3412"),
                ("#cffafe", "#164e63"), ("#f0fdf4", "#166534"),
            ]
        idx = sum(ord(c) for c in self.fallback_text) % len(palette)
        return palette[idx]

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

        bg, fg = self._get_theme_colors()
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


# =============================================================================
# BADGE
# =============================================================================

class ShadcnBadge(QLabel):
    def __init__(self, text: str = "", variant: str = "default",
                 parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.variant = variant
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def setText(self, text: str):  # type: ignore[override]
        super().setText(text)
        self.setAccessibleName(text or self.variant)

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
        base = max(9, t.get("font_size", 13) - 2)
        key = f"badge|{v}"

        def build():
            return f"""
                background: {bg};
                color: {fg};
                {border}
                border-radius: 99px;
                padding: 2px 9px;
                font-size: {base}px;
                font-weight: 600;
            """

        _apply_qss(self, key, build)


# =============================================================================
# ALERT
# =============================================================================

class ShadcnAlert(QFrame):
    def __init__(self, title: str, description: str = "",
                 variant: str = "default",
                 icon_name: Optional[str] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ShadcnAlert")
        self.alert_variant = variant
        self.icon_name = icon_name
        self.setAccessibleName(title)

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
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        v = self.alert_variant
        configs = {
            "default":     (t["surface"],            t["border"],       t["foreground"]),
            "destructive": (t["destructive-subtle"], t["destructive"],  t["destructive"]),
            "success":     (t["success-subtle"],     t["success"],      t["success-foreground"]),
            "warning":     (t["warning-subtle"],     t["warning"],      t["warning-foreground"]),
            "info":        (t["info-subtle"],        t["info"],         t["info-foreground"]),
        }
        bg, border_col, accent = configs.get(v, configs["default"])
        key = f"alert|{v}"

        def build():
            return f"""
                #ShadcnAlert {{
                    background: {bg};
                    border: 1px solid {border_col};
                    border-left: 3px solid {accent};
                    border-radius: {t["radius"]};
                }}
                #alertTitle {{ font-weight: 600; color: {accent}; }}
                #alertDesc {{ color: {t["foreground-secondary"]}; }}
            """

        _apply_qss(self, key, build)

        if self.icon_name and hasattr(self, "icon_lbl"):
            icon = IconManager().get_icon(self.icon_name, size=QSize(18, 18),
                                          state="active")
            self.icon_lbl.setPixmap(icon.pixmap(18, 18))


# =============================================================================
# ALERT DIALOG
# =============================================================================

class ShadcnAlertDialog(QDialog):
    def __init__(self, title: str, description: str,
                 cancel_text: str = "Cancel", action_text: str = "Continue",
                 destructive: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        self.setObjectName("ShadcnAlertDialog")
        self.setMinimumWidth(420)
        self.setAccessibleName(title)

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
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

        self.action_btn.setDefault(True)
        QTimer.singleShot(0, self.action_btn.setFocus)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "alertdialog"

        def build():
            return f"""
                #ShadcnAlertDialog {{
                    background: {t["surface"]};
                    border: 1px solid {t["border"]};
                    border-radius: {t["radius-xl"]};
                }}
            """

        _apply_qss(self, key, build)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
            event.accept()
            return
        super().keyPressEvent(event)


# =============================================================================
# DATA TABLE
# =============================================================================

class ShadcnDataTable(QTableWidget):
    def __init__(self, columns: List[str], parent: Optional[QWidget] = None,
                 numeric_columns: Optional[Sequence[int]] = None,
                 empty_message: str = "No records found"):
        super().__init__(parent)
        self._columns = list(columns)
        self._numeric_columns = set(numeric_columns or [])
        self._empty_message = empty_message
        self._raw_data: list = []

        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Data table")

        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(True)
        hdr.setHighlightSections(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(44)

        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        size = t.get("scrollbar_size", 10)
        radius = t.get("scrollbar_radius", 5)
        ring = t.get("ring", t["primary"])
        key = "datatable"

        def build():
            return f"""
                QTableWidget {{
                    background-color: {t["surface"]};
                    alternate-background-color: {t["muted"]};
                    border: 1px solid {t["border"]};
                    border-radius: {t["radius-lg"]};
                    gridline-color: transparent;
                    color: {t["foreground"]};
                    outline: none;
                }}
                QTableWidget:focus {{
                    border: 2px solid {ring};
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
                    font-weight: 600;
                }}
                QHeaderView::section:first {{
                    border-top-left-radius: {t["radius-lg"]};
                }}
                QHeaderView::section:last {{
                    border-top-right-radius: {t["radius-lg"]};
                }}
                QScrollBar:vertical {{
                    background: {t.get("scrollbar_track", t["muted"])};
                    width: {size}px;
                    border: none;
                    border-radius: {radius}px;
                }}
                QScrollBar::handle:vertical {{
                    background: {t.get("scrollbar_handle", t["border-strong"])};
                    border-radius: {radius}px;
                    min-height: 36px;
                    margin: 2px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background: {t.get("scrollbar_handle_hover", t["foreground-secondary"])};
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
                QScrollBar:horizontal {{
                    background: {t.get("scrollbar_track", t["muted"])};
                    height: {size}px;
                    border: none;
                    border-radius: {radius}px;
                }}
                QScrollBar::handle:horizontal {{
                    background: {t.get("scrollbar_handle", t["border-strong"])};
                    border-radius: {radius}px;
                    min-width: 36px;
                    margin: 2px;
                }}
                QScrollBar::handle:horizontal:hover {{
                    background: {t.get("scrollbar_handle_hover", t["foreground-secondary"])};
                }}
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            """

        _apply_qss(self, key, build)

    def populate(self, data: list, empty_message: Optional[str] = None):
        self._raw_data = list(data or [])
        self.setSortingEnabled(False)
        self.clearContents()
        self.setRowCount(0)

        if not self._raw_data:
            msg = empty_message or self._empty_message
            self.setRowCount(1)
            item = QTableWidgetItem(msg)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            t = _tok()
            item.setForeground(QColor(t["muted-foreground"]))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            if self.columnCount() > 0:
                self.setItem(0, 0, item)
            for col in range(1, self.columnCount()):
                filler = QTableWidgetItem("")
                filler.setFlags(Qt.ItemFlag.NoItemFlags)
                self.setItem(0, col, filler)
            self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            return

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setRowCount(len(self._raw_data))
        for row, row_data in enumerate(self._raw_data):
            if isinstance(row_data, dict):
                values = [row_data.get(col, "") for col in self._columns]
            elif isinstance(row_data, (tuple, list)):
                values = list(row_data)
            else:
                values = [row_data]

            for col in range(self.columnCount()):
                text = str(values[col]) if col < len(values) else ""
                item = QTableWidgetItem(text)
                if col in self._numeric_columns:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter)
                self.setItem(row, col, item)

    def sortItems(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder):
        if not self._raw_data:
            return

        def key_fn(row):
            if isinstance(row, dict):
                v = row.get(self._columns[column], "")
            elif isinstance(row, (tuple, list)):
                v = row[column] if column < len(row) else ""
            else:
                v = row
            try:
                return (0, float(v))
            except (TypeError, ValueError):
                return (1, str(v).lower())

        self._raw_data.sort(key=key_fn,
                            reverse=(order == Qt.SortOrder.DescendingOrder))
        self.populate(self._raw_data)

    def set_error(self, message: str):
        self.setSortingEnabled(False)
        self.clearContents()
        self.setRowCount(1)
        item = QTableWidgetItem(f"⚠  {message}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        t = _tok()
        item.setForeground(QColor(t["destructive"]))
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        if self.columnCount() > 0:
            self.setItem(0, 0, item)
        for col in range(1, self.columnCount()):
            filler = QTableWidgetItem("")
            filler.setFlags(Qt.ItemFlag.NoItemFlags)
            self.setItem(0, col, filler)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setAccessibleName(f"Data table - error: {message}")

    def show_all_rows(self):
        for row in range(self.rowCount()):
            self.setRowHidden(row, False)


# =============================================================================
# SKELETON
# =============================================================================

class ShadcnSkeleton(QFrame):
    _instances: list = []
    _shared_timer: Optional[QTimer] = None
    _pulse_state: bool = False

    def __init__(self, width: int = 120, height: int = 18,
                 rounded: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._rounded = rounded
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()

        ShadcnSkeleton._instances.append(self)
        self.destroyed.connect(lambda *_: ShadcnSkeleton._remove(self))

        if ShadcnSkeleton._shared_timer is None:
            ShadcnSkeleton._shared_timer = QTimer()
            ShadcnSkeleton._shared_timer.timeout.connect(
                ShadcnSkeleton._pulse_all
            )
            if not _reduced_motion():
                ShadcnSkeleton._shared_timer.start(700)

        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    @classmethod
    def _remove(cls, instance):
        try:
            cls._instances.remove(instance)
        except ValueError:
            pass

    @classmethod
    def _pulse_all(cls):
        cls._pulse_state = not cls._pulse_state
        for inst in list(cls._instances):
            try:
                inst.setStyleSheet(inst._style_b if cls._pulse_state else inst._style_a)
            except RuntimeError:
                cls._instances.remove(inst)

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        r = "99px" if self._rounded else t["radius"]
        self._style_a = f"background:{t['muted']}; border-radius:{r}; border:none;"
        self._style_b = f"background:{t['border']}; border-radius:{r}; border:none;"
        self.setStyleSheet(self._style_a)


# =============================================================================
# TOAST
# =============================================================================

class ShadcnToast(QWidget):
    _active_toasts: list = []
    _suppressed: int = 0

    MARGIN_RIGHT = 24
    MARGIN_BOTTOM = 24
    SPACING = 10

    @classmethod
    def suppress(cls, enable: bool = True):
        if enable:
            cls._suppressed += 1
        else:
            cls._suppressed = max(0, cls._suppressed - 1)

    @classmethod
    def is_suppressed(cls) -> bool:
        return cls._suppressed > 0

    def __new__(cls, *args, **kwargs):
        if cls._suppressed > 0:
            obj = QWidget.__new__(cls)
            return obj
        return super().__new__(cls)

    def __init__(
        self,
        message: str,
        description: str = "",
        variant: str = "default",
        duration: int = 4000,
        parent: Optional[QWidget] = None,
    ):
        if ShadcnToast._suppressed > 0:
            QWidget.__init__(self)
            self.hide()
            return

        if parent is None:
            parent = QApplication.activeWindow()

        if parent is not None:
            super().__init__(parent)
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self.setWindowFlags(Qt.WindowType.Widget)
        else:
            super().__init__(None)
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.WindowDoesNotAcceptFocus
            )
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setObjectName("ShadcnToast")

        self.toast_variant = variant
        self._duration = duration
        self._fade = None

        self.setAccessibleName(message)
        if description:
            self.setAccessibleDescription(description)

        lo = QHBoxLayout(self)
        lo.setContentsMargins(16, 14, 12, 14)
        lo.setSpacing(12)

        self._accent = QFrame(self)
        self._accent.setFixedWidth(4)
        self._accent.setObjectName("toastAccent")
        lo.addWidget(self._accent)

        self._dot = QLabel(self)
        self._dot.setFixedSize(10, 10)
        self._dot.setObjectName("toastDot")
        lo.addWidget(self._dot, 0, Qt.AlignTop | Qt.AlignVCenter)

        text_lo = QVBoxLayout()
        text_lo.setSpacing(3)
        text_lo.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel(message)
        self._title.setObjectName("toastTitle")
        self._title.setWordWrap(True)
        text_lo.addWidget(self._title)

        self._desc = None
        if description:
            self._desc = QLabel(description)
            self._desc.setObjectName("toastDesc")
            self._desc.setWordWrap(True)
            text_lo.addWidget(self._desc)

        lo.addLayout(text_lo, 1)

        self._close_btn = QPushButton("✕", self)
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._close_btn.setObjectName("toastClose")
        self._close_btn.setAccessibleName("Dismiss")
        self._close_btn.clicked.connect(self.close)
        lo.addWidget(self._close_btn, 0, Qt.AlignTop)

        self.setFixedWidth(380)
        self.setMinimumHeight(64)

        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self._apply_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self._apply_theme,
        )

        ShadcnToast._active_toasts.append(self)
        QTimer.singleShot(0, self._reposition_stack)

        self.show()
        self.raise_()
        self._fade_in()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.close)
        self._timer.start(duration)

    def _fade_in(self):
        if self.parent() is not None:
            return
        if _reduced_motion():
            self.setWindowOpacity(1.0)
            return
        try:
            self.setWindowOpacity(0.0)
            self._fade = QPropertyAnimation(self, b"windowOpacity", self)
            self._fade.setDuration(180)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._fade.start()
        except Exception:
            pass

    @classmethod
    def _reposition_stack(cls):
        by_parent: dict = {}
        for toast in cls._active_toasts:
            try:
                if not toast.isVisible():
                    continue
                parent = toast.parent()
                by_parent.setdefault(id(parent), (parent, []))[1].append(toast)
            except Exception:
                continue

        for _pid, (parent, toasts) in by_parent.items():
            try:
                if parent is not None and hasattr(parent, "rect"):
                    area = parent.rect()
                    right = area.right() - cls.MARGIN_RIGHT
                    bottom = area.bottom() - cls.MARGIN_BOTTOM
                else:
                    screen = QApplication.primaryScreen()
                    if not screen:
                        continue
                    geo = screen.availableGeometry()
                    right = geo.right() - cls.MARGIN_RIGHT
                    bottom = geo.bottom() - cls.MARGIN_BOTTOM

                y = bottom
                for toast in reversed(toasts):
                    try:
                        h = toast.sizeHint().height()
                        w = toast.width()
                        y -= h
                        toast.move(right - w, y)
                        toast.raise_()
                        y -= cls.SPACING
                    except Exception:
                        continue
            except Exception:
                continue

    def closeEvent(self, event):
        try:
            if self in ShadcnToast._active_toasts:
                ShadcnToast._active_toasts.remove(self)
        except Exception:
            pass
        try:
            ShadcnToast._reposition_stack()
        except Exception:
            pass
        super().closeEvent(event)

    def _variant_palette(self, t: dict) -> tuple:
        v = self.toast_variant
        if v == "success":
            return (t.get("success", "#16A34A"), t["surface"],
                    t.get("success", "#16A34A"), t["foreground"])
        if v == "destructive":
            return (t.get("destructive", "#DC2626"), t["surface"],
                    t.get("destructive", "#DC2626"), t["foreground"])
        if v == "warning":
            return (t.get("warning", "#F59E0B"), t["surface"],
                    t.get("warning", "#F59E0B"), t["foreground"])
        if v == "info":
            return (t.get("info", "#3B82F6"), t["surface"],
                    t.get("info", "#3B82F6"), t["foreground"])
        return (t.get("primary", "#2563EB"), t["surface"],
                t["border"], t["foreground"])

    def _apply_theme(self):
        if ShadcnToast._suppressed > 0:
            return
        t = self.theme_manager.get_tokens()
        accent, bg, border, title_col = self._variant_palette(t)
        muted = t.get("muted-foreground", "#64748B")
        key = f"toast|{self.toast_variant}"

        def build():
            return f"""
                #ShadcnToast {{
                    background: {bg};
                    border: 1px solid {border};
                    border-radius: {t["radius-lg"]};
                }}
                #toastAccent {{ background: {accent}; border-radius: 2px; border: none; }}
                #toastDot {{ background: {accent}; border-radius: 5px; border: none; }}
                #toastTitle {{ font-weight: 600; color: {title_col}; background: transparent; border: none; }}
                #toastDesc {{ color: {muted}; background: transparent; border: none; }}
                #toastClose {{
                    background: transparent;
                    border: none;
                    color: {muted};
                    font-weight: 600;
                    border-radius: 11px;
                    padding: 0;
                }}
                #toastClose:hover {{
                    background: {t["secondary"]};
                    color: {title_col};
                }}
                #toastClose:focus {{
                    border: 2px solid {t["ring"]};
                }}
            """

        _apply_qss(self, key, build)

        try:
            ShadcnToast._reposition_stack()
        except Exception:
            pass


# =============================================================================
# SHEET
# =============================================================================

class ShadcnSheet(QDialog):
    def __init__(self, title: str, description: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("ShadcnSheet")
        self.setMinimumWidth(420)
        self.setAccessibleName(title)

        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

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
        close_btn.setAccessibleName("Close")
        close_btn.clicked.connect(self.close)
        hdr_lo.addWidget(close_btn)
        lo.addWidget(hdr)

        sep = ShadcnSeparator()
        lo.addWidget(sep)

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

        self.footer = QWidget()
        self.footer.setObjectName("sheetFooter")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(22, 14, 22, 18)
        self.footer_layout.setSpacing(8)
        lo.addWidget(self.footer)

        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        size = t.get("scrollbar_size", 10)
        radius = t.get("scrollbar_radius", 5)
        key = "sheet"

        def build():
            return f"""
                #ShadcnSheet {{ background: {t["surface"]}; border-left: 1px solid {t["border"]}; }}
                #sheetHeader {{ background: {t["surface"]}; }}
                #sheetFooter {{ background: {t["surface"]}; border-top: 1px solid {t["border"]}; }}
                QScrollArea {{ background: transparent; border: none; }}
                QScrollBar:vertical {{
                    background: {t.get("scrollbar_track", t["muted"])};
                    width: {size}px;
                    border: none;
                    border-radius: {radius}px;
                }}
                QScrollBar::handle:vertical {{
                    background: {t.get("scrollbar_handle", t["border-strong"])};
                    border-radius: {radius}px;
                    min-height: 36px;
                    margin: 2px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background: {t.get("scrollbar_handle_hover", t["foreground-secondary"])};
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            """

        _apply_qss(self, key, build)

    def add_widget(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def add_button(self, button: QWidget):
        self.footer_layout.addWidget(button)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)


# =============================================================================
# PAGINATION
# =============================================================================

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

    def _prev(self):
        self._goto(self.current - 1)

    def _next(self):
        self._goto(self.current + 1)

    def update_theme(self):
        for b in [self.prev_btn, self.next_btn, *self._page_btns]:
            b.update_theme()


# =============================================================================
# FIELD / FIELD GROUP
# =============================================================================

class ShadcnField(QWidget):
    def __init__(self, label: str = "", description: str = "",
                 error: str = "", orientation: str = "vertical",
                 required: bool = False, parent: Optional[QWidget] = None):
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
            lbl_text = f"{label} *" if required else label
            self.label_w = ShadcnLabel(lbl_text)
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
            self.error_w.setStyleSheet(f"color:{t['destructive']};")
            self.input_lo.addWidget(self.error_w)
        else:
            self.error_w = None

    def set_input(self, widget: QWidget):
        self.input_lo.insertWidget(0, widget)

    def set_error(self, msg: str):
        t = self.theme_manager.get_tokens()
        if self.error_w:
            self.error_w.setText(msg)
        elif msg:
            self.error_w = ShadcnCaption(msg)
            self.error_w.setStyleSheet(f"color:{t['destructive']};")
            self.input_lo.addWidget(self.error_w)


class ShadcnFieldGroup(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(16)

    def add_field(self, field: QWidget):
        self.main_layout.addWidget(field)


# =============================================================================
# ITEM
# =============================================================================

class ShadcnItem(QFrame):
    clicked = Signal()

    def __init__(self, title: str, description: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ShadcnItem")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title)
        if description:
            self.setAccessibleDescription(description)
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
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "item"

        def build():
            return f"""
                #ShadcnItem {{
                    background: {t["surface"]};
                    border: 1px solid {t["border"]};
                    border-radius: {t["radius"]};
                }}
                #ShadcnItem:hover {{ background: {t["surface-hover"]}; }}
                #ShadcnItem:focus {{ border: 2px solid {t["ring"]}; }}
                #itemTitle {{ font-weight: 500; color: {t["foreground"]}; background: transparent; }}
                #itemDesc {{ color: {t["muted-foreground"]}; background: transparent; }}
            """

        _apply_qss(self, key, build)

    def add_action(self, widget: QWidget):
        self.action_lo.addWidget(widget)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


# =============================================================================
# MENUBAR / NAVIGATION MENU
# =============================================================================

class ShadcnMenubar(QMenuBar):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "menubar"

        def build():
            return f"""
                QMenuBar {{
                    background: {t["surface"]};
                    border-bottom: 1px solid {t["border"]};
                    padding: 2px 8px;
                    color: {t["foreground"]};
                }}
                QMenuBar::item {{
                    background: transparent;
                    padding: 5px 10px;
                    border-radius: {t["radius-sm"]};
                }}
                QMenuBar::item:selected {{ background: {t["secondary"]}; }}
                QMenuBar::item:focus {{ border: 2px solid {t["ring"]}; }}
                QMenu {{
                    background: {t["popover"]};
                    border: 1px solid {t["border"]};
                    border-radius: {t["radius"]};
                    padding: 4px;
                }}
                QMenu::item {{
                    padding: 6px 22px 6px 12px;
                    border-radius: {t["radius-sm"]};
                    color: {t["foreground"]};
                }}
                QMenu::item:selected {{ background: {t["secondary"]}; }}
                QMenu::item:focus {{ border: 2px solid {t["ring"]}; }}
                QMenu::separator {{ height:1px; background:{t["border"]}; margin:4px 8px; }}
            """

        _apply_qss(self, key, build)


class ShadcnNavigationMenu(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(12, 6, 12, 6)
        lo.setSpacing(4)
        self.theme_manager = _theme()
        self._last_qss: Optional[str] = None
        self.update_theme()
        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.update_theme,
        )

    def update_theme(self):
        t = self.theme_manager.get_tokens()
        key = "navmenu"

        def build():
            return f"background:{t['surface']}; border-bottom:1px solid {t['border']};"

        _apply_qss(self, key, build)

    def add_item(self, text: str, callback):
        btn = ShadcnButton(text, variant="ghost", size="sm")
        btn.clicked.connect(callback)
        self.layout().addWidget(btn)

