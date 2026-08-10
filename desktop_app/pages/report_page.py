from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QTableWidgetItem
from PySide6.QtCore import Signal, QTimer, Qt
from widgets.components import ShadcnCard, CardContent, ShadcnDataTable, ShadcnButton
from datetime import datetime, timedelta
from collections import defaultdict

class ReportPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, user_info, permissions, data_service):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service
        self.init_ui()
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_all)
        self.refresh_timer.start(10000)
        self.refresh_all()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

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
        self.today_visitors = self._create_stat_card("Visitors Today", "0")
        self.active_inside = self._create_stat_card("Currently Inside", "0")
        self.avg_duration = self._create_stat_card("Avg Visit (h)", "0")
        cards_layout.addWidget(self.today_visitors)
        cards_layout.addWidget(self.active_inside)
        cards_layout.addWidget(self.avg_duration)
        layout.addLayout(cards_layout)

        history_card = ShadcnCard()
        header = QLabel("Daily Visitor History (Last 7 Days)")
        header.setStyleSheet("font-weight: 600; font-size: 15px; padding: 16px 16px 0 16px;")
        card_content = CardContent()
        card_content.layout.setContentsMargins(16, 8, 16, 16)
        self.history_table = ShadcnDataTable(["Date", "Check-ins", "Check-outs", "Avg Duration (h)"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        card_content.layout.addWidget(self.history_table)
        history_card.set_header(header)
        history_card.set_content(card_content)
        layout.addWidget(history_card)

    def setup_employee_tab(self):
        layout = QVBoxLayout(self.emp_tab)
        layout.setSpacing(24)

        emp_card = ShadcnCard()
        header = QLabel("Employee Access Summary (Today)")
        header.setStyleSheet("font-weight: 600; font-size: 15px; padding: 16px 16px 0 16px;")
        card_content = CardContent()
        card_content.layout.setContentsMargins(16, 8, 16, 16)
        self.emp_table = ShadcnDataTable(["Employee", "Role", "Last Entry", "Entries Today"])
        self.emp_table.horizontalHeader().setStretchLastSection(True)
        card_content.layout.addWidget(self.emp_table)
        emp_card.set_header(header)
        emp_card.set_content(card_content)
        layout.addWidget(emp_card)

    def _create_stat_card(self, title, value):
        card = ShadcnCard()
        card.setFixedHeight(120)
        content = CardContent()
        content.layout.setContentsMargins(20, 16, 20, 16)
        v_layout = QVBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 14px; color: #64748B; font-weight: 500;")
        self.value_lbl = QLabel(value)
        self.value_lbl.setStyleSheet("font-size: 32px; font-weight: bold;")
        v_layout.addWidget(title_lbl)
        v_layout.addWidget(self.value_lbl)
        content.layout.addLayout(v_layout)
        card.set_content(content)
        card.value_label = self.value_lbl
        return card

    def refresh_all(self):
        # Use data_service for stats
        stats = self.data_service.get_dashboard_stats()
        self.today_visitors.value_label.setText(str(stats["today_entries"]))
        self.active_inside.value_label.setText(str(stats["active_visitors"]))

        # Weekly history
        history = self.data_service.get_visitor_history(limit=500)
        by_date = defaultdict(lambda: {'ins': 0, 'outs': 0, 'durations': []})
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
                except:
                    pass
        last_7 = []
        total_durations = []
        for i in range(7):
            d = (datetime.now() - timedelta(days=i)).date().isoformat()
            data = by_date.get(d, {'ins': 0, 'outs': 0, 'durations': []})
            avg_dur = sum(data['durations'])/len(data['durations']) if data['durations'] else 0
            total_durations.extend(data['durations'])
            last_7.append((d, data['ins'], data['outs'], f"{avg_dur:.1f}"))
        self.history_table.populate(last_7)
        overall_avg = sum(total_durations)/len(total_durations) if total_durations else 0
        self.avg_duration.value_label.setText(f"{overall_avg:.1f}")

        # Employee access today
        employees = self.data_service.get_employees(active_only=True)
        # For today's logs, we can get logs from data_service
        today = datetime.now().date().isoformat()
        logs = self.data_service.get_access_logs({"date_from": f"{today} 00:00:00", "date_to": f"{today} 23:59:59"})
        entries_today = defaultdict(int)
        last_entry = {}
        for log in logs:
            if log[1] == 'employee' and log[3] == 'in':
                emp_id = log[2]
                entries_today[emp_id] += 1
                last_entry[emp_id] = log[4]
        emp_data = []
        for emp in employees:
            emp_id = emp.get('id')
            emp_data.append((emp['full_name'], emp.get('role', ''),
                             last_entry.get(emp_id, 'Never')[:19] if last_entry.get(emp_id) else 'Never',
                             entries_today.get(emp_id, 0)))
        self.emp_table.populate(emp_data)

