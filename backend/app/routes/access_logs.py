from fastapi import APIRouter, Depends, Query
from ..config import db
from .auth import get_current_user
from ..models.access_log import access_log_helper
from typing import Optional

router = APIRouter(prefix="/access-logs", tags=["Access Logs"])

@router.get("")
async def get_logs(
    person_type: Optional[str] = None,
    direction: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 500,
    current_user=Depends(get_current_user)
):
    tenant = current_user.get("tenant_id")
    query = {"tenant_id": tenant}
    if person_type:
        query["person_type"] = person_type
    if direction:
        query["direction"] = direction
    if from_date or to_date:
        timestamp_query = {}
        if from_date:
            timestamp_query["$gte"] = from_date
        if to_date:
            timestamp_query["$lte"] = to_date
        if timestamp_query:
            query["timestamp"] = timestamp_query
    
    cursor = db.access_logs.find(query).sort("timestamp", -1).limit(limit)
    logs = []
    async for log in cursor:
        logs.append(access_log_helper(log))
    return logs
    