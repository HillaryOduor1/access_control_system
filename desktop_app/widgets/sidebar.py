import re
import colorsys
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QButtonGroup, QSizePolicy, QToolTip,
)
from PySide6.QtCore import (
    Qt, QSize, Signal, QPropertyAnimation, QEasingCurve,
    QTimer, QEvent, QSettings,
)
from PySide6.QtGui import QFont, QCursor, QColor, QPalette, QKeyEvent, QPixmap

from core.icon_manager import IconManager
from widgets.components import ShadcnButton, ShadcnAvatar
from config import Config

# NavigationButton

class NavigationButton(ShadcnButton):
    """
    Sidebar nav button — styling is entirely owned by the sidebar stylesheet.
    ShadcnButton.update_theme() is suppressed via the "nav-button" class property.
    """

    def __init__(self, parent=None):
        super().__init__(variant="ghost", size="sm", parent=parent)
        self.setProperty("class", "nav-button")
        self.setCheckable(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(36)
        # Left-align icon + text
        self.setStyleSheet("")   # blank until sidebar applies its sheet

    def update_theme(self):
        # Sidebar owns this button's stylesheet — do nothing here.
        pass

# Sidebar

class Sidebar(QWidget):
    toggled = Signal(bool)
    navigation_requested = Signal(str)

    # geometry constants
    EXPANDED_W  = 240
    COLLAPSED_W = 60
    AUTO_COLLAPSE_AT = 1100   # px — window width below which auto-collapse fires

    # page → permission mapping
    _PERM_MAP = {
        "dashboard":   "view_dashboard",
        "visitors":    "manage_visitors",
        "employees":   "manage_employees",
        "access_logs": "view_access_logs",
        "field_config":"configure_fields",
        "reports":     "view_reports",
        "settings":    "manage_settings",
        "users":       "manage_users",
    }

    _ICON_MAP = {
        "dashboard":   "dashboard",
        "visitors":    "visitors",
        "employees":   "employees",
        "access_logs": "access_logs",
        "field_config":"field_config",
        "reports":     "report",
        "settings":    "settings",
        "users":       "user",
    }

    def __init__(self, permissions, user_info, theme_manager, parent=None):
        super().__init__(parent)
        self.permissions   = permissions
        self.user_info     = user_info
        self.theme_manager = theme_manager
        self.expanded      = True

        self._settings    = QSettings("ICTAuthority", "AccessControl")
        self._user_locked = self._settings.value("sidebar_locked", False, type=bool)

        self.setObjectName("sidebar")
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.setAccessibleName("Application Navigation")

        self.icon_manager = IconManager()

        # animations
        dur = Config.SIDEBAR_ANIMATION_DURATION
        if getattr(Config, "REDUCED_MOTION", False):
            dur = 0
        self._anim_min = QPropertyAnimation(self, b"minimumWidth")
        self._anim_min.setDuration(dur)
        self._anim_min.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim_max = QPropertyAnimation(self, b"maximumWidth")
        self._anim_max.setDuration(dur)
        self._anim_max.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.setMinimumWidth(self.EXPANDED_W)
        self.setMaximumWidth(self.EXPANDED_W)

        # state
        self._nav_order:   list[str]                = []
        self._button_map:  dict[str, NavigationButton] = {}
        self._group_labels: dict[str, QLabel]        = {}
        self._current_index = -1

        self._init_ui()
        self._refresh_icons()
        self.theme_manager.theme_changed.connect(self._on_theme_changed)
        self._apply_stylesheet()

        self._build_button_list()
        self.setFocusPolicy(Qt.StrongFocus)

        if self.parent():
            self.parent().installEventFilter(self)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._handle_resize_debounced)

    # UI construction

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Logo row
        self._logo_widget = QWidget()
        self._logo_widget.setObjectName("sidebarLogo")
        self._logo_widget.setFixedHeight(52)
        logo_lo = QHBoxLayout(self._logo_widget)
        logo_lo.setContentsMargins(14, 0, 10, 0)
        logo_lo.setSpacing(10)

        # Logo image (replace monogram)
        self._logo_mark = QLabel()
        self._logo_mark.setFixedSize(28, 28)
        self._logo_mark.setObjectName("logoMark")
        self._logo_mark.setAlignment(Qt.AlignCenter)
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                 "assets", "images", "icta-desktop-logo1.png")
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._logo_mark.setPixmap(scaled)
            self._logo_mark.setStyleSheet("")   # clear any background
        else:
            # Fallback to initials
            self._logo_mark.setText("IA")
            self._logo_mark.setStyleSheet(
                "background:#16a34a; border-radius:7px; color:white;"
                "font-weight:600; font-size:11px;"
            )

        self._logo_text = QLabel("ICT Authority")
        self._logo_text.setObjectName("logoText")

        self._collapse_btn = ShadcnButton(variant="ghost", size="sm")
        self._collapse_btn.setObjectName("collapseBtn")
        self._collapse_btn.setFixedSize(26, 26)
        self._collapse_btn.setToolTip("Collapse sidebar")
        self._collapse_btn.clicked.connect(lambda: self.toggle_collapse(user_initiated=True))

        logo_lo.addWidget(self._logo_mark)
        logo_lo.addWidget(self._logo_text, 1)
        logo_lo.addWidget(self._collapse_btn)
        root.addWidget(self._logo_widget)

        # Logo separator
        sep = QFrame()
        sep.setObjectName("sidebarSep")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.viewport().setStyleSheet("background:transparent;")
        self._scroll.setAccessibleName("Navigation List")

        scroll_content = QWidget()
        self._nav_lo = QVBoxLayout(scroll_content)
        self._nav_lo.setContentsMargins(8, 10, 8, 10)
        self._nav_lo.setSpacing(1)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._btn_group.buttonClicked.connect(self._on_btn_clicked)

        # Build navigation groups
        nav_groups: dict[str, list[str]] = {
            "Main":          ["dashboard", "visitors", "employees"],
            "Security":      ["access_logs"],
            "Configuration": ["field_config", "settings"],
        }
        if "view_reports" in self.permissions:
            nav_groups["Analytics"] = ["reports"]
        if "manage_users" in self.permissions:
            nav_groups["Administration"] = ["users"]

        any_added = False
        for group_name, pages in nav_groups.items():
            accessible = [p for p in pages if self._has_access(p)]
            if not accessible:
                continue
            any_added = True

            lbl = QLabel(group_name.upper())
            lbl.setObjectName("navGroupLabel")
            lbl.setVisible(self.expanded)
            self._nav_lo.addWidget(lbl)
            self._group_labels[group_name] = lbl

            for page_id in accessible:
                btn = NavigationButton()
                btn.setObjectName("navButton")
                btn.setProperty("page", page_id)
                btn.setAccessibleName(page_id.replace("_", " ").title())
                btn.setAccessibleDescription(f"Navigate to {page_id.replace('_', ' ').title()}")
                self._nav_lo.addWidget(btn)
                self._button_map[page_id] = btn
                self._btn_group.addButton(btn)
                self._nav_order.append(page_id)

        if not any_added:
            empty = QLabel("No accessible modules.\nContact administrator.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet("color:gray; padding:24px;")
            self._nav_lo.addWidget(empty)

        self._nav_lo.addStretch()
        self._scroll.setWidget(scroll_content)
        root.addWidget(self._scroll, 1)

        # Footer separator
        foot_sep = QFrame()
        foot_sep.setObjectName("sidebarSep")
        foot_sep.setFrameShape(QFrame.Shape.HLine)
        foot_sep.setFixedHeight(1)
        root.addWidget(foot_sep)

        # User footer
        self._footer = QWidget()
        self._footer.setObjectName("sidebarFooter")
        self._footer.setFixedHeight(56)
        foot_lo = QHBoxLayout(self._footer)
        foot_lo.setContentsMargins(12, 0, 12, 0)
        foot_lo.setSpacing(10)

        full_name = self.user_info.get("full_name", "User")
        self._avatar = ShadcnAvatar(fallback_text=full_name, size=28)
        foot_lo.addWidget(self._avatar)

        self._user_info_widget = QWidget()
        info_lo = QVBoxLayout(self._user_info_widget)
        info_lo.setContentsMargins(0, 0, 0, 0)
        info_lo.setSpacing(1)
        self._user_name_lbl = QLabel(full_name)
        self._user_name_lbl.setObjectName("userName")
        role = self.user_info.get("role", "")
        self._user_role_lbl = QLabel(role)
        self._user_role_lbl.setObjectName("userRole")
        info_lo.addWidget(self._user_name_lbl)
        if role:
            info_lo.addWidget(self._user_role_lbl)
        foot_lo.addWidget(self._user_info_widget, 1)

        root.addWidget(self._footer)

    # Stylesheet

    def _hsl_to_rgb_str(self, color_str: str) -> str:
        color_str = color_str.strip()
        m = re.match(r"hsl\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*\)", color_str)
        if m:
            h = float(m.group(1)) / 360.0
            s = float(m.group(2)) / 100.0
            l = float(m.group(3)) / 100.0
            r, g, b = colorsys.hls_to_rgb(h, l, s)
            return f"{int(r*255)},{int(g*255)},{int(b*255)}"
        c = QColor(color_str)
        if c.isValid():
            return f"{c.red()},{c.green()},{c.blue()}"
        return "0,0,0"

    def _rgba(self, color_str: str, alpha: float) -> str:
        return f"rgba({self._hsl_to_rgb_str(color_str)},{alpha})"

    def _apply_stylesheet(self):
        t = self.theme_manager.get_tokens()
        bg         = t["background"]
        surface    = t["surface"]
        border     = t["border"]
        fg         = t["foreground"]
        fg2        = t["foreground-secondary"]
        muted_fg   = t["muted-foreground"]
        secondary  = t["secondary"]
        primary    = t["primary"]
        radius     = t["radius"]
        radius_sm  = t["radius-sm"]
        prim_sub   = t["primary-subtle"]
        brd_strong = t["border-strong"]

        sheet = f"""
            /* ── Shell ── */
            #sidebar {{
                background-color: {bg};
                border-right: 1px solid {border};
            }}

            /* ── Logo row ── */
            #sidebarLogo {{
                background: {bg};
            }}
            #logoText {{
                font-size: 13px;
                font-weight: 600;
                color: {fg};
            }}
            #collapseBtn {{
                background: transparent;
                border: none;
                color: {muted_fg};
                border-radius: {radius_sm};
                padding: 0;
            }}
            #collapseBtn:hover {{
                background: {secondary};
                color: {fg};
            }}

            /* ── Separator ── */
            #sidebarSep {{
                background: {border};
                border: none;
                max-height: 1px;
            }}

            /* ── Scroll area ── */
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 4px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: transparent;
                border-radius: 2px;
                min-height: 32px;
            }}
            QScrollArea:hover QScrollBar::handle:vertical {{
                background: {border};
            }}
            QScrollBar::handle:vertical:hover {{
                background: {brd_strong};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{ background: transparent; }}

            /* ── Group labels ── */
            #navGroupLabel {{
                font-size: 10px;
                font-weight: 600;
                color: {muted_fg};
                letter-spacing: 0.07em;
                padding: 12px 10px 3px;
                background: transparent;
            }}

            /* ── Nav buttons ── */
            #navButton {{
                background: transparent;
                color: {fg2};
                border: none;
                border-radius: {radius};
                padding: 0 10px;
                height: 36px;
                font-size: 13px;
                font-weight: 400;
                text-align: left;
            }}
            #navButton:hover {{
                background: {secondary};
                color: {fg};
            }}
            #navButton:checked {{
                background: {prim_sub};
                color: {primary};
                font-weight: 500;
            }}
            #navButton:focus {{
                outline: none;
                border: 1.5px solid {primary};
                padding: 0 9px;
            }}
            #navButton:checked:focus {{
                border: 1.5px solid {primary};
                padding: 0 9px;
            }}

            /* ── Footer ── */
            #sidebarFooter {{
                background: {bg};
            }}
            #userName {{
                font-size: 12px;
                font-weight: 500;
                color: {fg};
                background: transparent;
            }}
            #userRole {{
                font-size: 11px;
                color: {muted_fg};
                background: transparent;
            }}

            /* ── Tooltips ── */
            QToolTip {{
                background: {fg};
                color: {bg};
                border: none;
                border-radius: {radius_sm};
                padding: 4px 9px;
                font-size: 12px;
            }}
        """
        self.setStyleSheet(sheet)
        self._apply_tooltip_palette(t)

    def _apply_tooltip_palette(self, tokens: dict):
        def _hsl(s):
            m = re.match(r"hsl\(\s*(\d+)\s*,\s*(\d+)%\s*,\s*(\d+)%\s*\)", s)
            if m:
                return QColor.fromHslF(
                    int(m.group(1)) / 360.0,
                    int(m.group(2)) / 100.0,
                    int(m.group(3)) / 100.0,
                )
            return QColor(s)
        pal = QToolTip.palette()
        pal.setColor(QPalette.ToolTipBase, _hsl(tokens["foreground"]))
        pal.setColor(QPalette.ToolTipText, _hsl(tokens["background"]))
        QToolTip.setPalette(pal)

    # Theme change handler

    def _on_theme_changed(self):
        self._apply_stylesheet()
        self._refresh_icons()
        for child in self.findChildren(QWidget):
            child.style().unpolish(child)
            child.style().polish(child)

    # Back-compat public alias
    def update_theme(self):
        self._on_theme_changed()

    # Icon / text refresh


    def _refresh_icons(self):
        for page_id, btn in self._button_map.items():
            icon_name = self._ICON_MAP.get(page_id, "dashboard")
            state = "active" if btn.isChecked() else "default"
            btn.setIcon(
                self.icon_manager.get_icon(icon_name, size=QSize(16, 16), state=state)
            )
            btn.setIconSize(QSize(16, 16))
            if self.expanded:
                btn.setText(f"  {page_id.replace('_', ' ').title()}")
                btn.setToolTip("")
            else:
                btn.setText("")
                btn.setToolTip(page_id.replace("_", " ").title())

        # Collapse button icon
        arrow = "←" if self.expanded else "→"
        self._collapse_btn.setText(arrow)

        # Group labels
        for lbl in self._group_labels.values():
            lbl.setVisible(self.expanded)

        # Logo text
        self._logo_text.setVisible(self.expanded)

        # User info
        self._user_info_widget.setVisible(self.expanded)

    # Access helpers


    def _has_access(self, page_id: str) -> bool:
        return self._PERM_MAP.get(page_id) in self.permissions

    def _build_button_list(self):
        self._current_index = 0 if self._nav_order else -1

    # Navigation state


    def set_active(self, page_id: str):
        if page_id not in self._button_map:
            return
        btn = self._button_map[page_id]
        btn.blockSignals(True)
        btn.setChecked(True)
        btn.blockSignals(False)
        if page_id in self._nav_order:
            self._current_index = self._nav_order.index(page_id)
        self._refresh_icons()

    def _on_btn_clicked(self, btn):
        page_id = btn.property("page")
        if page_id and btn.isChecked():
            self.navigation_requested.emit(page_id)

    def set_badge(self, page_id: str, count: int):
        """Optionally surface badge counts (caller handles the visual)."""
        pass  # Extend if you want QLabel badges overlaid on buttons

    # Keyboard navigation


    def _highlight_button(self, idx: int):
        if not (0 <= idx < len(self._nav_order)):
            return
        btn = self._button_map[self._nav_order[idx]]
        btn.setFocus(Qt.FocusReason.TabFocusReason)
        self._scroll.ensureWidgetVisible(btn)

    def _set_focused_index(self, idx: int):
        if 0 <= idx < len(self._nav_order):
            self._current_index = idx
            self._highlight_button(idx)

    def keyPressEvent(self, event: QKeyEvent):
        if not self._nav_order:
            super().keyPressEvent(event)
            return
        k = event.key()
        n = len(self._nav_order)
        if k == Qt.Key_Down:
            self._set_focused_index((self._current_index + 1) % n); event.accept()
        elif k == Qt.Key_Up:
            self._set_focused_index((self._current_index - 1) % n); event.accept()
        elif k == Qt.Key_Home:
            self._set_focused_index(0); event.accept()
        elif k == Qt.Key_End:
            self._set_focused_index(n - 1); event.accept()
        elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if 0 <= self._current_index < n:
                self._button_map[self._nav_order[self._current_index]].click()
            event.accept()
        elif k == Qt.Key_Right:
            central = self.parent().findChild(QWidget, "centralWidget") if self.parent() else None
            if central: central.setFocus()
            event.accept()
        elif k == Qt.Key_Escape:
            self.clearFocus()
            central = self.parent().findChild(QWidget, "centralWidget") if self.parent() else None
            if central: central.setFocus()
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        if self._nav_order and self._current_index == -1:
            checked = self._btn_group.checkedButton()
            if checked:
                for i, pid in enumerate(self._nav_order):
                    if self._button_map[pid] is checked:
                        self._current_index = i; break
            else:
                self._current_index = 0
        if self._current_index >= 0:
            self._highlight_button(self._current_index)
        super().focusInEvent(event)

    # Collapse / expand

    def toggle_collapse(self, user_initiated: bool = False):
        if user_initiated:
            self._user_locked = True
            self._settings.setValue("sidebar_locked", True)

        self._anim_min.stop()
        self._anim_max.stop()

        self.expanded = not self.expanded
        w = self.EXPANDED_W if self.expanded else self.COLLAPSED_W
        for anim in (self._anim_min, self._anim_max):
            anim.setEndValue(w)
            anim.start()

        self._refresh_icons()
        self.toggled.emit(self.expanded)

    # Auto-collapse on resize

    def _handle_resize_debounced(self):
        if self._user_locked:
            return
        pw = self.parent().width() if self.parent() else 0
        should_collapse = pw < self.AUTO_COLLAPSE_AT
        if should_collapse == self.expanded:  # state mismatch → toggle
            self.toggle_collapse(user_initiated=False)

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == QEvent.Resize:
            self._resize_timer.start(150)
        return super().eventFilter(obj, event)

    # Public geometry setters (for external callers)

    def setExpandedWidth(self, width: int):
        self.EXPANDED_W = width
        if self.expanded:
            self.setMinimumWidth(width)
            self.setMaximumWidth(width)

    def setCollapsedWidth(self, width: int):
        self.COLLAPSED_W = width
        if not self.expanded:
            self.setMinimumWidth(width)
            self.setMaximumWidth(width)

