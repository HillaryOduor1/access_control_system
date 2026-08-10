from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from widgets.components import (
    ShadcnCard, CardContent, ShadcnDataTable, ShadcnButton, ShadcnToast
)
from core.icon_manager import IconManager
from datetime import datetime

class DashboardPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service
        self.icon_manager = IconManager()
        self.init_ui()
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.load_data)
        self.refresh_timer.start(5000)
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        welcome = QLabel(f"Welcome back, {self.user_info['full_name']}")
        welcome.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(welcome)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)
        self.active_visitors_card = self._create_stat_card("Active Visitors", "0", "visitors")
        self.active_employees_card = self._create_stat_card("Active Employees", "0", "employees")
        self.today_entries_card = self._create_stat_card("Today's Entries", "0", "check_in")
        self.checked_out_card = self._create_stat_card("Checked Out Today", "0", "check_out")
        cards_layout.addWidget(self.active_visitors_card)
        cards_layout.addWidget(self.active_employees_card)
        cards_layout.addWidget(self.today_entries_card)
        cards_layout.addWidget(self.checked_out_card)
        layout.addLayout(cards_layout)

        actions_bar = QHBoxLayout()
        actions_bar.addWidget(QLabel("Quick Actions:"))
        if 'manage_visitors' in self.permissions:
            checkin_btn = ShadcnButton("Check In Visitor", variant="outline", size="sm")
            checkin_btn.clicked.connect(lambda: self.navigate_requested.emit("visitors"))
            actions_bar.addWidget(checkin_btn)
        if 'view_access_logs' in self.permissions:
            logs_btn = ShadcnButton("View Access Logs", variant="outline", size="sm")
            logs_btn.clicked.connect(lambda: self.navigate_requested.emit("access_logs"))
            actions_bar.addWidget(logs_btn)
        actions_bar.addStretch()
        layout.addLayout(actions_bar)

        recent_label = QLabel("Recent Access Activity")
        recent_label.setStyleSheet("font-weight: 600; font-size: 16px; margin-top: 8px;")
        layout.addWidget(recent_label)

        self.logs_table = ShadcnDataTable(["Time", "Person Type", "Direction", "Granted", "Verified By"])
        layout.addWidget(self.logs_table)

    def _create_stat_card(self, title, value, icon_name):
        card = ShadcnCard()
        card.setFixedHeight(110)
        content = CardContent()
        content.layout.setContentsMargins(16, 12, 16, 12)

        h_layout = QHBoxLayout()
        icon = self.icon_manager.get_icon(icon_name, size=QSize(36, 36), state="default")
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(36, 36))
        h_layout.addWidget(icon_label)

        v_layout = QVBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 13px; color: #64748B;")
        self.value_lbl = QLabel(value)
        self.value_lbl.setStyleSheet("font-size: 28px; font-weight: bold;")
        v_layout.addWidget(title_lbl)
        v_layout.addWidget(self.value_lbl)
        h_layout.addLayout(v_layout, 1)

        content.layout.addLayout(h_layout)
        card.set_content(content)
        card.value_label = self.value_lbl
        return card

    def load_data(self):
        try:
            stats = self.data_service.get_dashboard_stats()
            self.active_visitors_card.value_label.setText(str(stats["active_visitors"]))
            self.active_employees_card.value_label.setText(str(stats["active_employees"]))
            self.today_entries_card.value_label.setText(str(stats["today_entries"]))
            self.checked_out_card.value_label.setText(str(stats["today_checkouts"]))

            recent = stats["recent_logs"]
            table_data = []
            for log in recent:
                table_data.append((
                    log.get("timestamp", "")[:19],
                    log.get("person_type", ""),
                    log.get("direction", ""),
                    "Yes" if log.get("granted") else "No",
                    log.get("verified_by", "")
                ))
            self.logs_table.populate(table_data)
        except Exception as e:
            ShadcnToast("Error", f"Failed to load dashboard data: {str(e)}", duration=3000, parent=self)
            
