# pages/visitors_page.py
"""
Enterprise visitor management page with validation and async operations.

Host source
-----------
The "Host Employee" dropdown is populated from the active user list
(GET /users) rather than the separate employees collection. Active users
are shown sorted by full name. If the users endpoint cannot be reached
(for example while offline), the page falls back to the local employee
list so check-in still works.

Theme integration
-----------------
This page registers with ThemeManager so the tab bar, its panes, and the
check-in scroll area repaint using the current token palette. Without
this, QTabWidget's pane paints using the default Qt palette (usually the
window color from the previous theme), leaking gray/white backgrounds.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QFormLayout,
    QComboBox, QCheckBox, QDateEdit, QDialog,
    QTableWidgetItem, QFrame, QLabel, QScrollArea, QSizePolicy,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer, QSize
from PySide6.QtGui import QDoubleValidator, QKeyEvent

from pages.base_page import BasePage
from widgets.components import (
    ShadcnDataTable, ShadcnButton, ShadcnInput,
    ShadcnCard, CardContent, ShadcnToast, ShadcnAlertDialog,
    ShadcnCaption, ShadcnBadge,
)
from dialogs.visitor_checkout_dialog import VisitorCheckoutDialog
from core.theme_manager import ThemeManager
from datetime import datetime
import csv
import re
import logging

logger = logging.getLogger(__name__)


class VisitorsPage(BasePage):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        self.data_service = data_service
        self.theme_manager = ThemeManager()
        self._is_checking_in = False
        self._visitor_cache = []
        self._initial_load_done = False
        super().__init__(user_info, permissions, page_id="visitors")

        # Re-register for theme updates so the tab widget repaints.
        try:
            self.theme_manager.register_widget(
                self, on_theme_changed=self._apply_theme
            )
        except Exception as e:
            logger.debug(f"ThemeManager registration failed: {e}")

        # Paint once now that the UI exists.
        self._apply_theme()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self, *_):
        """Paint page, tab widget, panes and check-in scroll area."""
        try:
            tokens = self.theme_manager.get_tokens()
            bg = tokens.get("background", "#F8FAFC")
            fg = tokens.get("foreground", "#0F172A")
            border = tokens.get("border", "#E2E8F0")
            surface = tokens.get("surface", bg)
            primary = tokens.get("primary", "#006B3F")
            muted_fg = tokens.get("muted-foreground", "#64748B")

            self.setStyleSheet(f"background-color: {bg};")

            if hasattr(self, "tabs"):
                self.tabs.setStyleSheet(f"""
                    QTabWidget::pane {{
                        background-color: {bg};
                        border: none;
                        top: -1px;
                    }}
                    QTabWidget > QWidget {{
                        background-color: {bg};
                    }}
                    QTabBar {{
                        background-color: {bg};
                    }}
                    QTabBar::tab {{
                        background: transparent;
                        color: {muted_fg};
                        padding: 8px 18px;
                        margin-right: 4px;
                        border: none;
                        border-bottom: 2px solid transparent;
                        font-weight: 500;
                    }}
                    QTabBar::tab:selected {{
                        color: {primary};
                        border-bottom: 2px solid {primary};
                    }}
                    QTabBar::tab:hover {{
                        color: {fg};
                    }}
                """)

            for pane in (getattr(self, "checkin_tab", None),
                         getattr(self, "active_tab", None),
                         getattr(self, "history_tab", None)):
                if pane is not None:
                    pane.setStyleSheet(f"background-color: {bg};")

            if hasattr(self, "checkin_tab"):
                for scroll in self.checkin_tab.findChildren(QScrollArea):
                    scroll.setStyleSheet(
                        f"QScrollArea {{ background: {bg}; border: none; }}"
                        f"QScrollArea > QWidget > QWidget "
                        f"{{ background: {bg}; }}"
                    )
        except Exception as e:
            logger.debug(f"_apply_theme failed: {e}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_theme()
        if not self._initial_load_done:
            self._initial_load_done = True
            QTimer.singleShot(0, self._initial_load)

    def _initial_load(self):
        try:
            self.refresh_host_list()
        except Exception as e:
            logger.debug(f"Failed to load host list: {e}")
        try:
            self.refresh_active_tab()
        except Exception as e:
            logger.debug(f"Failed to load active visitors: {e}")
        try:
            self.refresh_history_tab()
        except Exception as e:
            logger.debug(f"Failed to load visitor history: {e}")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

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

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh_active)

    def setup_checkin_tab(self):
        layout = QVBoxLayout(self.checkin_tab)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(24)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        form_container = QWidget()
        form_container.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground, True
        )
        form_layout = QVBoxLayout(form_container)
        form_layout.setSpacing(24)

        card = ShadcnCard()
        card.setMaximumWidth(850)
        card.setMinimumWidth(400)
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        content = CardContent()
        basic_layout = QFormLayout()
        basic_layout.setSpacing(16)
        basic_layout.setLabelAlignment(Qt.AlignRight)

        self.name_input = ShadcnInput("Full name")
        self.name_input.setAccessibleName("Visitor name")
        self.name_input.editingFinished.connect(self._validate_name)
        basic_layout.addRow("Visitor Name *", self.name_input)

        self.name_error = ShadcnCaption("")
        tokens = self.theme_manager.get_tokens()
        self.name_error.setStyleSheet(f"color: {tokens['destructive']};")
        self.name_error.hide()
        basic_layout.addRow("", self.name_error)

        self.host_combo = QComboBox()
        self.host_combo.setAccessibleName("Host employee")
        self.host_combo.addItem("Select Host", -1)
        basic_layout.addRow("Host Employee *", self.host_combo)

        self.consent_check = QCheckBox(
            "I consent to GDPR data storage for 30 days"
        )
        self.consent_check.setAccessibleName("GDPR consent")
        basic_layout.addRow("", self.consent_check)

        content.layout.addLayout(basic_layout)

        self.dynamic_fields = self._load_custom_fields_safe('visitor')
        self.dynamic_widgets = {}

        if self.dynamic_fields:
            dyn_layout = QFormLayout()
            dyn_layout.setSpacing(12)
            dyn_layout.setLabelAlignment(Qt.AlignRight)
            for field in self.dynamic_fields:
                widget = self.create_field_widget(field)
                self.dynamic_widgets[field['field_name']] = (widget, field)
                dyn_layout.addRow(
                    field['label'] + (" *" if field['required'] else ""),
                    widget,
                )
            content.layout.addLayout(dyn_layout)

        card.set_content(content)
        form_layout.addWidget(card)

        btn_container = QHBoxLayout()
        btn_container.addStretch()

        clear_btn = ShadcnButton("Clear", variant="outline", size="lg")
        clear_btn.setMinimumWidth(120)
        clear_btn.setMinimumHeight(44)
        clear_btn.clicked.connect(self._clear_checkin_form)
        btn_container.addWidget(clear_btn)

        btn_container.addSpacing(10)

        self.checkin_btn = ShadcnButton(
            "Check In Visitor", variant="default", size="lg"
        )
        self.checkin_btn.setMinimumWidth(220)
        self.checkin_btn.setMinimumHeight(44)
        self.checkin_btn.setToolTip("Check in a new visitor (Ctrl+Enter)")
        self.checkin_btn.clicked.connect(self.check_in)
        btn_container.addWidget(self.checkin_btn)
        btn_container.addStretch()

        form_layout.addLayout(btn_container)

        scroll.setWidget(form_container)
        layout.addWidget(scroll)

    def _load_custom_fields_safe(self, entity_type: str):
        try:
            return self.data_service.get_custom_fields(
                entity_type, active_only=True
            )
        except Exception as e:
            logger.warning(f"Failed to load custom fields: {e}")
            return []

    def _validate_name(self):
        text = self.name_input.text()
        if not text.strip():
            self.name_error.setText("Name is required")
            self.name_error.show()
        elif len(text.strip()) < 2:
            self.name_error.setText("Name must be at least 2 characters")
            self.name_error.show()
        elif re.search(r'[<>\'"]', text):
            self.name_error.setText("Name contains invalid characters")
            self.name_error.show()
        else:
            self.name_error.hide()

    def create_field_widget(self, field):
        dtype = field['data_type']
        if dtype == 'text':
            return ShadcnInput()
        if dtype == 'number':
            w = ShadcnInput()
            w.setValidator(QDoubleValidator())
            return w
        if dtype == 'date':
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDate(QDate.currentDate())
            return w
        if dtype == 'email':
            return ShadcnInput("example@domain.com")
        if dtype == 'phone':
            w = ShadcnInput()
            w.setInputMask('+99 999 999 9999;_')
            return w
        if dtype == 'dropdown':
            import json
            w = QComboBox()
            try:
                options = json.loads(field.get('dropdown_options', '[]'))
                w.addItems(options)
            except Exception:
                pass
            return w
        if dtype == 'checkbox':
            return QCheckBox()
        return ShadcnInput()

    # ------------------------------------------------------------------
    # Host list
    #
    # Preferred source is the active user list (GET /users). The fallback
    # to the local employee list keeps check-in working when offline.
    # ------------------------------------------------------------------

    def _fetch_hosts(self):
        """
        Return a list of (id, display_name) tuples for the host dropdown.

        Primary source: active users from the API, sorted by full name.
        Fallback: local employee list from the DB (used when the users
        endpoint is unreachable).
        """
        # Preferred: active users, sorted by display name.
        try:
            users = self.data_service.get_users() or []
            active = [u for u in users if u.get("is_active", True)]
            active.sort(key=lambda u: (
                u.get("full_name") or u.get("username") or ""
            ).lower())

            result = []
            for u in active:
                uid = u.get("id")
                display = u.get("full_name") or u.get("username") or ""
                if uid and display:
                    result.append((uid, display))

            if result:
                return result
            logger.debug("Users endpoint returned no active users; "
                         "trying local employee fallback")
        except Exception as e:
            logger.info(
                f"Host list from users failed ({e}); "
                f"falling back to local employee list"
            )

        # Fallback: local employees table.
        try:
            return list(self.data_service.get_employees_list_for_host() or [])
        except Exception as e:
            logger.error(f"Fallback host list failed: {e}")
            return []

    def refresh_host_list(self):
        current = self.host_combo.currentData()
        self.host_combo.blockSignals(True)
        self.host_combo.clear()
        self.host_combo.addItem("Select Host", -1)

        try:
            hosts = self._fetch_hosts()
            for uid, display in hosts:
                self.host_combo.addItem(display, uid)
            logger.info(f"Loaded {len(hosts)} host entries")
        except Exception as e:
            logger.error(f"Error loading host list: {e}")
        finally:
            # Restore previous selection if it still exists.
            if current is not None:
                idx = self.host_combo.findData(current)
                if idx >= 0:
                    self.host_combo.setCurrentIndex(idx)
            self.host_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Check-in
    # ------------------------------------------------------------------

    def _sanitize_input(self, value) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def check_in(self):
        if self._is_checking_in:
            return

        name = self.name_input.text().strip()
        if not name or len(name) < 2:
            ShadcnToast("Error",
                        description="Please enter a valid visitor name",
                        parent=self, variant="destructive")
            return
        name = self._sanitize_input(name)

        host_id = self.host_combo.currentData()
        if host_id == -1:
            ShadcnToast("Error",
                        description="Please select a host employee",
                        parent=self, variant="destructive")
            return

        if not self.consent_check.isChecked():
            ShadcnToast("Error",
                        description="GDPR consent is required",
                        parent=self, variant="destructive")
            return

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

        self._is_checking_in = True
        self.checkin_btn.set_loading(True, "Checking in…")

        try:
            visitor_id = self.data_service.check_in_visitor(
                name, host_id, dynamic_data, True
            )
            if visitor_id:
                ShadcnToast(
                    "Success",
                    description=f"{name} checked in at "
                                f"{datetime.now().strftime('%H:%M:%S')}",
                    parent=self, variant="success",
                )
                self._clear_checkin_form()
                self.tabs.setCurrentIndex(1)
                self.refresh_active_tab()
        except Exception as e:
            logger.error(f"Check-in error: {e}")
            ShadcnToast("Error", description=f"Check-in failed: {e}",
                        parent=self, variant="destructive")
        finally:
            self._is_checking_in = False
            self.checkin_btn.set_loading(False)

    def _clear_checkin_form(self):
        self.name_input.clear()
        self.host_combo.setCurrentIndex(0)
        self.consent_check.setChecked(False)
        for w, _ in self.dynamic_widgets.values():
            if isinstance(w, ShadcnInput):
                w.clear()
            elif isinstance(w, QDateEdit):
                w.setDate(QDate.currentDate())
            elif isinstance(w, QComboBox):
                w.setCurrentIndex(0)
        self.name_error.hide()

    # ------------------------------------------------------------------
    # Active visitors tab
    # ------------------------------------------------------------------

    def setup_active_tab(self):
        layout = QVBoxLayout(self.active_tab)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)

        self.active_status = ShadcnBadge("Active", variant="secondary")
        toolbar.addWidget(self.active_status)

        toolbar.addStretch()

        refresh_btn = ShadcnButton("Refresh", variant="outline", size="sm")
        refresh_btn.setMinimumWidth(100)
        refresh_btn.setToolTip("Refresh active visitors (Ctrl+R)")
        refresh_btn.clicked.connect(self.refresh_active_tab)
        toolbar.addWidget(refresh_btn)

        export_btn = ShadcnButton("Export", variant="outline", size="sm")
        export_btn.setMinimumWidth(100)
        export_btn.clicked.connect(self.export_active_list)
        toolbar.addWidget(export_btn)

        layout.addLayout(toolbar)

        self.active_table = ShadcnDataTable(
            ["ID", "Name", "Check-in Time", "Host", "Action"],
            numeric_columns=[0],
            empty_message="No visitors are currently checked in.",
        )
        self.active_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.active_table.setMinimumHeight(300)
        self.active_table.setColumnWidth(0, 60)
        self.active_table.setColumnWidth(1, 200)
        self.active_table.setColumnWidth(2, 180)
        self.active_table.setColumnWidth(3, 180)

        self.active_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.active_table.installEventFilter(self)

        layout.addWidget(self.active_table)

    def eventFilter(self, obj, event):
        if obj is self.active_table and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                selected = self.active_table.get_selected_rows()
                if selected:
                    visitors = self._visitor_cache
                    if selected[0] < len(visitors):
                        vid = visitors[selected[0]].get('id')
                        if vid:
                            self.check_out(vid)
                            return True
        return super().eventFilter(obj, event)

    def refresh_active_tab(self):
        try:
            visitors = self.data_service.get_active_visitors()
            self._visitor_cache = visitors

            rows = []
            for v in visitors:
                check_in = v.get('check_in_time', '')
                rows.append((
                    v.get('id', ''),
                    v.get('visitor_name', ''),
                    check_in[:19] if check_in else "",
                    v.get('host_name', 'Unknown'),
                    "",
                ))
            self.active_table.populate(rows)

            for row, v in enumerate(visitors):
                btn = ShadcnButton("Check Out", variant="outline", size="sm")
                btn.setMinimumWidth(90)
                btn.setAccessibleName(
                    f"Check out {v.get('visitor_name', 'visitor')}"
                )
                btn.clicked.connect(
                    lambda _, vid=v['id']: self.check_out(vid)
                )
                self.active_table.setCellWidget(row, 4, btn)

            count = len(visitors)
            self.active_status.setText(
                f"{count} Active" if count > 0 else "No Active"
            )
            self.active_status.variant = "success" if count > 0 else "secondary"
            self.active_status.update_theme()

            if not self._refresh_timer.isActive():
                self._refresh_timer.start(30000)

        except Exception as e:
            logger.error(f"Error refreshing active visitors: {e}")
            self.active_table.set_error(
                "Could not load active visitors. Click Refresh to retry."
            )
            self.active_status.setText("Error")
            self.active_status.variant = "destructive"
            self.active_status.update_theme()

    def check_out(self, visitor_id: int):
        try:
            dialog = VisitorCheckoutDialog(visitor_id, self.data_service, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh_active_tab()
                self.refresh_history_tab()
                ShadcnToast("Success",
                            description="Visitor checked out",
                            parent=self, variant="success")
        except Exception as e:
            logger.error(f"Checkout error: {e}")
            ShadcnToast("Error", description=f"Checkout failed: {e}",
                        parent=self, variant="destructive")

    def export_active_list(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Active Visitors",
                f"active_visitors_{datetime.now().strftime('%Y%m%d')}.csv",
                "CSV Files (*.csv)",
            )
            if not file_path:
                return

            data = []
            for row in range(self.active_table.rowCount()):
                row_data = []
                for col in range(self.active_table.columnCount() - 1):
                    item = self.active_table.item(row, col)
                    row_data.append(item.text() if item else "")
                data.append(row_data)

            if not data:
                ShadcnToast("Info", description="No data to export",
                            parent=self)
                return

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "Name", "Check-in Time", "Host"])
                writer.writerows(data)

            ShadcnToast("Success",
                        description=f"Exported {len(data)} records",
                        parent=self, variant="success")

        except Exception as e:
            logger.error(f"Export error: {e}")
            ShadcnToast("Error", description=f"Failed to export: {e}",
                        parent=self, variant="destructive")

    # ------------------------------------------------------------------
    # History tab
    # ------------------------------------------------------------------

    def setup_history_tab(self):
        layout = QVBoxLayout(self.history_tab)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)

        self.search_input = ShadcnInput("Search visitors...")
        self.search_input.setAccessibleName("Search visitor history")
        self.search_input.setMaximumWidth(350)
        self.search_input.textChanged.connect(self.filter_history)
        toolbar.addWidget(self.search_input)

        toolbar.addStretch()

        refresh_btn = ShadcnButton("Refresh", variant="outline", size="sm")
        refresh_btn.setMinimumWidth(100)
        refresh_btn.clicked.connect(self.refresh_history_tab)
        toolbar.addWidget(refresh_btn)

        export_btn = ShadcnButton("Export", variant="outline", size="sm")
        export_btn.setMinimumWidth(100)
        export_btn.clicked.connect(self.export_history)
        toolbar.addWidget(export_btn)

        layout.addLayout(toolbar)

        self.history_table = ShadcnDataTable(
            ["ID", "Name", "Check-in", "Check-out", "Host", "Duration"],
            numeric_columns=[0],
            empty_message="No visitor history to show.",
        )
        self.history_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.history_table.setMinimumHeight(300)
        self.history_table.setColumnWidth(0, 60)
        self.history_table.setColumnWidth(1, 180)
        self.history_table.setColumnWidth(2, 180)
        self.history_table.setColumnWidth(3, 180)
        self.history_table.setColumnWidth(4, 160)

        layout.addWidget(self.history_table)

    def refresh_history_tab(self):
        try:
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
                    except Exception:
                        pass
                data.append((
                    row[0],
                    row[1],
                    check_in[:19] if check_in else "",
                    check_out[:19] if check_out else "",
                    row[5] or "",
                    duration,
                ))
            self.history_table.populate(data)
        except Exception as e:
            logger.error(f"Error refreshing history: {e}")
            self.history_table.set_error(
                "Could not load visitor history. Click Refresh to retry."
            )

    def filter_history(self, text: str):
        if not text:
            self.history_table.show_all_rows()
            return

        text = text.lower()
        for row in range(self.history_table.rowCount()):
            match = False
            for col in range(self.history_table.columnCount()):
                item = self.history_table.item(row, col)
                if item and text in item.text().lower():
                    match = True
                    break
            self.history_table.setRowHidden(row, not match)

    def export_history(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Visitor History",
                f"visitor_history_{datetime.now().strftime('%Y%m%d')}.csv",
                "CSV Files (*.csv)",
            )
            if not file_path:
                return

            data = []
            for row in range(self.history_table.rowCount()):
                if self.history_table.isRowHidden(row):
                    continue
                row_data = []
                for col in range(self.history_table.columnCount()):
                    item = self.history_table.item(row, col)
                    row_data.append(item.text() if item else "")
                data.append(row_data)

            if not data:
                ShadcnToast("Info", description="No data to export",
                            parent=self)
                return

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "Name", "Check-in", "Check-out",
                                 "Host", "Duration"])
                writer.writerows(data)

            ShadcnToast("Success",
                        description=f"Exported {len(data)} records",
                        parent=self, variant="success")

        except Exception as e:
            logger.error(f"Export error: {e}")
            ShadcnToast("Error", description=f"Failed to export: {e}",
                        parent=self, variant="destructive")

    # ------------------------------------------------------------------
    # Navigation + shortcuts
    # ------------------------------------------------------------------

    def on_tab_changed(self, index: int):
        if not self._initial_load_done:
            return
        if index == 1:
            self.refresh_active_tab()
        elif index == 2:
            self.refresh_history_tab()
        elif index == 0:
            self.refresh_host_list()

    def _auto_refresh_active(self):
        if self.tabs.currentIndex() == 1:
            self.refresh_active_tab()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Return and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            if self.tabs.currentIndex() == 0:
                self.check_in()
            event.accept()
            return
        if event.key() == Qt.Key.Key_R and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.refresh_active_tab()
            event.accept()
            return
        super().keyPressEvent(event)

    def cleanup(self):
        if hasattr(self, '_refresh_timer') and self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer.deleteLater()
