# core/icon_manager.py
"""
Enterprise icon manager with theme-aware caching and fallback.

Cache invalidation
------------------
The icon cache is cleared whenever the theme OR the appearance changes.
Appearance changes (high contrast, font, density) can alter the colors
that mono icons are tinted with, so the cache must be dropped.
"""
import os
import re
import sys
import urllib.request
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QCoreApplication
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QGuiApplication
from PySide6.QtSvg import QSvgRenderer

from config import Config
from core.theme_manager import ThemeManager
import logging

logger = logging.getLogger(__name__)


def _resource_path(relative_path):
    """Get absolute path to a resource, works for dev and PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class IconManager:
    """Singleton icon manager with theme-aware caching."""

    _instance = None
    _cache = {}

    MATERIAL_CDN_BASE = "https://fonts.gstatic.com/s/i/materialicons"
    MATERIAL_VERSION = "v7"

    MATERIAL_NAME_MAP = {
        "user": "person",
        "lock": "lock",
        "email": "email",
        "eye": "visibility",
        "eye_off": "visibility_off",
        "loading": "sync",
        "search": "search",
        "settings": "settings",
        "home": "home",
        "menu": "menu",
        "close": "close",
        "arrow_back": "arrow_back",
        "arrow_forward": "arrow_forward",
        "add": "add",
        "remove": "remove",
        "delete": "delete",
        "edit": "edit",
        "save": "save",
        "cancel": "cancel",
        "check": "check",
        "warning": "warning",
        "info": "info",
        "help": "help",
        "logout": "logout",
        "login": "login",
        "profile": "account_circle",
        "dashboard": "dashboard",
        "visitors": "people",
        "employees": "badge",
        "access_logs": "history",
        "field_config": "settings_applications",
        "report": "assessment",
        "notifications": "notifications",
        "theme_light": "light_mode",
        "theme_dark": "dark_mode",
        "theme": "palette",
        "badge": "badge",
        "building": "business",
        "check_in": "login",
        "check_out": "logout",
        "export": "download",
        "id": "badge",
        "phone": "phone",
        "refresh": "refresh",
        "expand_more": "expand_more",
        "expand_less": "expand_less",
        "arrow_drop_down": "arrow_drop_down",


    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.user_cache_dir = os.path.join(os.path.expanduser("~"), ".ictaccess", "icons")
        os.makedirs(self.user_cache_dir, exist_ok=True)

        self.icons_dir = Config.get_icons_dir() if hasattr(Config, 'get_icons_dir') else Config.ICONS_DIR
        self.theme_manager = ThemeManager()

        # Invalidate on ANY appearance change, not just theme changes,
        # because token colors can change without the theme name changing.
        self.theme_manager.theme_changed.connect(self._clear_cache)
        self.theme_manager.appearance_changed.connect(self._clear_cache)

        self._cached_colors = None
        self._cached_theme = None
        self._cached_appearance_sig = None

        self._initialized = True
        logger.debug("IconManager initialized")

    def _appearance_signature(self):
        """Signature capturing everything that affects icon color."""
        try:
            a = self.theme_manager.get_appearance()
        except Exception:
            return None
        return (
            a.get("theme"),
            a.get("high_contrast"),
            a.get("font_size"),
            a.get("density"),
            a.get("radius"),
        )

    def _clear_cache(self, *_):
        """Clear the icon cache on theme or appearance change."""
        self._cache.clear()
        self._cached_colors = None
        self._cached_theme = None
        self._cached_appearance_sig = None
        logger.debug("Icon cache cleared")

    def _scale_for_dpi(self, size: QSize) -> QSize:
        try:
            app = QCoreApplication.instance()
            if not app:
                return size
            screen = QGuiApplication.primaryScreen()
            if not screen:
                return size
            dpi = screen.logicalDotsPerInch()
            scale = dpi / 96.0
            return QSize(
                max(1, int(size.width() * scale)),
                max(1, int(size.height() * scale))
            )
        except Exception:
            return size

    def _to_color(self, color_str: str) -> QColor:
        hsl_match = re.match(r"hsl\(\s*(\d+)\s*,\s*(\d+)%\s*,\s*(\d+)%\s*\)", color_str.strip())
        if hsl_match:
            h = int(hsl_match.group(1))
            s = int(hsl_match.group(2)) / 100.0
            l = int(hsl_match.group(3)) / 100.0
            return QColor.fromHslF(h / 360.0, s, l)
        return QColor(color_str)

    def _colors(self):
        current_theme = self.theme_manager.get_current_theme()
        sig = self._appearance_signature()

        if (self._cached_colors is not None
                and self._cached_theme == current_theme
                and self._cached_appearance_sig == sig):
            return self._cached_colors

        tokens = self.theme_manager.get_tokens()

        colors = {
            "default": self._to_color(tokens.get("foreground", "#0F172A")),
            "active": self._to_color(tokens.get("primary", "#006B3F")),
            "muted": self._to_color(tokens.get("muted-foreground", "#94A3B8")),
        }

        self._cached_colors = colors
        self._cached_theme = current_theme
        self._cached_appearance_sig = sig

        return colors

    def _download_icon(self, name: str) -> bool:
        material_name = self.MATERIAL_NAME_MAP.get(name, name)
        url = f"{self.MATERIAL_CDN_BASE}/{material_name}/{self.MATERIAL_VERSION}/24px.svg"
        local_path = os.path.join(self.user_cache_dir, f"{name}.svg")

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                svg_content = response.read().decode('utf-8')
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(svg_content)
            return True
        except Exception as e:
            logger.warning(f"Failed to download icon '{name}': {e}")
            return False

    def _create_fallback_svg(self, name: str) -> str:
        initial = name[0].upper() if name else "?"
        return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5" fill="none"/>
            <text x="12" y="16" text-anchor="middle" font-size="10" fill="currentColor" font-family="Arial, sans-serif">{initial}</text>
        </svg>'''

    def _ensure_icon_file(self, name: str) -> str:
        bundled_path = _resource_path(os.path.join("assets", "icons", f"{name}.svg"))
        if os.path.exists(bundled_path):
            return bundled_path

        cache_path = os.path.join(self.user_cache_dir, f"{name}.svg")
        if os.path.exists(cache_path):
            return cache_path

        if self._download_icon(name):
            return cache_path

        fallback_svg = self._create_fallback_svg(name)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(fallback_svg)
            logger.debug(f"Created fallback icon: {name}")
        except Exception as e:
            logger.error(f"Failed to create fallback icon: {e}")
        return cache_path

    def get_icon(self, name: str, size: QSize = QSize(24, 24),
                 state: str = "default", variant: str = "mono") -> QIcon:
        size = self._scale_for_dpi(size)
        colors = self._colors()
        theme = self.theme_manager.get_current_theme()
        sig = self._appearance_signature()
        cache_key = f"{theme}|{sig}|{name}_{size.width()}x{size.height()}_{state}_{variant}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        svg_path = self._ensure_icon_file(name)

        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)

        try:
            renderer = QSvgRenderer(svg_path)
            if not renderer.isValid():
                raise Exception("Invalid SVG")

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(painter)

            if variant == "mono":
                color = colors["default"] if state == "default" else colors["active"]
                painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
                painter.fillRect(pixmap.rect(), color)

            painter.end()

        except Exception as e:
            logger.warning(f"SVG rendering failed for '{name}': {e}")
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = colors["default"] if state == "default" else colors["active"]
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(2, 2, size.width() - 4, size.height() - 4)
            painter.end()

        icon = QIcon(pixmap)
        self._cache[cache_key] = icon
        return icon

    def get_icon_color(self) -> str:
        colors = self._colors()
        return colors["default"].name()

    def preload_icons(self, icon_names: list[str] = None):
        if icon_names is None:
            icon_names = list(self.MATERIAL_NAME_MAP.keys())
        for name in icon_names:
            self._ensure_icon_file(name)
        logger.info(f"Preloaded {len(icon_names)} icons")

    def preload_all_to_bundle(self):
        bundle_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons")
        os.makedirs(bundle_dir, exist_ok=True)

        downloaded = 0
        for name in self.MATERIAL_NAME_MAP.keys():
            material_name = self.MATERIAL_NAME_MAP[name]
            url = f"{self.MATERIAL_CDN_BASE}/{material_name}/{self.MATERIAL_VERSION}/24px.svg"
            local_path = os.path.join(bundle_dir, f"{name}.svg")
            if os.path.exists(local_path):
                continue
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    svg_content = response.read().decode('utf-8')
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(svg_content)
                downloaded += 1
                print(f"Downloaded {name}.svg")
            except Exception as e:
                print(f"Failed to download {name}: {e}")

        logger.info(f"Downloaded {downloaded} icons to bundle")

