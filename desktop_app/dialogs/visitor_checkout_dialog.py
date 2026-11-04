# dialogs/visitor_checkout_dialog.py
"""
Visitor checkout confirmation dialog.

CRITICAL FIX
------------
The previous version of this file referenced QHBoxLayout without
importing it, which raised NameError at runtime. This version adds the
missing import and migrates to Shadcn components + ShadcnToast so the
dialog matches the rest of the app visually and behaviourally.
"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from widgets.components import ShadcnButton, ShadcnToast
from core.theme_manager import ThemeManager


class VisitorCheckoutDialog(QDialog):
    def __init__(self, visitor_id, data_service, parent=None):
        super().__init__(parent)
        self.visitor_id = visitor_id
        self.data_service = data_service
        self.theme_manager = ThemeManager()

        self.setWindowTitle("Check Out Visitor")
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setAccessibleName("Confirm visitor checkout")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)

        message = QLabel(
            f"Confirm check-out for visitor ID: {visitor_id}"
        )
        message.setWordWrap(True)
        message.setAccessibleName(message.text())
        layout.addWidget(message)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        cancel_btn = ShadcnButton("Cancel", variant="outline", size="sm")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        checkout_btn = ShadcnButton("Check Out", variant="default", size="sm")
        checkout_btn.setDefault(True)
        checkout_btn.clicked.connect(self.checkout)
        btn_layout.addWidget(checkout_btn)

        layout.addLayout(btn_layout)

        # Focus the primary action when the dialog opens.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, checkout_btn.setFocus)

    def checkout(self):
        try:
            self.data_service.checkout_visitor(self.visitor_id)
        except Exception as e:
            ShadcnToast(
                "Checkout failed",
                description=str(e),
                variant="destructive",
                parent=self.parent() if self.parent() else self,
            )
            return

        ShadcnToast(
            "Visitor checked out",
            variant="success",
            parent=self.parent() if self.parent() else self,
        )
        self.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.checkout()
            event.accept()
            return
        super().keyPressEvent(event)
