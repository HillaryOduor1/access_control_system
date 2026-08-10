from datetime import datetime
from ..config import db
from ..models.access_log import ACCESS_LOG_COLLECTION

async def log_access(
    person_type: str,
    person_id: str,
    direction: str,
    granted: bool = True,
    reason: str = "",
    verified_by: str = "system",
    tenant_id: str = "default" 
):
    log_entry = {
        "person_type": person_type,
        "person_id": person_id,
        "direction": direction,
        "timestamp": datetime.utcnow().isoformat(),
        "granted": granted,
        "reason": reason,
        "verified_by": verified_by,
        "tenant_id": tenant_id,  # add this
    }
    await db[ACCESS_LOG_COLLECTION].insert_one(log_entry)

