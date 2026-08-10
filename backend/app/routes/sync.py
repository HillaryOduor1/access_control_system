from fastapi import APIRouter, Depends, HTTPException
from ..schemas.sync import SyncBatch, SyncResult
from ..config import db
from .auth import get_current_user
from bson import ObjectId

router = APIRouter(prefix="/sync", tags=["Sync"])

@router.post("", response_model=SyncResult)
async def sync_batch(batch: SyncBatch, current_user=Depends(get_current_user)):
    results = []
    for op in batch.operations:
        collection = db[op.collection]
        try:
            if op.op == "CREATE":
                # Insert without _id (let MongoDB generate)
                result = await collection.insert_one(op.data)
                results.append({"status": "ok", "id": str(result.inserted_id), "operation": op.op})
            elif op.op == "UPDATE":
                # Assume doc_id is the MongoDB _id string
                result = await collection.update_one({"_id": ObjectId(op.doc_id)}, {"$set": op.data})
                results.append({"status": "ok", "modified": result.modified_count, "operation": op.op})
            elif op.op == "DELETE":
                result = await collection.delete_one({"_id": ObjectId(op.doc_id)})
                results.append({"status": "ok", "deleted": result.deleted_count, "operation": op.op})
            else:
                results.append({"status": "error", "reason": "Unknown operation", "operation": op.op})
        except Exception as e:
            results.append({"status": "error", "reason": str(e), "operation": op.op})
    return SyncResult(success=True, results=results)

@router.get("/health")
async def health():
    return {"status": "ok"}