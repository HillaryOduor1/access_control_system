# dialogs/forgot_password_dialog.py
"""
Legacy/Simple forgot password dialog - redirects to the new reset password dialog.
"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
from dialogs.reset_password_dialog import ResetPasswordDialog

class ForgotPasswordDialog(QDialog):
    """Simple redirect dialog to the full reset flow."""
    
    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.setWindowTitle("Reset Password")
        self.setModal(True)
        self.setFixedWidth(350)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        layout.addWidget(QLabel("You will be redirected to the password reset wizard."))
        
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)
        
        continue_btn = QPushButton("Continue to Reset Password")
        continue_btn.setStyleSheet("""
            QPushButton {
                background: #0EA5E9;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #0284C7;
            }
        """)
        continue_btn.clicked.connect(self.open_reset_dialog)
        btn_layout.addWidget(continue_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748B;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 10px;
            }
            QPushButton:hover {
                background: #F1F5F9;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def open_reset_dialog(self):
        """Open the full reset password dialog."""
        self.accept()
        dialog = ResetPasswordDialog(self.api_client, self.parent())
        dialog.exec()

