from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, 
                               QDialogButtonBox, QMessageBox)
from PySide6.QtCore import Qt

class ChangePasswordDialog(QDialog):
    def __init__(self, user_id, data_service, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.data_service = data_service
        self.setWindowTitle("Change Password")
        self.setModal(True)
        self.setFixedWidth(400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        title = QLabel("Change Password")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        self.current_pass = QLineEdit()
        self.current_pass.setPlaceholderText("Current Password")
        self.current_pass.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.current_pass)

        self.new_pass = QLineEdit()
        self.new_pass.setPlaceholderText("New Password")
        self.new_pass.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.new_pass)

        self.confirm_pass = QLineEdit()
        self.confirm_pass.setPlaceholderText("Confirm New Password")
        self.confirm_pass.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.confirm_pass)

        requirements = QLabel(
            "Password must:\n"
            "• Be at least 8 characters long\n"
            "• Contain at least one uppercase letter\n"
            "• Contain at least one number\n"
            "• Contain at least one special character"
        )
        requirements.setStyleSheet("color: #64748B; font-size: 11px; padding: 5px; background-color: #F8FAFC; border-radius: 5px;")
        layout.addWidget(requirements)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.change_password)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.setLayout(layout)

    def validate_password(self, password):
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"
        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one number"
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            return False, "Password must contain at least one special character"
        return True, ""

    def change_password(self):
        current = self.current_pass.text()
        new = self.new_pass.text()
        confirm = self.confirm_pass.text()

        if not current or not new or not confirm:
            QMessageBox.warning(self, "Error", "Please fill in all fields")
            return
        if new != confirm:
            QMessageBox.warning(self, "Error", "New passwords do not match")
            return
        valid, message = self.validate_password(new)
        if not valid:
            QMessageBox.warning(self, "Weak Password", message)
            return

        success, msg = self.data_service.change_password(self.user_id, current, new)
        if success:
            QMessageBox.information(self, "Success", msg)
            self.accept()
        else:
            QMessageBox.critical(self, "Error", msg)

