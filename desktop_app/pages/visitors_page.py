from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QTabWidget, QFormLayout, QComboBox,
                               QCheckBox, QDateEdit, QMessageBox, QDialog,
                               QTableWidgetItem, QFrame, QLabel, QScrollArea)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QDoubleValidator
from pages.base_page import BasePage
from widgets.components import (ShadcnDataTable, ShadcnButton, ShadcnInput, 
                               ShadcnCard, CardContent, ShadcnToast, ShadcnAlertDialog)
from dialogs.visitor_checkout_dialog import VisitorCheckoutDialog
from datetime import datetime

class VisitorsPage(BasePage):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        self.data_service = data_service
        super().__init__(user_info, permissions, page_id="visitors")

    def init_ui(self):
        layout = self.content_layout
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setExpanding(False)
        layout.addWidget(self.tabs)

        self.checkin_tab = QWidget()
        self.setup_checkin_tab()
        self.tabs.addTab(self.checkin_tab, "Check In")

        self.active_tab = QWidget()
        self.setup_active_tab()
        self.tabs.addTab(self.active_tab, "Active Visitors")

        self.history_tab = QWidget()
        self.setup_history_tab()
        self.tabs.addTab(self.history_tab, "History")

        self.tabs.currentChanged.connect(self.on_tab_changed)

    def setup_checkin_tab(self):
        # Same as before, but use data_service for dynamic fields and host list
        layout = QVBoxLayout(self.checkin_tab)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(24)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form_layout.setSpacing(24)

        card = ShadcnCard()
        card.setMaximumWidth(850)
        card.setMinimumWidth(400)

        content = CardContent()
        basic_layout = QFormLayout()
        basic_layout.setSpacing(16)
        basic_layout.setLabelAlignment(Qt.AlignRight)

        self.name_input = ShadcnInput()
        self.name_input.setPlaceholderText("Full name")
        basic_layout.addRow("Visitor Name *", self.name_input)

        self.host_combo = QComboBox()
        self.refresh_host_list()
        basic_layout.addRow("Host Employee *", self.host_combo)

        self.consent_check = QCheckBox("I consent to GDPR data storage for 30 days")
        basic_layout.addRow("", self.consent_check)

        content.layout.addLayout(basic_layout)

        # Dynamic fields – use data_service for custom fields
        self.dynamic_fields = self.data_service.get_custom_fields('visitor', active_only=True)
        self.dynamic_widgets = {}
        if self.dynamic_fields:
            dyn_layout = QFormLayout()
            dyn_layout.setSpacing(12)
            dyn_layout.setLabelAlignment(Qt.AlignRight)
            for field in self.dynamic_fields:
                widget = self.create_field_widget(field)
                self.dynamic_widgets[field['field_name']] = (widget, field)
                dyn_layout.addRow(field['label'] + (" *" if field['required'] else ""), widget)
            content.layout.addLayout(dyn_layout)

        card.set_content(content)
        form_layout.addWidget(card)

        btn_container = QHBoxLayout()
        btn_container.addStretch()
        self.checkin_btn = ShadcnButton("Check In Visitor", variant="default", size="lg")
        self.checkin_btn.setMinimumWidth(200)
        self.checkin_btn.clicked.connect(self.check_in)
        btn_container.addWidget(self.checkin_btn)
        btn_container.addStretch()
        form_layout.addLayout(btn_container)

        scroll.setWidget(form_container)
        layout.addWidget(scroll)

    # create_field_widget remains unchanged

    def refresh_host_list(self):
        self.host_combo.clear()
        self.host_combo.addItem("Select Host", -1)
        employees = self.data_service.get_employees_list_for_host()
        for emp_id, name in employees:
            self.host_combo.addItem(name, emp_id)

    def check_in(self):
        name = self.name_input.text().strip()
        host_id = self.host_combo.currentData()
        consent = self.consent_check.isChecked()
        if not name or host_id == -1:
            ShadcnToast("Error", "Visitor name and host are required", parent=self)
            return
        if not consent:
            ShadcnToast("Error", "GDPR consent is required", parent=self)
            return

        dynamic_data = {}
        errors = []
        for fname, (widget, field) in self.dynamic_widgets.items():
            value = None
            if field['data_type'] == 'checkbox':
                value = widget.isChecked()
            elif field['data_type'] == 'date':
                value = widget.date().toString('yyyy-MM-dd')
            else:
                value = widget.text().strip() if hasattr(widget, 'text') else widget.currentText()
            if field['required'] and not value:
                errors.append(f"{field['label']} is required")
            dynamic_data[fname] = value
        if errors:
            ShadcnToast("Validation Error", "\n".join(errors), parent=self)
            return

        visitor_id = self.data_service.check_in_visitor(name, host_id, dynamic_data, consent)
        if visitor_id:
            ShadcnToast("Success", f"{name} checked in at {datetime.now().strftime('%H:%M:%S')}", parent=self)
            self.name_input.clear()
            self.consent_check.setChecked(False)
            for w, _ in self.dynamic_widgets.values():
                if isinstance(w, ShadcnInput):
                    w.clear()
                elif isinstance(w, QDateEdit):
                    w.setDate(QDate.currentDate())
                elif isinstance(w, QComboBox):
                    w.setCurrentIndex(0)
            self.tabs.setCurrentIndex(1)
            self.refresh_active_tab()

    def setup_active_tab(self):
        layout = QVBoxLayout(self.active_tab)
        layout.setContentsMargins(0, 16, 0, 16)
        self.active_table = ShadcnDataTable(["ID", "Name", "Check-in Time", "Host", "Action"])
        self.active_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.active_table)

    def setup_history_tab(self):
        layout = QVBoxLayout(self.history_tab)
        layout.setContentsMargins(0, 16, 0, 16)
        toolbar = QHBoxLayout()
        self.search_input = ShadcnInput()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.setMaximumWidth(300)
        self.search_input.textChanged.connect(self.filter_history)
        refresh_btn = ShadcnButton("Refresh", variant="outline", size="sm")
        refresh_btn.setMinimumWidth(100)
        refresh_btn.clicked.connect(self.refresh_history_tab)
        toolbar.addWidget(self.search_input)
        toolbar.addStretch()
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)
        layout.addSpacing(16)

        self.history_table = ShadcnDataTable(["ID", "Name", "Check-in", "Check-out", "Host", "Duration"])
        layout.addWidget(self.history_table)
        self.refresh_history_tab()

    def refresh_active_tab(self):
        visitors = self.data_service.get_active_visitors()
        self.active_table.setRowCount(len(visitors))
        for row, v in enumerate(visitors):
            self.active_table.setItem(row, 0, QTableWidgetItem(str(v['id'])))
            self.active_table.setItem(row, 1, QTableWidgetItem(v['visitor_name']))
            self.active_table.setItem(row, 2, QTableWidgetItem(v['check_in_time'][:19] if v.get('check_in_time') else ""))
            self.active_table.setItem(row, 3, QTableWidgetItem(v.get('host_name', 'Unknown')))
            btn = ShadcnButton("Check Out", variant="outline", size="sm")
            btn.setMinimumWidth(80)
            btn.clicked.connect(lambda checked, vid=v['id']: self.check_out(vid))
            self.active_table.setCellWidget(row, 4, btn)

    def check_out(self, visitor_id):
        dialog = VisitorCheckoutDialog(visitor_id, self.data_service, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_active_tab()
            self.refresh_history_tab()

    def refresh_history_tab(self):
        history = self.data_service.get_visitor_history(limit=200)
        data = []
        for row in history:
            check_in = row[2] or ""
            check_out = row[3] or ""
            duration = ""
            if check_in and check_out:
                try:
                    t1 = datetime.fromisoformat(check_in)
                    t2 = datetime.fromisoformat(check_out)
                    hours = (t2 - t1).total_seconds() / 3600
                    duration = f"{hours:.1f}h"
                except:
                    pass
            data.append((row[0], row[1], check_in[:19] if check_in else "", check_out[:19] if check_out else "", row[5] or "", duration))
        self.history_table.populate(data)

    def filter_history(self, text):
        for row in range(self.history_table.rowCount()):
            match = any(text.lower() in self.history_table.item(row, col).text().lower()
                        for col in range(self.history_table.columnCount())
                        if self.history_table.item(row, col))
            self.history_table.setRowHidden(row, not match)

    def on_tab_changed(self, index):
        if index == 1:
            self.refresh_active_tab()
        elif index == 2:
            self.refresh_history_tab()
        elif index == 0:
            self.refresh_host_list()
