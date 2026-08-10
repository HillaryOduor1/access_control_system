import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QStackedWidget
)
from PySide6.QtCore import Qt, Signal
from widgets.components import ShadcnButton, ShadcnToast
from widgets.floating_label_input import FloatingLabelInput
from widgets.password_strength_meter import PasswordStrengthMeter

class SignUpForm(QWidget):
    switch_to_signin = Signal()

    def __init__(self, auth_manager, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager
        self.data = {}  # store form data
        self.current_step = 0
        self.init_ui()
        self.show_step(0)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(48, 48, 48, 36)

        # Header (common for all steps)
        header_layout = QVBoxLayout()
        header_layout.setSpacing(6)
        self.title = QLabel("Create account")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setProperty("textRole", "title")
        self.title.setStyleSheet("background: transparent; border: none;")
        self.subtitle = QLabel("Fill in your details to get started.")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setProperty("textRole", "subtitle")
        self.subtitle.setStyleSheet("background: transparent; border: none;")
        header_layout.addWidget(self.title)
        header_layout.addWidget(self.subtitle)
        layout.addLayout(header_layout)

        # Stack for steps
        self.stack = QStackedWidget()
        self.step1 = self._create_step1()
        self.step2 = self._create_step2()
        self.step3 = self._create_step3()
        self.stack.addWidget(self.step1)
        self.stack.addWidget(self.step2)
        self.stack.addWidget(self.step3)
        layout.addWidget(self.stack, 1)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.back_btn = ShadcnButton("Back", variant="outline", size="sm")
        self.back_btn.clicked.connect(self.go_back)
        self.next_btn = ShadcnButton("Next", variant="default", size="sm")
        self.next_btn.clicked.connect(self.go_next)
        nav_layout.addStretch()
        nav_layout.addWidget(self.back_btn)
        nav_layout.addWidget(self.next_btn)
        layout.addLayout(nav_layout)

        # Sign in toggle (at bottom)
        self.signin_toggle = ShadcnButton("Already have an account? Sign in", variant="link", size="sm")
        self.signin_toggle.clicked.connect(self.switch_to_signin.emit)
        layout.addWidget(self.signin_toggle, alignment=Qt.AlignCenter)

    def _create_step1(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)

        self.first_name = FloatingLabelInput("First Name", icon_name="user")
        layout.addWidget(self.first_name)

        self.last_name = FloatingLabelInput("Last Name", icon_name="user")
        layout.addWidget(self.last_name)

        self.email = FloatingLabelInput("Email", icon_name="email")
        layout.addWidget(self.email)

        self.employee_number = FloatingLabelInput("Employee Number (optional)", icon_name="badge")
        layout.addWidget(self.employee_number)

        self.phone = FloatingLabelInput("Phone Number (optional)", icon_name="phone")
        layout.addWidget(self.phone)

        self.id_number = FloatingLabelInput("ID Number (optional)", icon_name="id")
        layout.addWidget(self.id_number)

        layout.addStretch()
        return widget

    def _create_step2(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)

        self.organisation = FloatingLabelInput("Organisation *", icon_name="building")
        layout.addWidget(self.organisation)

        # Role dropdown with consistent styling
        role_container = QWidget()
        role_container.setObjectName("roleContainer")
        role_container.setFixedHeight(72)
        role_layout = QHBoxLayout(role_container)
        role_layout.setContentsMargins(12, 8, 12, 8)
        role_layout.setSpacing(8)
        role_label = QLabel("Role")
        role_label.setProperty("textRole", "hint")
        role_label.setStyleSheet("background: transparent; border: none;")
        self.signup_role = QComboBox()
        self.signup_role.setObjectName("signupRoleCombo")
        self.signup_role.addItems(['staff', 'security', 'finance', 'admin'])
        role_layout.addWidget(role_label)
        role_layout.addWidget(self.signup_role, 1)
        layout.addWidget(role_container)

        layout.addStretch()
        return widget

    def _create_step3(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)

        self.password = FloatingLabelInput("Password", icon_name="lock", password=True)
        layout.addWidget(self.password)

        strength_layout = QVBoxLayout()
        strength_layout.setSpacing(6)
        strength_layout.setContentsMargins(2, 0, 2, 4)
        self.strength_meter = PasswordStrengthMeter()
        self.strength_label = QLabel("Password strength")
        self.strength_label.setProperty("textRole", "hint")
        self.strength_label.setStyleSheet("background: transparent; border: none;")
        strength_layout.addWidget(self.strength_meter)
        strength_layout.addWidget(self.strength_label)
        layout.addLayout(strength_layout)

        self.password.textChanged.connect(self.strength_meter.evaluate)
        self.password.textChanged.connect(self._on_password_changed)
        self.strength_meter.strengthChanged.connect(self._update_strength_label)

        self.confirm_password = FloatingLabelInput("Confirm Password", icon_name="lock", password=True)
        layout.addWidget(self.confirm_password)
        self.confirm_password.textChanged.connect(self._check_password_match)
        self.confirm_password.focusLost.connect(self._check_password_match)

        layout.addStretch()
        return widget

    def _on_password_changed(self, _text):
        if self.confirm_password.text():
            self._check_password_match()

    def _check_password_match(self):
        password = self.password.text()
        confirm = self.confirm_password.text()
        if not confirm:
            self.confirm_password.set_valid(True, "", shake=False)
            return
        if password == confirm:
            self.confirm_password.set_valid(True, "", shake=False)
        else:
            self.confirm_password.set_valid(False, "Passwords do not match", shake=False)

    def _update_strength_label(self, score):
        tokens = self.auth_manager.theme_manager.get_tokens()
        if not self.password.text():
            self.strength_label.setText("Password strength")
            self.strength_label.setStyleSheet(
                f"font-size: 11px; font-weight: 500; color: {tokens.get('muted-foreground', '#94A3B8')}; border: none; background: transparent;"
            )
            return
        if score <= 2:
            text, color = "Weak", tokens.get('error', '#EF4444')
        elif score <= 4:
            text, color = "Medium", tokens.get('warning', '#F59E0B')
        else:
            text, color = "Strong", tokens.get('success', '#10B981')
        self.strength_label.setText(f"Password strength · {text}")
        self.strength_label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {color}; border: none; background: transparent;")

    def show_step(self, index):
        self.current_step = index
        self.stack.setCurrentIndex(index)
        self.back_btn.setVisible(index > 0)
        if index == 2:  # last step
            self.next_btn.setText("Create Account")
            self.next_btn.clicked.disconnect()
            self.next_btn.clicked.connect(self.submit)
        else:
            self.next_btn.setText("Next")
            self.next_btn.clicked.disconnect()
            self.next_btn.clicked.connect(self.go_next)

    def go_back(self):
        if self.current_step > 0:
            self.show_step(self.current_step - 1)

    def go_next(self):
        if self.current_step == 0:
            # validate step 1
            if not self.first_name.text().strip():
                ShadcnToast("Error", "First Name is required", parent=self)
                return
            if not self.last_name.text().strip():
                ShadcnToast("Error", "Last Name is required", parent=self)
                return
            email = self.email.text().strip()
            email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not email or not re.match(email_regex, email):
                ShadcnToast("Error", "Valid email is required", parent=self)
                return
            # store data
            self.data['first_name'] = self.first_name.text().strip()
            self.data['last_name'] = self.last_name.text().strip()
            self.data['email'] = email
            self.data['employee_number'] = self.employee_number.text().strip()
            self.data['phone'] = self.phone.text().strip()
            self.data['id_number'] = self.id_number.text().strip()
            self.show_step(1)
        elif self.current_step == 1:
            # validate step 2
            organisation = self.organisation.text().strip()
            if not organisation:
                ShadcnToast("Error", "Organisation is required", parent=self)
                return
            self.data['tenant_id'] = organisation
            self.data['role'] = self.signup_role.currentText()
            self.show_step(2)

    def submit(self):
        # Validate password
        password = self.password.text()
        confirm = self.confirm_password.text()
        if not password:
            ShadcnToast("Error", "Password is required", parent=self)
            return
        if len(password) < 8:
            ShadcnToast("Error", "Password must be at least 8 characters", parent=self)
            return
        if not re.search(r'[A-Z]', password):
            ShadcnToast("Error", "Password must contain at least one uppercase letter", parent=self)
            return
        if not re.search(r'[a-z]', password):
            ShadcnToast("Error", "Password must contain at least one lowercase letter", parent=self)
            return
        if not re.search(r'[0-9]', password):
            ShadcnToast("Error", "Password must contain at least one number", parent=self)
            return
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            ShadcnToast("Error", "Password must contain at least one special character", parent=self)
            return
        if password != confirm:
            ShadcnToast("Error", "Passwords do not match", parent=self)
            return
        self.data['password'] = password

        # Build payload
        payload = {
            "username": self.data['email'],  # use email as username
            "email": self.data['email'],
            "first_name": self.data['first_name'],
            "last_name": self.data['last_name'],
            "full_name": f"{self.data['first_name']} {self.data['last_name']}",
            "employee_number": self.data.get('employee_number', ''),
            "phone": self.data.get('phone', ''),
            "id_number": self.data.get('id_number', ''),
            "tenant_id": self.data['tenant_id'],
            "roles": [self.data['role']],
            "password": password
        }

        try:
            self.auth_manager.api.request("POST", "/users", json=payload, need_auth=False)
            ShadcnToast("Success", "Account created! Please sign in.", duration=3000, parent=self)
            self.switch_to_signin.emit()
        except Exception as e:
            error_msg = str(e)
            if "409" in error_msg or "already exists" in error_msg:
                ShadcnToast("Error", "Username or email already taken.", parent=self)
            else:
                ShadcnToast("Error", f"Sign up failed: {error_msg}", parent=self)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.current_step == 2:
                self.submit()
            else:
                self.go_next()
        super().keyPressEvent(event)
