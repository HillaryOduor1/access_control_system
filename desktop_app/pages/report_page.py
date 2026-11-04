# pages/report_page.py
"""
Reports page.

Theming
-------
Section headers and stat-card text now use ShadcnHeading and ShadcnCaption
so they re-theme automatically when the user toggles the theme. This
replaces the previous pattern of plain QLabels with hardcoded colors,
which went stale on theme toggle.

Design notes
------------
The initial refresh is deferred to showEvent(), and the auto-refresh
timer only starts after the first successful load.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QSizePolicy, QFileDialog,
)
from PySide6.QtCore import Signal, QTimer, Qt, QThread, QObject, Slot
from PySide6.QtGui import QKeyEvent

from widgets.components import (
    ShadcnCard, CardContent, ShadcnDataTable, ShadcnButton, ShadcnToast,
    ShadcnHeading, ShadcnCaption,
)
from core.theme_manager import ThemeManager
from datetime import datetime, timedelta
from collections import defaultdict
import csv
import logging

logger = logging.getLogger(__name__)


class _ReportWorker(QObject):
    """Runs the report data collection off the UI thread."""

    finished = Signal(dict, list, list)
    failed = Signal(str)

    def __init__(self, data_service):
        super().__init__()
        self.data_service = data_service

    @Slot()
    def run(self):
        try:
            result = {"stats": {}, "history": [], "employees": []}

            try:
                result["stats"] = self.data_service.get_dashboard_stats()
            except Exception as e:
                logger.debug(f"Stats error: {e}")

            try:
                history = self.data_service.get_visitor_history(limit=500)
                by_date = defaultdict(
                    lambda: {'ins': 0, 'outs': 0, 'durations': []}
                )
                for row in history:
                    if not row[2]:
                        continue
                    date = row[2][:10]
                    by_date[date]['ins'] += 1
                    if row[3]:
                        by_date[date]['outs'] += 1
                        try:
                            t1 = datetime.fromisoformat(row[2])
                            t2 = datetime.fromisoformat(row[3])
                            hours = (t2 - t1).total_seconds() / 3600
                            by_date[date]['durations'].append(hours)
                        except Exception:
                            pass

                last_7 = []
                total_durations = []
                for i in range(7):
                    d = (datetime.now() - timedelta(days=i)).date().isoformat()
                    data = by_date.get(d, {'ins': 0, 'outs': 0, 'durations': []})
                    avg = (sum(data['durations']) / len(data['durations'])
                           if data['durations'] else 0)
                    total_durations.extend(data['durations'])
                    last_7.append((d, data['ins'], data['outs'], f"{avg:.1f}"))

                overall_avg = (sum(total_durations) / len(total_durations)
                               if total_durations else 0)
                result["history"] = last_7
                result["overall_avg"] = overall_avg
            except Exception as e:
                logger.debug(f"History error: {e}")

            try:
                employees = self.data_service.get_employees(active_only=True)
                today = datetime.now().date().isoformat()
                logs = self.data_service.get_access_logs({
                    "date_from": f"{today} 00:00:00",
                    "date_to": f"{today} 23:59:59",
                })
                entries_today = defaultdict(int)
                last_entry = {}
                for log in logs:
                    if len(log) > 3 and log[1] == 'employee' and log[3] == 'in':
                        emp_id = log[2]
                        entries_today[emp_id] += 1
                        if len(log) > 4:
                            last_entry[emp_id] = log[4]

                emp_data = []
                for emp in employees:
                    emp_id = emp.get('id')
                    emp_data.append((
                        emp.get('full_name', 'Unknown'),
                        emp.get('role', ''),
                        last_entry.get(emp_id, 'Never')[:19]
                            if last_entry.get(emp_id) else 'Never',
                        entries_today.get(emp_id, 0),
                    ))
                result["employees"] = emp_data
            except Exception as e:
                logger.debug(f"Employee error: {e}")

            self.finished.emit(
                result.get("stats", {}),
                result.get("history", []),
                result.get("employees", []),
            )
        except Exception as e:
            logger.error(f"Report worker failed: {e}")
            self.failed.emit(str(e))


class ReportPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service
        self.theme_manager = ThemeManager()
        self._is_refreshing = False
        self._is_closing = False
        self._initial_load_done = False
        self._thread = None
        self._worker = None

        self.init_ui()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_all)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_load_done:
            self._initial_load_done = True
            QTimer.singleShot(0, self._on_first_show)

    def _on_first_show(self):
        try:
            self.refresh_all()
        finally:
            if not self.refresh_timer.isActive():
                self.refresh_timer.start(60000)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.refresh_btn = ShadcnButton("Refresh", variant="outline", size="sm")
        self.refresh_btn.setMinimumWidth(100)
        self.refresh_btn.clicked.connect(self.refresh_all)
        toolbar.addWidget(self.refresh_btn)

        export_btn = ShadcnButton("Export Report", variant="outline", size="sm")
        export_btn.setMinimumWidth(120)
        export_btn.clicked.connect(self.export_report)
        toolbar.addWidget(export_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs)

        self.stats_tab = QWidget()
        self.setup_stats_tab()
        self.tabs.addTab(self.stats_tab, "Visitor Analytics")

        self.emp_tab = QWidget()
        self.setup_employee_tab()
        self.tabs.addTab(self.emp_tab, "Employee Activity")

    def setup_stats_tab(self):
        layout = QVBoxLayout(self.stats_tab)
        layout.setSpacing(24)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)
        self.today_visitors = self._create_stat_card("Visitors Today", "—")
        self.active_inside = self._create_stat_card("Currently Inside", "—")
        self.avg_duration = self._create_stat_card("Avg Visit (h)", "—")
        cards_layout.addWidget(self.today_visitors)
        cards_layout.addWidget(self.active_inside)
        cards_layout.addWidget(self.avg_duration)
        layout.addLayout(cards_layout)

        history_card = ShadcnCard()
        history_card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        header = ShadcnHeading("Daily Visitor History (Last 7 Days)", level=4)
        card_content = CardContent()
        card_content.layout.setContentsMargins(16, 8, 16, 16)

        self.history_table = ShadcnDataTable(
            ["Date", "Check-ins", "Check-outs", "Avg Duration (h)"],
            numeric_columns=[1, 2, 3],
            empty_message="No visitor history for the last 7 days.",
        )
        self.history_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.history_table.setMinimumHeight(200)
        card_content.layout.addWidget(self.history_table)

        history_card.set_header(header)
        history_card.set_content(card_content)
        layout.addWidget(history_card)

    def setup_employee_tab(self):
        layout = QVBoxLayout(self.emp_tab)
        layout.setSpacing(24)

        emp_card = ShadcnCard()
        emp_card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        header = ShadcnHeading("Employee Access Summary (Today)", level=4)
        card_content = CardContent()
        card_content.layout.setContentsMargins(16, 8, 16, 16)

        self.emp_table = ShadcnDataTable(
            ["Employee", "Role", "Last Entry", "Entries Today"],
            numeric_columns=[3],
            empty_message="No employee activity recorded today.",
        )
        self.emp_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.emp_table.setMinimumHeight(200)
        card_content.layout.addWidget(self.emp_table)

        emp_card.set_header(header)
        emp_card.set_content(card_content)
        layout.addWidget(emp_card)

    def _create_stat_card(self, title, value):
        card = ShadcnCard()
        card.setFixedHeight(120)
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        card.setAccessibleName(f"{title}: {value}")

        content = CardContent()
        content.layout.setContentsMargins(20, 16, 20, 16)
        v_layout = QVBoxLayout()

        title_lbl = ShadcnCaption(title)
        v_layout.addWidget(title_lbl)

        value_lbl = ShadcnHeading(value, level=1)
        value_lbl.setObjectName("statValue")
        v_layout.addWidget(value_lbl)

        content.layout.addLayout(v_layout)
        card.set_content(content)
        card.value_label = value_lbl
        card.title = title
        return card

    # ------------------------------------------------------------------
    # Refresh (async)
    # ------------------------------------------------------------------

    def refresh_all(self):
        if self._is_refreshing or self._is_closing:
            return
        self._is_refreshing = True
        self.refresh_btn.set_loading(True, "Refreshing…")

        self._thread = QThread(self)
        self._worker = _ReportWorker(self.data_service)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_data_ready)
        self._worker.failed.connect(self._on_data_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_thread_refs)

        self._thread.start()

    def _clear_thread_refs(self):
        self._thread = None
        self._worker = None

    @Slot(dict, list, list)
    def _on_data_ready(self, stats, history_rows, emp_rows):
        self._is_refreshing = False
        self.refresh_btn.set_loading(False)

        try:
            self.today_visitors.value_label.setText(
                str(stats.get("today_entries", 0))
            )
            self.active_inside.value_label.setText(
                str(stats.get("active_visitors", 0))
            )
        except Exception as e:
            logger.debug(f"Stat update error: {e}")

        if history_rows:
            self.history_table.populate(history_rows)
            durations = []
            for row in history_rows:
                try:
                    durations.append(float(row[3]))
                except (TypeError, ValueError):
                    pass
            overall = sum(durations) / len(durations) if durations else 0
            self.avg_duration.value_label.setText(f"{overall:.1f}")

        if emp_rows:
            self.emp_table.populate(emp_rows)

    @Slot(str)
    def _on_data_failed(self, message: str):
        self._is_refreshing = False
        self.refresh_btn.set_loading(False)
        logger.debug(f"Report refresh failed: {message}")
        ShadcnToast("Report Error",
                    description=f"Failed to refresh: {message}",
                    parent=self, variant="destructive")

    def export_report(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Report",
                f"report_{datetime.now().strftime('%Y%m%d')}.csv",
                "CSV Files (*.csv)",
            )
            if not file_path:
                return

            data = []
            for row in range(self.history_table.rowCount()):
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
                writer.writerow(["Date", "Check-ins", "Check-outs",
                                 "Avg Duration (h)"])
                writer.writerows(data)

            ShadcnToast("Success",
                        description=f"Exported {len(data)} records",
                        parent=self, variant="success")

        except Exception as e:
            logger.debug(f"Export error: {e}")
            ShadcnToast("Error", description=f"Failed to export: {e}",
                        parent=self, variant="destructive")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_R and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.refresh_all()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self._is_closing = True
        if hasattr(self, 'refresh_timer') and self.refresh_timer:
            self.refresh_timer.stop()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        event.accept()

    def cleanup(self):
        self._is_closing = True
        if hasattr(self, 'refresh_timer') and self.refresh_timer:
            self.refresh_timer.stop()
            self.refresh_timer.deleteLater()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
