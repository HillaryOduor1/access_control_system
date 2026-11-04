# widgets/header.py
"""
Enterprise header with search, environment management, and user profile.

Layout contract
---------------
The header is a fixed-height row. Every child control is sized so
that its *outer* box (including any focus ring drawn by QSS) fits
comfortably inside HEADER_HEIGHT with at least 6px of vertical
breathing room on top and bottom.

Search field sizing
-------------------
The search field has its own object-scoped QSS (`#searchInput`)
because the global `QLineEdit { min-height: control_height }` rule
would otherwise force it to grow past the 30px we want. The wrapper
(`#searchWrap`) is sized to the input's outer box plus a small
allowance for the focus ring.

Profile cluster
---------------
The profile is a QWidget wrapper containing a QToolButton (the
avatar + name) and a QLabel chevron. The wrapper handles clicks and
opens the button's menu; the button's own platform-drawn
menu-indicator is hidden because it is tiny, hard to restyle, and
inconsistent with the app's icon language. The chevron glyph is
drawn from the Material "expand_more" icon at 14px, matching the
adjacent icon buttons.

Theme-toggle latency
--------------------
Clicking the theme toggle used to feel slow because the click
handler synchronously ran the whole chain:

    toggle_theme() -> set_theme() -> update_appearance()
        -> apply_current_theme()   [repolish every visible widget]
        -> _emit_change()          [theme_changed + appearance_changed]
            -> Header.on_theme_changed()
            -> Header.on_appearance_changed()
            -> Sidebar.on_theme_changed()
            -> Sidebar.on_appearance_changed()
            -> every registered widget's hook

Each of those hooks did its own setStyleSheet() + icon re-rasterize.
The theme visibly changed only after all of that finished.

The fix is to coalesce header-side refreshes into a single
zero-delay pass and to skip work when the appearance signature has
not actually changed. The rest of the tree (sidebar, pages) is
similarly coalesced by ThemeManager itself.
"""
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QMenu,
    QDialog, QSizePolicy, QToolButton, QFrame, QToolTip, QApplication,
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QEvent
from PySide6.QtGui import (
    QAction, QCursor, QColor, QPalette, QIcon, QKeyEvent, QPixmap,
    QShortcut, QKeySequence,
)

from core.icon_manager import IconManager
from core.theme_manager import ThemeManager
from pages.profile_dialog import ProfileDialog
from pages.change_password_dialog import ChangePasswordDialog
from widgets.components import ShadcnButton, ShadcnAvatar
from config import Config

logger = logging.getLogger(__name__)


class Header(QWidget):
    """
    Enterprise application header with search, environment switching,
    and user menu.
    """

    menu_toggled = Signal()
    theme_toggled = Signal()
    logout_requested = Signal()
    search_requested = Signal(str)

    HEADER_HEIGHT = Config.TOPBAR_HEIGHT

    SEARCH_HEIGHT = 30
    SEARCH_FOCUS_ALLOWANCE = 4
    SEARCH_WIDTH = 260
    ICON_BUTTON_SIZE = 32

    def __init__(
        self,
        user_info: dict,
        theme_manager: ThemeManager,
        sidebar_expanded: bool = True,
        data_service=None,
        parent=None,
    ):
        super().__init__(parent)
        self.user_info = user_info
        self.theme_manager = theme_manager
        self.sidebar_expanded = sidebar_expanded
        self.data_service = data_service

        self.setObjectName("header")
        self.setFixedHeight(self.HEADER_HEIGHT)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAccessibleName("Application header")

        self.icon_manager = IconManager()
        self._current_page = "Dashboard"
        self._notification_count = 0
        self._profile_menu: Optional[QMenu] = None

        # Cache of the last appearance we styled against. Used to
        # short-circuit redundant refresh passes.
        self._last_style_key: Optional[tuple] = None

        # Coalesces theme/appearance change signals into a single
        # refresh pass. A single toggle can fire both signals; a
        # burst of update_appearance() calls can fire more. We only
        # want to run _apply_header_refresh once per event-loop turn.
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(0)
        self._apply_timer.timeout.connect(self._apply_header_refresh)

        # Debounce timer for theme-driven icon refreshes. Kept
        # separate because _do_refresh_icons is also called from
        # __init__ (no coalescing needed there).
        self._refresh_debounce = QTimer(self)
        self._refresh_debounce.setSingleShot(True)
        self._refresh_debounce.setInterval(0)
        self._refresh_debounce.timeout.connect(self._do_refresh_icons)

        # Debounce for search.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._emit_search)
        self._last_search = ""

        full_name = self.user_info.get("full_name", "User")
        self._avatar = ShadcnAvatar(fallback_text=full_name, size=28)

        self._init_ui()
        self._ensure_profile_menu()

        self._search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._search_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._search_shortcut.activated.connect(self._focus_search)

        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.on_theme_changed,
            on_appearance_changed=self.on_appearance_changed,
        )

        # Initial application of styles and icons. Called directly,
        # not through the coalescing timer, because we want the
        # header to be styled the moment it is created.
        self._apply_search_style()
        self._apply_profile_style()
        self._do_refresh_icons()
        self._last_style_key = self._style_key()

    # ==================================================================
    # UI construction
    # ==================================================================

    def _init_ui(self):
        lo = QHBoxLayout(self)
        lo.setContentsMargins(16, 0, 16, 0)
        lo.setSpacing(8)

        # --- left cluster ---------------------------------------------
        self.menu_btn = self._icon_btn("menu", "Toggle sidebar (Ctrl+B)")
        self.menu_btn.clicked.connect(self.menu_toggled.emit)
        lo.addWidget(self.menu_btn)

        self.breadcrumb = QLabel()
        self.breadcrumb.setObjectName("breadcrumb")
        self.breadcrumb.setAccessibleName("Breadcrumb")
        self._set_breadcrumb("Dashboard")
        lo.addWidget(self.breadcrumb)

        lo.addStretch()

        # --- search ---------------------------------------------------
        self._search_wrap = QWidget()
        self._search_wrap.setObjectName("searchWrap")
        self._search_wrap.setFixedHeight(
            self.SEARCH_HEIGHT + self.SEARCH_FOCUS_ALLOWANCE
        )
        self._search_wrap.setFixedWidth(
            self.SEARCH_WIDTH + self.SEARCH_FOCUS_ALLOWANCE
        )

        search_lo = QHBoxLayout(self._search_wrap)
        search_lo.setContentsMargins(
            self.SEARCH_FOCUS_ALLOWANCE // 2,
            self.SEARCH_FOCUS_ALLOWANCE // 2,
            self.SEARCH_FOCUS_ALLOWANCE // 2,
            self.SEARCH_FOCUS_ALLOWANCE // 2,
        )
        search_lo.setSpacing(0)

        self.search_prefix = QLabel()
        self.search_prefix.setObjectName("searchIcon")
        self.search_prefix.setFixedWidth(26)
        self.search_prefix.setAlignment(Qt.AlignCenter)
        search_lo.addWidget(self.search_prefix)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Search… (Ctrl+F)")
        self.search_input.setAccessibleName("Search")
        self.search_input.setFixedHeight(self.SEARCH_HEIGHT)
        self.search_input.setMinimumWidth(0)
        self.search_input.setMaximumWidth(16777215)
        self.search_input.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        self.search_input.textChanged.connect(self._on_search_changed)
        search_lo.addWidget(self.search_input, 1)

        lo.addWidget(self._search_wrap)

        # --- divider --------------------------------------------------
        div = QFrame()
        div.setObjectName("headerDiv")
        div.setFrameShape(QFrame.Shape.VLine)
        div.setFixedSize(1, 22)
        lo.addWidget(div)

        # --- right cluster --------------------------------------------
        self.notify_btn = self._icon_btn("notifications", "Notifications")
        self.notify_btn.clicked.connect(self._show_notifications)
        lo.addWidget(self.notify_btn)

        self.theme_btn = self._icon_btn("theme_light", "Toggle theme")
        self.theme_btn.clicked.connect(self._toggle_theme)
        lo.addWidget(self.theme_btn)

        lo.addSpacing(2)

        # --- profile cluster: button + chevron -----------------------
        self._profile_wrap = QWidget()
        self._profile_wrap.setObjectName("profileWrap")
        self._profile_wrap.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )

        profile_lo = QHBoxLayout(self._profile_wrap)
        profile_lo.setContentsMargins(6, 0, 8, 0)
        profile_lo.setSpacing(6)

        self.profile_btn = QToolButton(self._profile_wrap)
        self.profile_btn.setObjectName("profileBtn")
        self.profile_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.profile_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.profile_btn.setAutoRaise(True)
        self.profile_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.profile_btn.setIconSize(QSize(28, 28))
        self.profile_btn.setAccessibleName("User menu")
        self.profile_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        profile_lo.addWidget(self.profile_btn)

        self.profile_chevron = QLabel(self._profile_wrap)
        self.profile_chevron.setObjectName("profileChevron")
        self.profile_chevron.setFixedSize(16, 16)
        self.profile_chevron.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.profile_chevron.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        profile_lo.addWidget(self.profile_chevron)

        # Clicking anywhere on the wrapper opens the menu.
        self._profile_wrap.mousePressEvent = self._on_profile_wrap_clicked

        self._apply_profile_icon_and_text()
        lo.addWidget(self._profile_wrap)

    # ==================================================================
    # Coalesced header refresh
    # ==================================================================

    def _style_key(self) -> tuple:
        """
        Cheap signature of everything that affects the header's
        appearance. If this key is unchanged, a refresh pass can be
        skipped entirely.
        """
        appearance = self.theme_manager.get_appearance()
        return (
            appearance.get("theme"),
            appearance.get("font_family"),
            appearance.get("font_size"),
            appearance.get("font_weight"),
            appearance.get("density"),
            appearance.get("radius"),
            appearance.get("high_contrast"),
            appearance.get("reduced_effects"),
        )

    def _schedule_header_refresh(self):
        """
        Queue a coalesced refresh pass. Multiple calls within the
        same event-loop turn produce a single _apply_header_refresh.
        """
        try:
            self._apply_timer.start()
        except RuntimeError:
            return

    def _apply_header_refresh(self):
        """
        Run one refresh pass against the current theme. Bails out if
        nothing actually changed since the last pass.
        """
        try:
            key = self._style_key()
        except RuntimeError:
            return

        if key == self._last_style_key:
            return

        self._last_style_key = key

        try:
            self._apply_search_style()
            self._apply_profile_style()
            self._set_breadcrumb(self._current_page)
            self._refresh_icons()
            self.update()
        except RuntimeError:
            return

    # ==================================================================
    # Search field styling
    # ==================================================================

    def _apply_search_style(self):
        t = self.theme_manager.get_tokens()
        radius = t["radius"]
        ring = t.get("ring", t["primary"])

        self.search_input.setStyleSheet(f"""
            QLineEdit#searchInput {{
                background-color: {t['input']};
                border: 1px solid {t['border']};
                border-radius: {radius};
                padding: 0 10px;
                color: {t['foreground']};
                min-height: 0;
                max-height: {self.SEARCH_HEIGHT}px;
                selection-background-color: {t['primary']};
                selection-color: {t['primary-foreground']};
            }}
            QLineEdit#searchInput:hover {{
                border-color: {t['border-strong']};
            }}
            QLineEdit#searchInput:focus {{
                border: 2px solid {ring};
            }}
            QLineEdit#searchInput:disabled {{
                background-color: {t['muted']};
                color: {t['muted-foreground']};
            }}
        """)

        self.search_prefix.setStyleSheet(
            f"background: transparent; "
            f"color: {t['muted-foreground']}; "
            f"padding-right: 4px;"
        )

    # ==================================================================
    # Profile cluster styling
    # ==================================================================

    def _apply_profile_style(self):
        """
        Style the profile wrapper, button, and chevron.

        The button's default menu-indicator is hidden: on Windows it
        is drawn as a tiny platform chevron that cannot be themed or
        resized through QSS. We replace it with an explicit QLabel
        chevron rendered from the Material "expand_more" icon, which
        is 14px and sits in the same visual tier as the other header
        icons.
        """
        t = self.theme_manager.get_tokens()
        radius = t["radius"]
        ring = t.get("ring", t["primary"])

        self._profile_wrap.setStyleSheet(f"""
            QWidget#profileWrap {{
                background: transparent;
                border: 2px solid transparent;
                border-radius: {radius};
            }}
            QWidget#profileWrap:hover {{
                background: {t['secondary']};
            }}
            QWidget#profileWrap:focus {{
                border: 2px solid {ring};
            }}

            QToolButton#profileBtn {{
                background: transparent;
                border: none;
                padding: 0;
                color: {t['foreground']};
                font-weight: 500;
            }}
            QToolButton#profileBtn:hover {{
                background: transparent;
            }}
            QToolButton#profileBtn::menu-indicator {{
                image: none;
                width: 0px;
                height: 0px;
            }}

            QLabel#profileChevron {{
                background: transparent;
                color: {t['muted-foreground']};
            }}
        """)

    # ==================================================================
    # Profile menu
    # ==================================================================

    def _ensure_profile_menu(self):
        if self._profile_menu is not None:
            return

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

        self._profile_menu = menu
        self.profile_btn.setMenu(menu)

    def _on_profile_wrap_clicked(self, event):
        """
        Open the profile menu when the user clicks anywhere on the
        wrapper (avatar, name, or chevron).
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.profile_btn.showMenu()
            event.accept()
            return
        QWidget.mousePressEvent(self._profile_wrap, event)

    def _icon_btn(self, icon_name: str, tooltip: str) -> ShadcnButton:
        btn = ShadcnButton(variant="ghost", size="sm")
        btn.setFixedSize(self.ICON_BUTTON_SIZE, self.ICON_BUTTON_SIZE)
        btn.setToolTip(tooltip)
        btn.setAccessibleName(tooltip)
        btn._header_icon = icon_name
        return btn

    def _apply_profile_icon_and_text(self):
        full_name = self.user_info.get("full_name", "User")

        pix = self._avatar.label.pixmap()
        if pix and not pix.isNull():
            self.profile_btn.setIcon(QIcon(pix))
        else:
            self.profile_btn.setIcon(
                self.icon_manager.get_icon("profile", size=QSize(28, 28))
            )
        self.profile_btn.setText(f"  {full_name}")
        self.profile_btn.setAccessibleName(f"User menu, {full_name}")
        self.profile_btn.setAccessibleDescription(f"Signed in as {full_name}")

        chevron_icon = None
        try:
            chevron_icon = self.icon_manager.get_icon(
                "expand_more", size=QSize(14, 14), state="default"
            )
        except Exception:
            pass
        if chevron_icon is None or chevron_icon.isNull():
            try:
                chevron_icon = self.icon_manager.get_icon(
                    "arrow_forward", size=QSize(14, 14), state="default"
                )
            except Exception:
                chevron_icon = None
        if chevron_icon is not None and not chevron_icon.isNull():
            self.profile_chevron.setPixmap(chevron_icon.pixmap(14, 14))
        else:
            self.profile_chevron.setText("▾")

    # ==================================================================
    # Icon refresh
    # ==================================================================

    def _refresh_icons(self):
        timer = getattr(self, "_refresh_debounce", None)
        if timer is None:
            return
        try:
            timer.start()
        except RuntimeError:
            return

    def _do_refresh_icons(self):
        try:
            is_dark = self.theme_manager.get_current_theme() == "dark"

            theme_icon_name = "theme_dark" if is_dark else "theme_light"
            self.theme_btn.setIcon(
                self.icon_manager.get_icon(
                    theme_icon_name, size=QSize(18, 18), state="default"
                )
            )
            self.theme_btn.setIconSize(QSize(18, 18))
            self.theme_btn.setToolTip(
                "Switch to light mode" if is_dark
                else "Switch to dark mode"
            )
            self.theme_btn.setAccessibleName(self.theme_btn.toolTip())

            self.menu_btn.setIcon(
                self.icon_manager.get_icon(
                    "menu", size=QSize(18, 18), state="default"
                )
            )
            self.menu_btn.setIconSize(QSize(18, 18))

            self.notify_btn.setIcon(
                self.icon_manager.get_icon(
                    "notifications", size=QSize(18, 18), state="default"
                )
            )
            self.notify_btn.setIconSize(QSize(18, 18))

            try:
                pix = self.icon_manager.get_icon(
                    "search", size=QSize(14, 14), state="default"
                )
                self.search_prefix.setPixmap(pix.pixmap(14, 14))
            except Exception:
                self.search_prefix.setText("⌕")

            self._apply_profile_icon_and_text()
        except RuntimeError:
            return

    # ==================================================================
    # Breadcrumb
    # ==================================================================

    def _set_breadcrumb(self, page: str):
        t = self.theme_manager.get_tokens()
        muted = t.get("muted-foreground", "#888")
        fg = t.get("foreground", "#111")
        self.breadcrumb.setText(
            f"<span style='color:{muted}'>ICT Authority</span>"
            f"<span style='color:{muted}'> / </span>"
            f"<span style='color:{fg}; font-weight:500'>{page}</span>"
        )
        self.breadcrumb.setAccessibleName(f"Location: {page}")

    # ==================================================================
    # Theme hooks
    # ==================================================================

    def on_theme_changed(self, theme: str):
        # Coalesce. Do not run the refresh pass synchronously; that
        # is what made the click feel slow.
        self._schedule_header_refresh()

    def on_appearance_changed(self, *_):
        self._schedule_header_refresh()

    # ==================================================================
    # Public API
    # ==================================================================

    def set_title(self, title: str):
        self._current_page = title
        self._set_breadcrumb(title)

    def set_sidebar_expanded(self, expanded: bool):
        self.sidebar_expanded = expanded

    def set_notification_count(self, count: int):
        self._notification_count = count
        self.notify_btn.setToolTip(
            f"Notifications ({count})" if count else "Notifications"
        )
        self.notify_btn.setAccessibleName(self.notify_btn.toolTip())

    # ==================================================================
    # Actions
    # ==================================================================

    def _toggle_theme(self):
        # The theme switch itself is cheap; what was expensive was the
        # synchronous refresh that used to run inside the click
        # handler. The refresh is now driven by the coalesced timer
        # via on_theme_changed / on_appearance_changed.
        self.theme_manager.toggle_theme()
        self.theme_toggled.emit()

    def _focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _on_search_changed(self, text: str):
        self._last_search = text
        self._search_timer.start(280)

    def _emit_search(self):
        self.search_requested.emit(self._last_search)

    def _show_notifications(self):
        from widgets.components import (
            ShadcnSheet, ShadcnCaption, ShadcnButton as SButton,
        )
        sheet = ShadcnSheet("Notifications", parent=self)

        if self._notification_count == 0:
            sheet.add_widget(
                ShadcnCaption("You have no new notifications.")
            )
        else:
            sheet.add_widget(
                ShadcnCaption(
                    f"You have {self._notification_count} "
                    f"notification(s)."
                )
            )
            mark_btn = SButton(
                "Mark all as read", variant="outline", size="sm"
            )
            mark_btn.clicked.connect(self._clear_notifications)
            sheet.add_button(mark_btn)

        sheet.exec()

    def _clear_notifications(self):
        self._notification_count = 0
        self.notify_btn.setToolTip("Notifications")
        self.notify_btn.setAccessibleName("Notifications")

    # ==================================================================
    # Dialog launchers
    # ==================================================================

    def _get_data_service(self):
        if self.data_service is not None:
            return self.data_service

        logger.warning(
            "Header._get_data_service(): no data_service injected, "
            "creating a temporary one. This is a fallback."
        )
        from core.data_service import DataService
        from core.api_client import APIClient
        from database.db_manager import DatabaseManager
        from core.sync_manager import SyncManager

        api = APIClient()
        db = DatabaseManager()
        sync = SyncManager(api, db)
        return DataService(api, db, sync)

    def _show_profile(self):
        data_service = self._get_data_service()
        dialog = ProfileDialog(self.user_info, data_service, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.user_info.update(dialog.get_updated_info())
            self._refresh_icons()

    def _show_change_password(self):
        data_service = self._get_data_service()
        dialog = ChangePasswordDialog(
            self.user_info.get("id"), data_service, self
        )
        dialog.exec()

    # ==================================================================
    # Keyboard
    # ==================================================================

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            if self.search_input.hasFocus():
                self.search_input.clear()
                self.search_input.clearFocus()
                event.accept()
                return
        super().keyPressEvent(event)
