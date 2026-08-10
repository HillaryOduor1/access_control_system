# pages/access_logs_page.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit
from PySide6.QtCore import Qt, QDate, Signal
from widgets.components import ShadcnDataTable, ShadcnButton, ShadcnInput

class AccessLogsPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service
        self.init_ui()
        self.refresh_logs()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["All", "visitor", "employee"])
        filter_layout.addWidget(QLabel("Person Type:"))
        filter_layout.addWidget(self.type_combo)

        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["All", "in", "out"])
        filter_layout.addWidget(QLabel("Direction:"))
        filter_layout.addWidget(self.direction_combo)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-7))
        filter_layout.addWidget(QLabel("From:"))
        filter_layout.addWidget(self.date_from)

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(QLabel("To:"))
        filter_layout.addWidget(self.date_to)

        self.filter_btn = ShadcnButton("Apply Filters", variant="default", size="sm")
        self.filter_btn.clicked.connect(self.refresh_logs)
        filter_layout.addWidget(self.filter_btn)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self.table = ShadcnDataTable(["ID", "Type", "Person ID", "Direction", "Time", "Granted", "Reason", "Verified By"])
        layout.addWidget(self.table)

    def refresh_logs(self):
        filters = {}
        if self.type_combo.currentText() != "All":
            filters['person_type'] = self.type_combo.currentText()
        if self.direction_combo.currentText() != "All":
            filters['direction'] = self.direction_combo.currentText()
        filters['date_from'] = self.date_from.date().toString("yyyy-MM-dd 00:00:00")
        filters['date_to'] = self.date_to.date().toString("yyyy-MM-dd 23:59:59")
        logs = self.data_service.get_access_logs(filters)
        data = []
        for log in logs:
            data.append((log[0], log[1], log[2], log[3], log[4], "Yes" if log[5] else "No", log[6], log[7]))
        self.table.populate(data)
