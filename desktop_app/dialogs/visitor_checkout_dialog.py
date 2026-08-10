# dialogs/visitor_checkout_dialog.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QMessageBox
from PySide6.QtCore import Qt

class VisitorCheckoutDialog(QDialog):
    def __init__(self, visitor_id, data_service, parent=None):
        super().__init__(parent)
        self.visitor_id = visitor_id
        self.data_service = data_service
        self.setWindowTitle("Check Out Visitor")
        self.setModal(True)
        self.setFixedSize(300, 150)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Confirm check-out for visitor ID: " + str(visitor_id)))
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        checkout_btn = QPushButton("Check Out")
        checkout_btn.clicked.connect(self.checkout)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(checkout_btn)
        layout.addLayout(btn_layout)

    def checkout(self):
        self.data_service.checkout_visitor(self.visitor_id)
        QMessageBox.information(self, "Success", "Visitor checked out.")
        self.accept()

