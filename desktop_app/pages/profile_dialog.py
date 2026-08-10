# pages/profile_dialog.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLabel
from PySide6.QtCore import Qt
from widgets.components import ShadcnInput, ShadcnButton, ShadcnToast

class ProfileDialog(QDialog):
    def __init__(self, user_info, data_service, parent=None):
        super().__init__(parent)
        self.user_info = user_info
        self.data_service = data_service
        self.setWindowTitle("Profile Settings")
        self.setModal(True)
        self.setFixedWidth(500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        title = QLabel("Profile Settings")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        form_layout = QFormLayout()
        form_layout.setSpacing(15)

        username_label = QLabel(self.user_info.get('username', ''))
        username_label.setStyleSheet("padding: 8px; background-color: #F1F5F9; border-radius: 6px;")
        form_layout.addRow("Username:", username_label)

        self.full_name_input = ShadcnInput()
        self.full_name_input.setText(self.user_info.get('full_name', ''))
        form_layout.addRow("Full Name:", self.full_name_input)

        self.email_input = ShadcnInput()
        self.email_input.setText(self.user_info.get('email', ''))
        form_layout.addRow("Email:", self.email_input)

        role_label = QLabel(self.user_info.get('role', 'Staff').title())
        role_label.setStyleSheet("padding: 8px; background-color: #F1F5F9; border-radius: 6px;")
        form_layout.addRow("Role:", role_label)

        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        cancel_btn = ShadcnButton("Cancel", variant="outline")
        cancel_btn.clicked.connect(self.reject)
        save_btn = ShadcnButton("Save Changes", variant="default")
        save_btn.clicked.connect(self.save_profile)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def save_profile(self):
        full_name = self.full_name_input.text().strip()
        email = self.email_input.text().strip()
        success, msg = self.data_service.update_profile(self.user_info.get('id'), full_name, email)
        if success:
            ShadcnToast("Profile", msg, parent=self)
            self.accept()
        else:
            ShadcnToast("Error", msg, parent=self)
