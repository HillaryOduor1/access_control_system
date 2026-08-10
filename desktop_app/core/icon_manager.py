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

# Internal resource helper – works both in dev and when frozen

def _resource_path(relative_path):
    """Get absolute path to a resource, works for dev and PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class IconManager:
    _instance = None
    _cache = {}

    # Google Material Icons CDN
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
        # add any other mappings you need
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        # User-writable cache directory (for icons downloaded at runtime)
        self.user_cache_dir = os.path.join(os.path.expanduser("~"), ".ictaccess", "icons")
        os.makedirs(self.user_cache_dir, exist_ok=True)

        # Also keep the old icons_dir from Config for compatibility,
        # but we'll use it only as a fallback (it may point to the bundle).
        self.icons_dir = Config.ICONS_DIR

        self.theme_manager = ThemeManager()
        self.theme_manager.theme_changed.connect(self._clear_cache)

    def _clear_cache(self):
        self._cache.clear()

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
        tokens = self.theme_manager.get_tokens()
        return {
            "base": self._to_color(tokens.get("foreground", "#0F172A")),
            "accent": self._to_color(tokens.get("primary", "#16A34A")),
            "muted": self._to_color(tokens.get("foreground", "#0F172A")),
        }

    def _download_icon(self, name: str) -> bool:
        """Download a Material icon SVG and save it to the user cache."""
        material_name = self.MATERIAL_NAME_MAP.get(name, name)
        url = f"{self.MATERIAL_CDN_BASE}/{material_name}/{self.MATERIAL_VERSION}/24px.svg"
        local_path = os.path.join(self.user_cache_dir, f"{name}.svg")

        try:
            with urllib.request.urlopen(url) as response:
                svg_content = response.read().decode('utf-8')
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(svg_content)
            return True
        except Exception as e:
            print(f"[IconManager] Failed to download '{name}': {e}")
            return False

    def _create_fallback_svg(self, name: str) -> str:
        """Minimal fallback SVG (a circle with an initial)."""
        return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <text x="12" y="16" text-anchor="middle" font-size="10" fill="currentColor">{name[0].upper()}</text>
        </svg>'''

    def _ensure_icon_file(self, name: str) -> str:
        """
        Return the path to an icon file, trying:
          1. Bundled assets/icons/ (in the frozen app)
          2. User cache (~/.ictaccess/icons/)
          3. Download to user cache if missing
          4. Fallback placeholder (saved in user cache)
        """
        # 1. Check bundled location
        bundled_path = _resource_path(os.path.join("assets", "icons", f"{name}.svg"))
        if os.path.exists(bundled_path):
            return bundled_path

        # 2. Check user cache
        cache_path = os.path.join(self.user_cache_dir, f"{name}.svg")
        if os.path.exists(cache_path):
            return cache_path

        # 3. Try to download
        if self._download_icon(name):
            return cache_path

        # 4. Fallback: write a placeholder to cache and return its path
        fallback_svg = self._create_fallback_svg(name)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(fallback_svg)
        return cache_path

    def get_icon(self, name: str, size: QSize = QSize(24, 24),
                 state: str = "default", variant: str = "mono") -> QIcon:
        size = self._scale_for_dpi(size)
        colors = self._colors()
        theme = self.theme_manager.get_current_theme()
        cache_key = f"{theme}_{name}_{size.width()}x{size.height()}_{state}_{variant}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        svg_path = self._ensure_icon_file(name)

        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)

        renderer = QSvgRenderer(svg_path)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)

        # Colorize
        base = colors["muted"] if state == "default" else colors["accent"]
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), base)
        painter.end()

        icon = QIcon(pixmap)
        self._cache[cache_key] = icon
        return icon

    # Pre‑loading for bundling
    def preload_icons(self, icon_names: list[str] = None):
        """
        Download all icons to the user cache, or to a specified list.
        Call this during development, then copy the downloaded files
        from ~/.ictaccess/icons/ to assets/icons/ so they get bundled.
        """
        if icon_names is None:
            icon_names = list(self.MATERIAL_NAME_MAP.keys())
        for name in icon_names:
            self._ensure_icon_file(name)   # downloads only if missing

    def preload_all_to_bundle(self):
        """
        Download all icons to the project's assets/icons/ folder directly.
        This is meant to be run during development to populate the bundle.
        After running, you should have all SVGs in assets/icons/.
        """
        # Ensure the bundled directory exists in the project
        bundle_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons")
        os.makedirs(bundle_dir, exist_ok=True)

        for name in self.MATERIAL_NAME_MAP.keys():
            material_name = self.MATERIAL_NAME_MAP[name]
            url = f"{self.MATERIAL_CDN_BASE}/{material_name}/{self.MATERIAL_VERSION}/24px.svg"
            local_path = os.path.join(bundle_dir, f"{name}.svg")
            if os.path.exists(local_path):
                continue
            try:
                with urllib.request.urlopen(url) as response:
                    svg_content = response.read().decode('utf-8')
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(svg_content)
                print(f"Downloaded {name}.svg")
            except Exception as e:
                print(f"Failed to download {name}: {e}")
