# pages/field_config_page.py
"""
Dynamic field configuration page.

Changes in this revision
------------------------
- Delete confirmation is now destructive and labelled "Delete".
- Uses the shared DatabaseManager from DataService.
- Accessible names on inputs.
- Ctrl+N shortcut for Add Field.

Design notes
------------
The initial load_fields() is deferred to showEvent() so the page
constructor stays free of I/O during the login → dashboard swap.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDialog, QFormLayout, QCheckBox, QTextEdit, QTableWidgetItem,
)
from PySide6.QtCore import Signal, QTimer
from PySide6.QtGui import QKeyEvent

from widgets.components import (
    ShadcnDataTable, ShadcnButton, ShadcnInput, ShadcnToast,
    ShadcnAlertDialog, ShadcnComboBox,
)
from core.theme_manager import ThemeManager

import json
import logging

logger = logging.getLogger(__name__)


class FieldConfigPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service
        self.theme_manager = ThemeManager()

        self.db = getattr(data_service, "db", None)
        if self.db is None:
            from database.db_manager import DatabaseManager
            self.db = DatabaseManager()

        self._initial_load_done = False
        self.init_ui()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_load_done:
            self._initial_load_done = True
            QTimer.singleShot(0, self.load_fields)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        selector = QHBoxLayout()
        selector.addWidget(QLabel("Entity:"))
        self.entity_combo = ShadcnComboBox()
        self.entity_combo.addItems(["visitor", "employee"])
        self.entity_combo.currentTextChanged.connect(self.load_fields)
        self.entity_combo.setAccessibleName("Entity type")
        selector.addWidget(self.entity_combo)
        selector.addStretch()

        self.add_btn = ShadcnButton("Add Field", variant="default")
        self.add_btn.setToolTip("Add a custom field (Ctrl+N)")
        self.add_btn.clicked.connect(self.add_field)
        selector.addWidget(self.add_btn)
        layout.addLayout(selector)

        self.table = ShadcnDataTable(
            ["ID", "Field Name", "Label", "Data Type",
             "Required", "Actions"],
            numeric_columns=[0],
            empty_message="No custom fields defined for this entity.",
        )
        self.table.setColumnWidth(5, 140)
        layout.addWidget(self.table)

    def load_fields(self):
        entity = self.entity_combo.currentText()
        try:
            fields = self.db.get_custom_fields(entity, active_only=False)
        except Exception as e:
            logger.error(f"Failed to load fields: {e}")
            self.table.set_error("Could not load custom fields.")
            return

        rows = []
        for f in fields:
            rows.append((
                f['id'],
                f['field_name'],
                f['label'],
                f['data_type'],
                "Yes" if f['required'] else "No",
                "",
            ))
        self.table.populate(rows)

        for row, f in enumerate(fields):
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.setSpacing(4)

            edit_btn = ShadcnButton("Edit", variant="outline", size="sm")
            edit_btn.setAccessibleName(f"Edit field {f['label']}")
            edit_btn.clicked.connect(
                lambda _, fid=f['id']: self.edit_field(fid)
            )
            btn_layout.addWidget(edit_btn)

            del_btn = ShadcnButton("Delete", variant="destructive", size="sm")
            del_btn.setAccessibleName(f"Delete field {f['label']}")
            del_btn.clicked.connect(
                lambda _, fid=f['id']: self.delete_field(fid)
            )
            btn_layout.addWidget(del_btn)

            btn_layout.addStretch()
            self.table.setCellWidget(row, 5, btn_widget)

    def add_field(self):
        dialog = FieldDialog(self.db, self.entity_combo.currentText(),
                             None, self)
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
        dialog = ShadcnAlertDialog(
            "Confirm Delete",
            "Delete this field permanently? This cannot be undone.",
            cancel_text="Cancel",
            action_text="Delete",
            destructive=True,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.db.delete_custom_field(
                    self.entity_combo.currentText(), field_id
                )
                self.load_fields()
                ShadcnToast("Success", description="Field deleted",
                            parent=self, variant="success")
            except Exception as e:
                ShadcnToast("Error", description=f"Failed to delete: {e}",
                            parent=self, variant="destructive")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_N and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.add_field()
            event.accept()
            return
        super().keyPressEvent(event)


class FieldDialog(QDialog):
    def __init__(self, db, entity_type, field_data, parent=None):
        super().__init__(parent)
        self.db = db
        self.entity_type = entity_type
        self.field_data = field_data
        self.theme_manager = ThemeManager()

        self.setWindowTitle("Add Field" if not field_data else "Edit Field")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setAccessibleName(self.windowTitle())
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        form = QFormLayout()
        form.setSpacing(12)

        self.field_name = ShadcnInput()
        self.field_name.setAccessibleName("Internal field name")
        self.label = ShadcnInput()
        self.label.setAccessibleName("Display label")

        self.data_type = ShadcnComboBox()
        self.data_type.addItems([
            'text', 'number', 'date', 'email', 'phone', 'dropdown', 'checkbox'
        ])
        self.data_type.setAccessibleName("Data type")

        self.required = QCheckBox("Required")
        self.required.setAccessibleName("Required")

        self.regex = ShadcnInput("Optional regex validation")
        self.regex.setAccessibleName("Validation regex")

        self.options = QTextEdit()
        self.options.setPlaceholderText("One option per line (for dropdown)")
        self.options.setAccessibleName("Dropdown options")
        self.options.setVisible(False)

        form.addRow("Internal Field Name (snake_case):", self.field_name)
        form.addRow("Display Label:", self.label)
        form.addRow("Data Type:", self.data_type)
        form.addRow("", self.required)
        form.addRow("Validation Regex:", self.regex)
        form.addRow("Dropdown Options:", self.options)

        self.data_type.currentTextChanged.connect(self.toggle_options)
        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = ShadcnButton("Cancel", variant="outline")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = ShadcnButton("Save", variant="default")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.save)
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
                try:
                    opts_list = json.loads(opts)
                    self.options.setPlainText('\n'.join(opts_list))
                except Exception:
                    pass

    def toggle_options(self, dtype):
        self.options.setVisible(dtype == 'dropdown')

    def save(self):
        fname = self.field_name.text().strip().lower().replace(' ', '_')
        label = self.label.text().strip()
        dtype = self.data_type.currentText()
        required = self.required.isChecked()
        regex = self.regex.text().strip()

        if not fname or not label:
            ShadcnToast("Error",
                        description="Field name and label are required",
                        parent=self, variant="destructive")
            return

        opts_json = None
        if dtype == 'dropdown':
            opts = [
                line.strip()
                for line in self.options.toPlainText().split('\n')
                if line.strip()
            ]
            opts_json = json.dumps(opts)

        data = {
            'field_name': fname,
            'label': label,
            'data_type': dtype,
            'required': required,
            'validation_regex': regex,
            'dropdown_options': opts_json,
            'display_order': 0,
        }
        field_id = self.field_data['id'] if self.field_data else -1
        try:
            self.db.save_custom_field(self.entity_type, field_id, data)
            ShadcnToast("Success", description="Field saved",
                        parent=self, variant="success")
            self.accept()
        except Exception as e:
            ShadcnToast("Error", description=f"Failed to save: {e}",
                        parent=self, variant="destructive")

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
