from PySide6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QFormLayout, QSpinBox, QCheckBox, QDialog
from PySide6.QtCore import Signal
from database.db_manager import DatabaseManager
from config import Config
from widgets.components import ShadcnButton, ShadcnToast, ShadcnAlertDialog

class SettingsPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service=None):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service  # not used yet, but consistent with other pages
        self.db = DatabaseManager()       # keep local for now
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # GDPR Retention
        gdpr_group = QGroupBox("GDPR Data Retention")
        gdpr_layout = QFormLayout(gdpr_group)
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 365)
        self.retention_spin.setValue(Config.VISITOR_RETENTION_DAYS)
        self.retention_spin.setSuffix(" days")
        gdpr_layout.addRow("Visitor data retention:", self.retention_spin)
        save_btn = ShadcnButton("Save Retention Policy", variant="default")
        save_btn.clicked.connect(self.save_retention)
        gdpr_layout.addRow(save_btn)
        layout.addWidget(gdpr_group)

        # System options
        sys_group = QGroupBox("System Options")
        sys_layout = QFormLayout(sys_group)
        self.auto_sync = QCheckBox("Auto-sync every 5 minutes")
        self.auto_sync.setChecked(True)
        sys_layout.addRow(self.auto_sync)
        layout.addWidget(sys_group)

        # Danger zone (admin only)
        if 'admin' in self.user_info.get('role', ''):
            danger_group = QGroupBox("Danger Zone")
            danger_layout = QVBoxLayout(danger_group)
            purge_btn = ShadcnButton("Purge All Expired Visitor Records", variant="destructive")
            purge_btn.clicked.connect(self.purge_expired)
            danger_layout.addWidget(purge_btn)
            layout.addWidget(danger_group)

        layout.addStretch()

    def save_retention(self):
        Config.VISITOR_RETENTION_DAYS = self.retention_spin.value()
        ShadcnToast("Saved", f"Retention period updated to {self.retention_spin.value()} days", parent=self)

    def purge_expired(self):
        if ShadcnAlertDialog("Confirm Purge", "Delete all expired visitor records? This cannot be undone.",
                             action_text="Purge", parent=self).exec() == QDialog.DialogCode.Accepted:
            self.db.purge_expired_visitors()
            ShadcnToast("Purge Complete", "Expired records deleted.", parent=self)

