# pages/field_config_page.py
# This page still uses local db (no API), so it remains unchanged except we pass data_service but ignore it.
# For now, we keep it as is, but we could add sync later.

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QDialog, QFormLayout, QCheckBox,
                               QTextEdit, QTableWidgetItem)
from PySide6.QtCore import Signal
from database.db_manager import DatabaseManager
from widgets.components import ShadcnDataTable, ShadcnButton, ShadcnInput, ShadcnToast, ShadcnAlertDialog
import json

class FieldConfigPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service  # not used, but kept for consistency
        self.db = DatabaseManager()  # still using local db
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Entity selector
        selector = QHBoxLayout()
        selector.addWidget(QLabel("Entity:"))
        self.entity_combo = QComboBox()
        self.entity_combo.addItems(["visitor", "employee"])
        self.entity_combo.currentTextChanged.connect(self.load_fields)
        selector.addWidget(self.entity_combo)
        selector.addStretch()
        self.add_btn = ShadcnButton("Add Field", variant="default")
        self.add_btn.clicked.connect(self.add_field)
        selector.addWidget(self.add_btn)
        layout.addLayout(selector)

        self.table = ShadcnDataTable(["ID", "Field Name", "Label", "Data Type", "Required", "Actions"])
        self.table.setColumnWidth(5, 120)
        layout.addWidget(self.table)
        self.load_fields()

    def load_fields(self):
        entity = self.entity_combo.currentText()
        fields = self.db.get_custom_fields(entity, active_only=False)
        self.table.setRowCount(len(fields))
        for row, f in enumerate(fields):
            self.table.setItem(row, 0, QTableWidgetItem(str(f['id'])))
            self.table.setItem(row, 1, QTableWidgetItem(f['field_name']))
            self.table.setItem(row, 2, QTableWidgetItem(f['label']))
            self.table.setItem(row, 3, QTableWidgetItem(f['data_type']))
            self.table.setItem(row, 4, QTableWidgetItem("Yes" if f['required'] else "No"))
            # Actions
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            edit_btn = ShadcnButton("Edit", variant="outline", size="sm")
            edit_btn.clicked.connect(lambda _, fid=f['id']: self.edit_field(fid))
            del_btn = ShadcnButton("Delete", variant="destructive", size="sm")
            del_btn.clicked.connect(lambda _, fid=f['id']: self.delete_field(fid))
            btn_layout.addWidget(edit_btn)
            btn_layout.addWidget(del_btn)
            self.table.setCellWidget(row, 5, btn_widget)

    def add_field(self):
        dialog = FieldDialog(self.db, self.entity_combo.currentText(), None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_fields()

    def edit_field(self, field_id):
        entity = self.entity_combo.currentText()
        field = self.db.get_custom_field_by_id(entity, field_id)
        if field:
            dialog = FieldDialog(self.db, entity, field, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.load_fields()

    def delete_field(self, field_id):
        if ShadcnAlertDialog("Confirm Delete", "Delete this field permanently?", parent=self).exec() == QDialog.DialogCode.Accepted:
            self.db.delete_custom_field(self.entity_combo.currentText(), field_id)
            self.load_fields()
            ShadcnToast("Success", "Field deleted", parent=self)


class FieldDialog(QDialog):
    def __init__(self, db, entity_type, field_data, parent=None):
        super().__init__(parent)
        self.db = db
        self.entity_type = entity_type
        self.field_data = field_data
        self.setWindowTitle("Add Field" if not field_data else "Edit Field")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        form = QFormLayout()
        form.setSpacing(12)

        self.field_name = ShadcnInput()
        self.label = ShadcnInput()
        self.data_type = QComboBox()
        self.data_type.addItems(['text', 'number', 'date', 'email', 'phone', 'dropdown', 'checkbox'])
        self.required = QCheckBox("Required")
        self.regex = ShadcnInput()
        self.regex.setPlaceholderText("Optional regex validation")
        self.options = QTextEdit()
        self.options.setPlaceholderText("One option per line (for dropdown)")
        self.options.setVisible(False)

        form.addRow("Internal Field Name (snake_case):", self.field_name)
        form.addRow("Display Label:", self.label)
        form.addRow("Data Type:", self.data_type)
        form.addRow("", self.required)
        form.addRow("Validation Regex:", self.regex)
        form.addRow("Dropdown Options:", self.options)

        self.data_type.currentTextChanged.connect(self.toggle_options)
        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        cancel_btn = ShadcnButton("Cancel", variant="outline")
        cancel_btn.clicked.connect(self.reject)
        save_btn = ShadcnButton("Save", variant="default")
        save_btn.clicked.connect(self.save)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        if self.field_data:
            self.field_name.setText(self.field_data['field_name'])
            self.label.setText(self.field_data['label'])
            self.data_type.setCurrentText(self.field_data['data_type'])
            self.required.setChecked(self.field_data['required'])
            self.regex.setText(self.field_data.get('validation_regex', ''))
            opts = self.field_data.get('dropdown_options', '[]')
            if opts and opts != '[]':
                opts_list = json.loads(opts)
                self.options.setPlainText('\n'.join(opts_list))

    def toggle_options(self, dtype):
        self.options.setVisible(dtype == 'dropdown')

    def save(self):
        fname = self.field_name.text().strip().lower().replace(' ', '_')
        label = self.label.text().strip()
        dtype = self.data_type.currentText()
        required = self.required.isChecked()
        regex = self.regex.text().strip()
        opts_json = None
        if dtype == 'dropdown':
            opts = [line.strip() for line in self.options.toPlainText().split('\n') if line.strip()]
            opts_json = json.dumps(opts)
        if not fname or not label:
            ShadcnToast("Error", "Field name and label required", parent=self)
            return
        data = {
            'field_name': fname,
            'label': label,
            'data_type': dtype,
            'required': required,
            'validation_regex': regex,
            'dropdown_options': opts_json,
            'display_order': 0
        }
        field_id = self.field_data['id'] if self.field_data else -1
        self.db.save_custom_field(self.entity_type, field_id, data)
        ShadcnToast("Success", "Field saved", parent=self)
        self.accept()
