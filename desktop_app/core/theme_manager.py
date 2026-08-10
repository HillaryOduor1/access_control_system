from PySide6.QtCore import QSettings, Qt, QObject, Signal
from PySide6.QtWidgets import QApplication


class ThemeManager(QObject):
    _instance = None
    theme_changed = Signal()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self.settings = QSettings("ICTAuthority", "AccessControl")
        saved = self.settings.value("theme", "")
        if saved:
            self.current = saved
        else:
            color_scheme = QApplication.styleHints().colorScheme()
            self.current = "dark" if color_scheme == Qt.ColorScheme.Dark else "light"
        self._tokens = self._get_tokens_for_theme(self.current)
        self._initialized = True

    # Token definitions
    def _get_tokens_for_theme(self, theme):
        if theme == "light":
            return {
                # Core surfaces — layered from page → card → popover
                "background":           "hsl(0, 0%, 99%)",        # page canvas
                "surface":              "hsl(0, 0%, 100%)",        # card / panel
                "surface-hover":        "hsl(220, 14%, 96%)",      # hover tint
                "surface-active":       "hsl(220, 14%, 93%)",      # pressed tint
                "popover":              "hsl(0, 0%, 100%)",
                "popover-foreground":   "hsl(222, 47%, 11%)",

                # Text hierarchy
                "foreground":           "hsl(222, 47%, 11%)",      # primary text
                "foreground-secondary": "hsl(217, 19%, 35%)",      # secondary
                "muted-foreground":     "hsl(215, 16%, 47%)",      # muted / captions
                "on-primary":           "hsl(0, 0%, 100%)",        # text on primary bg

                # Brand / primary — green
                "primary":              "hsl(142, 72%, 29%)",
                "primary-hover":        "hsl(142, 72%, 23%)",
                "primary-subtle":       "hsl(143, 64%, 94%)",      # tinted bg
                "primary-foreground":   "hsl(0, 0%, 100%)",

                # Semantic
                "destructive":          "hsl(0, 72%, 51%)",
                "destructive-hover":    "hsl(0, 72%, 44%)",
                "destructive-subtle":   "hsl(0, 86%, 96%)",
                "destructive-foreground": "hsl(0, 0%, 100%)",

                "warning":              "hsl(38, 92%, 50%)",
                "warning-subtle":       "hsl(48, 100%, 95%)",
                "warning-foreground":   "hsl(32, 81%, 29%)",

                "success":              "hsl(142, 72%, 29%)",
                "success-subtle":       "hsl(143, 64%, 94%)",
                "success-foreground":   "hsl(143, 64%, 20%)",

                "info":                 "hsl(221, 83%, 53%)",
                "info-subtle":          "hsl(214, 100%, 96%)",
                "info-foreground":      "hsl(221, 70%, 30%)",

                # UI structure
                "secondary":            "hsl(220, 14%, 96%)",      # secondary btn / ghost hover
                "secondary-foreground": "hsl(222, 47%, 11%)",
                "muted":                "hsl(220, 14%, 96%)",
                "accent":               "hsl(220, 14%, 93%)",
                "accent-foreground":    "hsl(222, 47%, 11%)",
                "border":               "hsl(220, 13%, 91%)",
                "border-strong":        "hsl(217, 10%, 80%)",
                "input":                "hsl(0, 0%, 100%)",
                "ring":                 "hsl(142, 72%, 29%)",

                # Card / card-foreground alias
                "card":                 "hsl(0, 0%, 100%)",
                "card-foreground":      "hsl(222, 47%, 11%)",

                # Misc
                "radius":               "6px",
                "radius-sm":            "4px",
                "radius-lg":            "10px",
                "radius-xl":            "14px",

                # Legacy aliases kept for backward compat
                "bg_primary":           "hsl(0, 0%, 99%)",
                "bg_secondary":         "hsl(220, 14%, 96%)",
                "text_primary":         "hsl(222, 47%, 11%)",
                "text_secondary":       "hsl(217, 19%, 35%)",
                "text_muted":           "hsl(215, 16%, 47%)",
                "text_on_primary":      "hsl(0, 0%, 100%)",
                "primary_hover":        "hsl(142, 72%, 23%)",
                "accent_color":         "hsl(220, 14%, 93%)",
                "error":                "hsl(0, 72%, 51%)",
                "surface_hover":        "hsl(220, 14%, 96%)",
            }
        else:  # DARK
            return {
                # Core surfaces
                "background":           "hsl(224, 16%, 10%)",      # page canvas
                "surface":              "hsl(224, 14%, 13%)",       # card / panel
                "surface-hover":        "hsl(224, 14%, 17%)",       # hover tint
                "surface-active":       "hsl(224, 14%, 20%)",       # pressed tint
                "popover":              "hsl(224, 14%, 15%)",
                "popover-foreground":   "hsl(213, 31%, 91%)",

                # Text hierarchy
                "foreground":           "hsl(213, 31%, 91%)",
                "foreground-secondary": "hsl(215, 20%, 70%)",
                "muted-foreground":     "hsl(218, 11%, 55%)",
                "on-primary":           "hsl(0, 0%, 100%)",

                # Brand / primary — green
                "primary":              "hsl(142, 70%, 45%)",
                "primary-hover":        "hsl(142, 70%, 51%)",
                "primary-subtle":       "hsl(143, 40%, 14%)",
                "primary-foreground":   "hsl(0, 0%, 100%)",

                # Semantic
                "destructive":          "hsl(0, 63%, 55%)",
                "destructive-hover":    "hsl(0, 63%, 62%)",
                "destructive-subtle":   "hsl(0, 40%, 16%)",
                "destructive-foreground": "hsl(0, 0%, 100%)",

                "warning":              "hsl(38, 92%, 50%)",
                "warning-subtle":       "hsl(38, 40%, 14%)",
                "warning-foreground":   "hsl(38, 92%, 75%)",

                "success":              "hsl(142, 70%, 45%)",
                "success-subtle":       "hsl(143, 40%, 14%)",
                "success-foreground":   "hsl(143, 64%, 75%)",

                "info":                 "hsl(217, 91%, 60%)",
                "info-subtle":          "hsl(221, 40%, 16%)",
                "info-foreground":      "hsl(214, 100%, 80%)",

                # UI structure
                "secondary":            "hsl(224, 14%, 17%)",
                "secondary-foreground": "hsl(213, 31%, 91%)",
                "muted":                "hsl(224, 14%, 16%)",
                "accent":               "hsl(224, 14%, 19%)",
                "accent-foreground":    "hsl(213, 31%, 91%)",
                "border":               "hsl(224, 14%, 19%)",
                "border-strong":        "hsl(224, 12%, 26%)",
                "input":                "hsl(224, 14%, 15%)",
                "ring":                 "hsl(142, 70%, 45%)",

                # Card alias
                "card":                 "hsl(224, 14%, 13%)",
                "card-foreground":      "hsl(213, 31%, 91%)",

                # Misc
                "radius":               "6px",
                "radius-sm":            "4px",
                "radius-lg":            "10px",
                "radius-xl":            "14px",

                # Legacy aliases
                "bg_primary":           "hsl(224, 16%, 10%)",
                "bg_secondary":         "hsl(224, 14%, 17%)",
                "text_primary":         "hsl(213, 31%, 91%)",
                "text_secondary":       "hsl(215, 20%, 70%)",
                "text_muted":           "hsl(218, 11%, 55%)",
                "text_on_primary":      "hsl(0, 0%, 100%)",
                "primary_hover":        "hsl(142, 70%, 51%)",
                "accent_color":         "hsl(224, 14%, 19%)",
                "error":                "hsl(0, 63%, 55%)",
                "surface_hover":        "hsl(224, 14%, 17%)",
            }

    # Public API
    def get_tokens(self):
        return self._tokens

    def get_icon_color(self):
        return self._tokens.get("muted-foreground", "#64748B")

    def get_current_theme(self):
        return self.current

    def toggle_theme(self):
        self.current = "dark" if self.current == "light" else "light"
        self.settings.setValue("theme", self.current)
        self._tokens = self._get_tokens_for_theme(self.current)
        self.theme_changed.emit()

    # Global application stylesheet
    def get_stylesheet(self) -> str:
        t = self._tokens
        return f"""
            /* Base windows*/
            QMainWindow, QDialog {{
                background-color: {t["background"]};
                color: {t["foreground"]};
            }}

            /* Labels */
            QLabel {{
                color: {t["foreground"]};
                background: transparent;
            }}

            /*Buttons (base ,ShadcnButton overrides per variant)*/
            QPushButton {{
                border: none;
                border-radius: {t["radius"]};
                padding: 7px 16px;
                font-size: 13px;
                font-weight: 500;
                background-color: {t["primary"]};
                color: {t["primary-foreground"]};
            }}
            QPushButton:hover  {{ background-color: {t["primary-hover"]}; }}
            QPushButton:pressed {{ opacity: 0.9; }}
            QPushButton:disabled {{ opacity: 0.45; }}

            /* Inputs */
            QLineEdit, QTextEdit, QSpinBox, QDateEdit {{
                background-color: {t["input"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius"]};
                padding: 7px 11px;
                font-size: 13px;
                color: {t["foreground"]};
                selection-background-color: {t["primary"]};
                selection-color: {t["primary-foreground"]};
            }}
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDateEdit:focus {{
                border: 1.5px solid {t["ring"]};
                outline: none;
            }}
            QLineEdit:disabled, QTextEdit:disabled {{
                background-color: {t["muted"]};
                color: {t["muted-foreground"]};
            }}

            /* ComboBox */
            QComboBox {{
                background-color: {t["input"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius"]};
                padding: 7px 11px;
                font-size: 13px;
                color: {t["foreground"]};
            }}
            QComboBox:focus {{ border: 1.5px solid {t["ring"]}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background-color: {t["popover"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius"]};
                selection-background-color: {t["secondary"]};
                selection-color: {t["foreground"]};
                padding: 4px;
            }}

            /* Tables */
            QTableWidget {{
                background-color: {t["surface"]};
                alternate-background-color: {t["muted"]};
                gridline-color: {t["border"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius"]};
                font-size: 13px;
                color: {t["foreground"]};
            }}
            QTableWidget::item {{ padding: 10px 14px; }}
            QTableWidget::item:selected {{
                background-color: {t["primary-subtle"]};
                color: {t["primary"]};
            }}
            QHeaderView::section {{
                background-color: {t["muted"]};
                color: {t["muted-foreground"]};
                padding: 9px 14px;
                border: none;
                border-bottom: 1px solid {t["border"]};
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}

            /* Scrollbars, ultra-thin ghost style */
            QScrollBar:vertical {{
                background: transparent;
                width: 4px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: transparent;
                border-radius: 2px;
                min-height: 36px;
            }}
            QScrollBar:vertical:hover {{ background: {t["muted"]}; }}
            QScrollBar:vertical:hover QScrollBar::handle:vertical,
            QScrollBar::handle:vertical:hover {{
                background: {t["border-strong"]};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

            QScrollBar:horizontal {{
                background: transparent;
                height: 4px;
                margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {t["border-strong"]};
                border-radius: 2px;
                min-width: 36px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {t["muted-foreground"]}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

            /* Menu bar */
            QMenuBar {{
                background-color: {t["surface"]};
                border-bottom: 1px solid {t["border"]};
                padding: 2px 8px;
                font-size: 13px;
            }}
            QMenuBar::item {{
                background: transparent;
                padding: 5px 10px;
                border-radius: {t["radius-sm"]};
                color: {t["foreground"]};
            }}
            QMenuBar::item:selected {{ background-color: {t["secondary"]}; }}

            /* Menus */
            QMenu {{
                background-color: {t["popover"]};
                border: 1px solid {t["border"]};
                border-radius: {t["radius"]};
                padding: 4px;
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 6px 22px 6px 12px;
                border-radius: {t["radius-sm"]};
                color: {t["foreground"]};
            }}
            QMenu::item:selected {{ background-color: {t["secondary"]}; }}
            QMenu::separator {{
                height: 1px;
                background: {t["border"]};
                margin: 4px 8px;
            }}

            /* Tooltips */
            QToolTip {{
                background-color: {t["foreground"]};
                color: {t["background"]};
                border: none;
                border-radius: {t["radius-sm"]};
                padding: 5px 10px;
                font-size: 12px;
            }}

            /* Tool buttons */
            QToolButton {{
                background: transparent;
                border: none;
                border-radius: {t["radius"]};
                padding: 5px;
                color: {t["foreground"]};
            }}
            QToolButton:hover {{ background: {t["secondary"]}; }}
            QToolButton::menu-indicator {{ image: none; }}

            /* Progress bar */
            QProgressBar {{
                background-color: {t["muted"]};
                border: none;
                border-radius: {t["radius-sm"]};
                height: 6px;
                text-align: center;
                font-size: 11px;
                color: transparent;
            }}
            QProgressBar::chunk {{
                background-color: {t["primary"]};
                border-radius: {t["radius-sm"]};
            }}

            /* Separators */
            QFrame[frameShape="4"], QFrame[frameShape="5"] {{
                background-color: {t["border"]};
                border: none;
                max-height: 1px;
            }}
        """
 