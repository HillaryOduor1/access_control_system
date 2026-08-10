import qtawesome as qta
from config import Config

class IconLoader:
    """Load icons from QtAwesome library"""
    
    # Icon mapping - map our icon names to QtAwesome icons
    ICON_MAP = {
        # FontAwesome 6 icons
        "fa6.dashboard": ("fa6solid.dashboard", {}),
        "fa6.users": ("fa6solid.users", {}),
        "fa6.user": ("fa6solid.user", {}),
        "fa6.chalkboard-teacher": ("fa6solid.chalkboard-teacher", {}),
        "fa6.book": ("fa6solid.book", {}),
        "fa6.money-bill-wave": ("fa6solid.money-bill-wave", {}),
        "fa6.chart-bar": ("fa6solid.chart-bar", {}),
        "fa6.cog": ("fa6solid.cog", {}),
        "fa6.search": ("fa6solid.search", {}),
        "fa6.bell": ("fa6solid.bell", {}),
        "fa6.help": ("fa6solid.circle-question", {}),
        "fa6.moon": ("fa6solid.moon", {}),
        "fa6.sun": ("fa6solid.sun", {}),
        "fa6.menu": ("fa6solid.bars", {}),
        "fa6.home": ("fa6solid.house", {}),
        "fa6.add": ("fa6solid.plus", {}),
        "fa6.edit": ("fa6solid.pen-to-square", {}),
        "fa6.delete": ("fa6solid.trash", {}),
        "fa6.save": ("fa6solid.floppy-disk", {}),
        "fa6.download": ("fa6solid.download", {}),
        "fa6.upload": ("fa6solid.upload", {}),
        "fa6.print": ("fa6solid.print", {}),
        
        # Material Design icons (alternative)
        "md.dashboard": ("msc.dashboard", {}),
        "md.people": ("msc.people", {}),
        "md.school": ("msc.school", {}),
        "md.book": ("msc.book", {}),
        "md.money": ("msc.attach_money", {}),
        "md.settings": ("msc.settings", {}),
    }
    
    @staticmethod
    def get_icon(icon_name, color=None, size=None):
        """Get icon from QtAwesome"""
        if icon_name in IconLoader.ICON_MAP:
            icon_data = IconLoader.ICON_MAP[icon_name]
            options = icon_data[1].copy()
            
            if color:
                options['color'] = color
            if size:
                options['scale_factor'] = size / 16  # Assuming 16px base
            
            return qta.icon(icon_data[0], **options)
        
        # Return empty icon if not found
        return qta.icon()
    
    @staticmethod
    def get_char_icon(icon_name):
        """Get icon as text character (for places where QIcon not supported)"""
        char_map = {
            "dashboard": "📊",
            "users": "👥",
            "user": "👤",
            "teacher": "👨‍🏫",
            "book": "📚",
            "money": "💰",
            "chart": "📈",
            "settings": "⚙️",
            "help": "🆘",
            "moon": "🌙",
            "sun": "☀️",
            "menu": "☰",
            "home": "🏠",
        }
        
        return char_map.get(icon_name, "❓")