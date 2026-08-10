from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtSvg import QSvgRenderer
import resources.icons as icons

class IconManager:
    """Provides QIcons from a single file (icons.py)."""
    _cache = {}

    @classmethod
    def get_icon(cls, name: str, color: str = None, size: int = 24) -> QIcon:
        """
        Returns a QIcon for the given icon name.If color is provided, the icon is recolored.Icons are cached for performance.
        """
        cache_key = f"{name}_{color}_{size}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        svg_data = getattr(icons, "ICONS", {}).get(name)
        if not svg_data:
            # Fallback: create a blank icon
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            return QIcon(pixmap)

        # If recoloring needed, modify SVG content
        if color:
            # Replace fill="currentColor" or similar – we'll set fill to given color
            svg_data = svg_data.replace('fill="currentColor"', f'fill="{color}"')
            svg_data = svg_data.replace('fill="currentcolor"', f'fill="{color}"')
            # If no fill attribute, add it to root <svg>
            if 'fill="' not in svg_data:
                svg_data = svg_data.replace('<svg ', '<svg fill="{}" '.format(color))

        # Render SVG to QPixmap for consistent sizing
        renderer = QSvgRenderer(QByteArray(svg_data.encode()))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        icon = QIcon(pixmap)
        cls._cache[cache_key] = icon
        return icon

    @classmethod
    def get_icon_as_pixmap(cls, name: str, color: str = None, size: int = 24) -> QPixmap:
        """Return QPixmap for use in QLabel."""
        return cls.get_icon(name, color, size).pixmap(size, size)