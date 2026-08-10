# widgets/dashboard.py
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from utils.icon_manager import IconManager

class DashboardCard(QWidget):
    def __init__(self, title, value):
        super().__init__()
        self.setObjectName("dashboard-card")
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size:12px; color:#9CA3AF")
        value_lbl = QLabel(value)
        value_lbl.setStyleSheet("font-size:24px; font-weight:bold")
        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)

