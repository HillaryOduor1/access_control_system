# pages/access_logs_page.py
"""
Enterprise access logs page with filtering and export capabilities.

Changes in this revision
------------------------
- Error state uses ShadcnDataTable.set_error so the table shows an inline
  error instead of appearing empty.
- Status label uses the muted-foreground token, not a hardcoded hex.
- ID column is right-aligned.

Design notes
------------
The initial log fetch is deferred to showEvent() so the page constructor
never blocks the login → dashboard swap.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDateEdit, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QKeyEvent

from widgets.components import (
    ShadcnDataTable, ShadcnButton, ShadcnToast,
)
from core.theme_manager import ThemeManager
import csv
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class AccessLogsPage(QWidget):
    """Enterprise access logs page with filtering and export."""

    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service
        self.theme_manager = ThemeManager()
        self._last_logs = []
        self._initial_load_done = False
        self._is_refreshing = False
        self.init_ui()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_load_done:
            self._initial_load_done = True
            QTimer.singleShot(0, self.refresh_logs)

    def init_ui(self):
        tokens = self.theme_manager.get_tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)
        filter_layout.setContentsMargins(0, 0, 0, 0)

        filter_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.setAccessibleName("Person type filter")
        self.type_combo.addItems(["All", "visitor", "employee"])
        self.type_combo.setFixedWidth(100)
        filter_layout.addWidget(self.type_combo)

        filter_layout.addSpacing(8)

        filter_layout.addWidget(QLabel("Direction:"))
        self.direction_combo = QComboBox()
        self.direction_combo.setAccessibleName("Direction filter")
        self.direction_combo.addItems(["All", "in", "out"])
        self.direction_combo.setFixedWidth(80)
        filter_layout.addWidget(self.direction_combo)

        filter_layout.addSpacing(8)

        filter_layout.addWidget(QLabel("From:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-7))
        self.date_from.setFixedWidth(110)
        self.date_from.setAccessibleName("From date")
        filter_layout.addWidget(self.date_from)

        filter_layout.addWidget(QLabel("To:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setFixedWidth(110)
        self.date_to.setAccessibleName("To date")
        filter_layout.addWidget(self.date_to)

        filter_layout.addSpacing(8)

        self.filter_btn = ShadcnButton("Apply Filters", variant="default",
                                       size="sm")
        self.filter_btn.clicked.connect(self.refresh_logs)
        self.filter_btn.setMinimumWidth(100)
        filter_layout.addWidget(self.filter_btn)

        filter_layout.addStretch()

        self.export_btn = ShadcnButton("Export CSV", variant="outline",
                                       size="sm")
        self.export_btn.clicked.connect(self.export_csv)
        self.export_btn.setMinimumWidth(100)
        filter_layout.addWidget(self.export_btn)

        refresh_btn = ShadcnButton("Refresh", variant="outline", size="sm")
        refresh_btn.setToolTip("Reload logs (Ctrl+R)")
        refresh_btn.clicked.connect(self.refresh_logs)
        refresh_btn.setMinimumWidth(80)
        filter_layout.addWidget(refresh_btn)

        layout.addLayout(filter_layout)

        self.table = ShadcnDataTable(
            ["ID", "Type", "Person ID", "Direction",
             "Time", "Granted", "Reason", "Verified By"],
            numeric_columns=[0, 2],
            empty_message="No access logs match the current filters.",
        )
        layout.addWidget(self.table)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {tokens['muted-foreground']}; "
            f"font-size: {tokens['font.caption']}px; padding: 4px 0; "
            "background: transparent;"
        )
        layout.addWidget(self.status_label)

    def refresh_logs(self):
        if self._is_refreshing:
            return

        date_from = self.date_from.date()
        date_to = self.date_to.date()

        if date_from > date_to:
            ShadcnToast("Error",
                        description="Start date must be before end date",
                        parent=self, variant="destructive")
            return

        self._is_refreshing = True
        try:
            filters = {}
            if self.type_combo.currentText() != "All":
                filters['person_type'] = self.type_combo.currentText()
            if self.direction_combo.currentText() != "All":
                filters['direction'] = self.direction_combo.currentText()
            filters['date_from'] = date_from.toString("yyyy-MM-dd 00:00:00")
            filters['date_to'] = date_to.toString("yyyy-MM-dd 23:59:59")

            self._last_logs = self.data_service.get_access_logs(filters)

            data = []
            for log in self._last_logs:
                data.append((
                    str(log[0]),
                    log[1] or "",
                    str(log[2]) if log[2] else "",
                    log[3] or "",
                    log[4] or "",
                    "✓" if log[5] else "✗",
                    log[6] or "",
                    log[7] or "",
                ))

            self.table.populate(data)
            self.status_label.setText(f"Showing {len(data)} records")

        except Exception as e:
            logger.error(f"Error refreshing logs: {e}")
            self.table.set_error(
                "Could not load access logs. Click Refresh to retry."
            )
            self.status_label.setText("Error loading logs")
            ShadcnToast("Error", description=f"Failed to load logs: {e}",
                        parent=self, variant="destructive")
        finally:
            self._is_refreshing = False

    def export_csv(self):
        if not self._last_logs:
            ShadcnToast("Info", description="No data to export", parent=self)
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Logs",
            f"access_logs_{datetime.now().strftime('%Y%m%d')}.csv",
            "CSV Files (*.csv)",
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "ID", "Person Type", "Person ID", "Direction",
                    "Timestamp", "Granted", "Reason", "Verified By",
                ])
                for log in self._last_logs:
                    writer.writerow([
                        log[0], log[1], log[2], log[3],
                        log[4], "Yes" if log[5] else "No", log[6], log[7],
                    ])
            ShadcnToast("Success",
                        description=f"Exported {len(self._last_logs)} records",
                        parent=self, variant="success")
        except Exception as e:
            logger.error(f"Export error: {e}")
            ShadcnToast("Error", description=f"Failed to export: {e}",
                        parent=self, variant="destructive")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_R and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.refresh_logs()
            event.accept()
            return
        if event.key() == Qt.Key.Key_E and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.export_csv()
            event.accept()
            return
        super().keyPressEvent(event)
