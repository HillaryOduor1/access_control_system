from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QDialog,
                               QFormLayout, QComboBox, QCheckBox, QTableWidgetItem,
                               QPushButton, QLineEdit, QMessageBox)
from PySide6.QtCore import Qt, Signal
from widgets.components import ShadcnDataTable, ShadcnButton, ShadcnInput, ShadcnToast
from core.data_service import DataService

class UserManagementPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service: DataService):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service
        self.init_ui()
        self.refresh_users()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        toolbar = QHBoxLayout()
        self.add_btn = ShadcnButton("Create User", variant="default")
        self.add_btn.clicked.connect(self.create_user)
        toolbar.addWidget(self.add_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = ShadcnDataTable(["ID", "Username", "Full Name", "Email", "Roles", "Active", "Actions"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(6, 150)
        layout.addWidget(self.table)

    def refresh_users(self):
        try:
            users = self.data_service.get_users()
            self.table.setRowCount(len(users))
            for row, u in enumerate(users):
                self.table.setItem(row, 0, QTableWidgetItem(u.get('id', '')))
                self.table.setItem(row, 1, QTableWidgetItem(u.get('username', '')))
                self.table.setItem(row, 2, QTableWidgetItem(u.get('full_name', '')))
                self.table.setItem(row, 3, QTableWidgetItem(u.get('email', '')))
                self.table.setItem(row, 4, QTableWidgetItem(', '.join(u.get('roles', []))))
                self.table.setItem(row, 5, QTableWidgetItem("Yes" if u.get('is_active') else "No"))

                btn_widget = QWidget()
                btn_layout = QHBoxLayout(btn_widget)
                btn_layout.setContentsMargins(0, 0, 0, 0)
                edit_btn = ShadcnButton("Edit", variant="outline", size="sm")
                edit_btn.clicked.connect(lambda _, uid=u['id']: self.edit_user(uid))
                deactivate_btn = ShadcnButton("Deactivate", variant="destructive", size="sm")
                deactivate_btn.clicked.connect(lambda _, uid=u['id']: self.deactivate_user(uid))
                btn_layout.addWidget(edit_btn)
                btn_layout.addWidget(deactivate_btn)
                self.table.setCellWidget(row, 6, btn_widget)
        except Exception as e:
            ShadcnToast("Error", f"Failed to load users: {str(e)}", parent=self)
            self.table.setRowCount(0)

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
            ShadcnToast("Error", f"Failed to load user: {str(e)}", parent=self)

    def deactivate_user(self, user_id):
        from widgets.components import ShadcnAlertDialog
        if ShadcnAlertDialog("Confirm", "Deactivate this user?", parent=self).exec() == QDialog.DialogCode.Accepted:
            try:
                self.data_service.deactivate_user(user_id)
                ShadcnToast("Success", "User deactivated", parent=self)
                self.refresh_users()
            except Exception as e:
                ShadcnToast("Error", f"Failed to deactivate user: {str(e)}", parent=self)


class UserDialog(QDialog):
    def __init__(self, data_service, user_data, parent=None):
        super().__init__(parent)
        self.data_service = data_service
        self.user_data = user_data
        self.setWindowTitle("Create User" if not user_data else "Edit User")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.username_input = ShadcnInput()
        self.full_name_input = ShadcnInput()
        self.email_input = ShadcnInput()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Leave blank to keep current")
        self.role_combo = QComboBox()
        self.role_combo.addItems(['staff', 'security', 'finance', 'admin'])
        self.active_check = QCheckBox("Active")
        self.active_check.setChecked(True)

        form.addRow("Username *", self.username_input)
        form.addRow("Full Name", self.full_name_input)
        form.addRow("Email", self.email_input)
        form.addRow("Password", self.password_input)
        form.addRow("Role", self.role_combo)
        form.addRow(self.active_check)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        cancel_btn = ShadcnButton("Cancel", variant="outline")
        cancel_btn.clicked.connect(self.reject)
        save_btn = ShadcnButton("Save", variant="default")
        save_btn.clicked.connect(self.save)
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(save_btn)
        layout.addLayout(btn_box)

        if self.user_data:
            self.username_input.setText(self.user_data.get('username', ''))
            self.full_name_input.setText(self.user_data.get('full_name', ''))
            self.email_input.setText(self.user_data.get('email', ''))
            self.role_combo.setCurrentText(self.user_data.get('roles', ['staff'])[0])
            self.active_check.setChecked(self.user_data.get('is_active', True))

    def save(self):
        username = self.username_input.text().strip()
        full_name = self.full_name_input.text().strip()
        email = self.email_input.text().strip()
        password = self.password_input.text()
        role = self.role_combo.currentText()
        is_active = self.active_check.isChecked()

        if not username:
            ShadcnToast("Error", "Username is required", parent=self)
            return

        payload = {
            "username": username,
            "full_name": full_name,
            "email": email,
            "roles": [role],
            "is_active": is_active
        }
        if password:
            payload["password"] = password

        try:
            if self.user_data:
                self.data_service.update_user(self.user_data['id'], payload)
            else:
                self.data_service.create_user(payload)
            ShadcnToast("Success", "User saved", parent=self)
            self.accept()
        except Exception as e:
            ShadcnToast("Error", f"Failed to save user: {str(e)}", parent=self)

