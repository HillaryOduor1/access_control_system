# app/routes/updates.py
"""
Version manifest endpoint.
Serves the current release manifest to desktop clients.
"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/updates", tags=["updates"])


# ---------------------------------------------------------------------------
# Where the manifest lives on disk.
# Create this file and edit it whenever you ship a release:
#   backend/static/version.json
# ---------------------------------------------------------------------------
MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent.parent / "static" / "version.json"
)


@router.get("/manifest")
async def get_manifest():
    """
    Return the current version manifest.
    Desktop clients poll this to detect available updates.
    """
    try:
        if not MANIFEST_PATH.exists():
            logger.warning(f"Version manifest missing: {MANIFEST_PATH}")
            raise HTTPException(
                status_code=404,
                detail="Version manifest not configured",
            )
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to read version manifest")
        raise HTTPException(status_code=500, detail=str(e))