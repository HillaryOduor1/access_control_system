"""
Bare minimum QMainWindow + login-button transition. No splash, no
data, no widgets beyond what is strictly necessary. If the flicker
appears here, it is caused by the OS shell, not by the app.
"""
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel
)
from PySide6.QtCore import QTimer


class EmptyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Empty App - Login")
        self.setGeometry(100, 100, 1200, 700)

        # Simple login-like widget
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(40, 40, 40, 40)
        label = QLabel("Login page")
        label.setStyleSheet("font-size: 24px;")
        layout.addWidget(label)

        button = QPushButton("Sign In")
        button.setFixedSize(200, 50)
        button.clicked.connect(self.on_login)
        layout.addWidget(button)

        layout.addStretch()
        self.setCentralWidget(w)

    def on_login(self):
        """Simulate the login -> dashboard swap."""
        self.setWindowTitle("Empty App - Dashboard")

        # Swap the central widget, exactly like your app does
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(40, 40, 40, 40)
        label = QLabel("Dashboard page")
        label.setStyleSheet("font-size: 24px;")
        layout.addWidget(label)
        layout.addStretch()
        self.setCentralWidget(w)


def main():
    app = QApplication(sys.argv)
    window = EmptyApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()