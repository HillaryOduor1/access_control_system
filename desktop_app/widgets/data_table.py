# widgets/data_table.py
"""
Enterprise-grade Data Table component.

Features:
  - Theme-aware styling (light/dark)
  - Alternating row colors
  - Row selection (single/multiple/extended)
  - Column resize
  - Proportional scrollbars with visible handles and step buttons
  - Empty state
  - Error state
  - Sort indicators
  - Numeric column alignment
  - Accessible names
"""
import logging
from enum import Enum
from typing import List, Optional, Callable, Any, Sequence

from PySide6.QtCore import (
    Qt, Signal, QSize, QTimer, QSortFilterProxyModel,
)
from PySide6.QtGui import (
    QColor, QFont, QIcon, QAction, QKeyEvent, QCursor,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLabel, QFrame, QPushButton,
    QLineEdit, QSizePolicy, QApplication, QFileDialog,
)

from core.theme_manager import ThemeManager
from core.icon_manager import IconManager


logger = logging.getLogger(__name__)


class SortOrder(Enum):
    ASCENDING = "ascending"
    DESCENDING = "descending"
    NONE = "none"


class SelectionMode(Enum):
    SINGLE = "single"
    MULTIPLE = "multiple"
    EXTENDED = "extended"
    NONE = "none"


class ShadcnDataTable(QWidget):
    """
    Enterprise data table wrapper around QTableWidget.

    Adds empty/error states, row-count label, sortable headers with safe
    repopulation, and per-column numeric alignment.

    Scroll behaviour
    ----------------
    Both scrollbars are explicitly sized (12 px handle, 14 px on hover,
    16 px expanded track) and include arrow buttons + page-step zones.
    Column widths are driven by the user's interactive resizes plus a
    minimum section size, and `stretchLastSection` is disabled so that
    the horizontal handle is proportional to the total column width
    rather than jumping between "fits" and "fully scrolled".
    """

    row_selected = Signal(int, dict)
    row_double_clicked = Signal(int, dict)
    header_clicked = Signal(int, str)
    data_changed = Signal()
    selection_changed = Signal(list)

    # Scrollbar geometry. These are used both for the QSS and for
    # arithmetic that decides whether the horizontal bar should be
    # ScrollBarAsNeeded or ScrollBarAlwaysOff.
    SB_THICKNESS = 12
    SB_THICKNESS_HOVER = 14
    SB_MIN_HANDLE = 40

    def __init__(
        self,
        columns: List[str],
        parent: Optional[QWidget] = None,
        selectable: bool = True,
        selection_mode: SelectionMode = SelectionMode.SINGLE,
        sortable: bool = True,
        show_row_numbers: bool = False,
        empty_message: str = "No records found",
        min_height: int = 200,
        numeric_columns: Optional[Sequence[int]] = None,
    ):
        super().__init__(parent)

        self._columns = list(columns)
        self._selectable = selectable
        self._selection_mode = selection_mode
        self._sortable = sortable
        self._show_row_numbers = show_row_numbers
        self._empty_message = empty_message
        self._numeric_columns = set(numeric_columns or [])
        self._data = []
        self._column_widths = {}
        self._hidden_columns = set()
        self._sort_column = -1
        self._sort_order = SortOrder.NONE
        self._selected_rows = []
        self._filter_text = ""
        self._loading = False
        self._row_height = 44

        self.theme_manager = ThemeManager()

        self._init_ui()
        self._apply_theme()

        self.theme_manager.register_widget(
            self,
            on_theme_changed=self._on_theme_changed,
        )

        self.populate([])

    # ======================================================================
    # Backward-compatible QTableWidget proxies
    # ======================================================================

    @property
    def table(self) -> QTableWidget:
        return self._table

    @property
    def header(self):
        return self._table.horizontalHeader()

    def horizontalHeader(self):
        return self._table.horizontalHeader()

    def verticalHeader(self):
        return self._table.verticalHeader()

    def setRowCount(self, count: int):
        self._table.setRowCount(count)

    def rowCount(self) -> int:
        return self._table.rowCount()

    def setColumnCount(self, count: int):
        self._table.setColumnCount(count)

    def columnCount(self) -> int:
        return self._table.columnCount()

    def setItem(self, row: int, column: int, item: QTableWidgetItem):
        self._table.setItem(row, column, item)

    def item(self, row: int, column: int) -> Optional[QTableWidgetItem]:
        return self._table.item(row, column)

    def setCellWidget(self, row: int, column: int, widget: QWidget):
        self._table.setCellWidget(row, column, widget)

    def setColumnWidth(self, column: int, width: int):
        self._table.setColumnWidth(column, width)

    def setRowHeight(self, row: int, height: int):
        self._table.setRowHeight(row, height)

    def setRowHidden(self, row: int, hidden: bool):
        self._table.setRowHidden(row, hidden)

    def isRowHidden(self, row: int) -> bool:
        return self._table.isRowHidden(row)

    def setSortingEnabled(self, enabled: bool):
        self._table.setSortingEnabled(enabled)

    def clearSelection(self):
        self._table.clearSelection()

    def selectRow(self, row: int):
        self._table.selectRow(row)

    def resizeColumnsToContents(self):
        self._table.resizeColumnsToContents()

    def setMinimumHeight(self, height: int):
        self._table.setMinimumHeight(height)

    def clear(self):
        self._table.clear()
        self._data = []
        self._selected_rows = []
        self._update_row_count()
    
    def viewport(self):
        """Proxy to the underlying QTableWidget's viewport."""
        return self._table.viewport()

    def setUpdatesEnabled(self, enabled: bool):
        """Proxy to the underlying QTableWidget."""
        self._table.setUpdatesEnabled(enabled)

    def update(self, *args):
        """Proxy to the underlying QTableWidget and the wrapper."""
        try:
            self._table.update(*args)
        except Exception:
            pass
        super().update(*args)

    # ======================================================================
    # UI Construction
    # ======================================================================

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._table = QTableWidget()
        self._table.setObjectName("dataTable")
        self._table.setColumnCount(len(self._columns))
        self._table.setAccessibleName("Data table")

        if self._selectable:
            if self._selection_mode == SelectionMode.SINGLE:
                self._table.setSelectionBehavior(
                    QAbstractItemView.SelectionBehavior.SelectRows
                )
                self._table.setSelectionMode(
                    QAbstractItemView.SelectionMode.SingleSelection
                )
            elif self._selection_mode == SelectionMode.MULTIPLE:
                self._table.setSelectionBehavior(
                    QAbstractItemView.SelectionBehavior.SelectRows
                )
                self._table.setSelectionMode(
                    QAbstractItemView.SelectionMode.MultiSelection
                )
            elif self._selection_mode == SelectionMode.EXTENDED:
                self._table.setSelectionBehavior(
                    QAbstractItemView.SelectionBehavior.SelectRows
                )
                self._table.setSelectionMode(
                    QAbstractItemView.SelectionMode.ExtendedSelection
                )
            else:
                self._table.setSelectionMode(
                    QAbstractItemView.SelectionMode.NoSelection
                )
        else:
            self._table.setSelectionMode(
                QAbstractItemView.SelectionMode.NoSelection
            )

        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        # Let Qt show or hide the scrollbars based on the viewport.
        # The QSS keeps them thick and usable.
        self._table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._table.setMinimumHeight(200)
        self._table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Enable smooth scrolling so wheel / drag does not snap
        # between rows.
        self._table.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self._table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )

        self._table.setHorizontalHeaderLabels(self._columns)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(self._row_height)

        header = self._table.horizontalHeader()
        # Interactive resizing: the user drags columns, the scrollbar
        # appears when the total exceeds the viewport. We deliberately
        # do NOT stretch the last section: that made the horizontal
        # scrollbar jump between "no scroll needed" and "fully
        # scrolled" whenever the window width changed slightly.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(60)
        header.setHighlightSections(False)
        header.setSectionsClickable(True)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemDoubleClicked.connect(self._on_item_double_clicked)

        if self._sortable:
            header.sectionClicked.connect(self._on_header_clicked)

        layout.addWidget(self._table)

        self._footer = QWidget()
        self._footer.setObjectName("tableFooter")
        footer_layout = QHBoxLayout(self._footer)
        footer_layout.setContentsMargins(4, 4, 4, 4)
        footer_layout.setSpacing(8)

        self._row_count_label = QLabel("0 rows")
        self._row_count_label.setObjectName("rowCountLabel")
        footer_layout.addWidget(self._row_count_label)

        footer_layout.addStretch()

        self._show_all_btn = self._create_button(
            "Show All", "refresh", "Clear filter and show all rows",
            self.show_all_rows
        )
        self._show_all_btn.hide()
        footer_layout.addWidget(self._show_all_btn)

        self._export_btn = self._create_button(
            "Export", "export", "Export data to CSV", self._export_data
        )
        self._export_btn.hide()
        footer_layout.addWidget(self._export_btn)

        layout.addWidget(self._footer)

    def _create_button(self, text: str, icon_name: str, tooltip: str, callback):
        from widgets.components import ShadcnButton
        btn = ShadcnButton(text, variant="ghost", size="sm")
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        return btn

    def _apply_theme(self):
        tokens = self.theme_manager.get_tokens()
        ring = tokens.get("ring", tokens["primary"])

        sb_track = tokens.get("scrollbar_track", tokens.get("muted", "#1E293B"))
        sb_handle = tokens.get("scrollbar_handle", tokens.get("border", "#334155"))
        sb_handle_hover = tokens.get(
            "scrollbar_handle_hover",
            tokens.get("border-strong", "#475569"),
        )
        sb_handle_pressed = tokens.get(
            "primary",
            tokens.get("border-strong", "#475569"),
        )

        thickness = self.SB_THICKNESS
        hover_thickness = self.SB_THICKNESS_HOVER
        min_handle = self.SB_MIN_HANDLE

        table_style = f"""
            QTableWidget#dataTable {{
                background-color: {tokens.get("surface", "#1E293B")};
                alternate-background-color: {tokens.get("muted", "#1E293B")};
                border: 1px solid {tokens.get("border", "#334155")};
                border-radius: {tokens.get("radius-lg", "10px")};
                gridline-color: transparent;
                font-size: 13px;
                color: {tokens.get("foreground", "#F8FAFC")};
                outline: none;
            }}
            QTableWidget#dataTable:focus {{
                border: 2px solid {ring};
            }}
            QTableWidget#dataTable::item {{
                padding: 0 14px;
                border-bottom: 1px solid {tokens.get("border", "#334155")};
                color: {tokens.get("foreground", "#F8FAFC")};
            }}
            QTableWidget#dataTable::item:selected {{
                background: {tokens.get("primary-subtle", "#0A2E1A")};
                color: {tokens.get("primary", "#006B3F")};
            }}
            QTableWidget#dataTable::item:hover {{
                background: {tokens.get("surface-hover", "#334155")};
            }}
            QHeaderView::section {{
                background: {tokens.get("muted", "#1E293B")};
                color: {tokens.get("muted-foreground", "#64748B")};
                padding: 0 14px;
                height: 38px;
                border: none;
                border-bottom: 1px solid {tokens.get("border", "#334155")};
                font-size: 11px;
                font-weight: 600;
            }}
            QHeaderView::section:first {{
                border-top-left-radius: {tokens.get("radius-lg", "10px")};
            }}
            QHeaderView::section:last {{
                border-top-right-radius: {tokens.get("radius-lg", "10px")};
            }}
            QHeaderView::section:hover {{
                color: {tokens.get("foreground", "#F8FAFC")};
                background: {tokens.get("surface-hover", "#334155")};
            }}

            /* ----------------------------------------------------------
               Vertical scrollbar
               Explicit thickness, visible handle, arrow buttons, and a
               page-step zone above/below the handle.
               ---------------------------------------------------------- */
            QScrollBar:vertical {{
                background: {sb_track};
                width: {thickness}px;
                margin: 0;
                border: none;
                border-radius: 0;
            }}
            QScrollBar:hover:vertical {{
                width: {hover_thickness}px;
            }}
            QScrollBar::handle:vertical {{
                background: {sb_handle};
                border-radius: {thickness // 2}px;
                min-height: {min_handle}px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {sb_handle_hover};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {sb_handle_pressed};
            }}
            QScrollBar::add-line:vertical {{
                background: transparent;
                height: 14px;
                subcontrol-origin: margin;
                subcontrol-position: bottom;
            }}
            QScrollBar::sub-line:vertical {{
                background: transparent;
                height: 14px;
                subcontrol-origin: margin;
                subcontrol-position: top;
            }}
            QScrollBar::add-line:vertical:hover,
            QScrollBar::sub-line:vertical:hover {{
                background: {sb_handle_hover};
            }}
            QScrollBar::up-arrow:vertical,
            QScrollBar::down-arrow:vertical {{
                width: 6px;
                height: 6px;
                background: {sb_handle};
            }}
            QScrollBar::up-arrow:vertical:hover,
            QScrollBar::down-arrow:vertical:hover {{
                background: {sb_handle_pressed};
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
            }}

            /* ----------------------------------------------------------
               Horizontal scrollbar
               ---------------------------------------------------------- */
            QScrollBar:horizontal {{
                background: {sb_track};
                height: {thickness}px;
                margin: 0;
                border: none;
                border-radius: 0;
            }}
            QScrollBar:hover:horizontal {{
                height: {hover_thickness}px;
            }}
            QScrollBar::handle:horizontal {{
                background: {sb_handle};
                border-radius: {thickness // 2}px;
                min-width: {min_handle}px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {sb_handle_hover};
            }}
            QScrollBar::handle:horizontal:pressed {{
                background: {sb_handle_pressed};
            }}
            QScrollBar::add-line:horizontal {{
                background: transparent;
                width: 14px;
                subcontrol-origin: margin;
                subcontrol-position: right;
            }}
            QScrollBar::sub-line:horizontal {{
                background: transparent;
                width: 14px;
                subcontrol-origin: margin;
                subcontrol-position: left;
            }}
            QScrollBar::add-line:horizontal:hover,
            QScrollBar::sub-line:horizontal:hover {{
                background: {sb_handle_hover};
            }}
            QScrollBar::left-arrow:horizontal,
            QScrollBar::right-arrow:horizontal {{
                width: 6px;
                height: 6px;
                background: {sb_handle};
            }}
            QScrollBar::left-arrow:horizontal:hover,
            QScrollBar::right-arrow:horizontal:hover {{
                background: {sb_handle_pressed};
            }}
            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}

            /* Corner where the two scrollbars meet. */
            QAbstractScrollArea::corner {{
                background: {sb_track};
                border: none;
            }}
        """

        self._table.setStyleSheet(table_style)

        footer_style = f"""
            QWidget#tableFooter {{ background: transparent; }}
            QLabel#rowCountLabel {{
                color: {tokens.get("muted-foreground", "#64748B")};
                font-size: 12px;
            }}
        """
        self._footer.setStyleSheet(footer_style)

        self._refresh_icons()

    def _refresh_icons(self):
        icon_manager = IconManager()
        self._show_all_btn.setIcon(
            icon_manager.get_icon("refresh", size=QSize(14, 14), state="default")
        )
        self._show_all_btn.setIconSize(QSize(14, 14))
        self._export_btn.setIcon(
            icon_manager.get_icon("export", size=QSize(14, 14), state="default")
        )
        self._export_btn.setIconSize(QSize(14, 14))

    def _on_theme_changed(self, *args):
        self._apply_theme()
        self._table.update()
        self.update()

    def on_theme_changed(self, theme: str):
        self._on_theme_changed(theme)

    def update_theme(self):
        self._on_theme_changed()

    # ======================================================================
    # Data operations
    # ======================================================================

    def populate(self, data: list, clear_selection: bool = True,
                 empty_message: Optional[str] = None):
        self._data = list(data or [])
        self._selected_rows = [] if clear_selection else self._selected_rows

        self._table.setSortingEnabled(False)

        if clear_selection:
            self._table.clearSelection()

        if not self._data:
            self._show_empty_state(empty_message)
            self._update_row_count()
            self._show_all_btn.hide()
            return

        if isinstance(self._data[0], dict):
            self._populate_from_dicts(self._data)
        else:
            self._populate_from_tuples(self._data)

        self._table.setSortingEnabled(self._sortable)
        self._update_row_count()

        if self._filter_text:
            self._show_all_btn.show()
        else:
            self._show_all_btn.hide()

        self.data_changed.emit()

    def _align(self, col: int):
        if col in self._numeric_columns:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return Qt.AlignmentFlag.AlignVCenter

    def _populate_from_tuples(self, data: list):
        row_count = len(data)
        col_count = len(self._columns)

        self._table.setRowCount(row_count)

        for row, row_data in enumerate(data):
            if isinstance(row_data, (tuple, list)):
                for col in range(col_count):
                    value = row_data[col] if col < len(row_data) else ""
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(self._align(col))
                    self._table.setItem(row, col, item)
            else:
                item = QTableWidgetItem(str(row_data))
                item.setTextAlignment(self._align(0))
                self._table.setItem(row, 0, item)

    def _populate_from_dicts(self, data: list):
        self._table.setRowCount(len(data))

        for row, row_data in enumerate(data):
            for col, col_name in enumerate(self._columns):
                value = row_data.get(col_name, "")
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(self._align(col))
                item.setData(Qt.ItemDataRole.UserRole, row_data)
                self._table.setItem(row, col, item)

    def _show_empty_state(self, message: Optional[str] = None):
        msg = message or self._empty_message
        self._table.setRowCount(1)

        item = QTableWidgetItem(msg)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(Qt.ItemFlag.NoItemFlags)

        tokens = self.theme_manager.get_tokens()
        item.setForeground(QColor(tokens.get("muted-foreground", "#64748B")))

        for col in range(self._table.columnCount()):
            if col == 0:
                self._table.setItem(0, col, item)
            else:
                empty_item = QTableWidgetItem("")
                empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
                self._table.setItem(0, col, empty_item)

        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )

    def set_error(self, message: str):
        """Show an inline error state."""
        self._table.setSortingEnabled(False)
        self._table.clearContents()
        self._table.setRowCount(1)
        item = QTableWidgetItem(f"⚠  {message}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        tokens = self.theme_manager.get_tokens()
        item.setForeground(QColor(tokens.get("destructive", "#EF4444")))
        if self._table.columnCount() > 0:
            self._table.setItem(0, 0, item)
        for col in range(1, self._table.columnCount()):
            filler = QTableWidgetItem("")
            filler.setFlags(Qt.ItemFlag.NoItemFlags)
            self._table.setItem(0, col, filler)
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self._row_count_label.setText("Error")
        self._show_all_btn.hide()

    def _update_row_count(self):
        total = len(self._data)
        if total == 0:
            self._row_count_label.setText("0 rows")
        else:
            self._row_count_label.setText(f"{total} rows")

    # ======================================================================
    # Filtering
    # ======================================================================

    def filter_table(self, text: str):
        self._filter_text = text.strip().lower()

        if not self._filter_text:
            self.show_all_rows()
            return

        self._table.setSortingEnabled(False)

        visible_rows = []
        for row in range(self._table.rowCount()):
            match = False
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item and self._filter_text in item.text().lower():
                    match = True
                    break
            if match:
                visible_rows.append(row)

        for row in range(self._table.rowCount()):
            self._table.setRowHidden(row, row not in visible_rows)

        self._table.setSortingEnabled(self._sortable)
        self._update_row_count()
        self._show_all_btn.show()

    def show_all_rows(self):
        self._filter_text = ""
        self._table.setSortingEnabled(False)

        for row in range(self._table.rowCount()):
            self._table.setRowHidden(row, False)

        self._table.setSortingEnabled(self._sortable)
        self._update_row_count()
        self._show_all_btn.hide()

        if not self._data and self._table.rowCount() == 1:
            self._show_empty_state()
            self._update_row_count()

    # ======================================================================
    # Selection
    # ======================================================================

    def _on_selection_changed(self):
        selected_items = self._table.selectedItems()

        if not selected_items:
            self._selected_rows = []
            self.selection_changed.emit([])
            return

        rows = {item.row() for item in selected_items}
        self._selected_rows = sorted(rows)

        if self._selected_rows and self._data:
            row = self._selected_rows[0]
            if row < len(self._data):
                row_data = self._data[row]
                if isinstance(row_data, dict):
                    self.row_selected.emit(row, row_data)
                else:
                    row_dict = {}
                    for col, col_name in enumerate(self._columns):
                        if col < len(row_data):
                            row_dict[col_name] = row_data[col]
                    self.row_selected.emit(row, row_dict)

        self.selection_changed.emit(self._selected_rows)

    def _on_item_double_clicked(self, item):
        row = item.row()
        if 0 <= row < len(self._data):
            row_data = self._data[row]
            if isinstance(row_data, dict):
                self.row_double_clicked.emit(row, row_data)
            else:
                row_dict = {}
                for col, col_name in enumerate(self._columns):
                    if col < len(row_data):
                        row_dict[col_name] = row_data[col]
                self.row_double_clicked.emit(row, row_dict)

    def _on_header_clicked(self, column: int):
        if not self._sortable:
            return
        if column >= len(self._columns):
            return

        column_name = self._columns[column]

        if self._sort_column == column:
            if self._sort_order == SortOrder.ASCENDING:
                self._sort_order = SortOrder.DESCENDING
            elif self._sort_order == SortOrder.DESCENDING:
                self._sort_order = SortOrder.NONE
            else:
                self._sort_order = SortOrder.ASCENDING
        else:
            self._sort_column = column
            self._sort_order = SortOrder.ASCENDING

        self._update_header_indicators()

        if self._sort_order != SortOrder.NONE:
            self._sort_data(column, self._sort_order == SortOrder.ASCENDING)

        self.header_clicked.emit(column, column_name)

    def _update_header_indicators(self):
        header = self._table.horizontalHeader()
        for col in range(len(self._columns)):
            if col == self._sort_column and self._sort_order != SortOrder.NONE:
                indicator = " ▲" if self._sort_order == SortOrder.ASCENDING else " ▼"
                header.setSectionText(col, self._columns[col] + indicator)
            else:
                header.setSectionText(col, self._columns[col])

    def _sort_data(self, column: int, ascending: bool):
        """Sort the raw data list and repopulate.

        Repopulating preserves setCellWidget() widgets (unlike the base
        QTableWidget::sortItems() which only moves items).
        """
        if not self._data:
            return

        def key_fn(row):
            if isinstance(row, dict):
                v = row.get(self._columns[column], "")
            elif isinstance(row, (tuple, list)):
                v = row[column] if column < len(row) else ""
            else:
                v = row
            try:
                return (0, float(v))
            except (TypeError, ValueError):
                return (1, str(v).lower())

        self._data.sort(key=key_fn, reverse=not ascending)
        self.populate(self._data, clear_selection=False)

    def get_selected_rows(self) -> List[int]:
        return list(self._selected_rows)

    def get_selected_data(self) -> List[Any]:
        if not self._selected_rows:
            return []
        return [self._data[r] for r in self._selected_rows if r < len(self._data)]

    def select_row(self, row: int):
        if 0 <= row < self._table.rowCount():
            self._table.selectRow(row)

    # ======================================================================
    # Column operations
    # ======================================================================

    def set_column_width(self, column: int, width: int):
        if 0 <= column < self._table.columnCount():
            self._table.setColumnWidth(column, width)
            self._column_widths[column] = width

    def hide_column(self, column: int):
        if 0 <= column < self._table.columnCount():
            self._table.setColumnHidden(column, True)
            self._hidden_columns.add(column)

    def show_column(self, column: int):
        if column in self._hidden_columns:
            self._table.setColumnHidden(column, False)
            self._hidden_columns.remove(column)

    def set_column_visible(self, column: int, visible: bool):
        if visible:
            self.show_column(column)
        else:
            self.hide_column(column)

    def resize_columns_to_contents(self):
        self._table.resizeColumnsToContents()

    # ======================================================================
    # Export
    # ======================================================================

    def _export_data(self):
        try:
            import csv

            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export Data", "",
                "CSV Files (*.csv);;All Files (*)"
            )
            if not file_path:
                return

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                headers = [
                    self._columns[c] for c in range(self._table.columnCount())
                    if not self._table.isColumnHidden(c)
                ]
                writer.writerow(headers)
                for row in range(self._table.rowCount()):
                    if self._table.isRowHidden(row):
                        continue
                    row_data = []
                    for col in range(self._table.columnCount()):
                        if not self._table.isColumnHidden(col):
                            item = self._table.item(row, col)
                            row_data.append(item.text() if item else "")
                    writer.writerow(row_data)

            logger.info(f"Data exported to: {file_path}")

        except Exception as e:
            logger.error(f"Export failed: {e}")
            from widgets.components import ShadcnToast
            ShadcnToast("Export Failed", str(e), variant="destructive")

    # ======================================================================
    # Appearance
    # ======================================================================

    def set_empty_message(self, message: str):
        self._empty_message = message

    def set_loading(self, loading: bool):
        self._loading = loading
        self._table.setEnabled(not loading)
        if loading:
            self._row_count_label.setText("Loading...")
        else:
            self._update_row_count()

    def set_row_height(self, height: int):
        self._row_height = height
        self._table.verticalHeader().setDefaultSectionSize(height)

    # ======================================================================
    # Utilities
    # ======================================================================

    def get_data(self) -> List[Any]:
        return self._data

    def get_column_count(self) -> int:
        return self._table.columnCount()

    def get_row_count(self) -> int:
        return self._table.rowCount()

    def set_export_enabled(self, enabled: bool):
        self._export_btn.setVisible(enabled)

    def refresh_data(self, data: list):
        self.populate(data)

    # ======================================================================
    # Keyboard shortcuts
    # ======================================================================

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.clearSelection()
            event.accept()
        else:
            super().keyPressEvent(event)
