# core/theme_manager.py
"""
Enterprise application appearance and theme management.

System theme detection
----------------------
On first run (before any user preference is stored), the theme
follows the operating system's light/dark setting:

- Windows 10 1809+ / Windows 11: reads the
  `HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize`
  registry key for `AppsUseLightTheme` (1 = light, 0 = dark).
- macOS: reads the `AppleInterfaceStyle` user default via the
  `subprocess` call to `defaults read -g AppleInterfaceStyle`.
  Absence of the key means light mode.
- Linux: checks `$GTK_THEME` / `$XDG_CURRENT_DESKTOP` and falls
  back to `gsettings get org.gnome.desktop.interface color-scheme`
  when available. Absence of any signal means light mode.

The detection runs once, on ThemeManager construction, and only
matters if no user preference has ever been persisted. As soon as
the user changes the theme (either from the Settings page or via
the header's toggle button), the preference is persisted and the
system setting is no longer consulted.

Live system theme changes
-------------------------
On Windows and macOS the OS theme can change while the app is
running. We do not subscribe to native OS notifications (that
would require platform-specific code and, on some platforms,
extra permissions). Instead, the preference is only re-detected
if the user explicitly resets their appearance to defaults via
the Settings page. This is a deliberate trade-off: a running app
does not spontaneously change theme under the user, which is
generally what users expect from desktop software.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from copy import deepcopy
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import QSettings, Qt, QObject, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from core.tokens import (
    PRIMITIVES,
    build_semantic,
    build_components,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OS theme detection
# ---------------------------------------------------------------------------

def _detect_windows_theme() -> Optional[str]:
    """Return 'dark', 'light', or None if the detection fails."""
    try:
        import winreg  # noqa: WPS433 (Windows-only import)
    except ImportError:
        return None

    try:
        key_path = (
            r"Software\Microsoft\Windows\CurrentVersion"
            r"\Themes\Personalize"
        )
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path
        ) as key:
            # AppsUseLightTheme: 1 = light, 0 = dark
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if int(value) == 1 else "dark"
    except FileNotFoundError:
        # Key missing on very old Windows versions — assume light.
        return "light"
    except Exception as exc:
        logger.debug(f"Windows theme detection failed: {exc}")
        return None


def _detect_macos_theme() -> Optional[str]:
    """Return 'dark', 'light', or None if the detection fails."""
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug(f"macOS theme detection failed: {exc}")
        return None

    if result.returncode != 0:
        # Key does not exist -> Light mode.
        return "light"

    value = (result.stdout or "").strip().lower()
    if value == "dark":
        return "dark"
    return "light"


def _detect_linux_theme() -> Optional[str]:
    """Return 'dark', 'light', or None if the detection fails."""
    # 1. GNOME 42+ / many modern desktops expose this.
    try:
        result = subprocess.run(
            [
                "gsettings", "get",
                "org.gnome.desktop.interface",
                "color-scheme",
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if result.returncode == 0:
            value = (result.stdout or "").strip().lower()
            if "dark" in value:
                return "dark"
            if "light" in value or value in ("''", '""', "default"):
                return "light"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as exc:
        logger.debug(f"gsettings detection failed: {exc}")

    # 2. GTK_THEME env var, e.g. "Adwaita:dark".
    gtk_theme = os.environ.get("GTK_THEME", "").lower()
    if "dark" in gtk_theme:
        return "dark"
    if gtk_theme:
        return "light"

    return None


def detect_system_theme() -> str:
    """
    Detect the OS light/dark preference.

    Returns 'light' or 'dark'. Falls back to 'light' when the
    platform is unknown or detection fails.
    """
    try:
        if sys.platform == "win32":
            detected = _detect_windows_theme()
        elif sys.platform == "darwin":
            detected = _detect_macos_theme()
        else:
            detected = _detect_linux_theme()
    except Exception as exc:
        logger.debug(f"System theme detection raised: {exc}")
        detected = None

    if detected in ("light", "dark"):
        logger.info(f"Detected system theme: {detected}")
        return detected

    logger.info("System theme could not be detected; defaulting to light.")
    return "light"


# ---------------------------------------------------------------------------
# ThemeManager
# ---------------------------------------------------------------------------

class ThemeManager(QObject):
    _instance = None

    theme_changed = Signal(str)
    appearance_changed = Signal(dict)

    SUPPORTED_THEMES = {"light", "dark"}
    SUPPORTED_DENSITIES = {"compact", "comfortable", "spacious"}
    SUPPORTED_FONT_WEIGHTS = {
        "normal": QFont.Weight.Normal,
        "medium": QFont.Weight.Medium,
        "semibold": QFont.Weight.DemiBold,
        "bold": QFont.Weight.Bold,
    }

    # The default appearance, with theme set from the OS at
    # construction time. Do not rely on the literal value here;
    # use get_default_appearance() which returns a fresh copy with
    # the OS-detected theme.
    DEFAULT_APPEARANCE = {
        "theme": "light",  # overridden at construction by OS detection
        "font_family": "Segoe UI",
        "font_size": 13,
        "font_weight": "normal",
        "density": "comfortable",
        "radius": "medium",
        "high_contrast": False,
        "reduced_effects": False,
    }

    RADIUS_VALUES = {
        "small":  {"radius": "4px",  "radius-sm": "3px", "radius-lg": "7px",  "radius-xl": "10px"},
        "medium": {"radius": "6px",  "radius-sm": "4px", "radius-lg": "10px", "radius-xl": "14px"},
        "large":  {"radius": "10px", "radius-sm": "7px", "radius-lg": "14px", "radius-xl": "18px"},
    }
    DENSITY_VALUES = {
        "compact":     {"control_height": 28, "padding_vertical": 4, "padding_horizontal": 8,  "section_spacing": 10},
        "comfortable": {"control_height": 34, "padding_vertical": 6, "padding_horizontal": 10, "section_spacing": 14},
        "spacious":    {"control_height": 40, "padding_vertical": 8, "padding_horizontal": 12, "section_spacing": 18},
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        super().__init__()

        self.settings = QSettings("ICTAuthority", "AccessControl")
        self.current_user_id: Optional[str] = None

        # Detect the OS theme once. This becomes our baseline default
        # for first runs. If the user has already stored a preference,
        # it will be loaded by set_user() and override this.
        self._system_theme = detect_system_theme()
        self._default_appearance = self._build_default_appearance()

        self._appearance = deepcopy(self._default_appearance)
        self._tokens = self._get_tokens_for_theme(self._appearance["theme"])

        self._qss_cache: Dict[str, str] = {}
        self._app_qss_cache: Optional[str] = None

        self._pending_emit = False
        self._last_emitted_appearance: Optional[Dict[str, Any]] = None

        self._initialized = True

    # ==================================================================
    # DEFAULT APPEARANCE
    # ==================================================================

    def _build_default_appearance(self) -> Dict[str, Any]:
        """
        Build the default appearance, using the OS-detected theme as
        the baseline for the 'theme' key. All other defaults come
        from DEFAULT_APPEARANCE.
        """
        appearance = deepcopy(self.DEFAULT_APPEARANCE)
        if self._system_theme in self.SUPPORTED_THEMES:
            appearance["theme"] = self._system_theme
        return appearance

    def get_default_appearance(self) -> Dict[str, Any]:
        """Return a fresh copy of the current default appearance."""
        return deepcopy(self._default_appearance)

    def get_system_theme(self) -> str:
        """Return the OS theme detected at construction time."""
        return self._system_theme

    def re_detect_system_theme(self) -> str:
        """
        Re-run OS theme detection. Useful after a user chooses
        "Reset to defaults" so the reset picks up the current OS
        theme rather than whatever was detected at app start.
        """
        self._system_theme = detect_system_theme()
        self._default_appearance = self._build_default_appearance()
        return self._system_theme

    # ==================================================================
    # QSS CACHE
    # ==================================================================

    def get_qss(self, key: str, builder: Callable[[], str]) -> str:
        cached = self._qss_cache.get(key)
        if cached is not None:
            return cached
        value = builder()
        self._qss_cache[key] = value
        return value

    def invalidate_qss_cache(self):
        self._qss_cache.clear()
        self._app_qss_cache = None

    # ==================================================================
    # WIDGET SUBSCRIPTION
    # ==================================================================

    def register_widget(
        self,
        widget,
        *,
        on_theme_changed=None,
        on_appearance_changed=None,
    ):
        if on_theme_changed is not None:
            try:
                self.theme_changed.connect(on_theme_changed)
            except Exception:
                pass

            def _disconnect_theme(*_):
                try:
                    self.theme_changed.disconnect(on_theme_changed)
                except (TypeError, RuntimeError, SystemError):
                    pass

            try:
                widget.destroyed.connect(_disconnect_theme)
            except Exception:
                pass

        if on_appearance_changed is not None:
            try:
                self.appearance_changed.connect(on_appearance_changed)
            except Exception:
                pass

            def _disconnect_appearance(*_):
                try:
                    self.appearance_changed.disconnect(on_appearance_changed)
                except (TypeError, RuntimeError, SystemError):
                    pass

            try:
                widget.destroyed.connect(_disconnect_appearance)
            except Exception:
                pass

    # ==================================================================
    # USER CONTEXT
    # ==================================================================

    def set_user(self, user_id: Optional[str]):
        normalized = self._normalize_user_id(user_id)
        if normalized == self.current_user_id:
            return

        self.current_user_id = normalized
        old_appearance = dict(self._appearance)

        if normalized:
            self._load_user_preferences()
        else:
            # No user context -> reset to the system-derived defaults.
            self._appearance = deepcopy(self._default_appearance)

        self._tokens = self._get_tokens_for_theme(self._appearance["theme"])

        if self._appearance != old_appearance:
            self.invalidate_qss_cache()
            self.apply_current_theme()
            self._emit_change()

    @staticmethod
    def _normalize_user_id(user_id: Optional[str]) -> Optional[str]:
        if user_id is None:
            return None
        value = str(user_id).strip()
        if not value:
            return None
        return value.replace("\\", "_").replace("/", "_").replace(":", "_")

    # ==================================================================
    # USER PREFERENCE STORAGE
    # ==================================================================

    def _user_settings_prefix(self) -> Optional[str]:
        if not self.current_user_id:
            return None
        return f"users/{self.current_user_id}/appearance"

    def _load_user_preferences(self):
        prefix = self._user_settings_prefix()
        if not prefix:
            return

        # Start from the system-derived defaults so a partially
        # stored preference set still gets sensible values for
        # missing keys.
        appearance = deepcopy(self._default_appearance)

        for key, default_value in appearance.items():
            value = self.settings.value(f"{prefix}/{key}", default_value)

            if isinstance(default_value, bool):
                if isinstance(value, str):
                    value = value.lower() in ("true", "1", "yes", "on")
                else:
                    value = bool(value)
            elif isinstance(default_value, int):
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    value = default_value
            else:
                value = str(value)

            appearance[key] = value

        if appearance["theme"] not in self.SUPPORTED_THEMES:
            appearance["theme"] = self._default_appearance["theme"]
        if appearance["density"] not in self.SUPPORTED_DENSITIES:
            appearance["density"] = self._default_appearance["density"]
        if appearance["font_weight"] not in self.SUPPORTED_FONT_WEIGHTS:
            appearance["font_weight"] = self._default_appearance["font_weight"]
        if appearance["radius"] not in self.RADIUS_VALUES:
            appearance["radius"] = self._default_appearance["radius"]

        try:
            fs = int(appearance["font_size"])
            if not 9 <= fs <= 24:
                raise ValueError
            appearance["font_size"] = fs
        except (TypeError, ValueError):
            appearance["font_size"] = self._default_appearance["font_size"]

        try:
            families = QFontDatabase.families()
            if appearance["font_family"] not in families:
                appearance["font_family"] = self._default_appearance["font_family"]
        except Exception:
            appearance["font_family"] = self._default_appearance["font_family"]

        self._appearance = appearance

    def _save_user_preferences(self):
        prefix = self._user_settings_prefix()
        if not prefix:
            logger.warning("Cannot save appearance preferences without a user context.")
            return

        for key, value in self._appearance.items():
            self.settings.setValue(f"{prefix}/{key}", value)

        self.settings.sync()

    # ==================================================================
    # API
    # ==================================================================

    def get_current_theme(self) -> str:
        return self._appearance["theme"]

    def is_dark(self) -> bool:
        return self.get_current_theme() == "dark"

    def get_tokens(self) -> dict:
        return self._tokens

    def get_appearance(self) -> Dict[str, Any]:
        return deepcopy(self._appearance)

    def get_appearance_value(self, key: str, default: Any = None) -> Any:
        return self._appearance.get(key, default)

    def get_icon_color(self) -> str:
        return self._tokens.get("muted-foreground", "#64748B")

    def is_reduced_effects(self) -> bool:
        return bool(self._appearance.get("reduced_effects", False))

    # ==================================================================
    # UPDATE
    # ==================================================================

    def update_appearance(
        self,
        *,
        theme: Optional[str] = None,
        font_family: Optional[str] = None,
        font_size: Optional[int] = None,
        font_weight: Optional[str] = None,
        density: Optional[str] = None,
        radius: Optional[str] = None,
        high_contrast: Optional[bool] = None,
        reduced_effects: Optional[bool] = None,
        persist: bool = True,
    ):
        new_values: Dict[str, Any] = {}

        if theme is not None:
            if theme not in self.SUPPORTED_THEMES:
                raise ValueError(f"Unsupported theme: {theme}")
            new_values["theme"] = theme

        if font_family is not None:
            available = QFontDatabase.families()
            if font_family not in available:
                raise ValueError(f"Unsupported font family: {font_family}")
            new_values["font_family"] = font_family

        if font_size is not None:
            font_size = int(font_size)
            if not 9 <= font_size <= 24:
                raise ValueError("Font size must be between 9 and 24.")
            new_values["font_size"] = font_size

        if font_weight is not None:
            if font_weight not in self.SUPPORTED_FONT_WEIGHTS:
                raise ValueError(f"Unsupported font weight: {font_weight}")
            new_values["font_weight"] = font_weight

        if density is not None:
            if density not in self.SUPPORTED_DENSITIES:
                raise ValueError(f"Unsupported density: {density}")
            new_values["density"] = density

        if radius is not None:
            if radius not in self.RADIUS_VALUES:
                raise ValueError(f"Unsupported radius: {radius}")
            new_values["radius"] = radius

        if high_contrast is not None:
            new_values["high_contrast"] = bool(high_contrast)

        if reduced_effects is not None:
            new_values["reduced_effects"] = bool(reduced_effects)

        if not new_values:
            return

        old_appearance = dict(self._appearance)
        self._appearance.update(new_values)

        if self._appearance == old_appearance:
            return

        self._tokens = self._get_tokens_for_theme(self._appearance["theme"])
        self.invalidate_qss_cache()

        if persist:
            self._save_user_preferences()

        self.apply_current_theme()
        self._emit_change()

    def reset_to_defaults(self, persist: bool = True):
        """
        Reset appearance to the current defaults.

        Re-detects the OS theme first so a user who pressed "Reset to
        defaults" gets the OS theme in effect right now, not the one
        captured at app start.
        """
        self.re_detect_system_theme()

        old_appearance = dict(self._appearance)
        self._appearance = deepcopy(self._default_appearance)

        if self._appearance == old_appearance:
            return

        self._tokens = self._get_tokens_for_theme(self._appearance["theme"])
        self.invalidate_qss_cache()

        if persist:
            self._save_user_preferences()

        self.apply_current_theme()
        self._emit_change()

    def _emit_change(self):
        theme = self._appearance["theme"]
        self.theme_changed.emit(theme)
        self.appearance_changed.emit(self.get_appearance())

    # ==================================================================
    # LEGACY
    # ==================================================================

    def set_theme(self, theme: str):
        self.update_appearance(theme=theme)

    def toggle_theme(self):
        next_theme = "dark" if not self.is_dark() else "light"
        self.set_theme(next_theme)

    # ==================================================================
    # APPLICATION FONT
    # ==================================================================

    def _build_application_font(self) -> QFont:
        family = self._appearance["font_family"]
        size = self._appearance["font_size"]
        weight = self.SUPPORTED_FONT_WEIGHTS[self._appearance["font_weight"]]

        font = QFont(family, size)
        font.setWeight(weight)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        font.setStyleStrategy(
            QFont.StyleStrategy.PreferAntialias
            | QFont.StyleStrategy.PreferQuality
        )
        return font

    def apply_application_font(self):
        app = QApplication.instance()
        if app is None:
            return
        app.setFont(self._build_application_font())

    def apply_current_theme(self):
        app = QApplication.instance()
        if app is None:
            return

        self._tokens = self._get_tokens_for_theme(self._appearance["theme"])
        self.apply_application_font()

        if self._app_qss_cache is None:
            self._app_qss_cache = self._build_stylesheet()
        app.setStyleSheet(self._app_qss_cache)

        for w in app.allWidgets():
            try:
                if not w.isVisible():
                    continue
            except RuntimeError:
                continue
            try:
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()
            except Exception:
                pass

    # ==================================================================
    # TOKEN BUILDING
    # ==================================================================

    def _get_tokens_for_theme(self, theme: str) -> dict:
        semantic = build_semantic(
            theme=theme,
            density=self._appearance["density"],
            radius_key=self._appearance["radius"],
            high_contrast=self._appearance["high_contrast"],
            font_size=self._appearance["font_size"],
        )
        component = build_components(semantic)
        merged = dict(semantic)
        merged.update(component)
        return merged

    # ==================================================================
    # STYLESHEET
    # ==================================================================

    def get_stylesheet(self) -> str:
        if self._app_qss_cache is None:
            self._app_qss_cache = self._build_stylesheet()
        return self._app_qss_cache

    def _build_stylesheet(self) -> str:
        t = self._tokens
        font_family = self._appearance["font_family"]
        font_size = self._appearance["font_size"]
        sb_size = t.get("scrollbar_size", 10)
        sb_radius = t.get("scrollbar_radius", 5)
        focus_ring = t.get("ring", t["primary"])
        focus_width = "2px"

        return f"""
        /* ============================== GLOBAL ============================== */
        QMainWindow, QDialog {{
            background-color: {t["background"]};
            color: {t["foreground"]};
        }}
        QWidget {{
            color: {t["foreground"]};
            font-family: "{font_family}";
            font-size: {font_size}px;
        }}
        QLabel {{ color: {t["foreground"]}; background: transparent; }}

        /* ============================== FOCUS RING ========================= */
        QPushButton:focus,
        QCheckBox:focus,
        QRadioButton:focus,
        QComboBox:focus,
        QLineEdit:focus,
        QTextEdit:focus,
        QPlainTextEdit:focus,
        QSpinBox:focus,
        QDoubleSpinBox:focus,
        QDateEdit:focus {{
            outline: none;
        }}

        /* ============================== BUTTONS ============================ */
        QPushButton {{
            min-height: {t["control_height"]}px;
            border: 2px solid transparent;
            border-radius: {t["radius"]};
            padding: {t["padding_vertical"]}px {t["padding_horizontal"]}px;
            background-color: {t["primary"]};
            color: {t["primary-foreground"]};
            font-weight: 500;
        }}
        QPushButton:hover {{ background-color: {t["primary-hover"]}; }}
        QPushButton:pressed {{ background-color: {t["primary-hover"]}; }}
        QPushButton:focus {{ border: {focus_width} solid {focus_ring}; }}
        QPushButton:disabled {{
            color: {t["muted-foreground"]};
            background-color: {t["muted"]};
        }}

        QPushButton#secondaryButton {{
            background-color: {t["secondary"]};
            color: {t["secondary-foreground"]};
            border: 1px solid {t["border"]};
        }}
        QPushButton#secondaryButton:hover {{
            background-color: {t["accent"]};
            border-color: {t["border-strong"]};
        }}
        QPushButton#secondaryButton:focus {{
            border: {focus_width} solid {focus_ring};
        }}

        /* ============================== INPUTS ============================= */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit {{
            min-height: {t["control_height"]}px;
            background-color: {t["input"]};
            border: 1px solid {t["border"]};
            border-radius: {t["radius"]};
            padding: {t["padding_vertical"]}px {t["padding_horizontal"]}px;
            color: {t["foreground"]};
            selection-background-color: {t["primary"]};
            selection-color: {t["primary-foreground"]};
        }}
        QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
        QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover {{
            border-color: {t["border-strong"]};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
            border: {focus_width} solid {focus_ring};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
        QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled {{
            background-color: {t["muted"]};
            color: {t["muted-foreground"]};
        }}

        /* ============================== COMBOBOX =========================== */
        QComboBox {{
            min-height: {t["control_height"]}px;
            background-color: {t["input"]};
            border: 1px solid {t["border"]};
            border-radius: {t["radius"]};
            padding: {t["padding_vertical"]}px {t["padding_horizontal"]}px;
            color: {t["foreground"]};
        }}
        QComboBox:hover {{ border-color: {t["border-strong"]}; }}
        QComboBox:focus {{ border: {focus_width} solid {focus_ring}; }}
        QComboBox:disabled {{
            background-color: {t["muted"]};
            color: {t["muted-foreground"]};
        }}
        QComboBox::drop-down {{ border: none; width: 28px; }}
        QComboBox QAbstractItemView {{
            background-color: {t["popover"]};
            color: {t["popover-foreground"]};
            border: 1px solid {t["border"]};
            selection-background-color: {t["primary-subtle"]};
            selection-color: {t["foreground"]};
            outline: none;
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {t["primary-subtle"]};
            color: {t["foreground"]};
        }}
        QComboBox QAbstractItemView::item:selected:focus,
        QComboBox QAbstractItemView::item:selected:active {{
            background-color: {t["primary-subtle"]};
            color: {t["primary"]};
            border: 1px solid {focus_ring};
        }}

        /* ============================== CHECKBOX / RADIO =================== */
        QCheckBox, QRadioButton {{
            spacing: 8px;
            color: {t["foreground"]};
        }}
        QCheckBox:focus, QRadioButton:focus {{
            color: {focus_ring};
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border: 1.5px solid {t["border-strong"]};
            background: {t["input"]};
        }}
        QCheckBox::indicator {{ border-radius: {t["radius-sm"]}; }}
        QRadioButton::indicator {{ border-radius: 8px; }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border-color: {t["ring"]};
        }}
        QCheckBox::indicator:focus, QRadioButton::indicator:focus {{
            border: 2px solid {focus_ring};
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background: {t["primary"]};
            border-color: {t["primary"]};
        }}
        QCheckBox:disabled, QRadioButton:disabled {{
            color: {t["muted-foreground"]};
        }}

        /* ============================== TABLES ============================= */
        QTableWidget, QTableView {{
            background-color: {t["surface"]};
            alternate-background-color: {t["muted"]};
            gridline-color: transparent;
            border: 1px solid {t["border"]};
            border-radius: {t["radius-lg"]};
            color: {t["foreground"]};
            outline: none;
        }}
        QTableWidget::item, QTableView::item {{
            color: {t["foreground"]};
            padding: 0 14px;
            border-bottom: 1px solid {t["border"]};
        }}
        QTableWidget::item:hover, QTableView::item:hover {{
            background-color: {t["surface-hover"]};
        }}
        QTableWidget::item:selected, QTableView::item:selected {{
            background-color: {t["primary-subtle"]};
            color: {t["primary"]};
        }}
        QTableWidget:focus, QTableView:focus {{
            border: {focus_width} solid {focus_ring};
        }}
        QHeaderView::section {{
            background-color: {t["muted"]};
            color: {t["muted-foreground"]};
            padding: 9px 14px;
            border: none;
            border-bottom: 1px solid {t["border"]};
            font-weight: 600;
        }}
        QHeaderView::section:focus {{
            border-bottom: 2px solid {focus_ring};
        }}

        /* ============================== TABS =============================== */
        QTabWidget::pane {{
            border: 1px solid {t["border"]};
            border-radius: {t["radius-lg"]};
            background-color: {t["surface"]};
            top: -1px;
        }}
        QTabBar {{ qproperty-drawBase: 0; background: transparent; }}
        QTabBar::tab {{
            background: transparent;
            color: {t["muted-foreground"]};
            padding: 8px 14px;
            border: none;
            border-bottom: 2px solid transparent;
            margin-right: 2px;
        }}
        QTabBar::tab:hover {{
            color: {t["foreground"]};
            background: {t["surface-hover"]};
        }}
        QTabBar::tab:focus {{
            border: {focus_width} solid {focus_ring};
            border-bottom: 2px solid {focus_ring};
        }}
        QTabBar::tab:selected {{
            color: {t["primary"]};
            border-bottom: 2px solid {t["primary"]};
            font-weight: 600;
        }}

        /* ============================== SCROLLBARS ========================= */
        QScrollBar:vertical {{
            background: {t["scrollbar_track"]};
            width: {sb_size}px;
            margin: 0;
            border: none;
            border-radius: {sb_radius}px;
        }}
        QScrollBar::handle:vertical {{
            background: {t["scrollbar_handle"]};
            border-radius: {sb_radius}px;
            min-height: 36px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {t["scrollbar_handle_hover"]};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

        QScrollBar:horizontal {{
            background: {t["scrollbar_track"]};
            height: {sb_size}px;
            margin: 0;
            border: none;
            border-radius: {sb_radius}px;
        }}
        QScrollBar::handle:horizontal {{
            background: {t["scrollbar_handle"]};
            border-radius: {sb_radius}px;
            min-width: 36px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {t["scrollbar_handle_hover"]};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

        /* ============================== MENUS ============================== */
        QMenuBar {{
            background-color: {t["surface"]};
            border-bottom: 1px solid {t["border"]};
            color: {t["foreground"]};
        }}
        QMenuBar::item {{
            background: transparent;
            color: {t["foreground"]};
            padding: 5px 10px;
            border-radius: {t["radius-sm"]};
        }}
        QMenuBar::item:selected {{ background-color: {t["secondary"]}; }}
        QMenuBar::item:focus {{ border: {focus_width} solid {focus_ring}; }}
        QMenu {{
            background-color: {t["popover"]};
            color: {t["foreground"]};
            border: 1px solid {t["border"]};
            padding: 4px;
        }}
        QMenu::item {{
            color: {t["foreground"]};
            padding: 6px 22px 6px 12px;
            border-radius: {t["radius-sm"]};
        }}
        QMenu::item:selected {{ background-color: {t["secondary"]}; }}
        QMenu::item:focus {{ border: {focus_width} solid {focus_ring}; }}

        /* ============================== TOOLTIPS =========================== */
        QToolTip {{
            background-color: {t["foreground"]};
            color: {t["background"]};
            border: none;
            padding: 5px 10px;
        }}

        /* ============================== PROGRESS =========================== */
        QProgressBar {{
            background-color: {t["muted"]};
            border: none;
            border-radius: {t["radius-sm"]};
            height: 6px;
            color: transparent;
        }}
        QProgressBar::chunk {{
            background-color: {t["primary"]};
            border-radius: {t["radius-sm"]};
        }}

        /* ============================== SEPARATORS ========================= */
        QFrame[frameShape="4"], QFrame[frameShape="5"] {{
            background-color: {t["border"]};
            border: none;
            max-height: 1px;
        }}

        /* ============================== CARDS ============================== */
        QFrame#ShadcnCard {{
            background-color: {t["surface"]};
            border: 1px solid {t["border"]};
            border-radius: {t["radius-lg"]};
        }}

        /* ============================== SHELL ============================== */
        QWidget#header {{
            background-color: {t["background"]};
            border-bottom: 1px solid {t["border"]};
        }}
        QWidget#sidebar {{
            background-color: {t["background"]};
            border-right: 1px solid {t["border"]};
        }}

        /* ============================== CALENDAR =========================== */
        QCalendarWidget QWidget {{ alternate-background-color: {t["muted"]}; }}
        QCalendarWidget QAbstractItemView:enabled {{
            background-color: {t["surface"]};
            color: {t["foreground"]};
            selection-background-color: {t["primary"]};
            selection-color: {t["primary-foreground"]};
        }}
        QCalendarWidget QAbstractItemView:disabled {{
            color: {t["muted-foreground"]};
        }}
        QCalendarWidget QToolButton {{
            background: transparent;
            color: {t["foreground"]};
            border: none;
            padding: 4px 8px;
        }}
        QCalendarWidget QToolButton:hover {{ background: {t["surface-hover"]}; }}
        QCalendarWidget QToolButton:focus {{ border: {focus_width} solid {focus_ring}; }}
        QCalendarWidget QMenu {{ background: {t["popover"]}; color: {t["foreground"]}; }}
        QCalendarWidget QSpinBox {{
            background: {t["input"]};
            color: {t["foreground"]};
            border: 1px solid {t["border"]};
            border-radius: {t["radius-sm"]};
        }}

        /* ============================== SPLITTER =========================== */
        QSplitter::handle {{ background: {t["border"]}; }}
        QSplitter::handle:hover {{ background: {t["border-strong"]}; }}

        /* ============================== GROUP BOX ========================== */
        QGroupBox {{
            border: 1px solid {t["border"]};
            border-radius: {t["radius"]};
            margin-top: 10px;
            padding-top: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: {t["muted-foreground"]};
            background: {t["background"]};
        }}

        /* ============================== TOOLBAR / STATUS =================== */
        QToolBar {{
            background: {t["surface"]};
            border-bottom: 1px solid {t["border"]};
            spacing: 4px;
        }}
        QStatusBar {{
            background: {t["surface"]};
            border-top: 1px solid {t["border"]};
            color: {t["muted-foreground"]};
        }}

        /* ============================== SLIDER ============================= */
        QSlider::groove:horizontal {{
            background: {t["muted"]};
            height: 4px;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {t["primary"]};
            width: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }}
        QSlider::handle:horizontal:focus {{
            border: 2px solid {focus_ring};
        }}
        """

    def initialize_for_user(self, user_id: Optional[str]):
        self.current_user_id = None
        self.set_user(user_id)
