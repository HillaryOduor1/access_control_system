# dialogs/export_data_dialog.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QPushButton, QFileDialog, QMessageBox
from database.db_manager import DatabaseManager
import csv, json

class ExportDataDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Export Data")
        self.setModal(True)
        self.setFixedSize(300, 150)
        layout = QVBoxLayout(self)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["visitors", "employees", "access_logs"])
        layout.addWidget(self.type_combo)
        self.export_btn = QPushButton("Export as CSV")
        self.export_btn.clicked.connect(self.export_csv)
        layout.addWidget(self.export_btn)
        self.export_json_btn = QPushButton("Export as JSON")
        self.export_json_btn.clicked.connect(self.export_json)
        layout.addWidget(self.export_json_btn)

    def export_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV (*.csv)")
        if not file_path: return
        data_type = self.type_combo.currentText()
        if data_type == "visitors":
            rows = self.db.get_visitor_history(limit=1000)
            headers = ["ID", "Name", "Check In", "Check Out", "Host ID", "Host Name", "Status"]
        elif data_type == "employees":
            rows = self.db.get_employees(active_only=False)
            headers = ["ID", "Employee ID", "Full Name", "Role", "Badge", "Active"]
        else:
            rows = self.db.get_access_logs()
            headers = ["ID", "Person Type", "Person ID", "Direction", "Timestamp", "Granted", "Reason", "Verified By"]
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        QMessageBox.information(self, "Export", "Export completed")

    def export_json(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save JSON", "", "JSON (*.json)")
        if not file_path: return
        data_type = self.type_combo.currentText()
        data = {}
        if data_type == "visitors":
            data["visitors"] = self.db.get_visitor_history(limit=1000)
        elif data_type == "employees":
            data["employees"] = self.db.get_employees(active_only=False)
        else:
            data["access_logs"] = self.db.get_access_logs()
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        QMessageBox.information(self, "Export", "Export completed")

  