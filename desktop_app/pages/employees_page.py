from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QDialog,
                               QFormLayout, QComboBox, QCheckBox, QTableWidgetItem, QDateEdit)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QDoubleValidator
from widgets.components import ShadcnDataTable, ShadcnButton, ShadcnInput, ShadcnToast, ShadcnAlertDialog

class EmployeesPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        toolbar = QHBoxLayout()
        self.add_btn = ShadcnButton("Add Employee", variant="default")
        self.add_btn.clicked.connect(self.add_employee)
        toolbar.addWidget(self.add_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = ShadcnDataTable(["ID", "Employee ID", "Full Name", "Role", "Badge", "Active", "Actions"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(6, 120)
        layout.addWidget(self.table)

        self.refresh_table()

    def refresh_table(self):
        try:
            employees = self.data_service.get_employees(active_only=False)
            self.table.setRowCount(len(employees))
            for row, emp in enumerate(employees):
                self.table.setItem(row, 0, QTableWidgetItem(str(emp.get('id', ''))))
                self.table.setItem(row, 1, QTableWidgetItem(emp.get('employee_id', '')))
                self.table.setItem(row, 2, QTableWidgetItem(emp.get('full_name', '')))
                self.table.setItem(row, 3, QTableWidgetItem(emp.get('role', '')))
                self.table.setItem(row, 4, QTableWidgetItem(emp.get('badge_number', '')))
                self.table.setItem(row, 5, QTableWidgetItem("Yes" if emp.get('is_active') else "No"))

                btn_widget = QWidget()
                btn_layout = QHBoxLayout(btn_widget)
                btn_layout.setContentsMargins(0, 0, 0, 0)
                edit_btn = ShadcnButton("Edit", variant="outline", size="sm")
                edit_btn.clicked.connect(lambda _, eid=emp['id']: self.edit_employee(eid))
                del_btn = ShadcnButton("Delete", variant="destructive", size="sm")
                del_btn.clicked.connect(lambda _, eid=emp['id']: self.delete_employee(eid))
                btn_layout.addWidget(edit_btn)
                btn_layout.addWidget(del_btn)
                self.table.setCellWidget(row, 6, btn_widget)
        except Exception as e:
            ShadcnToast("Error", f"Failed to load employees: {str(e)}", parent=self)
            self.table.setRowCount(0)

    def add_employee(self):
        dialog = EmployeeDialog(self.data_service, None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_table()

    def edit_employee(self, emp_id):
        employees = self.data_service.get_employees(active_only=False)
        emp = next((e for e in employees if e['id'] == emp_id), None)
        if emp:
            dialog = EmployeeDialog(self.data_service, emp, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh_table()

    def delete_employee(self, emp_id):
        if ShadcnAlertDialog("Confirm Delete", "Deactivate this employee?", parent=self).exec() == QDialog.DialogCode.Accepted:
            self.data_service.deactivate_employee(emp_id)
            self.refresh_table()
            ShadcnToast("Success", "Employee deactivated", duration=2000, parent=self)


class EmployeeDialog(QDialog):
    def __init__(self, data_service, employee_data, parent=None):
        super().__init__(parent)
        self.data_service = data_service
        self.employee_data = employee_data
        self.setWindowTitle("Add Employee" if not employee_data else "Edit Employee")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        form = QFormLayout()
        form.setSpacing(12)

        self.emp_id_input = ShadcnInput()
        self.name_input = ShadcnInput()
        self.role_combo = QComboBox()
        self.role_combo.addItems(['admin', 'security', 'regular', 'maintenance', 'finance'])
        self.badge_input = ShadcnInput()
        self.active_check = QCheckBox("Active")
        self.active_check.setChecked(True)

        form.addRow("Employee ID *", self.emp_id_input)
        form.addRow("Full Name *", self.name_input)
        form.addRow("Role", self.role_combo)
        form.addRow("Badge Number", self.badge_input)
        form.addRow("", self.active_check)

        self.dynamic_fields = self.data_service.get_custom_fields('employee', active_only=True)
        self.dynamic_widgets = {}
        if self.dynamic_fields:
            dyn_form = QFormLayout()
            for field in self.dynamic_fields:
                widget = self.create_field_widget(field)
                self.dynamic_widgets[field['field_name']] = (widget, field)
                dyn_form.addRow(field['label'] + (" *" if field['required'] else ""), widget)
            form.addRow(dyn_form)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        cancel_btn = ShadcnButton("Cancel", variant="outline")
        cancel_btn.clicked.connect(self.reject)
        save_btn = ShadcnButton("Save", variant="default")
        save_btn.clicked.connect(self.save)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        if self.employee_data:
            self.emp_id_input.setText(self.employee_data.get('employee_id', ''))
            self.name_input.setText(self.employee_data.get('full_name', ''))
            self.role_combo.setCurrentText(self.employee_data.get('role', ''))
            self.badge_input.setText(self.employee_data.get('badge_number', ''))
            self.active_check.setChecked(self.employee_data.get('is_active', True))
            dyn = self.employee_data.get('dynamic_fields', {})
            for fname, (widget, _) in self.dynamic_widgets.items():
                if fname in dyn:
                    val = dyn[fname]
                    if hasattr(widget, 'setText'):
                        widget.setText(str(val))
                    elif isinstance(widget, QCheckBox):
                        widget.setChecked(val)

    def create_field_widget(self, field):
        dtype = field['data_type']
        if dtype == 'text':
            return ShadcnInput()
        elif dtype == 'number':
            w = ShadcnInput()
            w.setValidator(QDoubleValidator())
            return w
        elif dtype == 'date':
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDate(QDate.currentDate())
            return w
        elif dtype == 'email':
            return ShadcnInput()
        elif dtype == 'phone':
            w = ShadcnInput()
            w.setInputMask('+99 999 999 9999;_')
            return w
        elif dtype == 'dropdown':
            import json
            w = QComboBox()
            options = json.loads(field.get('dropdown_options', '[]'))
            w.addItems(options)
            return w
        elif dtype == 'checkbox':
            return QCheckBox()
        else:
            return ShadcnInput()

    def save(self):
        emp_id = self.emp_id_input.text().strip()
        name = self.name_input.text().strip()
        if not emp_id or not name:
            ShadcnToast("Error", "Employee ID and Name are required", parent=self)
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
        if self.employee_data:
            self.data_service.update_employee(self.employee_data['id'], name, self.role_combo.currentText(),
                                              self.badge_input.text(), dynamic_data, self.active_check.isChecked())
            ShadcnToast("Success", "Employee updated", parent=self)
        else:
            self.data_service.add_employee(emp_id, name, self.role_combo.currentText(),
                                           self.badge_input.text(), dynamic_data)
            ShadcnToast("Success", "Employee added", parent=self)
        self.accept()

