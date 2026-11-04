# pages/settings_page.py
"""
Enterprise settings page with appearance, environment, updates, and
diagnostics.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QMessageBox, QPushButton, QFrame, QCheckBox, QSpinBox, QScrollArea,
    QSizePolicy, QDialog,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFontDatabase

from widgets.components import (
    ShadcnCard, CardContent, ShadcnLoadingSpinner, ShadcnAlertDialog,
    ShadcnToast, ShadcnButton,
)
from core.theme_manager import ThemeManager

import os
import re
import sys
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

# A "well-formed" version is one or more dot-separated numeric segments,
# optionally followed by a pre-release suffix (-beta.1, +build.5, etc.).
_VERSION_RE = re.compile(
    r"^v?\d+(?:\.\d+){0,3}(?:[-+][0-9A-Za-z\.\-]+)?$"
)


def _format_version(raw: str) -> str:
    """
    Return a safe, human-readable version string.

    The version file that ships with the app is sometimes overwritten
    by a Windows resource tool that dumps a full VERSIONINFO block
    (``VSVersionInfo(ffi=FixedFileInfo(...))``) into it. Feeding that
    to a QLabel renders a page full of code. This helper inspects the
    raw text, extracts a plausible version number if one is present,
    and otherwise returns "unknown".
    """
    if not raw:
        return "unknown"

    text = str(raw).strip()
    if not text:
        return "unknown"

    # Happy path: the file contains a plain version string.
    if _VERSION_RE.match(text):
        return text

    # Some resource files contain a "ProductVersion" or "FileVersion"
    # line. Look for the first token that looks like a version number.
    for token in re.split(r"[\s,'\"\(\)=]+", text):
        token = token.strip()
        if not token:
            continue
        if _VERSION_RE.match(token):
            return token

    return "unknown"


def _read_app_version() -> str:
    """Read the app version, tolerating a malformed version file."""
    # Try the packaged version.txt first.
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(
            os.path.join(os.path.dirname(sys.executable), "version.txt")
        )
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "version.txt"))
    candidates.append(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "version.txt",
        )
    )
    candidates.append("version.txt")

    for path in candidates:
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    raw = f.read()
                return _format_version(raw)
        except Exception:
            continue

    # Fall back to the update checker if it exposes a version.
    try:
        from core.update_checker import _read_local_version
        return _format_version(_read_local_version())
    except Exception:
        return "unknown"


class SettingsPage(QWidget):
    """
    Enterprise settings page with:
    - Per-user appearance preferences
    - Environment management
    - Application updates (check / install)
    - Diagnostics (send logs to support)
    """

    navigate_requested = Signal(str)
    environment_changed = Signal(str)

    def __init__(
        self,
        user_info,
        permissions,
        data_service,
        env_manager=None,
        api_client=None,
    ):
        super().__init__()
        self.user_info = user_info
        self.permissions = permissions
        self.data_service = data_service
        self.env_manager = env_manager
        self.api_client = api_client

        self.theme_manager = ThemeManager()

        self._is_testing = False
        self._is_loading = True
        self._first_show_done = False
        self._fonts_populated = False
        self._ignore_next_appearance_signal = True

        self._appearance_section: QWidget = None
        self._appearance_status: QLabel = None
        self._appearance_spinner: ShadcnLoadingSpinner = None

        self.init_ui()
        self._is_loading = False

        try:
            self.theme_manager.appearance_changed.connect(
                self._on_appearance_changed
            )
        except Exception:
            pass

    # ==================================================================
    # Outer layout
    # ==================================================================

    def init_ui(self):
        tokens = self.theme_manager.get_tokens()
        bg = tokens.get("background", "#F8FAFC")
        fg = tokens.get("foreground", "#0F172A")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setAccessibleName("Settings")

        self._scroll_container = QWidget()
        self._scroll_container.setObjectName("settingsContainer")

        layout = QVBoxLayout(self._scroll_container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        title = QLabel("Settings")
        title.setStyleSheet(
            f"font-size: {tokens['font.h2']}px; font-weight: 600; "
            f"color: {fg}; background: transparent;"
        )
        layout.addWidget(title)

        # --- Sections, in display order ---
        self._appearance_section = self.create_appearance_settings()
        layout.addWidget(self._appearance_section)

        if self.env_manager and self.api_client:
            layout.addWidget(self.create_environment_settings())

        layout.addWidget(self.create_updates_section())
        layout.addWidget(self.create_logs_section())
        layout.addWidget(self.create_about_section())
        layout.addStretch()

        self._scroll.setWidget(self._scroll_container)
        root.addWidget(self._scroll)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._first_show_done:
            self._first_show_done = True
            QTimer.singleShot(0, self._apply_outer_styles)

    def _apply_outer_styles(self):
        try:
            tokens = self.theme_manager.get_tokens()
            bg = tokens.get("background", "#F8FAFC")
            fg = tokens.get("foreground", "#0F172A")
            self._scroll.setStyleSheet(self._scroll_style(bg, tokens))
            self._scroll_container.setStyleSheet(
                f"#settingsContainer {{ background-color: {bg}; "
                f"color: {fg}; }}"
            )
        except Exception as exc:
            logger.debug("Failed to apply settings styles: %s", exc)

    def _scroll_style(self, bg: str, tokens: dict) -> str:
        sb_size = tokens.get("scrollbar_size", 10)
        sb_radius = tokens.get("scrollbar_radius", 5)
        sb_track = tokens.get("scrollbar_track",
                              tokens.get("muted", "#F1F5F9"))
        sb_handle = tokens.get("scrollbar_handle",
                               tokens.get("border-strong", "#94A3B8"))
        sb_hover = tokens.get(
            "scrollbar_handle_hover",
            tokens.get("foreground-secondary", "#64748B"),
        )

        return f"""
            QScrollArea {{ background-color: {bg}; border: none; }}
            QScrollArea > QWidget > QWidget {{ background-color: {bg}; }}
            QScrollBar:vertical {{
                background: {sb_track};
                width: {sb_size}px;
                border: none;
                border-radius: {sb_radius}px;
            }}
            QScrollBar::handle:vertical {{
                background: {sb_handle};
                border-radius: {sb_radius}px;
                min-height: 40px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {sb_hover}; }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """

    def _on_appearance_changed(self, *_):
        if self._ignore_next_appearance_signal:
            self._ignore_next_appearance_signal = False
            return
        if self.isVisible():
            self._sync_controls()

    # ==================================================================
    # Appearance section
    # ==================================================================

    def create_appearance_settings(self):
        tokens = self.theme_manager.get_tokens()
        card = ShadcnCard()

        header_row = QWidget()
        header_row.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(16, 14, 16, 4)
        header_layout.setSpacing(10)

        header = QLabel("Appearance")
        header.setStyleSheet(
            f"font-weight: 600; font-size: {tokens['font.h4']}px; "
            "background: transparent;"
        )
        header_layout.addWidget(header)

        self._appearance_spinner = ShadcnLoadingSpinner(size="sm")
        self._appearance_spinner.set_color(tokens.get("primary", "#006B3F"))
        header_layout.addWidget(self._appearance_spinner)

        self._appearance_status = QLabel("")
        self._appearance_status.setStyleSheet(
            f"font-size: {tokens['font.caption']}px; "
            f"color: {tokens['muted-foreground']}; background: transparent;"
        )
        header_layout.addWidget(self._appearance_status)

        header_layout.addStretch()
        card.set_header(header_row)

        content = CardContent()
        content.layout.setContentsMargins(16, 8, 16, 16)

        description = QLabel(
            "Customize the appearance of the application. "
            "These preferences are saved to your user profile and will "
            "be restored the next time you sign in."
        )
        description.setWordWrap(True)
        description.setStyleSheet(
            f"color: {tokens['muted-foreground']}; "
            f"font-size: {tokens['font.small']}px; margin-bottom: 8px; "
            "background: transparent;"
        )
        content.layout.addWidget(description)

        appearance = self.theme_manager.get_appearance()

        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.setAccessibleName("Theme")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        self._set_combo_by_data(self.theme_combo, appearance["theme"])
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        content.layout.addLayout(self._row("Theme", self.theme_combo))

        # Font family
        self.font_combo = QComboBox()
        self.font_combo.setAccessibleName("Font family")
        self.font_combo.addItem(appearance["font_family"])
        self.font_combo.setCurrentIndex(0)
        self.font_combo.currentTextChanged.connect(self.on_font_changed)
        self.font_combo.showPopup = self._wrap_show_popup(
            self.font_combo.showPopup
        )
        content.layout.addLayout(self._row("Font family", self.font_combo))

        # Font size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setAccessibleName("Font size")
        self.font_size_spin.setRange(9, 24)
        self.font_size_spin.setSuffix(" px")
        self.font_size_spin.setValue(int(appearance["font_size"]))
        self.font_size_spin.valueChanged.connect(self.on_font_size_changed)
        content.layout.addLayout(self._row("Font size", self.font_size_spin))

        # Font weight
        self.font_weight_combo = QComboBox()
        self.font_weight_combo.setAccessibleName("Font weight")
        self.font_weight_combo.addItem("Normal", "normal")
        self.font_weight_combo.addItem("Medium", "medium")
        self.font_weight_combo.addItem("Semi-bold", "semibold")
        self.font_weight_combo.addItem("Bold", "bold")
        self._set_combo_by_data(
            self.font_weight_combo, appearance["font_weight"]
        )
        self.font_weight_combo.currentIndexChanged.connect(
            self.on_font_weight_changed
        )
        content.layout.addLayout(
            self._row("Font weight", self.font_weight_combo)
        )

        # Density
        self.density_combo = QComboBox()
        self.density_combo.setAccessibleName("Interface density")
        self.density_combo.addItem("Compact", "compact")
        self.density_combo.addItem("Comfortable", "comfortable")
        self.density_combo.addItem("Spacious", "spacious")
        self._set_combo_by_data(self.density_combo, appearance["density"])
        self.density_combo.currentIndexChanged.connect(
            self.on_density_changed
        )
        content.layout.addLayout(
            self._row("Interface density", self.density_combo)
        )

        # Radius
        self.radius_combo = QComboBox()
        self.radius_combo.setAccessibleName("Corner radius")
        self.radius_combo.addItem("Small", "small")
        self.radius_combo.addItem("Medium", "medium")
        self.radius_combo.addItem("Large", "large")
        self._set_combo_by_data(self.radius_combo, appearance["radius"])
        self.radius_combo.currentIndexChanged.connect(self.on_radius_changed)
        content.layout.addLayout(
            self._row("Corner radius", self.radius_combo)
        )

        # Accessibility
        content.layout.addSpacing(6)

        access_label = QLabel("Accessibility")
        access_label.setStyleSheet(
            f"font-weight: 600; font-size: {tokens['font.small']}px; "
            f"color: {tokens['muted-foreground']}; margin-top: 4px; "
            "background: transparent;"
        )
        content.layout.addWidget(access_label)

        self.high_contrast_checkbox = QCheckBox("Use high contrast colors")
        self.high_contrast_checkbox.setAccessibleName("High contrast colors")
        self.high_contrast_checkbox.setChecked(
            bool(appearance["high_contrast"])
        )
        self.high_contrast_checkbox.stateChanged.connect(
            self.on_high_contrast_changed
        )
        content.layout.addWidget(self.high_contrast_checkbox)

        self.reduced_effects_checkbox = QCheckBox("Reduce visual effects")
        self.reduced_effects_checkbox.setAccessibleName("Reduce visual effects")
        self.reduced_effects_checkbox.setToolTip(
            "Disables the sidebar slide animation, the floating-label "
            "slide, shake-on-error, and toast fade-in."
        )
        self.reduced_effects_checkbox.setChecked(
            bool(appearance["reduced_effects"])
        )
        self.reduced_effects_checkbox.stateChanged.connect(
            self.on_reduced_effects_changed
        )
        content.layout.addWidget(self.reduced_effects_checkbox)

        # Reset
        content.layout.addSpacing(10)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        content.layout.addWidget(sep)

        reset_row = QHBoxLayout()
        reset_row.setSpacing(8)

        reset_label = QLabel(
            "Restore the default application appearance for your account."
        )
        reset_label.setStyleSheet(
            f"color: {tokens['muted-foreground']}; "
            f"font-size: {tokens['font.small']}px; background: transparent;"
        )
        reset_label.setWordWrap(True)
        reset_row.addWidget(reset_label, 1)

        self.reset_button = QPushButton("Restore Defaults")
        self.reset_button.setObjectName("secondaryButton")
        self.reset_button.setAccessibleName("Restore default appearance")
        self.reset_button.setCursor(Qt.PointingHandCursor)
        self.reset_button.clicked.connect(self.reset_appearance)
        reset_row.addWidget(self.reset_button)

        content.layout.addLayout(reset_row)

        card.set_content(content)
        return card

    # ------------------------------------------------------------------
    # Lazy font population
    # ------------------------------------------------------------------

    def _wrap_show_popup(self, original):
        def wrapped():
            if not self._fonts_populated:
                self._fonts_populated = True
                try:
                    current = self.font_combo.currentText()
                    available = QFontDatabase.families()

                    preferred = [
                        "Segoe UI", "Inter", "Roboto", "Noto Sans",
                        "Arial", "Verdana", "Tahoma",
                    ]
                    ordered = [f for f in preferred if f in available]
                    for f in available:
                        if f not in ordered:
                            ordered.append(f)

                    self.font_combo.blockSignals(True)
                    self.font_combo.clear()
                    self.font_combo.addItems(ordered)
                    idx = self.font_combo.findText(current)
                    if idx >= 0:
                        self.font_combo.setCurrentIndex(idx)
                    self.font_combo.blockSignals(False)
                except Exception as exc:
                    logger.debug("Failed to populate fonts: %s", exc)
            return original()
        return wrapped

    def _row(self, label_text: str, control: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        label = QLabel(label_text)
        label.setMinimumWidth(150)
        label.setStyleSheet("font-weight: 500; background: transparent;")

        row.addWidget(label)
        control.setMinimumWidth(200)
        control.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        row.addWidget(control, 1)
        return row

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value):
        idx = combo.findData(value)
        if idx >= 0:
            combo.blockSignals(True)
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    @staticmethod
    def _set_combo_by_text(combo: QComboBox, value):
        idx = combo.findText(value)
        if idx >= 0:
            combo.blockSignals(True)
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    # ==================================================================
    # Loading feedback
    # ==================================================================

    def _begin_save(self, message: str):
        if self._appearance_spinner is not None:
            self._appearance_spinner.start()
        if self._appearance_status is not None:
            tokens = self.theme_manager.get_tokens()
            self._appearance_status.setText(message)
            self._appearance_status.setStyleSheet(
                f"font-size: {tokens['font.caption']}px; "
                f"color: {tokens['primary']}; background: transparent;"
            )

    def _end_save(self, message: str = "Saved", error: bool = False):
        if self._appearance_spinner is not None:
            self._appearance_spinner.stop()

        if self._appearance_status is None:
            return

        tokens = self.theme_manager.get_tokens()
        color = tokens["destructive"] if error else tokens["success"]
        self._appearance_status.setText(message)
        self._appearance_status.setStyleSheet(
            f"font-size: {tokens['font.caption']}px; "
            f"color: {color}; background: transparent;"
        )
        QTimer.singleShot(1800, self._clear_status)

    def _clear_status(self):
        if self._appearance_status is not None:
            self._appearance_status.setText("")

    # ==================================================================
    # Appearance handlers
    # ==================================================================

    def _apply_change(self, label: str, **kwargs):
        self._begin_save(label)

        def _do():
            try:
                self.theme_manager.update_appearance(**kwargs)
                self._end_save("Saved")
            except Exception as exc:
                logger.error("Appearance change failed: %s", exc, exc_info=True)
                self._end_save(f"Failed: {exc}", error=True)

        QTimer.singleShot(60, _do)

    def on_theme_changed(self, index):
        if self._is_loading:
            return
        theme = self.theme_combo.itemData(index)
        if not theme:
            return
        self._apply_change("Applying theme…", theme=theme)

    def on_font_changed(self, font_family: str):
        if self._is_loading or not font_family:
            return
        self._apply_change("Applying font…", font_family=font_family)

    def on_font_size_changed(self, size: int):
        if self._is_loading:
            return
        self._apply_change("Applying font size…", font_size=int(size))

    def on_font_weight_changed(self, index):
        if self._is_loading:
            return
        weight = self.font_weight_combo.itemData(index)
        if not weight:
            return
        self._apply_change("Applying font weight…", font_weight=weight)

    def on_density_changed(self, index):
        if self._is_loading:
            return
        density = self.density_combo.itemData(index)
        if not density:
            return
        self._apply_change("Applying density…", density=density)

    def on_radius_changed(self, index):
        if self._is_loading:
            return
        radius = self.radius_combo.itemData(index)
        if not radius:
            return
        self._apply_change("Applying corner radius…", radius=radius)

    def on_high_contrast_changed(self, state):
        if self._is_loading:
            return
        self._apply_change(
            "Applying contrast…",
            high_contrast=(state == Qt.CheckState.Checked.value),
        )

    def on_reduced_effects_changed(self, state):
        if self._is_loading:
            return
        self._apply_change(
            "Applying visual effects…",
            reduced_effects=(state == Qt.CheckState.Checked.value),
        )

    def reset_appearance(self):
        result = QMessageBox.question(
            self,
            "Restore Defaults",
            "Restore the default appearance settings for your account?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        self.reset_button.setEnabled(False)
        self.reset_button.setText("Restoring defaults…")
        self._begin_save("Restoring defaults…")

        def _do():
            try:
                self.theme_manager.reset_to_defaults()
                self._sync_controls()
                self._end_save("Restored")
            except Exception as exc:
                logger.error("Failed to reset appearance: %s", exc,
                             exc_info=True)
                self._end_save(f"Failed: {exc}", error=True)
            finally:
                self.reset_button.setEnabled(True)
                self.reset_button.setText("Restore Defaults")

        QTimer.singleShot(80, _do)

    def _sync_controls(self, *_):
        self._is_loading = True
        try:
            appearance = self.theme_manager.get_appearance()
            self._set_combo_by_data(self.theme_combo, appearance["theme"])

            current_text = self.font_combo.currentText()
            if current_text != appearance["font_family"]:
                if self._fonts_populated:
                    self._set_combo_by_text(
                        self.font_combo, appearance["font_family"]
                    )
                else:
                    self.font_combo.blockSignals(True)
                    self.font_combo.clear()
                    self.font_combo.addItem(appearance["font_family"])
                    self.font_combo.blockSignals(False)

            self.font_size_spin.setValue(int(appearance["font_size"]))
            self._set_combo_by_data(
                self.font_weight_combo, appearance["font_weight"]
            )
            self._set_combo_by_data(
                self.density_combo, appearance["density"]
            )
            self._set_combo_by_data(
                self.radius_combo, appearance["radius"]
            )
            self.high_contrast_checkbox.setChecked(
                bool(appearance["high_contrast"])
            )
            self.reduced_effects_checkbox.setChecked(
                bool(appearance["reduced_effects"])
            )

            tokens = self.theme_manager.get_tokens()
            bg = tokens.get("background", "#F8FAFC")
            fg = tokens.get("foreground", "#0F172A")
            self._scroll_container.setStyleSheet(
                f"#settingsContainer {{ background-color: {bg}; "
                f"color: {fg}; }}"
            )
            self._scroll.setStyleSheet(self._scroll_style(bg, tokens))

            if self._appearance_spinner is not None:
                self._appearance_spinner.set_color(
                    tokens.get("primary", "#006B3F")
                )
        finally:
            self._is_loading = False

    # ==================================================================
    # Environment section
    # ==================================================================

    def create_environment_settings(self):
        tokens = self.theme_manager.get_tokens()
        card = ShadcnCard()

        header = QLabel("API Connection Settings")
        header.setStyleSheet(
            f"font-weight: 600; font-size: {tokens['font.h4']}px; "
            "padding: 16px 16px 0 16px; background: transparent;"
        )
        card.set_header(header)

        content = CardContent()
        content.layout.setContentsMargins(16, 8, 16, 16)

        env_layout = QHBoxLayout()
        env_layout.setSpacing(8)
        env_label = QLabel("Current Environment:")
        env_label.setStyleSheet("font-weight: 500; background: transparent;")
        env_layout.addWidget(env_label)

        self.current_env_label = QLabel(self.env_manager.current_env.upper())
        self._update_env_label_style()
        env_layout.addWidget(self.current_env_label)
        env_layout.addStretch()
        content.layout.addLayout(env_layout)

        url_layout = QHBoxLayout()
        url_layout.setSpacing(8)
        url_label = QLabel("API URL:")
        url_label.setStyleSheet("font-weight: 500; background: transparent;")
        url_layout.addWidget(url_label)

        self.current_url_label = QLabel(self.env_manager.get_base_url())
        self.current_url_label.setWordWrap(True)
        url_layout.addWidget(self.current_url_label, 1)
        content.layout.addLayout(url_layout)

        content.layout.addSpacing(10)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        content.layout.addWidget(sep)
        content.layout.addSpacing(10)

        switch_label = QLabel("Switch to:")
        switch_label.setStyleSheet("font-weight: 500; background: transparent;")
        content.layout.addWidget(switch_label)

        env_selector_layout = QHBoxLayout()
        env_selector_layout.setSpacing(10)

        self.env_combo = QComboBox()
        self.env_combo.setAccessibleName("Environment")
        self.env_combo.addItems(self.env_manager.get_available_environments())
        self.env_combo.setCurrentText(self.env_manager.current_env)
        self.env_combo.currentTextChanged.connect(self.on_env_selected)
        self.env_combo.setMinimumWidth(150)
        env_selector_layout.addWidget(self.env_combo)
        env_selector_layout.addStretch()
        content.layout.addLayout(env_selector_layout)

        self.custom_url_widget = QWidget()
        custom_url_layout = QHBoxLayout(self.custom_url_widget)
        custom_url_layout.setContentsMargins(0, 8, 0, 0)
        custom_url_layout.setSpacing(10)

        custom_label = QLabel("Custom URL:")
        custom_label.setStyleSheet("font-weight: 500; background: transparent;")
        custom_url_layout.addWidget(custom_label)

        self.custom_url_input = QLineEdit()
        self.custom_url_input.setAccessibleName("Custom API URL")
        self.custom_url_input.setPlaceholderText("https://your-api-url.com")
        self.custom_url_input.setMinimumWidth(300)
        if self.env_manager.current_env == "custom":
            self.custom_url_input.setText(
                self.env_manager.settings.value("custom_api_url", "")
            )
        else:
            self.custom_url_widget.setVisible(False)

        custom_url_layout.addWidget(self.custom_url_input)

        self.save_custom_btn = QPushButton("Apply Custom URL")
        self.save_custom_btn.setObjectName("secondaryButton")
        self.save_custom_btn.setAccessibleName("Apply custom URL")
        self.save_custom_btn.setCursor(Qt.PointingHandCursor)
        self.save_custom_btn.clicked.connect(self.save_custom_url)
        self.save_custom_btn.setVisible(
            self.env_manager.current_env == "custom"
        )
        custom_url_layout.addWidget(self.save_custom_btn)

        content.layout.addWidget(self.custom_url_widget)
        content.layout.addSpacing(10)

        test_layout = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.setObjectName("secondaryButton")
        self.test_btn.setAccessibleName("Test connection")
        self.test_btn.setCursor(Qt.PointingHandCursor)
        self.test_btn.clicked.connect(self.test_connection)
        test_layout.addWidget(self.test_btn)
        test_layout.addStretch()
        content.layout.addLayout(test_layout)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {tokens['muted-foreground']}; margin-top: 5px; "
            f"font-size: {tokens['font.small']}px; background: transparent;"
        )
        content.layout.addWidget(self.status_label)

        card.set_content(content)
        return card

    # ==================================================================
    # Updates section
    # ==================================================================

    def create_updates_section(self):
        tokens = self.theme_manager.get_tokens()
        card = ShadcnCard()

        header = QLabel("Updates")
        header.setStyleSheet(
            f"font-weight: 600; font-size: {tokens['font.h4']}px; "
            "padding: 16px 16px 0 16px; background: transparent;"
        )
        card.set_header(header)

        content = CardContent()
        content.layout.setContentsMargins(16, 8, 16, 16)
        content.layout.setSpacing(10)

        desc = QLabel(
            "Check for and install the latest version of the application. "
            "The updater downloads a signed payload and restarts the app."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {tokens['muted-foreground']}; "
            f"font-size: {tokens['font.small']}px; background: transparent;"
        )
        content.layout.addWidget(desc)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.check_updates_btn = ShadcnButton(
            "Check for Updates", variant="default"
        )
        self.check_updates_btn.clicked.connect(self._on_check_updates)
        row.addWidget(self.check_updates_btn)

        self.auto_update_checkbox = QCheckBox("Check automatically on startup")
        try:
            from core.update_checker import UpdateChecker
            self.auto_update_checkbox.setChecked(
                UpdateChecker().is_auto_check_enabled()
            )
        except Exception:
            self.auto_update_checkbox.setChecked(True)
        self.auto_update_checkbox.stateChanged.connect(
            self._on_toggle_auto_update
        )
        row.addWidget(self.auto_update_checkbox)

        row.addStretch()
        content.layout.addLayout(row)

        self.update_status = QLabel("")
        self.update_status.setStyleSheet(
            f"color: {tokens['muted-foreground']}; "
            f"font-size: {tokens['font.small']}px; background: transparent;"
        )
        self.update_status.setWordWrap(True)
        content.layout.addWidget(self.update_status)

        card.set_content(content)
        return card

    def _on_check_updates(self):
        tokens = self.theme_manager.get_tokens()
        self.update_status.setText("Checking for updates…")
        self.update_status.setStyleSheet(
            f"color: {tokens['info']}; "
            f"font-size: {tokens['font.small']}px; background: transparent;"
        )
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            from core.update_checker import UpdateChecker
            checker = UpdateChecker()
            info = checker.check_now()
        except Exception as e:
            self.update_status.setText(f"Check failed: {e}")
            self.update_status.setStyleSheet(
                f"color: {tokens['destructive']}; "
                f"font-size: {tokens['font.small']}px; background: transparent;"
            )
            return

        if not info:
            self.update_status.setText("You are on the latest version.")
            self.update_status.setStyleSheet(
                f"color: {tokens['success']}; "
                f"font-size: {tokens['font.small']}px; background: transparent;"
            )
            return

        self.update_status.setText(
            f"Version {info.get('version')} is available."
        )
        self.update_status.setStyleSheet(
            f"color: {tokens['warning']}; "
            f"font-size: {tokens['font.small']}px; background: transparent;"
        )

        from dialogs.update_dialog import UpdateDialog
        dlg = UpdateDialog(info, parent=self)
        dlg.exec()

    def _on_toggle_auto_update(self, state):
        try:
            from core.update_checker import UpdateChecker
            UpdateChecker().set_auto_check_enabled(
                state == Qt.CheckState.Checked.value
            )
        except Exception as e:
            logger.error(f"Failed to persist auto-update preference: {e}")

    # ==================================================================
    # Diagnostics / logs section
    # ==================================================================

    def create_logs_section(self):
        tokens = self.theme_manager.get_tokens()
        card = ShadcnCard()

        header = QLabel("Diagnostics")
        header.setStyleSheet(
            f"font-weight: 600; font-size: {tokens['font.h4']}px; "
            "padding: 16px 16px 0 16px; background: transparent;"
        )
        card.set_header(header)

        content = CardContent()
        content.layout.setContentsMargins(16, 8, 16, 16)
        content.layout.setSpacing(10)

        desc = QLabel(
            "Send application logs to the support team. This bundles recent "
            "log files (passwords, tokens, and secrets are automatically "
            "redacted) and uploads them for diagnosis. Use this when you "
            "encounter an error."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {tokens['muted-foreground']}; "
            f"font-size: {tokens['font.small']}px; background: transparent;"
        )
        content.layout.addWidget(desc)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.send_logs_btn = ShadcnButton(
            "Send Logs to Support", variant="default"
        )
        self.send_logs_btn.clicked.connect(self._on_send_logs)
        row.addWidget(self.send_logs_btn)

        self.open_logs_btn = ShadcnButton(
            "Open Logs Folder", variant="outline"
        )
        self.open_logs_btn.clicked.connect(self._on_open_logs)
        row.addWidget(self.open_logs_btn)

        row.addStretch()
        content.layout.addLayout(row)

        self.logs_status = QLabel("")
        self.logs_status.setStyleSheet(
            f"color: {tokens['muted-foreground']}; "
            f"font-size: {tokens['font.small']}px; background: transparent;"
        )
        self.logs_status.setWordWrap(True)
        content.layout.addWidget(self.logs_status)

        card.set_content(content)
        return card

    def _on_send_logs(self):
        from PySide6.QtWidgets import QApplication
        import threading

        tokens = self.theme_manager.get_tokens()
        self.send_logs_btn.setEnabled(False)
        self.logs_status.setText("Collecting and uploading logs…")
        self.logs_status.setStyleSheet(
            f"color: {tokens['info']}; "
            f"font-size: {tokens['font.small']}px; background: transparent;"
        )
        QApplication.processEvents()

        user_info = self.user_info

        def _worker():
            try:
                from core.log_uploader import LogUploader
                result = LogUploader().collect_and_upload(user_info=user_info)
            except Exception as e:
                result = {"ok": False, "error": str(e)}
            QTimer.singleShot(0, lambda: self._on_logs_done(result))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_logs_done(self, result: dict):
        tokens = self.theme_manager.get_tokens()
        self.send_logs_btn.setEnabled(True)

        if result.get("ok"):
            self.logs_status.setText(
                f"Logs sent. Reference: {result.get('reference', '—')}"
            )
            self.logs_status.setStyleSheet(
                f"color: {tokens['success']}; "
                f"font-size: {tokens['font.small']}px; background: transparent;"
            )
        else:
            self.logs_status.setText(
                f"Upload failed: {result.get('error', 'unknown error')}"
            )
            self.logs_status.setStyleSheet(
                f"color: {tokens['destructive']}; "
                f"font-size: {tokens['font.small']}px; background: transparent;"
            )

    def _on_open_logs(self):
        import os, subprocess, sys
        try:
            log_dir = None
            try:
                from core.log_uploader import _log_dirs
                for d in _log_dirs():
                    d = os.path.abspath(d)
                    if os.path.isdir(d):
                        log_dir = d
                        break
            except Exception:
                pass

            if log_dir is None:
                self.logs_status.setText("Logs folder not found.")
                return

            if sys.platform == "win32":
                os.startfile(log_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", log_dir])
            else:
                subprocess.Popen(["xdg-open", log_dir])
        except Exception as e:
            logger.error(f"Could not open logs folder: {e}")

    # ==================================================================
    # About section
    # ==================================================================

    def create_about_section(self):
        """
        About card.

        Displays the product name, version, and copyright in a
        human-readable layout. The version string is sanitised: if
        version.txt contains a Windows VERSIONINFO block (which some
        resource editors write when they cannot parse the existing
        file), the raw text is not shown. Only a clean
        ``MAJOR.MINOR.PATCH`` string or "unknown" reaches the label.
        """
        tokens = self.theme_manager.get_tokens()
        card = ShadcnCard()

        header = QLabel("About")
        header.setStyleSheet(
            f"font-weight: 600; font-size: {tokens['font.h4']}px; "
            "padding: 16px 16px 0 16px; background: transparent;"
        )
        card.set_header(header)

        content = CardContent()
        content.layout.setContentsMargins(16, 12, 16, 16)
        content.layout.setSpacing(10)

        version = _read_app_version()

        # --- Product name and version ---
        product_row = QHBoxLayout()
        product_row.setSpacing(8)

        product_icon = QLabel("")
        product_icon.setFixedWidth(28)
        product_icon.setAlignment(Qt.AlignCenter)
        product_icon.setStyleSheet(
            f"font-size: 22px; color: {tokens['primary']}; "
            "background: transparent;"
        )
        product_row.addWidget(product_icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        product_name = QLabel("Access Control System")
        product_name.setStyleSheet(
            f"font-size: {tokens['font.h4']}px; font-weight: 600; "
            f"color: {tokens['foreground']}; background: transparent;"
        )
        text_col.addWidget(product_name)

        version_label = QLabel(f"Version {version}")
        version_label.setStyleSheet(
            f"font-size: {tokens['font.small']}px; "
            f"color: {tokens['muted-foreground']}; background: transparent;"
        )
        text_col.addWidget(version_label)

        product_row.addLayout(text_col, 1)
        content.layout.addLayout(product_row)

        content.layout.addSpacing(6)

        # --- Separator ---
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(
            f"background-color: {tokens['border']}; max-height: 1px; "
            "border: none;"
        )
        content.layout.addWidget(sep)

        content.layout.addSpacing(6)

        # --- Description ---
        description = QLabel(
            "A desktop application for managing visitor access, employee "
            "records, and site entry/exit logs."
        )
        description.setWordWrap(True)
        description.setStyleSheet(
            f"color: {tokens['foreground-secondary']}; "
            f"font-size: {tokens['font.small']}px; line-height: 1.5; "
            "background: transparent;"
        )
        content.layout.addWidget(description)

        content.layout.addSpacing(6)

        # --- Copyright ---
        copyright_label = QLabel(
            "© 2026 Hillary Oduor. All rights reserved."
        )
        copyright_label.setStyleSheet(
            f"color: {tokens['muted-foreground']}; "
            f"font-size: {tokens['font.caption']}px; background: transparent;"
        )
        content.layout.addWidget(copyright_label)

        card.set_content(content)
        return card

    # ==================================================================
    # Environment handlers
    # ==================================================================

    def _update_env_label_style(self):
        tokens = self.theme_manager.get_tokens()
        env = self.env_manager.current_env
        if env == "local":
            color = tokens["success-foreground"]
            bg = tokens["success-subtle"]
        elif env == "deployed":
            color = tokens["info-foreground"]
            bg = tokens["info-subtle"]
        else:
            color = tokens["warning-foreground"]
            bg = tokens["warning-subtle"]

        self.current_env_label.setStyleSheet(f"""
            font-weight: 600;
            color: {color};
            background-color: {bg};
            padding: 2px 12px;
            border-radius: 10px;
        """)

    def _update_display(self):
        self.current_env_label.setText(self.env_manager.current_env.upper())
        self.current_url_label.setText(self.env_manager.get_base_url())
        self._update_env_label_style()
        self.env_combo.setCurrentText(self.env_manager.current_env)

        if self.env_manager.current_env == "custom":
            self.custom_url_widget.setVisible(True)
            self.save_custom_btn.setVisible(True)
            self.custom_url_input.setText(
                self.env_manager.settings.value("custom_api_url", "")
            )
        else:
            self.custom_url_widget.setVisible(False)
            self.save_custom_btn.setVisible(False)

        tokens = self.theme_manager.get_tokens()
        self.status_label.setText("")
        self.status_label.setStyleSheet(
            f"color: {tokens['muted-foreground']}; margin-top: 5px; "
            f"font-size: {tokens['font.small']}px; background: transparent;"
        )

    def _validate_url(self, url: str) -> bool:
        if not url or not url.startswith(("http://", "https://")):
            return False
        pattern = (
            r'^https?://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}'
            r'(:[0-9]+)?(/.*)?$'
        )
        return bool(re.match(pattern, url.strip()))

    def on_env_selected(self, env_name: str):
        if env_name == self.env_manager.current_env:
            return

        if env_name == "custom":
            self.custom_url_widget.setVisible(True)
            self.save_custom_btn.setVisible(True)
            self.custom_url_input.setFocus()
            tokens = self.theme_manager.get_tokens()
            self.status_label.setText(
                "Enter a custom URL and click Apply"
            )
            self.status_label.setStyleSheet(
                f"color: {tokens['info']}; margin-top: 5px; "
                f"font-size: {tokens['font.small']}px; "
                "background: transparent;"
            )
            return

        dialog = ShadcnAlertDialog(
            "Switch Environment",
            f"Switch the API environment to '{env_name}'? "
            f"This will change which backend the application talks to.",
            action_text="Switch",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.env_combo.blockSignals(True)
            self.env_combo.setCurrentText(self.env_manager.current_env)
            self.env_combo.blockSignals(False)
            return

        self.custom_url_widget.setVisible(False)
        self.save_custom_btn.setVisible(False)

        if self.env_manager.set_environment(env_name):
            self._update_display()
            self.environment_changed.emit(env_name)
            tokens = self.theme_manager.get_tokens()
            self.status_label.setText(
                f"Switched to {env_name} environment"
            )
            self.status_label.setStyleSheet(
                f"color: {tokens['success']}; margin-top: 5px; "
                f"font-size: {tokens['font.small']}px; "
                "background: transparent;"
            )
            QTimer.singleShot(3000, self._clear_env_status)

    def save_custom_url(self):
        url = self.custom_url_input.text().strip()

        tokens = self.theme_manager.get_tokens()

        if not url:
            self.status_label.setText("Please enter a URL")
            self.status_label.setStyleSheet(
                f"color: {tokens['destructive']}; margin-top: 5px; "
                f"font-size: {tokens['font.small']}px; "
                "background: transparent;"
            )
            return

        if not self._validate_url(url):
            self.status_label.setText(
                "Invalid URL format. Use http:// or https://"
            )
            self.status_label.setStyleSheet(
                f"color: {tokens['destructive']}; margin-top: 5px; "
                f"font-size: {tokens['font.small']}px; "
                "background: transparent;"
            )
            return

        if self.env_manager.set_environment("custom", url):
            self._update_display()
            self.environment_changed.emit("custom")
            self.status_label.setText(f"Switched to custom URL: {url}")
            self.status_label.setStyleSheet(
                f"color: {tokens['success']}; margin-top: 5px; "
                f"font-size: {tokens['font.small']}px; "
                "background: transparent;"
            )
            QTimer.singleShot(3000, self._clear_env_status)

    def test_connection(self):
        if self._is_testing or not self.api_client:
            return

        tokens = self.theme_manager.get_tokens()
        self._is_testing = True
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing...")
        self.status_label.setText("Testing connection...")
        self.status_label.setStyleSheet(
            f"color: {tokens['info']}; margin-top: 5px; "
            f"font-size: {tokens['font.small']}px; background: transparent;"
        )

        try:
            if self.api_client.is_online(force_check=True):
                self.status_label.setText("Connection successful!")
                self.status_label.setStyleSheet(
                    f"color: {tokens['success']}; margin-top: 5px; "
                    f"font-size: {tokens['font.small']}px; "
                    "background: transparent;"
                )
            else:
                self.status_label.setText(
                    "✗ Connection failed! Check your URL and network."
                )
                self.status_label.setStyleSheet(
                    f"color: {tokens['destructive']}; margin-top: 5px; "
                    f"font-size: {tokens['font.small']}px; "
                    "background: transparent;"
                )
        except Exception as e:
            logger.error(f"Connection test error: {e}")
            self.status_label.setText(f"✗ Error: {str(e)[:60]}...")
            self.status_label.setStyleSheet(
                f"color: {tokens['destructive']}; margin-top: 5px; "
                f"font-size: {tokens['font.small']}px; "
                "background: transparent;"
            )
        finally:
            self._is_testing = False
            self.test_btn.setEnabled(True)
            self.test_btn.setText("Test Connection")
            QTimer.singleShot(5000, self._clear_env_status)

    def _clear_env_status(self):
        if not self._is_testing:
            tokens = self.theme_manager.get_tokens()
            self.status_label.setText("")
            self.status_label.setStyleSheet(
                f"color: {tokens['muted-foreground']}; margin-top: 5px; "
                f"font-size: {tokens['font.small']}px; "
                "background: transparent;"
            )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_T and (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.test_connection()
            event.accept()
            return
        super().keyPressEvent(event)

    # ==================================================================
    # Cleanup
    # ==================================================================

    def cleanup(self):
        try:
            self.theme_manager.appearance_changed.disconnect(
                self._on_appearance_changed
            )
        except Exception:
            pass
        try:
            if self._appearance_spinner is not None:
                self._appearance_spinner.stop()
        except Exception:
            pass

