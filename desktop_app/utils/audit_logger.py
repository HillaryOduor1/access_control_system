from database.db_manager import DatabaseManager

class AuditLogger:
    def __init__(self):
        self.db = DatabaseManager()
    
    def log(self, user_id, action, entity_type, record_id, details=""):
        self.db.log_audit(user_id, action, entity_type, record_id, details)