# pages/dashboard_page.py
"""
Enterprise dashboard page with async data loading and real-time updates.

Theming
-------
Every heading, label, and value uses a Shadcn* component (ShadcnHeading,
ShadcnLabel, ShadcnCaption) instead of a plain QLabel with a hardcoded
color. Those components subscribe to ThemeManager.theme_changed and
re-render automatically, which fixes the "stale color after theme toggle"
problem that plain QLabels exhibit.

Design notes
------------
This page is constructed during the login -> dashboard transition. To
avoid repaint flicker on the just-shown main window:

  * No widget mutations happen in __init__ beyond building the placeholder UI.
  * The first data load is triggered from showEvent(), debounced so it only
    fires once, regardless of how many times the page is re-shown.
  * Bulk table updates are wrapped in setUpdatesEnabled(False).
  * The auto-refresh timer only starts after the first successful load.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize, Slot

from widgets.components import (
    ShadcnCard, CardContent, ShadcnDataTable, ShadcnButton, ShadcnToast,
    ShadcnLoadingSpinner, ShadcnHeading, ShadcnLabel, ShadcnCaption,
)
from core.icon_manager import IconManager
from core.theme_manager import ThemeManager
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DashboardPage(QWidget):
    """Enterprise dashboard with async data loading."""

    navigate_requested = Signal(str)
    data_loaded = Signal(dict)
    data_error = Signal(str)

    def __init__(self, user_info: dict, permissions: list, data_service):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service
        self.icon_manager = IconManager()
        self.theme_manager = ThemeManager()
        self._loading = False
        self._stats = {}
        self._initial_load_complete = False
        self._first_show_done = False
        self._card_spinners = []

        # Auto-refresh timer — started only after first successful load.
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(30000)
        self.auto_refresh_timer.timeout.connect(self.load_data)

        self.init_ui()

        self.data_loaded.connect(self._update_ui)
        self.data_error.connect(self._show_error)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # Welcome header
        welcome_layout = QHBoxLayout()

        self.welcome_label = ShadcnHeading(
            f"Welcome back, {self.user_info.get('full_name', 'User')}",
            level=2,
        )
        welcome_layout.addWidget(self.welcome_label)
        welcome_layout.addStretch()

        self.refresh_btn = ShadcnButton(
            "Refresh", variant="outline", size="sm", icon="refresh"
        )
        self.refresh_btn.clicked.connect(self.load_data)
        welcome_layout.addWidget(self.refresh_btn)

        layout.addLayout(welcome_layout)

        # Stat cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)

        self.active_visitors_card = self._create_stat_card(
            "Active Visitors", "---", "visitors"
        )
        self.active_employees_card = self._create_stat_card(
            "Active Employees", "---", "employees"
        )
        self.today_entries_card = self._create_stat_card(
            "Today's Entries", "---", "check_in"
        )
        self.checked_out_card = self._create_stat_card(
            "Checked Out Today", "---", "check_out"
        )

        for card in (
            self.active_visitors_card,
            self.active_employees_card,
            self.today_entries_card,
            self.checked_out_card,
        ):
            cards_layout.addWidget(card)

        layout.addLayout(cards_layout)

        # Quick actions
        actions_bar = QHBoxLayout()
        actions_label = ShadcnLabel("Quick Actions:")
        actions_bar.addWidget(actions_label)

        if 'manage_visitors' in self.permissions:
            checkin_btn = ShadcnButton(
                "Check In Visitor", variant="outline", size="sm"
            )
            checkin_btn.clicked.connect(
                lambda: self.navigate_requested.emit("visitors")
            )
            checkin_btn.setToolTip("Go to Visitors page")
            actions_bar.addWidget(checkin_btn)

        if 'view_access_logs' in self.permissions:
            logs_btn = ShadcnButton(
                "View Access Logs", variant="outline", size="sm"
            )
            logs_btn.clicked.connect(
                lambda: self.navigate_requested.emit("access_logs")
            )
            logs_btn.setToolTip("Go to Access Logs page")
            actions_bar.addWidget(logs_btn)

        if 'manage_employees' in self.permissions:
            employees_btn = ShadcnButton(
                "Manage Employees", variant="outline", size="sm"
            )
            employees_btn.clicked.connect(
                lambda: self.navigate_requested.emit("employees")
            )
            employees_btn.setToolTip("Go to Employees page")
            actions_bar.addWidget(employees_btn)

        actions_bar.addStretch()
        layout.addLayout(actions_bar)

        # Recent activity
        recent_label = ShadcnHeading("Recent Access Activity", level=4)
        layout.addWidget(recent_label)

        self.logs_table = ShadcnDataTable(
            ["Time", "Person Type", "Direction", "Granted", "Verified By"],
            empty_message="No recent activity to show.",
        )
        self.logs_table.setMinimumHeight(200)
        layout.addWidget(self.logs_table)

    def _create_stat_card(self, title: str, value: str,
                          icon_name: str) -> ShadcnCard:
        card = ShadcnCard()
        card.setMinimumHeight(110)
        card.setMaximumHeight(120)
        card.setAccessibleName(f"{title}: {value}")

        content = CardContent()
        content.layout.setContentsMargins(16, 12, 16, 12)

        h_layout = QHBoxLayout()

        icon = self.icon_manager.get_icon(
            icon_name, size=QSize(36, 36), state="default"
        )
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(36, 36))
        icon_label.setFixedSize(36, 36)
        icon_label.setAccessibleName("")
        h_layout.addWidget(icon_label)

        v_layout = QVBoxLayout()

        title_lbl = ShadcnCaption(title)
        v_layout.addWidget(title_lbl)

        # Use ShadcnHeading for the value so it re-themes automatically.
        value_lbl = ShadcnHeading(value, level=1)
        value_lbl.setObjectName("statValue")
        v_layout.addWidget(value_lbl)

        h_layout.addLayout(v_layout, 1)

        # Inline loading spinner, hidden until a load starts.
        spinner = ShadcnLoadingSpinner(size="sm")
        spinner.set_color(self.theme_manager.get_tokens().get(
            "primary", "#006B3F"
        ))
        h_layout.addWidget(spinner, 0, Qt.AlignTop)
        self._card_spinners.append(spinner)

        content.layout.addLayout(h_layout)
        card.set_content(content)
        card.value_label = value_lbl
        card.title = title
        return card

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._first_show_done:
            self._first_show_done = True
            QTimer.singleShot(0, self.load_data)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_data(self):
        if self._loading:
            return

        self._loading = True
        self._set_loading_state(True)

        try:
            self.data_service.get_dashboard_stats_async(
                callback=self.data_loaded.emit,
                error_callback=self.data_error.emit,
            )
        except Exception as e:
            logger.error(f"Error loading dashboard data: {e}")
            self.data_error.emit(str(e))
            self._loading = False

    @Slot(dict)
    def _update_ui(self, stats: dict):
        self._stats = stats
        self._initial_load_complete = True
        self._loading = False
        self._set_loading_state(False)

        self.setUpdatesEnabled(False)
        try:
            values = {
                self.active_visitors_card: stats.get("active_visitors", 0),
                self.active_employees_card: stats.get("active_employees", 0),
                self.today_entries_card: stats.get("today_entries", 0),
                self.checked_out_card: stats.get("today_checkouts", 0),
            }
            for card, value in values.items():
                card.value_label.setText(str(value))
                card.setAccessibleName(f"{card.title}: {value}")

            recent = stats.get("recent_logs", [])
            table_data = []
            for log in recent[:10]:
                ts = log.get("timestamp") or ""
                table_data.append((
                    ts[:19] if ts else "",
                    log.get("person_type", ""),
                    log.get("direction", ""),
                    "Yes" if log.get("granted") else "No",
                    log.get("verified_by", ""),
                ))

            self.logs_table.setUpdatesEnabled(False)
            try:
                self.logs_table.populate(table_data)
            finally:
                self.logs_table.setUpdatesEnabled(True)
        finally:
            self.setUpdatesEnabled(True)
            self.update()

        if not self.auto_refresh_timer.isActive():
            self.auto_refresh_timer.start()

    @Slot(str)
    def _show_error(self, error_msg: str):
        self._loading = False
        self._set_loading_state(False)
        logger.error(f"Dashboard data error: {error_msg}")

        if not self._initial_load_complete:
            for card in (
                self.active_visitors_card,
                self.active_employees_card,
                self.today_entries_card,
                self.checked_out_card,
            ):
                card.value_label.setText("—")
            self.logs_table.set_error(
                "Failed to load recent activity. Click Refresh to retry."
            )

        ShadcnToast(
            "Dashboard Error",
            description=f"Failed to load data: {error_msg}",
            variant="destructive",
            duration=4000,
            parent=self,
        )

    def _set_loading_state(self, loading: bool):
        self.refresh_btn.setEnabled(not loading)
        for spinner in self._card_spinners:
            if loading:
                spinner.start()
            else:
                spinner.stop()
        if loading:
            for card in (
                self.active_visitors_card,
                self.active_employees_card,
                self.today_entries_card,
                self.checked_out_card,
            ):
                if card.value_label.text() in ("---", "—"):
                    card.value_label.setText("…")

    def refresh_data(self):
        self.load_data()

    def cleanup(self):
        if getattr(self, 'auto_refresh_timer', None):
            self.auto_refresh_timer.stop()
            self.auto_refresh_timer.deleteLater()

        for spinner in self._card_spinners:
            try:
                spinner.stop()
            except Exception:
                pass

        try:
            self.data_loaded.disconnect()
            self.data_error.disconnect()
        except Exception:
            pass

        logger.debug("Dashboard page cleaned up")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_1 and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            if 'manage_visitors' in self.permissions:
                self.navigate_requested.emit("visitors")
            event.accept()
            return
        if event.key() == Qt.Key.Key_2 and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            if 'view_access_logs' in self.permissions:
                self.navigate_requested.emit("access_logs")
            event.accept()
            return
        if event.key() == Qt.Key.Key_3 and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            if 'manage_employees' in self.permissions:
                self.navigate_requested.emit("employees")
            event.accept()
            return
        if event.key() == Qt.Key.Key_R and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.load_data()
            event.accept()
            return
        super().keyPressEvent(event)
