# pages/employees_page.py
"""
Enterprise employee management with validation and secure operations.

Changes in this revision
------------------------
- Validation for required fields now runs on blur (focusLost) rather than
  on every keystroke, so the user is not told "Employee ID is required"
  before they have typed anything.
- Row action buttons are keyboard-reachable via Enter (edit) and Delete
  (deactivate) on the selected row.
- Hardcoded error colors replaced with the destructive token.
- ID column is right-aligned.

Design notes
------------
The initial table load is deferred to showEvent() so the page constructor
never blocks the login -> dashboard swap.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QDialog, QFormLayout,
    QComboBox, QCheckBox, QTableWidgetItem, QDateEdit, QLabel,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QDate, QSize, QTimer
from PySide6.QtGui import QDoubleValidator, QKeyEvent

from widgets.components import (
    ShadcnDataTable, ShadcnButton, ShadcnInput, ShadcnToast,
    ShadcnAlertDialog, ShadcnCaption,
)
from core.theme_manager import ThemeManager
import re
import logging

logger = logging.getLogger(__name__)


class EmployeesPage(QWidget):
    """Enterprise employee management with validation and secure operations."""

    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service
        self.theme_manager = ThemeManager()
        self._initial_load_done = False
        self._is_refreshing = False
        self.init_ui()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_load_done:
            self._initial_load_done = True
            QTimer.singleShot(0, self.refresh_table)

    def init_ui(self):
        tokens = self.theme_manager.get_tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.add_btn = ShadcnButton("Add Employee", variant="default")
        self.add_btn.setToolTip("Add a new employee (Ctrl+N)")
        self.add_btn.clicked.connect(self.add_employee)
        toolbar.addWidget(self.add_btn)

        refresh_btn = ShadcnButton("Refresh", variant="outline", size="sm")
        refresh_btn.setToolTip("Reload the employee list (Ctrl+R)")
        refresh_btn.clicked.connect(self.refresh_table)
        toolbar.addWidget(refresh_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = ShadcnDataTable(
            ["ID", "Employee ID", "Full Name", "Role", "Badge",
             "Active", "Actions"],
            numeric_columns=[0],
            empty_message="No employees yet. Use Add Employee to create one.",
        )
        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.table.setMinimumHeight(400)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 180)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 80)

        # Keyboard access to row actions.
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.installEventFilter(self)

        layout.addWidget(self.table)

    # ------------------------------------------------------------------
    # Keyboard: Enter = edit, Delete = deactivate
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self.table and event.type() == event.Type.KeyPress:
            key = event.key()
            selected = self.table.get_selected_rows()
            if selected:
                emp = None
                try:
                    emp = self.data_service.get_employees(
                        active_only=False
                    )[selected[0]]
                except Exception:
                    emp = None
                if emp:
                    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                        self.edit_employee(emp['id'])
                        return True
                    if key == Qt.Key.Key_Delete and emp.get('is_active', True):
                        self.delete_employee(emp['id'])
                        return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def refresh_table(self):
        if self._is_refreshing:
            return
        self._is_refreshing = True
        try:
            employees = self.data_service.get_employees(active_only=False)

            rows = []
            for emp in employees:
                rows.append((
                    emp.get('id', ''),
                    emp.get('employee_id', ''),
                    emp.get('full_name', ''),
                    emp.get('role', ''),
                    emp.get('badge_number', ''),
                    "Yes" if emp.get('is_active') else "No",
                    "",  # actions column filled below
                ))

            self.table.populate(rows)

            # Attach action buttons per row.
            for row, emp in enumerate(employees):
                btn_widget = QWidget()
                btn_layout = QHBoxLayout(btn_widget)
                btn_layout.setContentsMargins(2, 2, 2, 2)
                btn_layout.setSpacing(4)

                edit_btn = ShadcnButton("Edit", variant="outline", size="sm")
                edit_btn.setFixedWidth(60)
                edit_btn.setAccessibleName(
                    f"Edit {emp.get('full_name', 'employee')}"
                )
                edit_btn.clicked.connect(
                    lambda _, eid=emp['id']: self.edit_employee(eid)
                )
                btn_layout.addWidget(edit_btn)

                if emp.get('is_active', True):
                    del_btn = ShadcnButton(
                        "Deactivate", variant="destructive", size="sm"
                    )
                    del_btn.setFixedWidth(80)
                    del_btn.setAccessibleName(
                        f"Deactivate {emp.get('full_name', 'employee')}"
                    )
                    del_btn.clicked.connect(
                        lambda _, eid=emp['id']: self.delete_employee(eid)
                    )
                    btn_layout.addWidget(del_btn)

                btn_layout.addStretch()
                self.table.setCellWidget(row, 6, btn_widget)
        except Exception as e:
            logger.error(f"Error loading employees: {e}")
            ShadcnToast("Error", description=f"Failed to load employees: {e}",
                        parent=self, variant="destructive")
            self.table.set_error("Could not load employees. Click Refresh to retry.")
        finally:
            self._is_refreshing = False

    def add_employee(self):
        dialog = EmployeeDialog(self.data_service, None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_table()

    def edit_employee(self, emp_id: int):
        employees = self.data_service.get_employees(active_only=False)
        emp = next((e for e in employees if e['id'] == emp_id), None)
        if emp:
            dialog = EmployeeDialog(self.data_service, emp, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh_table()

    def delete_employee(self, emp_id: int):
        employees = self.data_service.get_employees(active_only=False)
        emp = next((e for e in employees if e['id'] == emp_id), None)
        if not emp:
            return

        dialog = ShadcnAlertDialog(
            "Confirm Deactivation",
            f"Deactivate employee '{emp.get('full_name', 'Unknown')}'?",
            action_text="Deactivate",
            destructive=True,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.data_service.deactivate_employee(emp_id)
                self.refresh_table()
                ShadcnToast("Success", description="Employee deactivated",
                            parent=self, variant="success")
            except Exception as e:
                logger.error(f"Deactivation error: {e}")
                ShadcnToast("Error", description=f"Failed to deactivate: {e}",
                            parent=self, variant="destructive")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_N and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.add_employee()
            event.accept()
            return
        if event.key() == Qt.Key.Key_R and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.refresh_table()
            event.accept()
            return
        super().keyPressEvent(event)


class EmployeeDialog(QDialog):
    """Employee dialog with validation and dynamic fields."""

    def __init__(self, data_service, employee_data, parent=None):
        super().__init__(parent)
        self.data_service = data_service
        self.employee_data = employee_data
        self.is_edit = employee_data is not None
        self.theme_manager = ThemeManager()

        self.setWindowTitle("Add Employee" if not self.is_edit else "Edit Employee")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(420)
        self.setAccessibleName(self.windowTitle())
        self.init_ui()

        if self.is_edit:
            self._load_data()

    def init_ui(self):
        tokens = self.theme_manager.get_tokens()
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignRight)

        # Employee ID
        self.emp_id_input = ShadcnInput("e.g., EMP-001")
        self.emp_id_input.setAccessibleName("Employee ID")
        self.emp_id_input.editingFinished.connect(self._validate_emp_id)
        form.addRow("Employee ID *", self.emp_id_input)

        self.emp_id_error = ShadcnCaption("")
        self.emp_id_error.setStyleSheet(f"color: {tokens['destructive']};")
        self.emp_id_error.hide()
        form.addRow("", self.emp_id_error)

        # Name
        self.name_input = ShadcnInput("Full name")
        self.name_input.setAccessibleName("Full name")
        self.name_input.editingFinished.connect(self._validate_name)
        form.addRow("Full Name *", self.name_input)

        self.name_error = ShadcnCaption("")
        self.name_error.setStyleSheet(f"color: {tokens['destructive']};")
        self.name_error.hide()
        form.addRow("", self.name_error)

        # Role
        self.role_combo = QComboBox()
        self.role_combo.setAccessibleName("Role")
        self.role_combo.addItems(
            ['staff', 'security', 'regular', 'maintenance',
             'finance', 'admin']
        )
        form.addRow("Role", self.role_combo)

        # Badge
        self.badge_input = ShadcnInput("Badge number")
        self.badge_input.setAccessibleName("Badge number")
        form.addRow("Badge Number", self.badge_input)

        self.active_check = QCheckBox("Active")
        self.active_check.setChecked(True)
        self.active_check.setAccessibleName("Active")
        form.addRow("", self.active_check)

        # Dynamic fields
        try:
            self.dynamic_fields = self.data_service.get_custom_fields(
                'employee', active_only=True
            )
        except Exception:
            self.dynamic_fields = []
        self.dynamic_widgets = {}

        if self.dynamic_fields:
            dyn_label = QLabel("Additional Information")
            dyn_label.setStyleSheet(
                f"font-weight: 600; color: {tokens['foreground']}; "
                "margin-top: 8px; background: transparent;"
            )
            form.addRow(dyn_label)

            for field in self.dynamic_fields:
                widget = self.create_field_widget(field)
                self.dynamic_widgets[field['field_name']] = (widget, field)
                form.addRow(
                    field['label'] + (" *" if field['required'] else ""),
                    widget,
                )

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        cancel_btn = ShadcnButton("Cancel", variant="outline")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.save_btn = ShadcnButton("Save", variant="default")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save)
        self.save_btn.setMinimumWidth(100)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)
        QTimer.singleShot(0, self.emp_id_input.setFocus)

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
            w = ShadcnInput("example@domain.com")
            return w
        elif dtype == 'phone':
            w = ShadcnInput()
            w.setInputMask('+99 999 999 9999;_')
            return w
        elif dtype == 'dropdown':
            import json
            w = QComboBox()
            try:
                options = json.loads(field.get('dropdown_options', '[]'))
                w.addItems(options)
            except Exception:
                pass
            return w
        elif dtype == 'checkbox':
            return QCheckBox()
        return ShadcnInput()

    def _validate_emp_id(self):
        text = self.emp_id_input.text()
        if not text.strip():
            self.emp_id_error.setText("Employee ID is required")
            self.emp_id_error.show()
        elif re.search(r'[<>\'"]', text):
            self.emp_id_error.setText("Invalid characters in Employee ID")
            self.emp_id_error.show()
        else:
            self.emp_id_error.hide()

    def _validate_name(self):
        text = self.name_input.text()
        if not text.strip():
            self.name_error.setText("Full name is required")
            self.name_error.show()
        elif len(text.strip()) < 2:
            self.name_error.setText("Name must be at least 2 characters")
            self.name_error.show()
        elif re.search(r'[<>\'"]', text):
            self.name_error.setText("Name contains invalid characters")
            self.name_error.show()
        else:
            self.name_error.hide()

    def _load_data(self):
        if not self.employee_data:
            return
        self.emp_id_input.setText(self.employee_data.get('employee_id', ''))
        self.name_input.setText(self.employee_data.get('full_name', ''))
        self.role_combo.setCurrentText(self.employee_data.get('role', ''))
        self.badge_input.setText(self.employee_data.get('badge_number', ''))
        self.active_check.setChecked(
            self.employee_data.get('is_active', True)
        )

        dyn = self.employee_data.get('dynamic_fields', {})
        for fname, (widget, _) in self.dynamic_widgets.items():
            if fname not in dyn:
                continue
            val = dyn[fname]
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(val))
            elif isinstance(widget, QComboBox):
                idx = widget.findText(str(val))
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif hasattr(widget, 'setText'):
                widget.setText(str(val))

    def save(self):
        emp_id = self.emp_id_input.text().strip()
        name = self.name_input.text().strip()

        if not emp_id:
            self._validate_emp_id()
            ShadcnToast("Error", description="Employee ID is required",
                        parent=self, variant="destructive")
            return
        if not name:
            self._validate_name()
            ShadcnToast("Error", description="Full name is required",
                        parent=self, variant="destructive")
            return

        emp_id = self._sanitize_input(emp_id)
        name = self._sanitize_input(name)

        dynamic_data = {}
        errors = []
        for fname, (widget, field) in self.dynamic_widgets.items():
            if field['data_type'] == 'checkbox':
                value = widget.isChecked()
            elif field['data_type'] == 'date':
                value = widget.date().toString('yyyy-MM-dd')
            else:
                value = widget.text().strip() if hasattr(widget, 'text') \
                    else widget.currentText()
                value = self._sanitize_input(value)

            if field['required'] and not value:
                errors.append(f"{field['label']} is required")
            dynamic_data[fname] = value

        if errors:
            ShadcnToast("Validation Error",
                        description="\n".join(errors),
                        parent=self, variant="destructive")
            return

        try:
            if self.is_edit:
                self.data_service.update_employee(
                    self.employee_data['id'],
                    name,
                    self.role_combo.currentText(),
                    self.badge_input.text().strip(),
                    dynamic_data,
                    self.active_check.isChecked(),
                )
                ShadcnToast("Success", description="Employee updated",
                            parent=self, variant="success")
            else:
                self.data_service.add_employee(
                    emp_id,
                    name,
                    self.role_combo.currentText(),
                    self.badge_input.text().strip(),
                    dynamic_data,
                )
                ShadcnToast("Success", description="Employee added",
                            parent=self, variant="success")
            self.accept()
        except Exception as e:
            logger.error(f"Save employee error: {e}")
            ShadcnToast("Error", description=f"Failed to save: {e}",
                        parent=self, variant="destructive")

    def _sanitize_input(self, value) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.save()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)
