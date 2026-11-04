# app/routes/logs.py
"""
Log collection endpoint.
Receives diagnostic zip bundles from desktop clients.
"""
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])

# Where uploaded bundles are stored. Create the folder and add a rotation
# job (cron, logrotate, or a nightly script) so it doesn't grow unbounded.
STORAGE_ROOT = (
    Path(__file__).resolve().parent.parent.parent / "collected_logs"
)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB hard cap


@router.post("/upload")
async def upload_logs(
    bundle: UploadFile = File(...),
    meta: str = Form("{}"),
):
    """
    Receive a log bundle from the desktop client.
    Returns a reference ID the user can quote to support.
    """
    try:
        STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        ref = uuid4().hex[:12]
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        dest = STORAGE_ROOT / f"{stamp}_{ref}.zip"

        content = await bundle.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Bundle too large")
        dest.write_bytes(content)
        dest.with_suffix(".meta.json").write_text(meta, encoding="utf-8")

        logger.info(
            f"Received log bundle {ref} "
            f"({len(content)} bytes) from {dest.name}"
        )
        return {"reference": ref}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to store log bundle")
        raise HTTPException(status_code=500, detail=str(e))