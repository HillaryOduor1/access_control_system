# dialogs/reset_password_dialog.py
# dialogs/reset_password_dialog.py
"""
Enterprise-grade password reset dialog with OTP verification.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QStackedWidget, QFrame,
    QSpacerItem, QSizePolicy, QGridLayout
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QFont, QColor
from widgets.components import (
    ShadcnButton, ShadcnInput, ShadcnToast, ShadcnHeading,
    ShadcnCaption, ShadcnSeparator, ShadcnAlert
)
from widgets.floating_label_input import FloatingLabelInput
from core.icon_manager import IconManager
from core.theme_manager import ThemeManager
import re
import logging

logger = logging.getLogger(__name__)

class ResetPasswordDialog(QDialog):
    """Compact password reset dialog with OTP verification."""
    
    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.username = ""
        self.reset_token = ""
        self.otp = ""
        self.resend_timer = None
        self.countdown = 0
        self.current_step = 0
        
        # Initialize managers
        self.theme_manager = ThemeManager()
        self.icon_manager = IconManager()
        
        self.setWindowTitle("Reset Password")
        self.setModal(True)
        self.setFixedSize(480, 480)
        # Use standard dialog with system title bar
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        # Remove help button
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        self.init_ui()
        self.show_step(0)
        self.apply_theme()
        self.theme_manager.theme_changed.connect(self.apply_theme)
        
    def init_ui(self):
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Container
        container = QFrame()
        container.setObjectName("resetDialogContainer")
        self.container = container
        
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # ── HEADER ──
        header = QFrame()
        header.setObjectName("dialogHeader")
        header.setFixedHeight(72)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 16, 24, 16)
        header_layout.setSpacing(12)
        
        # Icon
        icon_container = QLabel()
        icon_container.setFixedSize(40, 40)
        icon_container.setAlignment(Qt.AlignCenter)
        icon_pixmap = self.icon_manager.get_icon("shield-check", size=QSize(28, 28), state="active")
        if icon_pixmap and not icon_pixmap.isNull():
            icon_container.setPixmap(icon_pixmap.pixmap(28, 28))
        else:
            icon_container.setText("🔒")
            icon_container.setStyleSheet("font-size: 20px; background: transparent;")
        header_layout.addWidget(icon_container)
        
        # Title and subtitle
        title_widget = QWidget()
        title_layout = QVBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        
        self.title_label = QLabel("Reset Password")
        self.title_label.setObjectName("dialogTitle")
        title_layout.addWidget(self.title_label)
        
        self.subtitle_label = QLabel("Secure account recovery")
        self.subtitle_label.setObjectName("dialogSubtitle")
        title_layout.addWidget(self.subtitle_label)
        
        header_layout.addWidget(title_widget, 1)
        
        container_layout.addWidget(header)
        
        # ── CONTENT ──
        content = QWidget()
        content.setObjectName("dialogContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 20, 32, 12)
        content_layout.setSpacing(16)
        
        # Stack - only one page visible at a time
        self.stack = QStackedWidget()
        self.stack.setObjectName("resetStack")
        self.stack.setContentsMargins(0, 0, 0, 0)
        
        # Create all steps
        self.step0 = self._create_request_step()
        self.stack.addWidget(self.step0)
        
        self.step1 = self._create_verify_step()
        self.stack.addWidget(self.step1)
        
        self.step2 = self._create_reset_step()
        self.stack.addWidget(self.step2)
        
        self.step3 = self._create_success_step()
        self.stack.addWidget(self.step3)
        
        content_layout.addWidget(self.stack, 1)
        container_layout.addWidget(content, 1)
        
        # ── FOOTER WITH CANCEL BUTTON ──
        footer = QFrame()
        footer.setObjectName("dialogFooter")
        footer.setFixedHeight(60)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(32, 12, 32, 12)
        footer_layout.setSpacing(12)
        
        # Back button (hidden initially, shown on steps 1 and 2)
        self.back_btn = ShadcnButton("← Back", variant="outline", size="sm")
        self.back_btn.setMinimumHeight(36)
        self.back_btn.clicked.connect(self.go_back)
        self.back_btn.hide()
        footer_layout.addWidget(self.back_btn)
        
        footer_layout.addStretch()
        
        # Cancel button
        self.cancel_btn = ShadcnButton("Cancel", variant="ghost", size="sm")
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(self.cancel_btn)
        
        container_layout.addWidget(footer)
        
        main_layout.addWidget(container)
        
    def _create_request_step(self):
        """Step 0: Request OTP."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        # Progress dots
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(8)
        progress_layout.setAlignment(Qt.AlignCenter)
        
        self.progress_dots = []
        for i in range(3):
            dot = QLabel("●")
            dot.setObjectName("progressDot")
            dot.setFixedSize(10, 10)
            self.progress_dots.append(dot)
            progress_layout.addWidget(dot)
        layout.addLayout(progress_layout)
        
        info = QLabel("Enter your username or email to receive a verification code.")
        info.setObjectName("stepInfo")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        self.username_input = FloatingLabelInput("Username or Email", icon_name="user")
        self.username_input.input.returnPressed.connect(self.request_otp)
        layout.addWidget(self.username_input)
        
        layout.addStretch()
        
        self.request_btn = ShadcnButton("Send Code", variant="default", size="lg")
        self.request_btn.setMinimumHeight(44)
        self.request_btn.clicked.connect(self.request_otp)
        layout.addWidget(self.request_btn)
        
        return widget
    
    def _create_verify_step(self):
        """Step 1: Verify OTP."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        # Progress dots
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(8)
        progress_layout.setAlignment(Qt.AlignCenter)
        
        self.progress_dots_v = []
        for i in range(3):
            dot = QLabel("●")
            dot.setObjectName("progressDot")
            dot.setFixedSize(10, 10)
            self.progress_dots_v.append(dot)
            progress_layout.addWidget(dot)
        layout.addLayout(progress_layout)
        
        info_label = QLabel("Enter the 6-digit code sent to your email.")
        info_label.setObjectName("stepInfo")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # OTP input boxes
        otp_container = QWidget()
        otp_container.setFixedHeight(56)
        otp_layout = QHBoxLayout(otp_container)
        otp_layout.setContentsMargins(0, 0, 0, 0)
        otp_layout.setSpacing(8)
        otp_layout.setAlignment(Qt.AlignCenter)
        
        self.otp_boxes = []
        for i in range(6):
            box = QLineEdit()
            box.setObjectName("otpBox")
            box.setFixedSize(44, 52)
            box.setAlignment(Qt.AlignCenter)
            box.setMaxLength(1)
            self.otp_boxes.append(box)
            otp_layout.addWidget(box)
            box.textChanged.connect(lambda text, idx=i: self._on_otp_changed(idx, text))
            box.returnPressed.connect(self.verify_otp)
        
        layout.addWidget(otp_container)
        
        # Hidden OTP input
        self.otp_input = FloatingLabelInput("", icon_name="shield-check")
        self.otp_input.input.setMaxLength(6)
        self.otp_input.hide()
        
        # Timer
        timer_widget = QWidget()
        timer_layout = QHBoxLayout(timer_widget)
        timer_layout.setContentsMargins(0, 0, 0, 0)
        timer_layout.setSpacing(8)
        timer_layout.setAlignment(Qt.AlignCenter)
        
        self.timer_label = QLabel("Expires in 15:00")
        self.timer_label.setObjectName("timerLabel")
        timer_layout.addWidget(self.timer_label)
        
        self.resend_btn = QPushButton("Resend")
        self.resend_btn.setObjectName("resendBtn")
        self.resend_btn.setCursor(Qt.PointingHandCursor)
        self.resend_btn.clicked.connect(self.resend_otp)
        self.resend_btn.setEnabled(False)
        timer_layout.addWidget(self.resend_btn)
        
        layout.addWidget(timer_widget)
        layout.addStretch()
        
        self.verify_btn = ShadcnButton("Verify", variant="default", size="lg")
        self.verify_btn.setMinimumHeight(44)
        self.verify_btn.clicked.connect(self.verify_otp)
        layout.addWidget(self.verify_btn)
        
        return widget
    
    def _create_reset_step(self):
        """Step 2: Set new password."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # Progress dots
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(8)
        progress_layout.setAlignment(Qt.AlignCenter)
        
        self.progress_dots_r = []
        for i in range(3):
            dot = QLabel("●")
            dot.setObjectName("progressDot")
            dot.setFixedSize(10, 10)
            self.progress_dots_r.append(dot)
            progress_layout.addWidget(dot)
        layout.addLayout(progress_layout)
        
        info = QLabel("Create a strong password for your account.")
        info.setObjectName("stepInfo")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        self.new_password = FloatingLabelInput("New Password", icon_name="lock", password=True)
        self.new_password.textChanged.connect(self._validate_password)
        layout.addWidget(self.new_password)
        
        self.confirm_password = FloatingLabelInput("Confirm Password", icon_name="lock", password=True)
        self.confirm_password.textChanged.connect(self._validate_password_match)
        layout.addWidget(self.confirm_password)
        
        # Strength meter
        meter_container = QWidget()
        meter_container.setFixedHeight(20)
        meter_layout = QVBoxLayout(meter_container)
        meter_layout.setContentsMargins(0, 0, 0, 0)
        meter_layout.setSpacing(2)
        
        meter_bar = QFrame()
        meter_bar.setObjectName("strengthMeterTrack")
        meter_bar.setFixedHeight(4)
        self.strength_meter = QFrame(meter_bar)
        self.strength_meter.setObjectName("strengthMeterFill")
        self.strength_meter.setFixedHeight(4)
        self.strength_meter.setGeometry(0, 0, 0, 4)
        meter_layout.addWidget(meter_bar)
        
        self.strength_label = QLabel("")
        self.strength_label.setObjectName("strengthLabel")
        meter_layout.addWidget(self.strength_label)
        
        layout.addWidget(meter_container)
        
        # Password requirements
        req_container = QWidget()
        req_layout = QGridLayout(req_container)
        req_layout.setContentsMargins(0, 0, 0, 0)
        req_layout.setSpacing(4)
        
        self.req_labels = []
        requirements = [
            ("8+ characters", "len"),
            ("Uppercase", "upper"),
            ("Lowercase", "lower"),
            ("Number", "digit"),
            ("Special", "special")
        ]
        
        for i, (text, key) in enumerate(requirements):
            chip = QLabel(f"○ {text}")
            chip.setObjectName("requirementChip")
            setattr(chip, "_req_key", key)
            req_layout.addWidget(chip, i // 3, i % 3, Qt.AlignLeft)
            self.req_labels.append(chip)
        
        layout.addWidget(req_container)
        layout.addStretch()
        
        self.reset_btn = ShadcnButton("Reset Password", variant="default", size="lg")
        self.reset_btn.setMinimumHeight(44)
        self.reset_btn.clicked.connect(self.reset_password)
        self.reset_btn.setEnabled(False)
        layout.addWidget(self.reset_btn)
        
        return widget
    
    def _create_success_step(self):
        """Step 3: Success state."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)
        
        # Progress dots (all filled)
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(8)
        progress_layout.setAlignment(Qt.AlignCenter)
        
        for i in range(3):
            dot = QLabel("●")
            dot.setObjectName("progressDot")
            dot.setFixedSize(10, 10)
            progress_layout.addWidget(dot)
        layout.addLayout(progress_layout)
        
        # Success icon
        success_icon = QLabel("✓")
        success_icon.setObjectName("successIcon")
        success_icon.setAlignment(Qt.AlignCenter)
        success_icon.setFixedSize(64, 64)
        layout.addWidget(success_icon, alignment=Qt.AlignCenter)
        
        title = QLabel("Password Updated!")
        title.setObjectName("successTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        desc = QLabel("Your password has been changed successfully.")
        desc.setObjectName("successDesc")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        layout.addStretch()
        
        self.done_btn = ShadcnButton("Continue", variant="default", size="lg")
        self.done_btn.setMinimumHeight(44)
        self.done_btn.clicked.connect(self.accept)
        layout.addWidget(self.done_btn)
        
        return widget
    
    def _on_otp_changed(self, index, text):
        """Handle OTP box input."""
        if text:
            if index < 5:
                self.otp_boxes[index + 1].setFocus()
            else:
                self.verify_btn.setFocus()
        
        otp = "".join([box.text() for box in self.otp_boxes])
        self.otp_input.input.setText(otp)
        
        if len(otp) == 6 and otp.isdigit():
            self.verify_otp()
    
    def show_step(self, index):
        """Show a specific step."""
        self.current_step = index
        
        # Update progress dots
        tokens = self.theme_manager.get_tokens()
        primary = tokens.get('primary', '#0EA5E9')
        muted = tokens.get('muted-foreground', '#94A3B8')
        
        # Get the dots from the current step
        if index == 0:
            dots = self.progress_dots
        elif index == 1:
            dots = self.progress_dots_v
        elif index == 2:
            dots = self.progress_dots_r
        else:
            dots = []
            
        for i in range(3):
            if i <= index:
                dots[i].setStyleSheet(f"color: {primary}; font-size: 10px; background: transparent;")
            else:
                dots[i].setStyleSheet(f"color: {muted}; font-size: 10px; background: transparent;")
        
        # Update subtitle
        subtitles = [
            "Enter your username to receive a code",
            "Enter the 6-digit code sent to your email",
            "Create your new password",
            "Password updated successfully"
        ]
        self.subtitle_label.setText(subtitles[index] if index < len(subtitles) else "")
        
        # Update back button visibility (show on steps 1 and 2)
        self.back_btn.setVisible(index in [1, 2])
        
        # Update cancel button text
        if index == 3:
            self.cancel_btn.setText("Close")
        else:
            self.cancel_btn.setText("Cancel")
        
        # Switch stack
        self.stack.setCurrentIndex(index)
        
        # Auto-focus
        if index == 0:
            self.username_input.input.setFocus()
        elif index == 1:
            self.otp_boxes[0].setFocus()
        elif index == 2:
            self.new_password.input.setFocus()
    
    def go_back(self):
        """Go to previous step."""
        if self.current_step > 0:
            self.show_step(self.current_step - 1)
    
    def request_otp(self):
        """Request OTP from backend."""
        username = self.username_input.text().strip()
        if not username:
            ShadcnToast("Error", "Please enter your username or email.", parent=self)
            return
        
        self.username = username
        self.request_btn.setEnabled(False)
        self.request_btn.setText("Sending...")
        
        try:
            self.api_client.request(
                "POST",
                "/auth/forgot-password",
                json={"username": username},
                need_auth=False
            )
            
            ShadcnToast("Success", "Code sent to your email.", duration=3000, parent=self)
            self.show_step(1)
            self.start_timer()
            
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                ShadcnToast("Rate Limited", "Too many attempts. Please wait 1 hour.", parent=self)
            else:
                logger.error(f"Password reset request failed: {error_msg}")
                ShadcnToast("Success", "If the account exists, a code has been sent.", duration=3000, parent=self)
                self.show_step(1)
                self.start_timer()
        finally:
            self.request_btn.setEnabled(True)
            self.request_btn.setText("Send Code")
    
    def verify_otp(self):
        """Verify OTP and get reset token."""
        otp = self.otp_input.text().strip()
        if not otp or len(otp) != 6 or not otp.isdigit():
            ShadcnToast("Error", "Please enter a valid 6-digit code.", parent=self)
            return
        
        self.otp = otp
        self.verify_btn.setEnabled(False)
        self.verify_btn.setText("Verifying...")
        
        try:
            response = self.api_client.request(
                "POST",
                "/auth/verify-otp",
                json={"token": otp},
                need_auth=False
            )
            
            self.reset_token = response.get("reset_token")
            if self.reset_token:
                ShadcnToast("Success", "Code verified!", duration=2000, parent=self)
                self.show_step(2)
                if self.resend_timer:
                    self.resend_timer.stop()
            else:
                ShadcnToast("Error", "Invalid or expired code.", parent=self)
                
        except Exception as e:
            ShadcnToast("Error", "Invalid or expired code.", parent=self)
        finally:
            self.verify_btn.setEnabled(True)
            self.verify_btn.setText("Verify")
    
    def resend_otp(self):
        """Resend OTP."""
        if not self.username:
            return
        
        self.resend_btn.setEnabled(False)
        
        try:
            self.api_client.request(
                "POST",
                "/auth/resend-otp",
                json={"username": self.username},
                need_auth=False
            )
            ShadcnToast("Success", "New code sent.", duration=3000, parent=self)
            self.start_timer()
            
        except Exception as e:
            ShadcnToast("Error", "Failed to resend code.", parent=self)
            self.resend_btn.setEnabled(True)
    
    def start_timer(self):
        """Start the OTP countdown timer (15 minutes)."""
        self.countdown = 900
        self.resend_btn.setEnabled(False)
        
        if self.resend_timer:
            self.resend_timer.stop()
        
        self.resend_timer = QTimer()
        self.resend_timer.timeout.connect(self._update_timer)
        self.resend_timer.start(1000)
        self._update_timer()
    
    def _update_timer(self):
        """Update the timer display."""
        self.countdown -= 1
        minutes = self.countdown // 60
        seconds = self.countdown % 60
        self.timer_label.setText(f"Expires in {minutes:02d}:{seconds:02d}")
        
        if self.countdown <= 0:
            self.resend_timer.stop()
            self.timer_label.setText("Code expired")
            self.resend_btn.setEnabled(True)
    
    def _validate_password(self, text):
        """Validate password strength in real-time."""
        password = text
        requirements = {
            "len": len(password) >= 8,
            "upper": bool(re.search(r'[A-Z]', password)),
            "lower": bool(re.search(r'[a-z]', password)),
            "digit": bool(re.search(r'[0-9]', password)),
            "special": bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password))
        }
        
        tokens = self.theme_manager.get_tokens()
        success = tokens.get('success', '#10B981')
        destructive = tokens.get('destructive', '#EF4444')
        muted = tokens.get('muted-foreground', '#94A3B8')
        muted_bg = tokens.get('muted', '#F1F5F9')
        
        # Update requirement chips
        for chip in self.req_labels:
            key = chip._req_key
            text = chip.text()[2:]
            if password and requirements.get(key, False):
                chip.setText(f"✓ {text}")
                chip.setStyleSheet(f"""
                    font-size: 10px;
                    color: {success};
                    background: #D1FAE5;
                    padding: 2px 8px;
                    border-radius: 4px;
                """)
            elif password:
                chip.setText(f"✗ {text}")
                chip.setStyleSheet(f"""
                    font-size: 10px;
                    color: {destructive};
                    background: #FEE2E2;
                    padding: 2px 8px;
                    border-radius: 4px;
                """)
            else:
                chip.setText(f"○ {text}")
                chip.setStyleSheet(f"""
                    font-size: 10px;
                    color: {muted};
                    background: {muted_bg};
                    padding: 2px 8px;
                    border-radius: 4px;
                """)
        
        # Update strength meter
        score = sum(1 for v in requirements.values() if v)
        percentage = int((score / 5) * 100)
        
        colors = [destructive, "#F59E0B", "#F59E0B", success, success]
        color = colors[score] if score < len(colors) else success
        
        self.strength_meter.setStyleSheet(f"""
            background: {color};
            border-radius: 2px;
        """)
        self.strength_meter.setFixedWidth(int(percentage * 3))
        
        labels = ["Weak", "Fair", "Fair", "Strong", "Strong"]
        self.strength_label.setText(f"Strength: {labels[score] if password else ''}")
        self.strength_label.setStyleSheet(f"color: {color if password else muted}; font-size: 11px; background: transparent;")
        
        is_valid = all(requirements.values()) if password else True
        if password and not is_valid:
            self.new_password.set_valid(False, "Password does not meet requirements")
        else:
            self.new_password.set_valid(True)
        
        self._validate_password_match()
    
    def _validate_password_match(self):
        """Check if passwords match."""
        password = self.new_password.text()
        confirm = self.confirm_password.text()
        
        if not confirm:
            self.confirm_password.set_valid(True)
            self.reset_btn.setEnabled(False)
            return
        
        if password == confirm and self._is_password_valid():
            self.confirm_password.set_valid(True)
            self.reset_btn.setEnabled(True)
        else:
            self.confirm_password.set_valid(False, "Passwords do not match")
            self.reset_btn.setEnabled(False)
    
    def _is_password_valid(self) -> bool:
        """Check if password meets all requirements."""
        password = self.new_password.text()
        if not password or len(password) < 8:
            return False
        if not re.search(r'[A-Z]', password):
            return False
        if not re.search(r'[a-z]', password):
            return False
        if not re.search(r'[0-9]', password):
            return False
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False
        return True
    
    def reset_password(self):
        """Reset password using the token."""
        new_password = self.new_password.text()
        
        if not self._is_password_valid():
            return
        
        self.reset_btn.setEnabled(False)
        self.reset_btn.setText("Resetting...")
        
        try:
            self.api_client.request(
                "POST",
                "/auth/reset-password",
                json={
                    "token": self.reset_token,
                    "new_password": new_password
                },
                need_auth=False
            )
            self.show_step(3)
            
        except Exception as e:
            ShadcnToast("Error", "Reset token expired. Please start over.", parent=self)
            self.reject()
        finally:
            self.reset_btn.setEnabled(True)
            self.reset_btn.setText("Reset Password")
    
    def apply_theme(self):
        """Apply current theme colors."""
        tokens = self.theme_manager.get_tokens()
        is_dark = self.theme_manager.get_current_theme() == "dark"
        
        background = tokens.get('background', '#0F172A' if is_dark else '#FFFFFF')
        surface = tokens.get('surface', '#1E293B' if is_dark else '#F8FAFC')
        border = tokens.get('border', '#334155' if is_dark else '#E2E8F0')
        foreground = tokens.get('foreground', '#F8FAFC' if is_dark else '#0F172A')
        muted_foreground = tokens.get('muted-foreground', '#94A3B8')
        primary = tokens.get('primary', '#38BDF8')
        input_bg = tokens.get('input', '#0F172A' if is_dark else '#F8FAFC')
        
        self.container.setStyleSheet(f"""
            #resetDialogContainer {{
                background: {background};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            
            #dialogHeader {{
                background: {surface};
                border-bottom: 1px solid {border};
                border-radius: 12px 12px 0 0;
            }}
            
            #dialogTitle {{
                color: {foreground};
                font-size: 18px;
                font-weight: 600;
                background: transparent;
            }}
            
            #dialogSubtitle {{
                color: {muted_foreground};
                font-size: 12px;
                background: transparent;
            }}
            
            #dialogContent {{
                background: {background};
            }}
            
            #dialogFooter {{
                background: {surface};
                border-top: 1px solid {border};
                border-radius: 0 0 12px 12px;
            }}
            
            #stepInfo {{
                color: {muted_foreground};
                font-size: 13px;
                background: transparent;
            }}
            
            #progressDot {{
                font-size: 10px;
                background: transparent;
            }}
            
            #otpBox {{
                background: {input_bg};
                border: 2px solid {border};
                border-radius: 8px;
                color: {foreground};
                font-size: 20px;
                font-weight: 600;
            }}
            #otpBox:focus {{
                border-color: {primary};
            }}
            
            #timerLabel {{
                color: {muted_foreground};
                font-size: 12px;
                background: transparent;
            }}
            
            #resendBtn {{
                background: transparent;
                border: none;
                color: {primary};
                font-size: 12px;
                font-weight: 500;
            }}
            #resendBtn:hover {{
                text-decoration: underline;
            }}
            #resendBtn:disabled {{
                color: {muted_foreground};
            }}
            
            #strengthMeterTrack {{
                background: {surface};
                border-radius: 2px;
            }}
            
            #strengthLabel {{
                font-size: 11px;
                background: transparent;
            }}
            
            #requirementChip {{
                font-size: 10px;
                padding: 2px 8px;
                border-radius: 4px;
            }}
            
            #successIcon {{
                color: #10B981;
                background: #D1FAE5;
                border-radius: 32px;
                font-size: 32px;
                font-weight: 700;
            }}
            
            #successTitle {{
                color: {foreground};
                font-size: 20px;
                font-weight: 600;
                background: transparent;
            }}
            
            #successDesc {{
                color: {muted_foreground};
                font-size: 13px;
                background: transparent;
            }}
        """)
        
        # Update FloatingLabelInput widgets
        for child in self.findChildren(FloatingLabelInput):
            child.update_theme_colors()
            child.update_icon()
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.current_step == 0:
                self.request_otp()
            elif self.current_step == 1:
                self.verify_otp()
            elif self.current_step == 2:
                self.reset_password()
            elif self.current_step == 3:
                self.accept()
        super().keyPressEvent(event)

