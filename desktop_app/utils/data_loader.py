import json
import os
from config import Config

class DataLoader:
    """Simple data loader"""
    
    def __init__(self):
        self.data = {}
        self.load_data()
    
    def load_data(self):
        try:
            if os.path.exists(Config.DATA_FILE):
                with open(Config.DATA_FILE, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            else:
                self.data = self.get_default_data()
        except Exception as e:
            print(f"Error loading data: {e}")
            self.data = self.get_default_data()
    
    def get_default_data(self):
        return {
            "app": {"name": "SchoolPro", "version": "1.0.0"},
            "sidebar": {
                "logo": "SchoolPro",
                "items": [
                    {"id": "dashboard", "text": "Dashboard", "icon": ""},
                    {"id": "students", "text": "Students", "icon": ""}
                ]
            },
            "dashboard": {
                "title": "Dashboard Overview",
                "cards": [
                    {"title": "Total Students", "value": "1,248", "color": "#3B82F6"},
                    {"title": "Total Teachers", "value": "85", "color": "#10B981"},
                    {"title": "Active Classes", "value": "42", "color": "#F59E0B"},
                    {"title": "Pending Fees", "value": "₹2,85,400", "color": "#EF4444"}
                ]
            }
        }
    
    def get(self, key, default=None):
        try:
            keys = key.split('.')
            data = self.data
            
            for k in keys:
                if isinstance(data, dict) and k in data:
                    data = data[k]
                else:
                    return default
            return data
        except:
            return default

# Global instance
app_data = DataLoader()