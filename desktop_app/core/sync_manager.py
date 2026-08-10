from PySide6.QtCore import QThread, Signal
import time

class SyncManager(QThread):
    sync_completed = Signal(bool, int)  # success, number_of_ops
    
    def __init__(self, api_client, db_manager, interval_sec=60):
        super().__init__()
        self.api = api_client
        self.db = db_manager
        self.interval = interval_sec
        self.running = True
        
    def run(self):
        while self.running:
            if self.api.is_online():
                pending = self.db.get_pending_operations()
                if pending:
                    try:
                        # Send batch to backend
                        payload = {"operations": [{
                            "op": op["operation"],
                            "collection": op["collection"],
                            "doc_id": op["doc_id"],
                            "data": op["data"]
                        } for op in pending]}
                        result = self.api.request("POST", "/sync", json=payload)
                        if result.get("success"):
                            self.db.mark_synced([op["id"] for op in pending])
                            self.sync_completed.emit(True, len(pending))
                    except Exception as e:
                        self.sync_completed.emit(False, 0)
            time.sleep(self.interval)
            
    def stop(self):
        self.running = False
        self.wait()