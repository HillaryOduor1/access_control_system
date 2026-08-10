import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QStackedWidget, QSizePolicy, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QColor
from pages.signin_form import SignInForm
from pages.signup_form import SignUpForm
from widgets.floating_label_input import FloatingLabelInput
from core.theme_manager import ThemeManager
from core.icon_manager import IconManager
from utils.path_utils import resource_path
import logging

class LoginPage(QWidget):
    login_successful = Signal(dict)

    def __init__(self, auth_manager=None, parent=None):
        super().__init__(parent)
        if auth_manager is None:
            from core.api_client import APIClient
            from database.db_manager import DatabaseManager
            from core.auth_manager import AuthManager
            self.auth_manager = AuthManager(APIClient(), DatabaseManager())
        else:
            self.auth_manager = auth_manager
        self.theme_manager = ThemeManager()
        self.icon_manager = IconManager()
        self.mode = "signin"

        self.init_ui()
        self.show_signin()
        self.apply_theme()
        self.theme_manager.theme_changed.connect(self.apply_theme)

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # LEFT PANEL
        self.left_panel = QFrame()
        self.left_panel.setObjectName("leftPanel")
        self.bg_label = QLabel(self.left_panel)
        self.bg_label.setScaledContents(True)
        self.set_background_image()

        # Overlay – keep original black gradient (works for both themes)
        self.overlay = QFrame(self.left_panel)
        self.overlay.setObjectName("overlay")
        self.overlay.setStyleSheet("""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(0,0,0,0.88),
                stop:1 rgba(0,0,0,0.78)
            );
            border: none;
        """)

        self.logo_label = QLabel(self.left_panel)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedSize(280, 120)
        self.logo_label.setStyleSheet("background: transparent; border: none;")

        self.left_text = QLabel(self.left_panel)
        self.left_text.setAlignment(Qt.AlignCenter)
        self.left_text.setWordWrap(True)
        self.left_text.setStyleSheet("font-size: 42px; font-weight: 800; line-height: 1.1; color: white; background: transparent; border: none;")

        self.left_subtitle = QLabel(self.left_panel)
        self.left_subtitle.setAlignment(Qt.AlignCenter)
        self.left_subtitle.setStyleSheet("font-size: 16px; font-weight: 400; color: rgba(255,255,255,0.85); background: transparent; border: none;")
        self.left_subtitle.setText("Access control system for ICT Authority")

        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setAlignment(Qt.AlignCenter)
        left_layout.setSpacing(16)
        left_layout.addStretch()
        left_layout.addWidget(self.logo_label, alignment=Qt.AlignCenter)
        left_layout.addWidget(self.left_text, alignment=Qt.AlignCenter)
        left_layout.addWidget(self.left_subtitle, alignment=Qt.AlignCenter)
        left_layout.addStretch()

        main_layout.addWidget(self.left_panel, 1)

        # RIGHT PANEL
        self.right_panel = QFrame()
        self.right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setAlignment(Qt.AlignCenter)
        right_layout.setContentsMargins(40, 40, 40, 40)

        self.form_container = QFrame(self.right_panel)
        self.form_container.setFixedWidth(480)
        self.form_container.setMinimumHeight(560)
        self.form_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.MinimumExpanding)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(15, 23, 42, 28))
        self.form_container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self.form_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Stack for signin/signup forms
        self.stack = QStackedWidget()
        self.signin_form = SignInForm(self.auth_manager)
        self.signin_form.login_successful.connect(self.login_successful.emit)
        self.signin_form.switch_to_signup.connect(self.switch_to_signup)

        self.signup_form = SignUpForm(self.auth_manager)
        self.signup_form.switch_to_signin.connect(self.switch_to_signin)

        self.stack.addWidget(self.signin_form)
        self.stack.addWidget(self.signup_form)

        container_layout.addWidget(self.stack)
        right_layout.addWidget(self.form_container, alignment=Qt.AlignCenter)

        main_layout.addWidget(self.right_panel, 1)

        self.left_text.setText("Welcome Back")
        self.update_logo()

    def set_background_image(self):
        image_path = resource_path("assets/images/icta1.jpg")
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            self.bg_label.setPixmap(pixmap.scaled(self.left_panel.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        else:
            logging.warning(f"Background image not found at: {image_path}")
            self.bg_label.setStyleSheet("background-color: #2c3e50; border: none;")

    def show_signin(self):
        self.mode = "signin"
        self.stack.setCurrentWidget(self.signin_form)
        self.left_text.setText("Welcome Back")

    def show_signup(self):
        self.mode = "signup"
        self.stack.setCurrentWidget(self.signup_form)
        self.left_text.setText("Join With Us")

    def switch_to_signup(self):
        if self.mode == "signin":
            self.show_signup()

    def switch_to_signin(self):
        if self.mode == "signup":
            self.show_signin()

    def update_logo(self):
        is_dark = self.theme_manager.get_current_theme() == "dark"
        logo_path = resource_path(f"assets/images/ictaLogo_{'dark' if is_dark else 'light'}.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            scaled = pixmap.scaled(self.logo_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(scaled)
        else:
            self.logo_label.setText("ICT AUTHORITY")
            self.logo_label.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background: transparent; border: none;")

    def apply_theme(self):
        tokens = self.theme_manager.get_tokens()
        is_dark = self.theme_manager.get_current_theme() == "dark"

        # RIGHT PANEL – use theme background
        right_bg = tokens.get('background', "#F8FAFC" if not is_dark else "#0B1220")
        self.right_panel.setStyleSheet(f"#rightPanel {{ background-color: {right_bg}; border: none; }}")

        # FORM CONTAINER
        form_bg = tokens.get('background', "#FFFFFF" if not is_dark else "#1E293B")
        form_border = tokens.get('border', "#E2E8F0" if not is_dark else "#334155")
        self.form_container.setStyleSheet(f"""
            QFrame {{
                background-color: {form_bg};
                border-radius: 20px;
                border: 1px solid {form_border};
            }}
        """)

        # Keep the overlay as is – no changes needed

        text_color = tokens.get('foreground', "#0F172A" if not is_dark else "#F8FAFC")
        subtext_color = tokens.get('muted-foreground', "#64748B" if not is_dark else "#94A3B8")
        hint_color = tokens.get('muted-foreground', "#94A3B8" if not is_dark else "#64748B")

        for lbl in self.findChildren(QLabel):
            role = lbl.property("textRole")
            if role == "title":
                lbl.setStyleSheet(
                    f"font-size: 26px; font-weight: 700; letter-spacing: -0.5px; "
                    f"background: transparent; border: none; color: {text_color};"
                )
            elif role == "subtitle":
                lbl.setStyleSheet(f"font-size: 13px; background: transparent; border: none; color: {subtext_color};")
            elif role == "hint":
                lbl.setStyleSheet(f"font-size: 11px; font-weight: 500; background: transparent; border: none; color: {hint_color};")

        self.update_logo()

        # Update floating inputs and icons
        for child in self.findChildren(FloatingLabelInput):
            child.update_icon()
            child.update_theme_colors()

        # Style the role dropdown in signup form (step 2)
        if hasattr(self.signup_form, 'signup_role'):
            self.signup_form.signup_role.setStyleSheet(f"""
                QComboBox#signupRoleCombo {{
                    background-color: {form_bg};
                    border: 1px solid {form_border};
                    border-radius: calc({tokens['radius']} - 2px);
                    padding: 8px 12px;
                    color: {text_color};
                    min-height: 30px;
                }}
                QComboBox#signupRoleCombo::drop-down {{
                    border: none;
                    width: 20px;
                }}
                QComboBox#signupRoleCombo::down-arrow {{
                    image: none;
                    border: none;
                    padding-right: 5px;
                    color: {text_color};
                }}
                QComboBox#signupRoleCombo QAbstractItemView {{
                    background-color: {form_bg};
                    color: {text_color};
                    border: 1px solid {form_border};
                    selection-background-color: {tokens['primary']};
                    selection-color: {tokens['primary-foreground']};
                }}
            """)
        # Style the role container in signup form
        role_container = self.signup_form.findChild(QWidget, "roleContainer")
        if role_container:
            role_container.setStyleSheet(f"""
                QWidget#roleContainer {{
                    background: {form_bg};
                    border: 1px solid {form_border};
                    border-radius: calc({tokens['radius']} - 2px);
                }}
            """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.bg_label.setGeometry(self.left_panel.rect())
        self.overlay.setGeometry(self.left_panel.rect())
        fw = self.form_container.width()
        fh = self.form_container.height()
        self.form_container.move((self.right_panel.width() - fw) // 2,
                                 (self.right_panel.height() - fh) // 2)

