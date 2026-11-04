# utils/path_utils.py
"""
Utility functions for resource path resolution.
Supports both development and frozen (PyInstaller) environments.
"""
import sys
import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def resource_path(relative_path: str) -> str:
    """
    Get absolute path to a resource, works for dev and PyInstaller.
    
    Args:
        relative_path: Relative path to the resource
        
    Returns:
        Absolute path to the resource
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        logger.debug(f"Resource path (frozen): {base_path}")
    except AttributeError:
        # Running from source
        base_path = os.path.abspath(".")
        logger.debug(f"Resource path (development): {base_path}")
    
    full_path = os.path.join(base_path, relative_path)
    logger.debug(f"Resolved resource: {full_path}")
    return full_path


def get_app_data_dir() -> Path:
    """
    Get the application data directory (platform-specific).
    
    Returns:
        Path to application data directory
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", os.path.expanduser("~")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    
    return base / "ICTAuthority" / "AccessControl"


def get_app_config_dir() -> Path:
    """
    Get the application config directory (platform-specific).
    
    Returns:
        Path to application config directory
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", os.path.expanduser("~")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Preferences"
    else:
        base = Path.home() / ".config"
    
    return base / "ICTAuthority" / "AccessControl"


def get_app_cache_dir() -> Path:
    """
    Get the application cache directory (platform-specific).
    
    Returns:
        Path to application cache directory
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path.home() / ".cache"
    
    return base / "ICTAuthority" / "AccessControl"


def get_app_log_dir() -> Path:
    """
    Get the application log directory.
    
    Returns:
        Path to application log directory
    """
    if getattr(sys, 'frozen', False):
        return get_app_data_dir() / "logs"
    else:
        return Path(os.path.abspath(".")) / "logs"


def ensure_directories() -> bool:
    """
    Ensure all required directories exist.
    
    Returns:
        True if all directories were created successfully
    """
    try:
        for d in [
            get_app_data_dir(),
            get_app_config_dir(),
            get_app_cache_dir(),
            get_app_log_dir(),
        ]:
            d.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory: {d}")
        return True
    except Exception as e:
        logger.error(f"Failed to create directories: {e}")
        return False


def is_frozen() -> bool:
    """
    Check if the application is running as a frozen executable.
    
    Returns:
        True if running as frozen executable
    """
    return getattr(sys, 'frozen', False)


def is_development() -> bool:
    """
    Check if the application is running in development mode.
    
    Returns:
        True if running from source
    """
    return not is_frozen()


# Ensure directories on import if running as app
if __name__ != "__main__":
    ensure_directories()
'''import sys
import os

def resource_path(relative_path):
    """Get absolute path to a resource, works for dev and PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)'''