from pydantic import BaseModel
from typing import List, Dict, Any, Optional   # <-- Optional is needed for client_id

class SyncOperation(BaseModel):
    op: str  # 'CREATE', 'UPDATE', 'DELETE'
    collection: str
    doc_id: str
    data: Dict[str, Any]

class SyncBatch(BaseModel):
    operations: List[SyncOperation]
    client_id: Optional[str] = None

class SyncResult(BaseModel):
    success: bool
    results: List[Dict[str, Any]]