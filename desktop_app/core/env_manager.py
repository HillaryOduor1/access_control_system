# core/env_manager.py
from PySide6.QtCore import QObject, Signal, QSettings
import json

class EnvironmentManager(QObject):
    env_changed = Signal(str)
    
    ENVIRONMENTS = {
        "local": "http://localhost:8000",
        "deployed": "https://icta-access-control-system.onrender.com",
        "custom": None  # Will be set by user
    }
    
    def __init__(self):
        super().__init__()
        self.settings = QSettings("ICTA", "AccessControlApp")
        self.current_env = self._load_current_env()
        
    def _load_current_env(self):
        env = self.settings.value("api_environment", "local")
        if env not in self.ENVIRONMENTS:
            env = "local"
        return env
    
    def get_base_url(self):
        if self.current_env == "custom":
            custom_url = self.settings.value("custom_api_url")
            if custom_url:
                return custom_url
        return self.ENVIRONMENTS.get(self.current_env, "http://localhost:8000")
    
    def set_environment(self, env_name, custom_url=None):
        if env_name == "custom" and custom_url:
            self.settings.setValue("custom_api_url", custom_url)
        self.current_env = env_name
        self.settings.setValue("api_environment", env_name)
        self.env_changed.emit(self.get_base_url())
        
    def get_available_environments(self):
        return list(self.ENVIRONMENTS.keys())