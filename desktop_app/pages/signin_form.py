from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QIcon
from widgets.components import ShadcnButton, ShadcnToast, ShadcnCheckBox
from widgets.floating_label_input import FloatingLabelInput
from core.icon_manager import IconManager


class SignInForm(QWidget):
    login_successful = Signal(dict)
    switch_to_signup = Signal()

    def __init__(self, auth_manager, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager
        self.icon_manager = IconManager()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(18)
        layout.setContentsMargins(48, 48, 48, 36)

        header = QVBoxLayout()
        header.setSpacing(6)
        title = QLabel("Sign in")
        title.setAlignment(Qt.AlignCenter)
        title.setProperty("textRole", "title")
        title.setStyleSheet("background: transparent; border: none;")
        subtitle = QLabel("Welcome back! Enter your details to continue.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setProperty("textRole", "subtitle")
        subtitle.setStyleSheet("background: transparent; border: none;")
        header.addWidget(title)
        header.addWidget(subtitle)
        layout.addLayout(header)
        layout.addSpacing(8)

        self.login_username = FloatingLabelInput("Username or email", icon_name="user")
        layout.addWidget(self.login_username)

        self.login_password = FloatingLabelInput("Password", icon_name="lock", password=True)
        layout.addWidget(self.login_password)

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(2, 0, 2, 0)
        # Use ShadcnCheckBox for theme‑aware styling
        self.remember_checkbox = ShadcnCheckBox("Remember me")
        row_layout.addWidget(self.remember_checkbox)
        row_layout.addStretch()
        self.forgot_btn = ShadcnButton("Forgot password?", variant="link", size="sm")
        self.forgot_btn.clicked.connect(self.forgot_password)
        row_layout.addWidget(self.forgot_btn)
        layout.addLayout(row_layout)
        layout.addSpacing(4)

        self.login_btn = ShadcnButton("Sign in", variant="default", size="lg")
        self.login_btn.setMinimumHeight(50)
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.clicked.connect(self.animate_login)
        self.login_btn.setStyleSheet(self.login_btn.styleSheet() + """
            QPushButton {
                border-radius: 12px;
                font-weight: 600;
                font-size: 14px;
                text-align: center;
            }
        """)
        layout.addWidget(self.login_btn)
        layout.addStretch()

        self.signup_toggle = ShadcnButton("Don't have an account? Sign up", variant="link", size="sm")
        self.signup_toggle.clicked.connect(self.switch_to_signup.emit)
        layout.addWidget(self.signup_toggle, alignment=Qt.AlignCenter)

    def validate_signin(self):
        valid = True
        username = self.login_username.text().strip()
        password = self.login_password.text().strip()
        if not username:
            self.login_username.set_valid(False, "Username or email is required")
            valid = False
        else:
            self.login_username.set_valid(True)
        if not password:
            self.login_password.set_valid(False, "Password is required")
            valid = False
        else:
            self.login_password.set_valid(True)
        return valid

    def animate_login(self):
        if not self.validate_signin():
            return
        self.login_btn.setText("")
        spinner = QLabel()
        spinner_icon = self.icon_manager.get_icon("loading", size=QSize(22, 22), state="default")
        spinner.setPixmap(spinner_icon.pixmap(22, 22))
        self.login_btn.setIcon(spinner.pixmap())
        self.login_btn.setEnabled(False)
        QTimer.singleShot(100, self.process_login)

    def process_login(self):
        username = self.login_username.text().strip()
        password = self.login_password.text().strip()
        success = self.auth_manager.login(username, password)
        if success:
            user_data = self.auth_manager.current_user
            user_info = {
                'id': user_data.get('id'),
                'username': user_data.get('username'),
                'full_name': user_data.get('full_name', username),
                'email': user_data.get('email', ''),
                'role': 'staff'
            }
            self.login_successful.emit(user_info)
        else:
            ShadcnToast("Login failed", "Invalid username or password", duration=2000, parent=self)
            self.login_password.set_valid(False, "Invalid credentials")
            self.login_btn.setText("Sign in")
            self.login_btn.setIcon(QIcon())
            self.login_btn.setEnabled(True)

    def forgot_password(self):
        """Open the password reset dialog."""
        from dialogs.reset_password_dialog import ResetPasswordDialog
        dialog = ResetPasswordDialog(self.auth_manager.api, None)  # Pass None as parent to avoid double rendering
        
        # Center the dialog on screen
        screen_geometry = self.screen().availableGeometry()
        x = (screen_geometry.width() - dialog.width()) // 2
        y = (screen_geometry.height() - dialog.height()) // 2
        dialog.move(x, y)
        
        dialog.exec()
        dialog.deleteLater()  # Clean up after closing

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.animate_login()
        super().keyPressEvent(event)
