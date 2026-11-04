# dialogs/export_data_dialog.py
"""
Data export dialog with theme awareness and error handling.

Changes in this revision
------------------------
- Uses ShadcnComboBox, ShadcnButton, ShadcnToast.
- Wraps file writes in try/except and reports failures as toasts.
- Minimum width instead of fixed size.
- Accessible names on all interactive controls.
"""
import csv
import json

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog
)
from PySide6.QtCore import Qt, QTimer

from widgets.components import (
    ShadcnButton, ShadcnComboBox, ShadcnToast, ShadcnCaption,
)
from core.theme_manager import ThemeManager


class ExportDataDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.theme_manager = ThemeManager()

        self.setWindowTitle("Export Data")
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setAccessibleName("Export data")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        layout.addWidget(QLabel("Select a dataset to export:"))

        self.type_combo = ShadcnComboBox()
        self.type_combo.addItems(["visitors", "employees", "access_logs"])
        self.type_combo.setAccessibleName("Dataset")
        layout.addWidget(self.type_combo)

        layout.addWidget(ShadcnCaption(
            "Files are written to the location you choose. Existing files "
            "with the same name will be overwritten."
        ))

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.export_csv_btn = ShadcnButton("Export as CSV", variant="outline")
        self.export_csv_btn.clicked.connect(self.export_csv)
        btn_layout.addWidget(self.export_csv_btn)

        self.export_json_btn = ShadcnButton("Export as JSON", variant="outline")
        self.export_json_btn.clicked.connect(self.export_json)
        btn_layout.addWidget(self.export_json_btn)

        layout.addLayout(btn_layout)

        cancel_row = QHBoxLayout()
        cancel_row.addStretch()
        cancel_btn = ShadcnButton("Close", variant="ghost", size="sm")
        cancel_btn.clicked.connect(self.reject)
        cancel_row.addWidget(cancel_btn)
        layout.addLayout(cancel_row)

        QTimer.singleShot(0, self.export_csv_btn.setFocus)

    # ------------------------------------------------------------------

    def _fetch(self, data_type):
        if data_type == "visitors":
            return (
                self.db.get_visitor_history(limit=1000),
                ["ID", "Name", "Check In", "Check Out",
                 "Host ID", "Host Name", "Status"],
            )
        if data_type == "employees":
            return (
                self.db.get_employees(active_only=False),
                ["ID", "Employee ID", "Full Name", "Role", "Badge", "Active"],
            )
        return (
            self.db.get_access_logs(),
            ["ID", "Person Type", "Person ID", "Direction",
             "Timestamp", "Granted", "Reason", "Verified By"],
        )

    def export_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", "", "CSV (*.csv)"
        )
        if not file_path:
            return

        data_type = self.type_combo.currentText()
        try:
            rows, headers = self._fetch(data_type)
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
        except Exception as e:
            ShadcnToast(
                "Export failed",
                description=str(e),
                variant="destructive",
                parent=self,
            )
            return

        ShadcnToast(
            "Export complete",
            description=f"{len(rows)} records written to {file_path}",
            variant="success",
            parent=self,
        )

    def export_json(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save JSON", "", "JSON (*.json)"
        )
        if not file_path:
            return

        data_type = self.type_combo.currentText()
        try:
            rows, _ = self._fetch(data_type)
            payload = {data_type: rows}
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
        except Exception as e:
            ShadcnToast(
                "Export failed",
                description=str(e),
                variant="destructive",
                parent=self,
            )
            return

        ShadcnToast(
            "Export complete",
            description=f"{len(rows)} records written to {file_path}",
            variant="success",
            parent=self,
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)
