"""Enterprise navigation sidebar.

Layout contract
---------------
The sidebar's top block (the "logo" strip) has exactly the same
height as the header (`Config.TOPBAR_HEIGHT`). The horizontal
separator below it therefore lands at the same y-coordinate as the
header's bottom border, producing a single continuous line across
the top of the main window.

Sidebar toggle
--------------
The sidebar has no collapse button of its own. Collapsing and
expanding are driven exclusively by the header's hamburger menu
button (`Header.menu_btn`), which is wired through
`MainApp.sidebar.toggle_collapse`. This keeps exactly one control
on screen for the action and avoids the visual duplication that
existed when both the header hamburger and an inline chevron were
present.

Flicker-free refresh
--------------------
Two independent bugs caused a caption-bar flicker during page
transitions:

  1. **Top-level-window churn.** Calling `setVisible(True)` on a
     `QLabel` that has no parent and is not yet in a layout makes
     Qt briefly treat it as a top-level widget. On Windows that
     creates and destroys a native `HWND` in the same event-loop
     tick, which the compositor renders as a sub-frame flicker.
     Fixed by parenting every group label into the layout BEFORE
     any visibility decision is made.

  2. **Scroll-area layout churn.** Calling `setVisible` on a
     parented widget that lives inside a `QScrollArea` invalidates
     the scroll area's layout, which cascades up through the page
     stack. If that happens while `QStackedWidget.setCurrentWidget`
     is still settling, Qt runs two full layout passes in the same
     frame, and the caption bar flickers. Fixed by guarding the
     layout-affecting pass in `_refresh_icons` with
     `_last_expanded_state` so it only runs when the collapsed /
     expanded state has actually flipped.

Footer
------
The footer is a clickable user card:
  [avatar]  [name / role or email]                    [chevron]

Clicking it opens the same profile menu that the header uses.
When the sidebar is collapsed, only the avatar is shown, centred,
with a tooltip carrying the full name.
"""
import colorsys
import logging
import re
from typing import Dict, List, Optional

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPoint, QPropertyAnimation, QSettings,
    QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QCursor, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenu,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from config import Config
from core.icon_manager import IconManager
from widgets.components import ShadcnAvatar


logger = logging.getLogger(__name__)


class NavigationButton(QPushButton):
    """
    Sidebar navigation button.

    Inherits directly from QPushButton rather than ShadcnButton
    because the sidebar applies its own object-scoped stylesheet
    (`#navButton`), and ShadcnButton's own theme machinery would
    otherwise fight it.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navButton")
        self.setProperty("class", "nav-button")
        self.setCheckable(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(40)
        self.setMinimumWidth(40)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.setAccessibleName("Navigation item")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("")
        self.setFlat(True)


class _SidebarUserCard(QWidget):
    """
    Footer user card. Emits `clicked` when the user activates it.
    """

    clicked = Signal()

    def __init__(self, user_info: Dict, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarUserCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._user_info = dict(user_info or {})
        self._expanded = True
        # Guards repeated set_expanded calls so the footer's layout is
        # not invalidated on every _refresh_icons pass.
        self._last_expanded: Optional[bool] = None

        full_name = (
            self._user_info.get("full_name")
            or self._user_info.get("username")
            or "User"
        )

        secondary = (
            self._user_info.get("role")
            or self._user_info.get("title")
            or self._user_info.get("email")
            or "Signed in"
        )

        self.setAccessibleName(f"User menu, {full_name}")
        self.setAccessibleDescription(f"Signed in as {full_name}")
        self.setToolTip("")

        lo = QHBoxLayout(self)
        lo.setContentsMargins(8, 6, 8, 6)
        lo.setSpacing(10)

        self._avatar = ShadcnAvatar(fallback_text=full_name, size=36)
        self._avatar.setObjectName("sidebarAvatar")
        lo.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        self._text_col = QWidget()
        self._text_col.setObjectName("sidebarUserCardText")
        text_lo = QVBoxLayout(self._text_col)
        text_lo.setContentsMargins(0, 0, 0, 0)
        text_lo.setSpacing(1)

        self._name_lbl = QLabel(full_name)
        self._name_lbl.setObjectName("sidebarUserCardName")
        self._name_lbl.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self._name_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction
        )

        self._secondary_lbl = QLabel(secondary)
        self._secondary_lbl.setObjectName("sidebarUserCardSecondary")
        self._secondary_lbl.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self._secondary_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction
        )

        text_lo.addWidget(self._name_lbl)
        text_lo.addWidget(self._secondary_lbl)
        lo.addWidget(self._text_col, 1)

        self._chevron = QLabel()
        self._chevron.setObjectName("sidebarUserCardChevron")
        self._chevron.setFixedSize(14, 14)
        self._chevron.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(self._chevron, 0, Qt.AlignmentFlag.AlignVCenter)

        self._full_name = full_name

    def set_expanded(self, expanded: bool):
        """
        Switch between the full card layout and the avatar-only
        layout. No-op if the state has not changed since the last
        call, so repeated invocations from _refresh_icons do not
        invalidate the footer's layout.
        """
        if self._last_expanded == expanded:
            return
        self._last_expanded = expanded

        self._expanded = expanded
        self._text_col.setVisible(expanded)
        self._chevron.setVisible(expanded)
        self.setToolTip("" if expanded else self._full_name)

        if expanded:
            self.layout().setContentsMargins(8, 6, 8, 6)
            self._avatar.setFixedSize(36, 36)
        else:
            self.layout().setContentsMargins(0, 6, 0, 6)
            self._avatar.setFixedSize(32, 32)

        self._avatar.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )

    def set_icon(self, icon: Optional[QIcon]):
        if icon is None:
            self._chevron.clear()
        else:
            self._chevron.setPixmap(icon.pixmap(14, 14))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (
            Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space
        ):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class Sidebar(QWidget):
    toggled = Signal(bool)
    navigation_requested = Signal(str)

    EXPANDED_W = Config.SIDEBAR_EXPANDED
    COLLAPSED_W = Config.SIDEBAR_COLLAPSED
    AUTO_COLLAPSE_AT = Config.SIDEBAR_AUTO_COLLAPSE_AT

    HEADER_BLOCK_HEIGHT = Config.TOPBAR_HEIGHT
    FOOTER_HEIGHT = 62

    _PERM_MAP = {
        "dashboard": "view_dashboard",
        "visitors": ("manage_visitors", "view_visitors"),
        "employees": ("manage_employees", "view_employees"),
        "access_logs": "view_access_logs",
        "field_config": "configure_fields",
        "reports": "view_reports",
        "settings": "manage_settings",
        "users": "manage_users",
    }

    _ICON_MAP = {
        "dashboard": "dashboard",
        "visitors": "visitors",
        "employees": "employees",
        "access_logs": "access_logs",
        "field_config": "field_config",
        "reports": "report",
        "settings": "settings",
        "users": "user",
    }

    _LABEL_MAP = {
        "dashboard": "Dashboard",
        "visitors": "Visitors",
        "employees": "Employees",
        "access_logs": "Access Logs",
        "field_config": "Field Config",
        "reports": "Reports",
        "settings": "Settings",
        "users": "User Management",
    }

    _GROUPS = {
        "Main": ["dashboard", "visitors", "employees"],
        "Security": ["access_logs"],
        "Configuration": ["field_config", "settings"],
        "Analytics": ["reports"],
        "Administration": ["users"],
    }

    def __init__(self, permissions: List[str], user_info: Dict,
                 theme_manager, parent=None):
        super().__init__(parent)

        self.permissions = list(permissions) if permissions else []
        self.user_info = dict(user_info) if user_info else {}
        self.theme_manager = theme_manager

        self.expanded = True
        self._is_animating = False
        self._pending_toggle = False

        self._nav_order: List[str] = []
        self._button_map: Dict[str, QPushButton] = {}
        self._group_labels: Dict[str, QLabel] = {}
        self._badge_map: Dict[str, QLabel] = {}

        self._current_index = -1
        self._last_qss: str = ""

        # Guards the layout-affecting pass in _refresh_icons so it
        # only runs when the collapsed/expanded state actually flips.
        # Without this guard, every theme change, appearance change,
        # and set_active call invalidates the sidebar's scroll-area
        # layout, which cascades up through the page stack and
        # flickers the caption bar during page transitions.
        self._last_expanded_state: Optional[bool] = None

        self._user_menu: Optional[QMenu] = None

        self._settings = QSettings("ICTAuthority", "AccessControl")
        self._user_locked = self._settings.value(
            "sidebar_locked", False, type=bool
        )

        self.setObjectName("sidebar")
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.setAccessibleName("Application Navigation")
        self.setAccessibleDescription("Primary application navigation")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        # Ensures the object-scoped stylesheet's background is used
        # from the first paint, instead of the platform palette.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.icon_manager = IconManager()

        duration = getattr(Config, "SIDEBAR_ANIMATION_DURATION", 180)
        if getattr(Config, "REDUCED_MOTION", False):
            duration = 0

        self._anim_min = QPropertyAnimation(self, b"minimumWidth", self)
        self._anim_min.setDuration(duration)
        self._anim_min.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim_min.finished.connect(self._on_animation_finished)

        self._anim_max = QPropertyAnimation(self, b"maximumWidth", self)
        self._anim_max.setDuration(duration)
        self._anim_max.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.setMinimumWidth(self.EXPANDED_W)
        self.setMaximumWidth(self.EXPANDED_W)

        self._init_ui()
        self._build_button_list()

        # Apply the stylesheet synchronously, before the widget is
        # ever painted. Removes the white flash on startup.
        try:
            self._apply_stylesheet()
        except Exception as e:
            logger.debug(f"Initial stylesheet application failed: {e}")

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._handle_resize_debounced)

        if self.parent():
            self.parent().installEventFilter(self)

        # Icons need the icon manager warmed up, so keep the deferred
        # pass for icon refresh only.
        QTimer.singleShot(0, self._deferred_init)

        self.theme_manager.register_widget(
            self,
            on_theme_changed=self.on_theme_changed,
            on_appearance_changed=self.on_appearance_changed,
        )

    # ------------------------------------------------------------------
    # Deferred initialization
    # ------------------------------------------------------------------

    def _deferred_init(self):
        try:
            self._refresh_icons()
        except RuntimeError:
            return

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- header block --------------------------------------------
        self._logo_widget = QWidget()
        self._logo_widget.setObjectName("sidebarHeader")
        self._logo_widget.setFixedHeight(self.HEADER_BLOCK_HEIGHT)

        logo_layout = QHBoxLayout(self._logo_widget)
        logo_layout.setContentsMargins(14, 0, 14, 0)
        logo_layout.setSpacing(10)

        self._logo_text = QLabel("")
        self._logo_text.setObjectName("logoText")
        self._logo_text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._logo_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_layout.addWidget(self._logo_text, 1)

        root.addWidget(self._logo_widget)

        # --- separator -----------------------------------------------
        separator = QFrame()
        separator.setObjectName("sidebarSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFixedHeight(1)
        root.addWidget(separator)

        # --- scrollable navigation area ------------------------------
        self._scroll = QScrollArea()
        self._scroll.setObjectName("sidebarScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._scroll.setAccessibleName("Navigation list")

        scroll_content = QWidget()
        scroll_content.setObjectName("sidebarNavigation")
        self._nav_lo = QVBoxLayout(scroll_content)
        self._nav_lo.setContentsMargins(8, 12, 8, 12)
        self._nav_lo.setSpacing(2)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._btn_group.buttonClicked.connect(self._on_btn_clicked)

        self._build_navigation_groups()
        self._nav_lo.addStretch(1)

        self._scroll.setWidget(scroll_content)
        root.addWidget(self._scroll, 1)

        # --- footer separator ----------------------------------------
        footer_separator = QFrame()
        footer_separator.setObjectName("sidebarSeparator")
        footer_separator.setFrameShape(QFrame.Shape.HLine)
        footer_separator.setFixedHeight(1)
        root.addWidget(footer_separator)

        # --- footer: clickable user card -----------------------------
        self._footer = QWidget()
        self._footer.setObjectName("sidebarFooter")
        self._footer.setFixedHeight(self.FOOTER_HEIGHT)

        footer_layout = QHBoxLayout(self._footer)
        footer_layout.setContentsMargins(6, 4, 6, 4)
        footer_layout.setSpacing(0)

        self._user_card = _SidebarUserCard(self.user_info)
        self._user_card.clicked.connect(self._show_user_menu)
        footer_layout.addWidget(self._user_card, 1)

        root.addWidget(self._footer)

    def _build_navigation_groups(self):
        any_added = False

        for group_name, pages in self._GROUPS.items():
            accessible = [pid for pid in pages if self._has_access(pid)]
            if not accessible:
                continue

            any_added = True

            # Create the label, set its properties, add it to the
            # layout, THEN (optionally) apply visibility. The order
            # matters: setVisible(True) on a parentless widget makes
            # Qt briefly treat it as a top-level window, which on
            # Windows creates a native HWND that is destroyed in the
            # same event-loop tick. Visibility is applied later, from
            # _refresh_icons, by which time every label is parented.
            group_label = QLabel(group_name.upper())
            group_label.setObjectName("navGroupLabel")
            group_label.setContentsMargins(10, 12, 8, 5)
            self._nav_lo.addWidget(group_label)
            self._group_labels[group_name] = group_label

            for page_id in accessible:
                button = NavigationButton()
                button.setObjectName("navButton")
                button.setProperty("page", page_id)

                label = self._LABEL_MAP.get(
                    page_id, page_id.replace("_", " ").title()
                )
                button.setAccessibleName(label)
                button.setAccessibleDescription(f"Navigate to {label}")

                wrapper = self._create_navigation_item(button, page_id)
                self._nav_lo.addWidget(wrapper)

                self._button_map[page_id] = button
                self._btn_group.addButton(button)
                self._nav_order.append(page_id)

        if not any_added:
            empty = QLabel(
                "No accessible modules.\nContact your administrator."
            )
            empty.setObjectName("emptyNavigation")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            empty.setContentsMargins(16, 30, 16, 30)
            self._nav_lo.addWidget(empty)

    def _create_navigation_item(self, button: NavigationButton,
                                 page_id: str) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("navItem")
        wrapper.setFixedHeight(40)
        wrapper.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(button, 1)

        badge = QLabel()
        badge.setObjectName(f"badge_{page_id}")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMinimumWidth(20)
        badge.setFixedHeight(20)
        badge.setVisible(False)
        self._badge_map[page_id] = badge
        layout.addWidget(badge)

        return wrapper

    # ------------------------------------------------------------------
    # User menu (footer)
    # ------------------------------------------------------------------

    def _show_user_menu(self):
        parent = self.parent()
        header = getattr(parent, "header", None) if parent else None

        menu: Optional[QMenu] = None
        if header is not None and hasattr(header, "_ensure_profile_menu"):
            try:
                header._ensure_profile_menu()
                menu = getattr(header, "_profile_menu", None)
            except Exception as e:
                logger.debug(f"Could not reuse header menu: {e}")

        if menu is None:
            if self._user_menu is None:
                m = QMenu(self)
                m.addAction("Profile")
                m.addAction("Change password")
                m.addSeparator()
                act_logout = m.addAction("Sign out")
                if parent is not None and hasattr(parent, "logout"):
                    act_logout.triggered.connect(parent.logout)
                self._user_menu = m
            menu = self._user_menu

        menu.adjustSize()
        menu_size = menu.sizeHint()

        card = self._user_card
        card_top_left_global = card.mapToGlobal(card.rect().topLeft())
        card_bottom_left_global = card.mapToGlobal(card.rect().bottomLeft())

        preferred = QPoint(
            card_top_left_global.x(),
            card_top_left_global.y() - menu_size.height(),
        )

        screen = QApplication.screenAt(card_top_left_global)
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            if preferred.y() < avail.top():
                preferred = QPoint(
                    card_bottom_left_global.x(),
                    card_bottom_left_global.y(),
                )

            max_x = avail.right() - menu_size.width()
            if preferred.x() > max_x:
                preferred.setX(max_x)
            if preferred.x() < avail.left():
                preferred.setX(avail.left())

        menu.popup(preferred)

    # ------------------------------------------------------------------
    # Theme helpers
    # ------------------------------------------------------------------

    def _get_theme_tokens(self) -> Dict:
        try:
            tokens = self.theme_manager.get_tokens()
            if isinstance(tokens, dict):
                return tokens
        except Exception:
            pass
        return {}

    def _token(self, tokens: Dict, *names, default: str) -> str:
        for name in names:
            value = tokens.get(name)
            if value:
                return str(value)
        return default

    def _hsl_to_rgb_str(self, color_str: str) -> str:
        if not color_str:
            return "0,0,0"
        color_str = str(color_str).strip()

        match = re.match(
            r"hsl\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*\)",
            color_str,
            re.IGNORECASE,
        )
        if match:
            h = float(match.group(1)) / 360.0
            s = float(match.group(2)) / 100.0
            l = float(match.group(3)) / 100.0
            r, g, b = colorsys.hls_to_rgb(h, l, s)
            return f"{int(r * 255)},{int(g * 255)},{int(b * 255)}"

        color = QColor(color_str)
        if color.isValid():
            return f"{color.red()},{color.green()},{color.blue()}"
        return "0,0,0"

    def _rgba(self, color_str: str, alpha: float) -> str:
        return f"rgba({self._hsl_to_rgb_str(color_str)},{alpha})"

    def _appearance_font_family(self) -> str:
        try:
            return self.theme_manager.get_appearance_value(
                "font_family", "Segoe UI"
            )
        except Exception:
            return "Segoe UI"

    def _appearance_font_size(self) -> int:
        try:
            return int(
                self.theme_manager.get_appearance_value("font_size", 13)
            )
        except Exception:
            return 13

    def _appearance_radius(self) -> int:
        try:
            tokens = self.theme_manager.get_tokens()
            raw = tokens.get("radius", "6px")
            return int(str(raw).replace("px", "").strip())
        except Exception:
            return 6

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------

    def _apply_stylesheet(self):
        try:
            tokens = self._get_theme_tokens()
        except RuntimeError:
            return

        background = self._token(
            tokens, "background", "background_color", "bg",
            default="#ffffff",
        )
        foreground = self._token(
            tokens, "foreground", "foreground_color", "text",
            default="#171717",
        )
        muted = self._token(
            tokens, "muted-foreground", "muted_foreground",
            "text_muted", default="#737373",
        )
        border = self._token(
            tokens, "border", "border_color", default="#e5e7eb"
        )
        accent = self._token(
            tokens, "primary", "primary_color", "accent",
            default="#16a34a",
        )
        accent_foreground = self._token(
            tokens, "primary-foreground", "primary_foreground",
            "on_primary", default="#ffffff",
        )
        card = self._token(
            tokens, "card", "surface", "surface_color",
            default=background,
        )

        hover_bg = self._rgba(accent, 0.075)
        active_bg = self._rgba(accent, 0.115)
        focus_bg = self._rgba(accent, 0.10)
        active_border = self._rgba(accent, 0.28)
        badge_bg = self._rgba(accent, 0.12)
        separator = self._rgba(border, 0.80)

        user_card_bg = self._token(
            tokens, "muted", default=self._rgba(border, 0.55)
        )
        user_card_hover = self._rgba(accent, 0.10)
        user_card_focus = self._rgba(accent, 0.16)

        font_family = self._appearance_font_family()
        base_size = self._appearance_font_size()
        radius = self._appearance_radius()

        nav_font_size = base_size
        group_font_size = max(9, base_size - 3)
        logo_font_size = base_size + 1
        user_name_size = max(11, base_size - 1)
        user_secondary_size = max(9, base_size - 3)
        badge_font_size = max(9, base_size - 3)
        tooltip_font_size = max(9, base_size - 2)

        item_radius = max(4, radius + 2)
        badge_radius = 10
        card_radius = max(6, radius + 2)

        sb_track = self._token(
            tokens, "scrollbar_track",
            default=self._token(tokens, "muted", default="#F1F5F9"),
        )
        sb_handle = self._token(
            tokens, "scrollbar_handle",
            default=self._token(
                tokens, "border-strong", "border", default="#94A3B8"
            ),
        )
        sb_handle_hover = self._token(
            tokens, "scrollbar_handle_hover",
            default=self._token(
                tokens, "foreground-secondary", "muted-foreground",
                default="#64748B",
            ),
        )

        sb_size = int(tokens.get("scrollbar_size", 10))
        sb_radius = int(tokens.get("scrollbar_radius", 5))

        stylesheet = f"""
        QWidget#sidebar {{ background: {background}; color: {foreground}; border-right: 1px solid {separator}; }}
        QWidget#sidebarHeader {{ background: {background}; }}
        QWidget#sidebarNavigation {{ background: transparent; }}
        QScrollArea#sidebarScroll {{ background: transparent; border: none; }}
        QScrollArea#sidebarScroll > QWidget {{ background: transparent; border: none; }}

        QScrollBar:vertical {{ background: {sb_track}; width: {sb_size}px; margin: 4px 2px 4px 0; border: none; border-radius: {sb_radius}px; }}
        QScrollBar::handle:vertical {{ background: {sb_handle}; border-radius: {sb_radius}px; min-height: 32px; }}
        QScrollBar::handle:vertical:hover {{ background: {sb_handle_hover}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

        QLabel#logoMark {{ background: transparent; border: none; border-radius: 8px; color: {accent_foreground}; font-family: "{font_family}"; font-size: {group_font_size}px; font-weight: 700; }}
        QLabel#logoText {{ color: {foreground}; font-family: "{font_family}"; font-size: {logo_font_size}px; font-weight: 650; letter-spacing: 0.1px; }}

        QFrame#sidebarSeparator {{ background: {separator}; border: none; color: transparent; }}

        QLabel#navGroupLabel {{ color: {muted}; font-family: "{font_family}"; font-size: {group_font_size}px; font-weight: 700; letter-spacing: 0.7px; }}

        QWidget#navItem {{ background: transparent; }}
        QPushButton#navButton {{ background: transparent; border: 1px solid transparent; border-radius: {item_radius}px; color: {foreground}; font-family: "{font_family}"; font-size: {nav_font_size}px; font-weight: 500; text-align: left; padding: 0px 10px; margin: 0px; }}
        QPushButton#navButton:hover {{ background: {hover_bg}; color: {foreground}; }}
        QPushButton#navButton:pressed {{ background: {active_bg}; }}
        QPushButton#navButton:focus {{ border: 1px solid {active_border}; background: {focus_bg}; }}
        QPushButton#navButton:checked {{ background: {active_bg}; border: 1px solid {active_border}; color: {accent}; font-weight: 600; }}
        QPushButton#navButton:checked:hover {{ background: {active_bg}; color: {accent}; }}
        QPushButton#navButton:disabled {{ color: {self._rgba(muted, 0.50)}; }}

        QLabel[objectName^="badge_"] {{ background: {badge_bg}; border: 1px solid {active_border}; border-radius: {badge_radius}px; color: {accent}; font-family: "{font_family}"; font-size: {badge_font_size}px; font-weight: 700; padding: 0px 5px; margin-right: 7px; }}

        QLabel#emptyNavigation {{ color: {muted}; font-family: "{font_family}"; font-size: {nav_font_size}px; line-height: 1.4; }}

        QWidget#sidebarFooter {{ background: {background}; }}

        QWidget#sidebarUserCard {{
            background: {user_card_bg};
            border: 1px solid transparent;
            border-radius: {card_radius}px;
        }}
        QWidget#sidebarUserCard:hover {{
            background: {user_card_hover};
            border-color: {active_border};
        }}
        QWidget#sidebarUserCard:focus {{
            background: {user_card_focus};
            border: 1px solid {accent};
        }}

        QWidget#sidebarUserCardText {{ background: transparent; }}
        QLabel#sidebarUserCardName {{
            color: {foreground};
            font-family: "{font_family}";
            font-size: {user_name_size}px;
            font-weight: 600;
            background: transparent;
        }}
        QLabel#sidebarUserCardSecondary {{
            color: {muted};
            font-family: "{font_family}";
            font-size: {user_secondary_size}px;
            font-weight: 450;
            background: transparent;
        }}
        QLabel#sidebarUserCardChevron {{
            color: {muted};
            background: transparent;
        }}
        QLabel#sidebarAvatar {{ border-radius: 18px; }}

        QToolTip {{ background: {card}; color: {foreground}; border: 1px solid {border}; border-radius: {item_radius}px; padding: 6px 8px; font-family: "{font_family}"; font-size: {tooltip_font_size}px; }}
        """

        if self._last_qss == stylesheet:
            return

        try:
            self.setStyleSheet(stylesheet)
            self._last_qss = stylesheet
        except RuntimeError:
            return

        try:
            self.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Icons & labels
    # ------------------------------------------------------------------

    def _refresh_icons(self):
        """
        Refresh nav icons and labels.

        Split into two passes:

          1. Layout-neutral — icon swap, per-item text, tooltip.
             Runs on every refresh; does not invalidate any layout.

          2. Layout-affecting — visibility of group labels, logo,
             footer text column, footer card rearrangement. Guarded
             by _last_expanded_state so it only runs when the
             collapsed / expanded state has actually flipped.

        Without the guard, every theme change, appearance change, or
        set_active call would invalidate the sidebar's scroll-area
        layout. That cascades up through the page stack, and if it
        lands during a QStackedWidget.setCurrentWidget transition, it
        flickers the caption bar.
        """
        # ---- Pass 1: icons and per-item text (layout-neutral) ----
        for page_id, button in self._button_map.items():
            icon_name = self._ICON_MAP.get(page_id, "dashboard")
            state = "active" if button.isChecked() else "default"

            try:
                icon = self.icon_manager.get_icon(
                    icon_name, size=QSize(18, 18), state=state
                )
                button.setIcon(icon)
                button.setIconSize(QSize(18, 18))
            except Exception:
                pass

            label = self._LABEL_MAP.get(
                page_id, page_id.replace("_", " ").title()
            )

            if self.expanded:
                button.setText(f"  {label}")
                button.setToolTip("")
            else:
                button.setText("")
                button.setToolTip(label)

            badge = self._badge_map.get(page_id)
            if badge:
                badge.setVisible(self.expanded and badge.text() != "")

        # ---- Pass 2: layout-affecting state (only on change) ----
        if self._last_expanded_state == self.expanded:
            return

        self._last_expanded_state = self.expanded

        for label in self._group_labels.values():
            label.setVisible(self.expanded)

        self._logo_text.setVisible(self.expanded)
        self._logo_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._user_card.set_expanded(self.expanded)
        try:
            chevron = self.icon_manager.get_icon(
                "arrow_forward", size=QSize(14, 14), state="default"
            )
            self._user_card.set_icon(chevron)
        except Exception:
            self._user_card.set_icon(None)

    # ------------------------------------------------------------------
    # Theme change hooks
    # ------------------------------------------------------------------

    def on_theme_changed(self, theme: str):
        try:
            self._apply_stylesheet()
            self._refresh_icons()
        except RuntimeError:
            return

    def on_appearance_changed(self, *_):
        try:
            self._apply_stylesheet()
            self._refresh_icons()
        except RuntimeError:
            return

    # ------------------------------------------------------------------
    # Permissions & navigation
    # ------------------------------------------------------------------

    def _has_access(self, page_id: str) -> bool:
        required_permission = self._PERM_MAP.get(page_id)
        if not required_permission:
            return False
        if isinstance(required_permission, tuple):
            return any(p in self.permissions for p in required_permission)
        return required_permission in self.permissions

    def _build_button_list(self):
        self._current_index = 0 if self._nav_order else -1

    def set_active(self, page_id: str):
        if page_id not in self._button_map:
            return
        button = self._button_map[page_id]
        button.blockSignals(True)
        button.setChecked(True)
        button.blockSignals(False)

        if page_id in self._nav_order:
            self._current_index = self._nav_order.index(page_id)

        self._refresh_icons()

    def _on_btn_clicked(self, button):
        if button is None:
            return
        page_id = button.property("page")
        if page_id and button.isChecked():
            if page_id in self._nav_order:
                self._current_index = self._nav_order.index(page_id)
            self.navigation_requested.emit(page_id)

    def set_badge(self, page_id: str, count: int):
        badge = self._badge_map.get(page_id)
        if not badge:
            return
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 0
        if count <= 0:
            badge.clear()
            badge.setVisible(False)
            return
        text = "99+" if count > 99 else str(count)
        badge.setText(text)
        badge.setVisible(self.expanded)

    # ------------------------------------------------------------------
    # Keyboard navigation
    # ------------------------------------------------------------------

    def _highlight_button(self, index: int):
        if not (0 <= index < len(self._nav_order)):
            return
        button = self._button_map[self._nav_order[index]]
        button.setFocus(Qt.FocusReason.TabFocusReason)
        self._scroll.ensureWidgetVisible(button, 0, 12)

    def _set_focused_index(self, index: int):
        if 0 <= index < len(self._nav_order):
            self._current_index = index
            self._highlight_button(index)

    def keyPressEvent(self, event: QKeyEvent):
        if not self._nav_order:
            super().keyPressEvent(event)
            return

        key = event.key()
        count = len(self._nav_order)

        if key == Qt.Key.Key_Down:
            if (
                self._current_index == count - 1
                and self._user_card is not None
            ):
                self._user_card.setFocus(Qt.FocusReason.TabFocusReason)
                event.accept()
                return
            self._set_focused_index((self._current_index + 1) % count)
            event.accept()
            return
        if key == Qt.Key.Key_Up:
            self._set_focused_index((self._current_index - 1) % count)
            event.accept()
            return
        if key == Qt.Key.Key_Home:
            self._set_focused_index(0)
            event.accept()
            return
        if key == Qt.Key.Key_End:
            self._set_focused_index(count - 1)
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if 0 <= self._current_index < count:
                self._button_map[
                    self._nav_order[self._current_index]
                ].click()
            event.accept()
            return
        if key == Qt.Key.Key_Right:
            self._focus_central_widget()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.clearFocus()
            self._focus_central_widget()
            event.accept()
            return
        if (
            key == Qt.Key.Key_B
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.toggle_collapse(user_initiated=True)
            event.accept()
            return

        super().keyPressEvent(event)

    def _focus_central_widget(self):
        parent = self.parent()
        if not parent:
            return
        central = parent.findChild(QWidget, "centralWidget")
        if central:
            central.setFocus(Qt.FocusReason.TabFocusReason)

    def focusInEvent(self, event):
        if self._nav_order and self._current_index == -1:
            checked = self._btn_group.checkedButton()
            if checked:
                for index, page_id in enumerate(self._nav_order):
                    if self._button_map[page_id] is checked:
                        self._current_index = index
                        break
            else:
                self._current_index = 0
        if self._current_index >= 0:
            self._highlight_button(self._current_index)
        super().focusInEvent(event)

    # ------------------------------------------------------------------
    # Collapse / resize
    # ------------------------------------------------------------------

    def toggle_collapse(self, user_initiated: bool = False):
        if self._is_animating:
            self._pending_toggle = True
            return
        if user_initiated:
            self._user_locked = True
            self._settings.setValue("sidebar_locked", True)

        self._anim_min.stop()
        self._anim_max.stop()

        self.expanded = not self.expanded
        target_width = self.EXPANDED_W if self.expanded else self.COLLAPSED_W
        self._is_animating = True

        for animation in (self._anim_min, self._anim_max):
            animation.setStartValue(self.width())
            animation.setEndValue(target_width)
            animation.start()

        self._refresh_icons()
        self.toggled.emit(self.expanded)

    def _on_animation_finished(self):
        self._is_animating = False
        if self._pending_toggle:
            self._pending_toggle = False
            QTimer.singleShot(
                0, lambda: self.toggle_collapse(user_initiated=True)
            )

    def _handle_resize_debounced(self):
        if self._user_locked:
            return
        parent = self.parent()
        if not parent:
            return
        should_collapse = parent.width() < self.AUTO_COLLAPSE_AT
        if should_collapse == self.expanded:
            self.toggle_collapse(user_initiated=False)

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self._resize_timer.start(150)
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Public width setters
    # ------------------------------------------------------------------

    def setExpandedWidth(self, width: int):
        width = max(180, int(width))
        self.EXPANDED_W = width
        if self.expanded:
            self.setMinimumWidth(width)
            self.setMaximumWidth(width)

    def setCollapsedWidth(self, width: int):
        width = max(52, int(width))
        self.COLLAPSED_W = width
        if not self.expanded:
            self.setMinimumWidth(width)
            self.setMaximumWidth(width)

    # ------------------------------------------------------------------
    # Permissions refresh & state
    # ------------------------------------------------------------------

    def refresh_permissions(self, new_permissions: List[str]):
        """
        Rebuild navigation items to reflect new permissions.

        Runs on authentication transitions only — not on resize or
        theme changes.
        """
        self.permissions = list(new_permissions) if new_permissions else []

        for button in list(self._button_map.values()):
            try:
                self._btn_group.removeButton(button)
            except Exception:
                pass
            button.deleteLater()

        self._button_map.clear()
        self._badge_map.clear()
        self._nav_order.clear()
        self._group_labels.clear()

        while self._nav_lo.count():
            item = self._nav_lo.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._build_navigation_groups()
        self._nav_lo.addStretch(1)
        self._build_button_list()
        self._refresh_icons()
        self._apply_stylesheet()

    def unlock_auto_collapse(self):
        self._user_locked = False
        self._settings.setValue("sidebar_locked", False)

    def is_expanded(self) -> bool:
        return self.expanded

    def is_collapsed(self) -> bool:
        return not self.expanded
