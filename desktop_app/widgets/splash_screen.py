# widgets/splash_screen.py
from PySide6.QtWidgets import QSplashScreen, QProgressBar, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QTimer
from core.theme_manager import ThemeManager


class SplashScreen(QSplashScreen):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(500, 300)

        # Get current theme tokens
        self.theme_manager = ThemeManager()
        tokens = self.theme_manager.get_tokens()

        bg     = tokens["background"]
        fg     = tokens["foreground"]
        primary = tokens["primary"]
        muted  = tokens["muted"]

        # ── Splash shell ──
        self.setStyleSheet(f"""
            QSplashScreen {{
                background-color: {bg};
                border: none;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ── Title ──
        title = QLabel("ICT AUTHORITY")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"""
            color: {fg};
            font-size: 28px;
            font-weight: bold;
        """)
        layout.addWidget(title)

        # ── Subtitle ──
        subtitle = QLabel("Access Control System")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"""
            color: {fg};
            font-size: 16px;
            opacity: 0.9;
        """)
        layout.addWidget(subtitle)

        # ── Status message ──
        self.message_label = QLabel("Initializing...")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setStyleSheet(f"""
            color: {fg};
            margin-top: 20px;
        """)
        layout.addWidget(self.message_label)

        # ── Progress bar ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(300)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: {muted};
                border-radius: 3px;
                height: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {primary};
                border-radius: 3px;
            }}
        """)
        layout.addWidget(self.progress_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── Percentage label ──
        self.status_label = QLabel("0%")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(f"""
            color: {fg};
            font-size: 11px;
        """)
        layout.addWidget(self.status_label)

        self.center_on_screen()

    def center_on_screen(self):
        screen = self.screen().availableGeometry()
        self.move(screen.center() - self.rect().center())

    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.message_label.setText(message)
        self.status_label.setText(f"{value}%")
        QTimer.singleShot(0, self.repaint)

    