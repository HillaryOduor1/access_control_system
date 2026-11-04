# pages/user_management_page.py
"""
Enterprise user management.

Data sources
------------
The Users page merges two sources:

1. The server's user list from `GET /users` (tenant-scoped) or
   `GET /users/admin/all` (all tenants, admin only).
2. The local SQLite users table, which always contains the built-in
   admin/security/finance/staff accounts and any users created while
   offline.

Merging happens in `DataService.get_all_users()` (tenant-scoped) or
`DataService.get_all_users_across_tenants()` (admin only). Keyed by
lowercased username. Server rows win on collision because they carry
the canonical id and roles the API expects.

Toolbar layout
--------------
The toolbar is split across two rows:

  Row 1:  [Create User]  [Refresh]                              [N users]
  Row 2:  [Filter input]  [Show local-only]  [Show all tenants]

This keeps each row's minimum width well under the window's typical
content width. A single-row toolbar that packed all six controls
together needed roughly 850px minimum, which forced a heavy layout
pass on first show — and if that pass landed during the
QStackedWidget transition, the caption bar flickered.
"""
import re
import logging
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QDialog, QFormLayout,
    QComboBox, QCheckBox, QTableWidgetItem, QLineEdit,
    QLabel, QSizePolicy, QToolButton,
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QKeyEvent, QIcon, QCursor

from pages.base_page import BasePage
from widgets.components import (
    ShadcnButton, ShadcnInput, ShadcnToast,
    ShadcnAlertDialog, ShadcnCaption,
)
from widgets.data_table import ShadcnDataTable
from widgets.password_strength_meter import PasswordStrengthMeter
from core.icon_manager import IconManager
from core.theme_manager import ThemeManager

logger = logging.getLogger(__name__)


class UserManagementPage(BasePage):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        self.data_service = data_service
        self.theme_manager = ThemeManager()
        self._initial_load_done = False
        self._is_refreshing = False
        self._rebuild_pending = False
        self._users_cache: List[Dict[str, Any]] = []
        self._current_tenant: str = ""
        # Availability of the cross-tenant endpoint. None = unknown,
        # True = server answered, False = server 404/403'd.
        self._cross_tenant_available: Optional[bool] = None

        super().__init__(user_info, permissions, page_id="user_management")

        try:
            self._current_tenant = str(
                (self.user_info or {}).get("tenant_id", "") or ""
            )
        except Exception:
            self._current_tenant = ""

        try:
            self.theme_manager.register_widget(
                self, on_theme_changed=self._apply_theme
            )
        except Exception as e:
            logger.debug(f"ThemeManager registration failed: {e}")

        self._apply_theme()

    # ------------------------------------------------------------------
    # Capability check
    # ------------------------------------------------------------------

    def _can_manage_users(self) -> bool:
        try:
            perms = set(self.permissions or [])
        except Exception:
            perms = set()

        if "manage_users" in perms:
            return True

        try:
            role = str((self.user_info or {}).get("role", "")).lower()
        except Exception:
            role = ""
        return role == "admin"

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self, *_):
        try:
            tokens = self.theme_manager.get_tokens()
            bg = tokens.get("background", "#F8FAFC")
            fg = tokens.get("foreground", "#0F172A")
            self.setStyleSheet(f"background-color: {bg}; color: {fg};")
        except Exception as e:
            logger.debug(f"_apply_theme failed: {e}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_theme()
        if not self._initial_load_done:
            self._initial_load_done = True
            # Defer the initial fetch so the QStackedWidget transition
            # has fully completed before the table starts populating.
            QTimer.singleShot(50, self._initial_load)

    def _initial_load(self):
        """First-load path. Runs with no loading spinner on the
        refresh button, because resizing that button mid-transition
        invalidates the parent layout."""
        try:
            if hasattr(self.data_service, "refresh_online_snapshot"):
                self.data_service.refresh_online_snapshot()
        except Exception:
            pass

        try:
            self._fetch_and_render(show_spinner=False)
        except Exception:
            logger.exception("Initial user load failed")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def init_ui(self):
        layout = self.content_layout
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # ----------------------------------------------------------
        # Toolbar row 1: primary actions + count
        # ----------------------------------------------------------
        toolbar_top = QHBoxLayout()
        toolbar_top.setSpacing(10)

        self.add_btn = ShadcnButton("Create User", variant="default")
        self.add_btn.setToolTip("Create a new user (Ctrl+N)")
        self.add_btn.clicked.connect(self.create_user)
        toolbar_top.addWidget(self.add_btn)

        self.refresh_btn = ShadcnButton(
            "Refresh", variant="outline", size="sm"
        )
        self.refresh_btn.setToolTip("Reload the user list (Ctrl+R)")
        self.refresh_btn.clicked.connect(self.refresh_users)
        toolbar_top.addWidget(self.refresh_btn)

        toolbar_top.addStretch()

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("background: transparent;")
        toolbar_top.addWidget(self.count_label)

        layout.addLayout(toolbar_top)

        # ----------------------------------------------------------
        # Toolbar row 2: filters
        # ----------------------------------------------------------
        toolbar_bottom = QHBoxLayout()
        toolbar_bottom.setSpacing(10)

        self.filter_input = ShadcnInput(
            "Filter by username, name, email…"
        )
        self.filter_input.setMinimumWidth(240)
        self.filter_input.setMaximumWidth(360)
        self.filter_input.textChanged.connect(self._on_filter_changed)
        toolbar_bottom.addWidget(self.filter_input)

        self.local_toggle = QCheckBox("Show local-only users")
        self.local_toggle.setToolTip(
            "Include users that exist only in the local database "
            "(built-in accounts, offline signups)."
        )
        self.local_toggle.setChecked(True)
        self.local_toggle.stateChanged.connect(
            lambda _: self._rebuild_table()
        )
        toolbar_bottom.addWidget(self.local_toggle)

        self.all_tenants_toggle = QCheckBox("Show all tenants")
        self.all_tenants_toggle.setChecked(False)
        self.all_tenants_toggle.stateChanged.connect(
            self._on_all_tenants_toggled
        )
        # Non-admins see the checkbox but cannot interact with it.
        # Using setEnabled instead of setVisible keeps the toolbar's
        # layout stable — no extra layout pass on first show.
        self.all_tenants_toggle.setEnabled(self._can_manage_users())
        self._update_cross_tenant_tooltip()
        toolbar_bottom.addWidget(self.all_tenants_toggle)

        toolbar_bottom.addStretch()

        layout.addLayout(toolbar_bottom)

        # ----------------------------------------------------------
        # Table
        # ----------------------------------------------------------
        self.table = ShadcnDataTable(
            ["Source", "Tenant", "ID", "Username", "Full Name",
             "Email", "Roles", "Active", "Actions"],
            empty_message="No users yet. Use Create User to add one.",
        )
        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.table.setMinimumHeight(400)
        self.table.setColumnWidth(0, 70)    # Source
        self.table.setColumnWidth(1, 130)   # Tenant
        self.table.setColumnWidth(2, 110)   # ID
        self.table.setColumnWidth(3, 130)   # Username
        self.table.setColumnWidth(4, 160)   # Full Name
        self.table.setColumnWidth(5, 180)   # Email
        self.table.setColumnWidth(6, 110)   # Roles
        self.table.setColumnWidth(7, 70)    # Active
        self.table.setColumnWidth(8, 180)   # Actions

        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.installEventFilter(self)
        layout.addWidget(self.table)

    def _update_cross_tenant_tooltip(self):
        can_manage = self._can_manage_users()
        if not can_manage:
            self.all_tenants_toggle.setToolTip(
                "Requires the manage_users permission."
            )
            return

        if self._cross_tenant_available is False:
            self.all_tenants_toggle.setToolTip(
                "Cross-tenant listing is not enabled on this server."
            )
        else:
            self.all_tenants_toggle.setToolTip(
                "Include users from every tenant, not just your own."
            )

    # ------------------------------------------------------------------
    # Data fetch
    # ------------------------------------------------------------------

    def _wants_all_tenants(self) -> bool:
        return (
            self._can_manage_users()
            and hasattr(self, "all_tenants_toggle")
            and self.all_tenants_toggle.isChecked()
            and self._cross_tenant_available is not False
        )

    def _fetch_users(self) -> List[Dict]:
        if self._wants_all_tenants() and hasattr(
            self.data_service, "get_all_users_across_tenants"
        ):
            try:
                users = self.data_service.get_all_users_across_tenants() or []
                self._cross_tenant_available = True
                return users
            except Exception as e:
                logger.warning(
                    f"Cross-tenant fetch failed: {e}. "
                    f"Falling back to tenant-scoped."
                )
                self._cross_tenant_available = False
                try:
                    self.all_tenants_toggle.blockSignals(True)
                    self.all_tenants_toggle.setChecked(False)
                finally:
                    self.all_tenants_toggle.blockSignals(False)
                self._update_cross_tenant_tooltip()

        if hasattr(self.data_service, "get_all_users"):
            return self.data_service.get_all_users() or []

        if hasattr(self.data_service, "get_users"):
            return self.data_service.get_users() or []

        raise AttributeError(
            "data_service exposes neither get_all_users_across_tenants, "
            "get_all_users, nor get_users"
        )

    def _fetch_and_render(self, show_spinner: bool = True):
        if show_spinner:
            self.refresh_btn.set_loading(True, "Refreshing…")

        try:
            try:
                if hasattr(self.data_service, "refresh_online_snapshot"):
                    self.data_service.refresh_online_snapshot()
            except Exception:
                pass

            users = self._fetch_users()
            self._users_cache = list(users)
            logger.info(f"Loaded {len(users)} users")

            if self._cross_tenant_available is not None:
                self._update_cross_tenant_tooltip()

            self._rebuild_table()
        finally:
            if show_spinner:
                self.refresh_btn.set_loading(False)

    def refresh_users(self):
        """Public refresh triggered by the Refresh button or Ctrl+R."""
        if self._is_refreshing:
            return
        self._is_refreshing = True
        try:
            # Only spin the refresh button if the page is already
            # visible and the initial layout has settled.
            show_spinner = (
                self._initial_load_done and self.isVisible()
            )
            self._fetch_and_render(show_spinner=show_spinner)
        except Exception as e:
            logger.exception("Failed to load users")
            detail = str(e)
            if hasattr(e, "response") and getattr(e, "response", None):
                try:
                    detail = (
                        f"HTTP {e.response.status_code}: "
                        f"{e.response.text[:300]}"
                    )
                except Exception:
                    pass

            self.table.set_error(f"Could not load users. {detail}")
            ShadcnToast(
                "Error",
                description=f"Failed to load users: {detail}",
                parent=self,
                variant="destructive",
            )
        finally:
            self._is_refreshing = False

    def _on_all_tenants_toggled(self, _state):
        if not self._can_manage_users():
            return
        if not self._initial_load_done:
            return
        if self._is_refreshing:
            return

        self._is_refreshing = True
        try:
            self._fetch_and_render(show_spinner=False)
        except Exception as e:
            logger.exception("Cross-tenant toggle refresh failed")
            ShadcnToast(
                "Error",
                description=f"Failed to load users: {e}",
                parent=self,
                variant="destructive",
            )
        finally:
            self._is_refreshing = False

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------

    def _tenant_display_for(self, user: Dict) -> str:
        source = (user.get("source") or "api").lower()
        tenant = (
            user.get("tenant_id")
            or user.get("tenant")
            or user.get("tenant_name")
        )
        if tenant:
            return str(tenant)
        if source == "local":
            return "local"
        return self._current_tenant or "—"

    def _rebuild_table(self):
        """
        Render the cached users into the table.

        Deferred by one event-loop tick and guarded against stacking,
        so that if this runs during a QStackedWidget transition the
        table's layout pass does not interleave with the page stack's.
        """
        if self._rebuild_pending:
            return
        self._rebuild_pending = True

        def _do():
            self._rebuild_pending = False
            try:
                self._rebuild_table_now()
            except Exception:
                logger.exception("Rebuild table failed")

        QTimer.singleShot(0, _do)

    def _rebuild_table_now(self):
        if not hasattr(self, "table"):
            return

        show_local = (
            self.local_toggle.isChecked()
            if hasattr(self, "local_toggle") else True
        )

        rows = []
        visible_users: List[Dict] = []

        for u in self._users_cache:
            source = (u.get("source") or "api").lower()
            if not show_local and source == "local":
                continue

            roles = u.get("roles")
            if isinstance(roles, str):
                roles = [roles]
            elif roles is None:
                role = u.get("role")
                roles = [role] if role else []

            display_id = u.get("id", u.get("_id", ""))
            source_label = "Server" if source == "api" else "Local"
            tenant_label = self._tenant_display_for(u)
            is_active = u.get("is_active", True)

            rows.append((
                source_label,
                tenant_label,
                str(display_id),
                u.get("username", ""),
                u.get("full_name", ""),
                u.get("email", "") or "",
                ", ".join(str(r) for r in roles) if roles else "-",
                "Yes" if is_active else "No",
                "",
            ))
            visible_users.append(u)

        # Batch the populate + setCellWidget calls so Qt performs one
        # layout pass on the table instead of one per widget.
        self.table.setUpdatesEnabled(False)
        try:
            self.table.populate(rows)

            for row, u in enumerate(visible_users):
                btn_widget = QWidget()
                btn_layout = QHBoxLayout(btn_widget)
                btn_layout.setContentsMargins(2, 2, 2, 2)
                btn_layout.setSpacing(4)

                edit_btn = ShadcnButton(
                    "Edit", variant="outline", size="sm"
                )
                edit_btn.setFixedWidth(60)
                edit_btn.setAccessibleName(
                    f"Edit {u.get('username', 'user')}"
                )
                uid = u.get("id", u.get("_id"))
                edit_btn.clicked.connect(
                    lambda _=False, _uid=uid: self.edit_user(_uid)
                )
                btn_layout.addWidget(edit_btn)

                if u.get("is_active", True):
                    deactivate_btn = ShadcnButton(
                        "Deactivate", variant="destructive", size="sm"
                    )
                    deactivate_btn.setFixedWidth(80)
                    deactivate_btn.setAccessibleName(
                        f"Deactivate {u.get('username', 'user')}"
                    )
                    deactivate_btn.clicked.connect(
                        lambda _=False, _uid=uid:
                            self.deactivate_user(_uid)
                    )
                    btn_layout.addWidget(deactivate_btn)

                btn_layout.addStretch()
                self.table.setCellWidget(row, 8, btn_widget)
        finally:
            self.table.setUpdatesEnabled(True)
            self.table.viewport().update()

        total = len(self._users_cache)
        shown = len(visible_users)
        if hasattr(self, "count_label"):
            if shown == total:
                self.count_label.setText(f"{total} users")
            else:
                self.count_label.setText(f"{shown} of {total} users")

        if (hasattr(self, "filter_input")
                and self.filter_input.text().strip()):
            self.table.filter_table(self.filter_input.text())

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _on_filter_changed(self, text: str):
        if hasattr(self, "table"):
            self.table.filter_table(text)

    # ------------------------------------------------------------------
    # Event filter and shortcuts
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self.table and event.type() == event.Type.KeyPress:
            key = event.key()
            selected = self.table.get_selected_rows()
            if selected:
                try:
                    users = self._users_cache
                    user = (
                        users[selected[0]]
                        if selected[0] < len(users) else None
                    )
                except Exception:
                    user = None
                if user:
                    uid = user.get("id", user.get("_id"))
                    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                        self.edit_user(uid)
                        return True
                    if (key == Qt.Key.Key_Delete
                            and user.get("is_active", True)):
                        self.deactivate_user(uid)
                        return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def create_user(self):
        dialog = UserDialog(self.data_service, None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_users()

    def edit_user(self, user_id):
        try:
            user = self.data_service.get_user(user_id)
            if user:
                dialog = UserDialog(self.data_service, user, self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    self.refresh_users()
        except Exception as e:
            logger.exception("Error loading user")
            ShadcnToast(
                "Error",
                description=f"Failed to load user: {e}",
                parent=self,
                variant="destructive",
            )

    def deactivate_user(self, user_id):
        try:
            user = self.data_service.get_user(user_id)
            if not user:
                return

            dialog = ShadcnAlertDialog(
                "Confirm Deactivation",
                f"Deactivate user '{user.get('full_name', 'Unknown')}'?",
                action_text="Deactivate",
                destructive=True,
                parent=self,
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.data_service.deactivate_user(user_id)
                ShadcnToast(
                    "Success",
                    description="User deactivated",
                    parent=self,
                    variant="success",
                )
                self.refresh_users()
        except Exception as e:
            logger.exception("Deactivation error")
            ShadcnToast(
                "Error",
                description=f"Failed to deactivate: {e}",
                parent=self,
                variant="destructive",
            )

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_N and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.create_user()
            event.accept()
            return
        if event.key() == Qt.Key.Key_R and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.refresh_users()
            event.accept()
            return
        super().keyPressEvent(event)


class UserDialog(QDialog):
    """User dialog with password show/hide and validation."""

    def __init__(self, data_service, user_data, parent=None):
        super().__init__(parent)
        self.data_service = data_service
        self.user_data = user_data
        self.is_edit = user_data is not None
        self.theme_manager = ThemeManager()
        self.icon_manager = IconManager()

        self.setWindowTitle(
            "Create User" if not self.is_edit else "Edit User"
        )
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setAccessibleName(self.windowTitle())
        self.init_ui()

        if self.is_edit:
            self._load_data()

    def init_ui(self):
        tokens = self.theme_manager.get_tokens()
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignRight)

        self.username_input = ShadcnInput("Username")
        self.username_input.setAccessibleName("Username")
        self.username_input.editingFinished.connect(self._validate_username)
        form.addRow("Username *", self.username_input)

        self.username_error = ShadcnCaption("")
        self.username_error.setStyleSheet(
            f"color: {tokens['destructive']};"
        )
        self.username_error.hide()
        form.addRow("", self.username_error)

        self.full_name_input = ShadcnInput("Full name")
        self.full_name_input.setAccessibleName("Full name")
        form.addRow("Full Name", self.full_name_input)

        self.email_input = ShadcnInput("email@domain.com")
        self.email_input.setAccessibleName("Email")
        self.email_input.editingFinished.connect(self._validate_email)
        form.addRow("Email", self.email_input)

        self.email_error = ShadcnCaption("")
        self.email_error.setStyleSheet(f"color: {tokens['destructive']};")
        self.email_error.hide()
        form.addRow("", self.email_error)

        self.tenant_input = ShadcnInput("Tenant (organisation)")
        self.tenant_input.setAccessibleName("Tenant")
        self.tenant_input.setToolTip(
            "Server-side tenant identifier. Leave blank to keep the "
            "user in the same tenant as you."
        )
        form.addRow("Tenant", self.tenant_input)

        self.password_container = QWidget()
        password_layout = QVBoxLayout(self.password_container)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.setSpacing(6)

        pw_row = QHBoxLayout()
        pw_row.setSpacing(6)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText(
            "Enter password" if not self.is_edit
            else "Leave blank to keep current"
        )
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setAccessibleName("Password")
        self.password_input.textChanged.connect(self._on_password_changed)
        pw_row.addWidget(self.password_input, 1)

        self.show_pass_btn = QToolButton()
        self.show_pass_btn.setCheckable(True)
        self.show_pass_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.show_pass_btn.setFixedSize(32, 32)
        self.show_pass_btn.setAccessibleName("Show password")
        self.show_pass_btn.setToolTip("Show / hide password")
        self.show_pass_btn.toggled.connect(self._toggle_password_visibility)
        pw_row.addWidget(self.show_pass_btn)

        password_layout.addLayout(pw_row)

        self.strength_meter = PasswordStrengthMeter()
        self.strength_meter.setFixedHeight(6)
        password_layout.addWidget(self.strength_meter)

        self.strength_label = QLabel("Password strength")
        self.strength_label.setStyleSheet(
            f"font-size: {tokens['font.caption']}px; "
            f"color: {tokens['muted-foreground']}; "
            "background: transparent;"
        )
        password_layout.addWidget(self.strength_label)

        form.addRow("Password", self.password_container)

        self.role_combo = QComboBox()
        self.role_combo.setAccessibleName("Role")
        self.role_combo.addItems(
            ['staff', 'security', 'finance', 'admin']
        )
        form.addRow("Role", self.role_combo)

        self.active_check = QCheckBox("Active")
        self.active_check.setChecked(True)
        self.active_check.setAccessibleName("Active")
        form.addRow("", self.active_check)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        cancel_btn = ShadcnButton("Cancel", variant="outline")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.save_btn = ShadcnButton("Save", variant="default")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save)
        self.save_btn.setMinimumWidth(100)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

        self._refresh_show_hide_icon()
        QTimer.singleShot(0, self.username_input.setFocus)

    def _refresh_show_hide_icon(self):
        name = (
            "eye_off"
            if self.password_input.echoMode() == QLineEdit.EchoMode.Normal
            else "eye"
        )
        icon = self.icon_manager.get_icon(name, size=QSize(18, 18))
        self.show_pass_btn.setIcon(QIcon(icon))
        self.show_pass_btn.setIconSize(QSize(18, 18))

    def _toggle_password_visibility(self, checked: bool):
        if checked:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_pass_btn.setAccessibleName("Hide password")
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_pass_btn.setAccessibleName("Show password")
        self._refresh_show_hide_icon()

    def _validate_username(self):
        text = self.username_input.text()
        if not text.strip():
            self.username_error.setText("Username is required")
            self.username_error.show()
        elif len(text.strip()) < 3:
            self.username_error.setText(
                "Username must be at least 3 characters"
            )
            self.username_error.show()
        elif not re.match(r'^[a-zA-Z0-9_]+$', text):
            self.username_error.setText(
                "Username can only contain letters, numbers, "
                "and underscore"
            )
            self.username_error.show()
        else:
            self.username_error.hide()

    def _validate_email(self):
        text = self.email_input.text()
        if not text.strip():
            self.email_error.hide()
            return
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, text.strip()):
            self.email_error.setText("Invalid email format")
            self.email_error.show()
        else:
            self.email_error.hide()

    def _on_password_changed(self, text: str):
        self.strength_meter.evaluate(text)
        score = (
            self.strength_meter.get_strength_score()
            if hasattr(self.strength_meter, "get_strength_score")
            else 0
        )
        self._update_strength_label(score)

    def _update_strength_label(self, score: int):
        tokens = self.theme_manager.get_tokens()
        if not self.password_input.text():
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

    def _load_data(self):
        if not self.user_data:
            return
        self.username_input.setText(self.user_data.get('username', ''))
        self.full_name_input.setText(self.user_data.get('full_name', ''))
        self.email_input.setText(self.user_data.get('email', ''))

        tenant = (
            self.user_data.get('tenant_id')
            or self.user_data.get('tenant')
            or ''
        )
        if tenant:
            self.tenant_input.setText(str(tenant))

        roles = self.user_data.get('roles')
        if isinstance(roles, str):
            roles = [roles]
        if not roles:
            role = self.user_data.get('role')
            roles = [role] if role else ['staff']
        if roles:
            self.role_combo.setCurrentText(str(roles[0]))

        self.active_check.setChecked(
            bool(self.user_data.get('is_active', True))
        )
        self.password_input.setPlaceholderText(
            "Leave blank to keep current"
        )

    def _validate_password(self, password: str) -> tuple:
        if not password:
            return False, "Password is required"
        if len(password) < 8:
            return False, "Password must be at least 8 characters"
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        if not re.search(r'[0-9]', password):
            return False, "Password must contain at least one number"
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one special character"
        return True, ""

    def save(self):
        username = self.username_input.text().strip()
        full_name = self.full_name_input.text().strip()
        email = self.email_input.text().strip()
        tenant = self.tenant_input.text().strip()
        password = self.password_input.text()
        role = self.role_combo.currentText()
        is_active = self.active_check.isChecked()

        if not username:
            self._validate_username()
            ShadcnToast(
                "Error",
                description="Username is required",
                parent=self,
                variant="destructive",
            )
            return

        if self.username_error.isVisible():
            ShadcnToast(
                "Error",
                description="Please fix username errors",
                parent=self,
                variant="destructive",
            )
            return

        if email and self.email_error.isVisible():
            ShadcnToast(
                "Error",
                description="Please fix email errors",
                parent=self,
                variant="destructive",
            )
            return

        if not self.is_edit or password:
            valid, error = self._validate_password(password)
            if not valid:
                ShadcnToast(
                    "Error",
                    description=error,
                    parent=self,
                    variant="destructive",
                )
                return

        payload = {
            "username": username,
            "full_name": full_name,
            "email": email,
            "roles": [role],
            "is_active": is_active,
        }
        if tenant:
            payload["tenant_id"] = tenant
        if password:
            payload["password"] = password

        try:
            if self.is_edit:
                uid = self.user_data.get("id", self.user_data.get("_id"))
                self.data_service.update_user(uid, payload)
                ShadcnToast(
                    "Success",
                    description="User updated",
                    parent=self,
                    variant="success",
                )
            else:
                self.data_service.create_user(payload)
                ShadcnToast(
                    "Success",
                    description="User created",
                    parent=self,
                    variant="success",
                )
            self.accept()
        except Exception as e:
            logger.error(f"Save user error: {e}")
            error_msg = str(e)
            if (
                "unique constraint" in error_msg.lower()
                or "duplicate" in error_msg.lower()
                or "409" in error_msg
            ):
                ShadcnToast(
                    "Error",
                    description="Username or email already exists",
                    parent=self,
                    variant="destructive",
                )
            else:
                ShadcnToast(
                    "Error",
                    description=f"Failed to save user: {error_msg}",
                    parent=self,
                    variant="destructive",
                )

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.save()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)
