# dialogs/connection_settings_dialog.py
"""
Connection settings dialog with a backgrounded health check.

The previous version performed the HTTP health check on the UI thread,
freezing the dialog for up to 10 seconds. The check now runs in a
QThread so the dialog stays responsive.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject, Slot, QTimer

from core.env_manager import EnvironmentManager
from widgets.components import (
    ShadcnButton, ShadcnComboBox, ShadcnInput, ShadcnToast,
)
from core.theme_manager import ThemeManager


class _HealthCheckWorker(QObject):
    """Runs a single HTTP health check off the UI thread."""

    finished = Signal(bool, str)  # (ok, message)

    def __init__(self, url: str, timeout: float = 10.0):
        super().__init__()
        self.url = url
        self.timeout = timeout

    @Slot()
    def run(self):
        try:
            import httpx
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{self.url}/health")
            if resp.status_code == 200:
                self.finished.emit(True, "Connection successful")
            else:
                self.finished.emit(
                    False,
                    f"Connection failed (HTTP {resp.status_code})",
                )
        except Exception as e:
            self.finished.emit(False, f"Connection error: {str(e)[:120]}")


class ConnectionSettingsDialog(QDialog):
    url_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.env_manager = EnvironmentManager()
        self.theme_manager = ThemeManager()

        self.setWindowTitle("Connection Settings")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setAccessibleName("Connection settings")

        self._thread: QThread = None
        self._worker: _HealthCheckWorker = None

        self.setup_ui()
        self.load_current_settings()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        # Environment selection
        env_layout = QHBoxLayout()
        env_label = QLabel("Environment:")
        env_label.setMinimumWidth(110)
        env_layout.addWidget(env_label)

        self.env_combo = ShadcnComboBox()
        self.env_combo.addItems(self.env_manager.get_available_environments())
        self.env_combo.currentTextChanged.connect(self.on_env_changed)
        self.env_combo.setAccessibleName("Environment")
        env_layout.addWidget(self.env_combo, 1)
        layout.addLayout(env_layout)

        # Custom URL
        url_layout = QHBoxLayout()
        url_label = QLabel("Custom URL:")
        url_label.setMinimumWidth(110)
        url_layout.addWidget(url_label)

        self.url_input = ShadcnInput("https://your-api-url.com")
        self.url_input.setEnabled(False)
        self.url_input.setAccessibleName("Custom API URL")
        url_layout.addWidget(self.url_input, 1)
        layout.addLayout(url_layout)

        # Test connection
        test_row = QHBoxLayout()
        self.test_btn = ShadcnButton("Test Connection", variant="outline")
        self.test_btn.clicked.connect(self.test_connection)
        test_row.addWidget(self.test_btn)
        test_row.addStretch()
        layout.addLayout(test_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Connection test result")
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_btn = ShadcnButton("Cancel", variant="outline", size="sm")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = ShadcnButton("Save", variant="default", size="sm")
        self.save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

    def _set_status(self, text: str, kind: str = "info"):
        t = self.theme_manager.get_tokens()
        colors = {
            "info": t.get("info", "#3B82F6"),
            "success": t.get("success", "#10B981"),
            "error": t.get("destructive", "#EF4444"),
        }
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color: {colors.get(kind, colors['info'])};"
        )

    def load_current_settings(self):
        current_env = self.env_manager.current_env
        index = self.env_combo.findText(current_env)
        if index >= 0:
            self.env_combo.setCurrentIndex(index)

        if current_env == "custom":
            self.url_input.setEnabled(True)
            self.url_input.setText(
                self.env_manager.settings.value("custom_api_url", "")
            )

    def on_env_changed(self, env_name):
        self.url_input.setEnabled(env_name == "custom")
        if env_name != "custom":
            target = self.env_manager.ENVIRONMENTS.get(env_name, "")
            self._set_status(f"Using: {target}", "info")

    def get_current_url(self):
        if self.env_combo.currentText() == "custom":
            return self.url_input.text()
        return self.env_manager.ENVIRONMENTS.get(self.env_combo.currentText())

    def test_connection(self):
        if self._thread is not None and self._thread.isRunning():
            return

        url = (self.get_current_url() or "").strip()
        if not url:
            self._set_status("Please enter a URL first.", "error")
            return

        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing...")
        self._set_status("Testing connection...", "info")

        self._thread = QThread(self)
        self._worker = _HealthCheckWorker(url, timeout=10.0)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_test_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_thread_refs)

        self._thread.start()

    def _clear_thread_refs(self):
        self._thread = None
        self._worker = None

    @Slot(bool, str)
    def _on_test_finished(self, ok: bool, message: str):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Test Connection")
        if ok:
            self._set_status(f"✓ {message}", "success")
        else:
            self._set_status(f"✗ {message}", "error")

    def save_settings(self):
        env_name = self.env_combo.currentText()
        custom_url = self.url_input.text().strip() if env_name == "custom" else None

        if env_name == "custom" and not custom_url:
            self._set_status("Please enter a custom URL.", "error")
            return

        try:
            self.env_manager.set_environment(env_name, custom_url)
        except Exception as e:
            self._set_status(f"Failed to save: {e}", "error")
            return

        self.url_changed.emit(self.env_manager.get_base_url())
        self.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)
