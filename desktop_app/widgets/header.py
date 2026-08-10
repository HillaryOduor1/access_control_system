import re

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QMenu,
    QDialog, QSizePolicy, QToolButton, QFrame,QToolTip,
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QAction, QCursor, QColor, QPalette, QIcon

from core.icon_manager import IconManager
from core.theme_manager import ThemeManager
from pages.profile_dialog import ProfileDialog
from pages.change_password_dialog import ChangePasswordDialog
from widgets.components import ShadcnButton, ShadcnAvatar


class Header(QWidget):
    menu_toggled    = Signal()
    theme_toggled   = Signal()
    logout_requested = Signal()
    search_requested = Signal(str)

    def __init__(self, user_info, theme_manager: ThemeManager,
                 sidebar_expanded: bool = True, parent=None):
        super().__init__(parent)
        self.user_info        = user_info
        self.theme_manager    = theme_manager
        self.sidebar_expanded = sidebar_expanded
        self.setObjectName("header")
        self.setFixedHeight(52)

        self.icon_manager = IconManager()

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._emit_search)
        self._last_search = ""

        self._init_ui()
        self._refresh_icons()
        self.theme_manager.theme_changed.connect(self._on_theme_changed)
        self._apply_stylesheet()

    # UI construction

    def _init_ui(self):
        lo = QHBoxLayout(self)
        lo.setContentsMargins(16, 0, 16, 0)
        lo.setSpacing(8)

        # Sidebar toggle
        self.menu_btn = self._icon_btn("menu", "Toggle sidebar")
        self.menu_btn.clicked.connect(self.menu_toggled.emit)
        lo.addWidget(self.menu_btn)

        # Breadcrumb 
        self.breadcrumb = QLabel()
        self.breadcrumb.setObjectName("breadcrumb")
        self._set_breadcrumb("Dashboard")
        lo.addWidget(self.breadcrumb)

        lo.addStretch()

        # Search 
        search_wrap = QWidget()
        search_wrap.setObjectName("searchWrap")
        search_lo = QHBoxLayout(search_wrap)
        search_lo.setContentsMargins(0, 0, 0, 0)
        search_lo.setSpacing(0)

        self.search_prefix = QLabel()
        self.search_prefix.setObjectName("searchIcon")
        self.search_prefix.setFixedWidth(32)
        self.search_prefix.setAlignment(Qt.AlignCenter)
        search_lo.addWidget(self.search_prefix)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Search…")
        self.search_input.setMinimumWidth(220)
        self.search_input.setMaximumWidth(300)
        self.search_input.setFixedHeight(32)
        self.search_input.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        self.search_input.textChanged.connect(self._on_search_changed)
        search_lo.addWidget(self.search_input)
        search_wrap.setFixedHeight(32)
        lo.addWidget(search_wrap)

        # Divider 
        div = QFrame()
        div.setObjectName("headerDiv")
        div.setFrameShape(QFrame.Shape.VLine)
        div.setFixedSize(1, 22)
        lo.addWidget(div)

        # Notifications 
        self.notify_btn = self._icon_btn("notifications", "Notifications")
        self.notify_btn.clicked.connect(self._show_notifications)
        lo.addWidget(self.notify_btn)

        # Theme toggle 
        self.theme_btn = self._icon_btn("theme_light", "Toggle theme")
        self.theme_btn.clicked.connect(self._toggle_theme)
        lo.addWidget(self.theme_btn)

        lo.addSpacing(2)

        # User profile
        self.profile_btn = QToolButton(self)
        self.profile_btn.setObjectName("profileBtn")
        self.profile_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.profile_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.profile_btn.setAutoRaise(True)
        self.profile_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.profile_btn.setIconSize(QSize(28, 28))

        full_name = self.user_info.get("full_name", "User")
        avatar = ShadcnAvatar(fallback_text=full_name, size=28)
        pix = avatar.label.pixmap()
        if pix and not pix.isNull():
            self.profile_btn.setIcon(QIcon(pix))
        else:
            self.profile_btn.setIcon(
                self.icon_manager.get_icon("profile", size=QSize(28, 28))
            )
        self.profile_btn.setText(f"  {full_name}")

        menu = QMenu(self.profile_btn)
        menu.setObjectName("profileMenu")

        act_profile = QAction("Profile", self)
        act_profile.triggered.connect(self._show_profile)
        menu.addAction(act_profile)

        act_pw = QAction("Change password", self)
        act_pw.triggered.connect(self._show_change_password)
        menu.addAction(act_pw)

        menu.addSeparator()

        act_logout = QAction("Sign out", self)
        act_logout.triggered.connect(self.logout_requested.emit)
        menu.addAction(act_logout)

        self.profile_btn.setMenu(menu)
        lo.addWidget(self.profile_btn)

    def _icon_btn(self, icon_name: str, tooltip: str) -> ShadcnButton:
        btn = ShadcnButton(variant="ghost", size="sm")
        btn.setFixedSize(32, 32)
        btn.setToolTip(tooltip)
        btn._header_icon = icon_name   # store for refresh
        return btn

    # Stylesheet

    def _apply_stylesheet(self):
        t = self.theme_manager.get_tokens()
        bg        = t["background"]
        border    = t["border"]
        fg        = t["foreground"]
        muted     = t["muted-foreground"]
        secondary = t["secondary"]
        ring      = t["ring"]
        primary   = t["primary"]
        radius    = t["radius"]
        radius_sm = t["radius-sm"]
        popover   = t["popover"]
        popover_fg = t["popover-foreground"]
        brd_stg   = t["border-strong"]
        surface   = t["surface"]

        sheet = f"""
            /* Shell */
            #header {{
                background-color: {bg};
                border-bottom: 1px solid {border};
            }}

            /* Breadcrumb */
            #breadcrumb {{
                font-size: 13px;
                color: {muted};
                background: transparent;
            }}

            /* Search wrap */
            #searchWrap {{
                background: {surface};
                border: 1px solid {border};
                border-radius: {radius};
                padding: 0;
            }}
            #searchWrap:focus-within {{
                border: 1.5px solid {ring};
                background: {bg};
            }}
            #searchIcon {{
                color: {muted};
                font-size: 14px;
                background: transparent;
            }}
            #searchInput {{
                background: transparent;
                border: none;
                font-size: 13px;
                color: {fg};
                padding: 0 10px 0 0;
            }}
            #searchInput::placeholder {{ color: {muted}; }}
            #searchInput:focus {{ outline: none; border: none; }}

            /* Vertical divider*/
            #headerDiv {{
                background: {border};
                border: none;
                max-width: 1px;
            }}

            /* Ghost icon buttons */
            ShadcnButton[variant="ghost"] {{
                background: transparent;
                border: none;
                border-radius: {radius};
                color: {muted};
            }}
            ShadcnButton[variant="ghost"]:hover {{
                background: {secondary};
                color: {fg};
            }}

            /* Profile button */
            #profileBtn {{
                background: transparent;
                border: none;
                border-radius: {radius};
                padding: 4px 8px;
                font-size: 13px;
                font-weight: 500;
                color: {fg};
                spacing: 0px;
            }}
            #profileBtn:hover {{
                background: {secondary};
            }}
            #profileBtn::menu-indicator {{ image: none; }}

            /* Profile dropdown menu */
            #profileMenu, QMenu {{
                background: {popover};
                border: 1px solid {border};
                border-radius: {radius};
                padding: 4px;
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 6px 20px 6px 12px;
                border-radius: {radius_sm};
                color: {popover_fg};
            }}
            QMenu::item:selected {{
                background: {secondary};
            }}
            QMenu::separator {{
                height: 1px;
                background: {border};
                margin: 4px 8px;
            }}

            /* Tooltip */
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

    # Icon refresh

    def _refresh_icons(self):
        is_dark = self.theme_manager.get_current_theme() == "dark"

        icon_assignments = {
            self.menu_btn:   "menu",
            self.notify_btn: "notifications",
            self.theme_btn:  "theme_dark" if is_dark else "theme_light",
        }
        for btn, name in icon_assignments.items():
            btn.setIcon(
                self.icon_manager.get_icon(name, size=QSize(18, 18), state="default")
            )
            btn.setIconSize(QSize(18, 18))

        self.theme_btn.setToolTip(
            "Switch to light mode" if is_dark else "Switch to dark mode"
        )

        # Search magnifier icon (text fallback if icon not available)
        try:
            pix = self.icon_manager.get_icon("search", size=QSize(14, 14), state="default")
            self.search_prefix.setPixmap(pix.pixmap(14, 14))
        except Exception:
            self.search_prefix.setText("⌕")

        # Profile avatar
        full_name = self.user_info.get("full_name", "User")
        avatar = ShadcnAvatar(fallback_text=full_name, size=28)
        pix = avatar.label.pixmap()
        if pix and not pix.isNull():
            self.profile_btn.setIcon(QIcon(pix))
        self.profile_btn.setText(f"  {full_name}")

    # Breadcrumb helper

    def _set_breadcrumb(self, page: str):
        t = self.theme_manager.get_tokens()
        muted = t.get("muted-foreground", "#888")
        fg    = t.get("foreground", "#111")
        self.breadcrumb.setText(
            f"<span style='color:{muted}'>ICT Authority</span>"
            f"<span style='color:{muted}'> / </span>"
            f"<span style='color:{fg}; font-weight:500'>{page}</span>"
        )

    # Theme change
    
    def _on_theme_changed(self):
        self._apply_stylesheet()
        self._refresh_icons()
        self._set_breadcrumb(self._current_page)

    # Back-compat alias
    def update_theme(self):
        self._on_theme_changed()

    # Public API

    _current_page = "Dashboard"

    def set_title(self, title: str):
        self._current_page = title
        self._set_breadcrumb(title)

    def set_sidebar_expanded(self, expanded: bool):
        self.sidebar_expanded = expanded

    def _toggle_theme(self):
        self.theme_manager.toggle_theme()
        self.theme_toggled.emit()

    # Search debounce

    def _on_search_changed(self, text: str):
        self._last_search = text
        self._search_timer.start(280)

    def _emit_search(self):
        self.search_requested.emit(self._last_search)

    # Dialogs

    def _show_notifications(self):
        from widgets.components import ShadcnSheet
        sheet = ShadcnSheet("Notifications", parent=self)
        from widgets.components import ShadcnCaption
        sheet.add_widget(ShadcnCaption("You have no new notifications."))
        sheet.exec()

    def _show_profile(self):
        dialog = ProfileDialog(self.user_info, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.user_info.update(dialog.get_updated_info())
            self._refresh_icons()

    def _show_change_password(self):
        dialog = ChangePasswordDialog(self.user_info["id"], self)
        dialog.exec()
