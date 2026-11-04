# widgets/splash_screen.py
"""
Enterprise splash screen with DPI scaling and font-aware typography.

Anti-flicker notes
------------------
The splash is the ONLY visible top-level window during startup. It does
not control the main window's visibility — that is the ApplicationLoader's
job.

`finish_with_animation()` deliberately does NOT animate windowOpacity.
Animating a top-level widget's windowOpacity on Windows forces the widget
to become a layered window (WS_EX_LAYERED). When a layered window is
destroyed, Windows DWM can cache its last composited frame for a short
period. If the main window is subsequently resized or repainted within
the cached region, DWM briefly re-composites the splash's ghost frame —
producing the flicker of a small gray window with a default caption bar.

To avoid this, the splash is hidden and destroyed in a single frame with
no intermediate layered state.

Font-awareness
--------------
The splash reads font_family, font_size and font_weight from the
ThemeManager appearance at construction time only. It does NOT subscribe
to appearance_changed. The splash is visible for a few seconds; it
should not react to theme updates during that window.

Font stability
--------------
Qt clears any explicit widget font when a stylesheet is applied to the
widget, unless the stylesheet itself declares a font. This is
documented Qt behaviour ("Setting a style sheet on a widget overrides
the widget's font") and it was the source of a visible mid-startup font
shrink: the labels had their fonts set via setFont(), then immediately
had a stylesheet applied which wiped those fonts, so the labels fell
back to the application font. When ThemeManager.set_user() later
changed the application font, the splash's labels visibly shrank.

The fix is to declare the font (family, size in *pixels*, weight)
inside each label's stylesheet, in addition to calling setFont() for
accessibility tools. Point sizes are deliberately avoided because
they are DPI-relative and would still track the application font
indirectly through the QApplication DPI settings.

Type scale
----------
Five text elements with a deliberate hierarchy:

    title    : base + 6pt bold      (app name)
    subtitle : base + 1pt demibold  ("Loading", primary color)
    message  : base pt regular      ("Initializing…")
    percent  : base - 1pt regular   ("5%")
    version  : base - 2pt regular   ("v2.0.0")

Sizes are floored at 9-12pt so the layout does not collapse under
smaller accessibility font settings, and the title is capped at 22pt
so it never dominates the 500x320 splash card.
"""
from PySide6.QtWidgets import (
    QSplashScreen, QProgressBar, QLabel, QVBoxLayout, QApplication, QWidget
)
from PySide6.QtCore import (
    Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve, QRect
)
from PySide6.QtGui import QPixmap, QFont, QPainter, QColor, QBrush, QPen

from core.theme_manager import ThemeManager
import os
from utils.path_utils import resource_path


class SplashScreen(QSplashScreen):
    def __init__(self, show_logo: bool = True, version: str = "2.0.0"):
        super().__init__()
        self.version = version
        self._is_finishing = False
        self._fade_anim = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAccessibleName("ICT Authority Access Control startup")

        screen = QApplication.primaryScreen()
        self.dpi_scale = (
            screen.logicalDotsPerInch() / 96.0 if screen else 1.0
        )

        base_width = 500
        base_height = 320
        self.setFixedSize(
            int(base_width * self.dpi_scale),
            int(base_height * self.dpi_scale)
        )

        self.theme_manager = ThemeManager()

        # Snapshot the appearance ONCE. The splash does not react to
        # later appearance changes.
        self._appearance_snapshot = self.theme_manager.get_appearance()
        self._theme_snapshot = self.theme_manager.get_current_theme()
        self._tokens_snapshot = dict(self.theme_manager.get_tokens())

        self._setup_ui(show_logo)
        self._apply_theme()

        self.center_on_screen()

    # ------------------------------------------------------------------
    # UI construction (positions only — no colors here)
    # ------------------------------------------------------------------

    def _setup_ui(self, show_logo: bool):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(int(8 * self.dpi_scale))
        layout.setContentsMargins(
            int(40 * self.dpi_scale),
            int(30 * self.dpi_scale),
            int(40 * self.dpi_scale),
            int(30 * self.dpi_scale)
        )

        self.title_label = QLabel("Access Control System")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setAccessibleName("Access Control System")
        layout.addWidget(
            self.title_label, alignment=Qt.AlignmentFlag.AlignCenter
        )

        self.subtitle_label = QLabel("Loading")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setAccessibleName("Loading")
        layout.addWidget(
            self.subtitle_label, alignment=Qt.AlignmentFlag.AlignCenter
        )

        layout.addSpacing(int(8 * self.dpi_scale))

        self.message_label = QLabel("Initializing...")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(
            self.message_label, alignment=Qt.AlignmentFlag.AlignCenter
        )

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(int(300 * self.dpi_scale))
        self.progress_bar.setFixedHeight(int(6 * self.dpi_scale))
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setAccessibleName("Startup progress")
        layout.addWidget(
            self.progress_bar, alignment=Qt.AlignmentFlag.AlignCenter
        )

        self.status_label = QLabel("0%")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(
            self.status_label, alignment=Qt.AlignmentFlag.AlignCenter
        )

        self.version_label = QLabel(f"v{self.version}")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(
            self.version_label, alignment=Qt.AlignmentFlag.AlignCenter
        )

    # ------------------------------------------------------------------
    # Theme + font application (uses the frozen snapshot)
    # ------------------------------------------------------------------

    def _resolve_fonts(self):
        """
        Return (title_px, subtitle_px, message_px, percent_px,
        version_px, family, weights) for the splash type scale.

        Sizes are in *pixels* so they are independent of the
        application font and DPI. Point sizes would still drift when
        ThemeManager.apply_application_font() runs during startup,
        because the QApplication font size affects the pixel
        resolution Qt uses for point-to-pixel conversion.
        """
        appearance = self._appearance_snapshot
        family = appearance.get("font_family", "Segoe UI")
        base_pt = int(appearance.get("font_size", 13))
        weight_key = appearance.get("font_weight", "normal")
        weight_map = {
            "normal":   QFont.Weight.Normal,
            "medium":   QFont.Weight.Medium,
            "semibold": QFont.Weight.DemiBold,
            "bold":     QFont.Weight.Bold,
        }
        base_weight = weight_map.get(weight_key, QFont.Weight.Normal)

        # Approximate pixel sizes from the base point size. Qt's own
        # point-to-pixel conversion uses 96 DPI as the reference, so
        # 1 pt ≈ 1.333 px. We multiply by dpi_scale so the splash
        # remains proportional on high-DPI displays.
        scale = self.dpi_scale
        px = lambda pt: max(1, int(round(pt * 1.333 * scale)))

        title_pt = min(base_pt + 6, 22)
        subtitle_pt = max(base_pt + 1, 12)
        message_pt = base_pt
        percent_pt = max(base_pt - 1, 10)
        version_pt = max(base_pt - 2, 9)

        return (
            px(title_pt), px(subtitle_pt), px(message_pt),
            px(percent_pt), px(version_pt),
            family, base_weight,
        )

    def _apply_theme(self, *_):
        """Apply snapshot tokens + frozen fonts to every element."""
        tokens = self._tokens_snapshot

        bg = tokens.get("background", "#0B1220")
        surface = tokens.get("surface", bg)
        fg = tokens.get("foreground", "#F8FAFC")
        secondary = tokens.get(
            "foreground-secondary",
            tokens.get("muted-foreground", "#475569"),
        )
        primary = tokens.get("primary", "#006B3F")
        border = tokens.get("border", "#CBD5E1")
        track = tokens.get("muted", "#E2E8F0")

        self.setStyleSheet(f"""
            QSplashScreen {{
                background-color: {surface};
                border: 2px solid {border};
                border-radius: 12px;
            }}
        """)

        (title_px, subtitle_px, message_px, percent_px, version_px,
         family, base_weight) = self._resolve_fonts()

        # Weight mapping for stylesheet use.
        weight_css_map = {
            QFont.Weight.Normal: 400,
            QFont.Weight.Medium: 500,
            QFont.Weight.DemiBold: 600,
            QFont.Weight.Bold: 700,
        }
        base_weight_css = weight_css_map.get(base_weight, 400)

        # Font family declared in the stylesheet must be quoted if it
        # contains spaces; wrap in single quotes here.
        family_css = f"'{family}'"

        # ----- title -----
        self.title_label.setStyleSheet(
            f"color: {fg}; "
            f"font-family: {family_css}; "
            f"font-size: {title_px}px; "
            f"font-weight: 700; "
            "background: transparent; border: none;"
        )

        # ----- subtitle -----
        self.subtitle_label.setStyleSheet(
            f"color: {primary}; "
            f"font-family: {family_css}; "
            f"font-size: {subtitle_px}px; "
            f"font-weight: 600; "
            "background: transparent; border: none;"
        )

        # ----- message -----
        self.message_label.setStyleSheet(
            f"color: {secondary}; "
            f"font-family: {family_css}; "
            f"font-size: {message_px}px; "
            f"font-weight: {base_weight_css}; "
            "background: transparent; border: none;"
        )

        # ----- progress bar -----
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: {track};
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {primary};
                border-radius: 3px;
            }}
        """)

        # ----- percent -----
        self.status_label.setStyleSheet(
            f"color: {secondary}; "
            f"font-family: {family_css}; "
            f"font-size: {percent_px}px; "
            f"font-weight: {base_weight_css}; "
            "background: transparent; border: none;"
        )

        # ----- version -----
        self.version_label.setStyleSheet(
            f"color: {secondary}; "
            f"font-family: {family_css}; "
            f"font-size: {version_px}px; "
            f"font-weight: {base_weight_css}; "
            "background: transparent; border: none;"
        )

        # Also call setFont() so accessibility tools and any future
        # widget that reads font() get the correct values. This is
        # purely informational; the stylesheet is the source of
        # truth for rendering.
        self.title_label.setFont(self._make_qfont(
            family, title_px, QFont.Weight.Bold
        ))
        self.subtitle_label.setFont(self._make_qfont(
            family, subtitle_px, QFont.Weight.DemiBold
        ))
        self.message_label.setFont(self._make_qfont(
            family, message_px, base_weight
        ))
        self.status_label.setFont(self._make_qfont(
            family, percent_px, base_weight
        ))
        self.version_label.setFont(self._make_qfont(
            family, version_px, base_weight
        ))

    @staticmethod
    def _make_qfont(family: str, pixel_size: int,
                    weight: QFont.Weight) -> QFont:
        """Build a QFont with an explicit pixel size (DPI-independent)."""
        font = QFont(family)
        font.setPixelSize(pixel_size)
        font.setWeight(weight)
        return font

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def center_on_screen(self):
        screen = self.screen()
        if screen:
            geometry = screen.availableGeometry()
            self.move(
                geometry.center().x() - self.width() // 2,
                geometry.center().y() - self.height() // 2
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_progress(self, value: int, message: str):
        if self._is_finishing:
            return

        value = max(0, min(100, value))

        self.progress_bar.setValue(value)
        self.progress_bar.setAccessibleName(
            f"Startup progress: {value} percent, {message}"
        )
        self.message_label.setText(message)
        self.status_label.setText(f"{value}%")

        QTimer.singleShot(0, self.repaint)

    def show_message(self, message: str):
        if self._is_finishing:
            return
        self.message_label.setText(message)
        QTimer.singleShot(0, self.repaint)

    def finish_with_animation(self, main_window=None, duration: int = 300):
        """Close the splash instantly. See module docstring."""
        if self._is_finishing:
            return
        self._is_finishing = True

        try:
            self.hide()
        except Exception:
            pass
        try:
            self.close()
        except Exception:
            pass
        try:
            self.deleteLater()
        except Exception:
            pass

    def finish(self, main_window=None):
        """Legacy finish method — does not show the main window."""
        try:
            self.hide()
        except Exception:
            pass
        try:
            self.close()
        except Exception:
            pass
        try:
            self.deleteLater()
        except Exception:
            pass

    def mousePressEvent(self, event):
        event.ignore()
