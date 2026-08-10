import re
import json
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from config import Config

class AccessControlHelper:
    @staticmethod
    def encrypt_sensitive(value, field_name):
        if field_name in Config.SENSITIVE_FIELDS and value:
            cipher = Fernet(Config.ENCRYPTION_KEY.encode())
            return cipher.encrypt(value.encode()).decode()
        return value
    
    @staticmethod
    def decrypt_sensitive(value, field_name):
        if field_name in Config.SENSITIVE_FIELDS and value:
            try:
                cipher = Fernet(Config.ENCRYPTION_KEY.encode())
                return cipher.decrypt(value.encode()).decode()
            except:
                return value
        return value
    
    @staticmethod
    def validate_field(value, field_def):
        if field_def['required'] and not value:
            return False, f"{field_def['label']} is required"
        if value and field_def['validation_regex']:
            if not re.match(field_def['validation_regex'], str(value)):
                return False, f"{field_def['label']} format invalid"
        return True, ""
    
    @staticmethod
    def calculate_retention_date(check_in_time):
        dt = datetime.fromisoformat(check_in_time) if isinstance(check_in_time, str) else check_in_time
        return (dt + timedelta(days=Config.VISITOR_RETENTION_DAYS)).date()