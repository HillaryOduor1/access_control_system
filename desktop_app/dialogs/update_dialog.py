# dialogs/update_dialog.py
"""
Update prompt with download, SHA-256 verification, silent install.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile
import threading
from typing import Dict

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
)

from widgets.components import ShadcnButton, ShadcnToast
from core.theme_manager import ThemeManager

logger = logging.getLogger(__name__)


class UpdateDialog(QDialog):
    def __init__(self, info: Dict, parent=None):
        super().__init__(parent)
        self.info = info
        self.theme_manager = ThemeManager()
        self._cancel = False
        self.setWindowTitle("Update Available")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._build_ui()

    def _build_ui(self):
        t = self.theme_manager.get_tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel(
            f"Access Control System {self.info.get('version', '?')} is available"
        )
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; "
            f"color: {t['foreground']}; background: transparent;"
        )
        layout.addWidget(title)

        local = self.info.get("_local_version", "?")
        sub = QLabel(f"You are currently running version {local}.")
        sub.setStyleSheet(
            f"color: {t['muted-foreground']}; background: transparent;"
        )
        layout.addWidget(sub)

        notes = self.info.get("notes", "")
        if notes:
            notes_label = QLabel(notes)
            notes_label.setWordWrap(True)
            notes_label.setStyleSheet(
                f"padding: 12px; border: 1px solid {t['border']}; "
                f"border-radius: 8px; color: {t['foreground']}; "
                f"background: {t['surface']};"
            )
            layout.addWidget(notes_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setStyleSheet(
            f"color: {t['muted-foreground']}; font-size: 12px; "
            "background: transparent;"
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        btns = QHBoxLayout()
        btns.addStretch()

        self.later_btn = ShadcnButton("Later", variant="outline")
        self.later_btn.clicked.connect(self.reject)
        btns.addWidget(self.later_btn)

        self.install_btn = ShadcnButton(
            "Download and Install", variant="default"
        )
        self.install_btn.clicked.connect(self._start_download)
        btns.addWidget(self.install_btn)

        layout.addLayout(btns)

    def _start_download(self):
        self.install_btn.setEnabled(False)
        self.later_btn.setEnabled(False)
        self.progress.show()
        self.status.setText("Starting download…")

        threading.Thread(
            target=self._download_worker, daemon=True
        ).start()

    def _download_worker(self):
        url = self.info.get("url")
        expected = (self.info.get("sha256") or "").lower()

        if not url:
            QTimer.singleShot(0, lambda: self._fail("No URL in manifest."))
            return

        try:
            import httpx
            target = os.path.join(tempfile.gettempdir(),
                                  "acs_update_payload.exe")
            if os.path.exists(target):
                try: os.remove(target)
                except Exception: pass

            sha = hashlib.sha256()
            with httpx.stream("GET", url, timeout=180.0,
                              follow_redirects=True) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0)) or 1
                done = 0
                with open(target, "wb") as f:
                    for chunk in r.iter_bytes(65536):
                        if self._cancel:
                            return
                        f.write(chunk)
                        sha.update(chunk)
                        done += len(chunk)
                        pct = int(done * 100 / total)
                        QTimer.singleShot(
                            0, lambda p=pct: self._progress(p)
                        )

            actual = sha.hexdigest()
            if expected and actual != expected:
                QTimer.singleShot(
                    0, lambda: self._fail("SHA-256 verification failed.")
                )
                return

            QTimer.singleShot(0, lambda: self._install(target))
        except Exception as e:
            QTimer.singleShot(0, lambda err=str(e): self._fail(err))

    def _progress(self, pct: int):
        self.progress.setValue(pct)
        self.status.setText(f"Downloading… {pct}%")

    def _install(self, path: str):
        try:
            self.status.setText("Launching installer…")
            self.progress.setValue(100)
            subprocess.Popen(
                [path, "/SILENT", "/SUPPRESSMSGBOXES",
                 "/NORESTART", "/SP-"],
                close_fds=True,
            )
            self.accept()
            QTimer.singleShot(400, self._quit_app)
        except Exception as e:
            self._fail(f"Could not launch installer: {e}")

    def _quit_app(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.quit()

    def _fail(self, message: str):
        t = self.theme_manager.get_tokens()
        self.status.setText(f"Failed: {message}")
        self.status.setStyleSheet(
            f"color: {t['destructive']}; font-size: 12px; "
            "background: transparent;"
        )
        self.install_btn.setEnabled(True)
        self.later_btn.setEnabled(True)
        self.progress.hide()
        ShadcnToast("Update Failed", description=message,
                    parent=self, variant="destructive")