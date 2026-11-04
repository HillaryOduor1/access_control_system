# core/update_checker.py
"""
Automatic update checker.

Reads a remote JSON manifest and compares it against the locally
installed version (version.txt bundled with the app).

Manifest format

{
  "version": "1.2.6",
  "min_supported": "1.0.0",
  "url": "https://example.com/Access_Control_System_1.2.6_Payload.exe",
  "sha256": "<hex>",
  "notes": "Release notes shown in the dialog.",
  "mandatory": false
}
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Optional

from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)


# CONFIGURE THIS — the public URL of your version manifest.Point it at the FastAPI backend route we add later:GET /updates/manifest

UPDATE_MANIFEST_URL = (
    "https://REPLACE-WITH-YOUR-HOST/updates/manifest"
)

LOCAL_VERSION_FILE = "version.txt"

# Don't hit the server more than once every 6 hours on auto-check.
AUTO_CHECK_INTERVAL_SECONDS = 6 * 3600


# Local version lookup

def _read_local_version() -> Optional[str]:
    """Return the version string from version.txt or None if missing."""
    candidates = []
    # Frozen onedir: version.txt sits next to the exe.
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable),
                                       LOCAL_VERSION_FILE))
    # Frozen onefile: unpacked _MEIPASS folder.
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, LOCAL_VERSION_FILE))
    # Development: version.txt sits next to main.py.
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", LOCAL_VERSION_FILE))
    candidates.append(LOCAL_VERSION_FILE)

    for p in candidates:
        try:
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    v = f.read().strip()
                if v:
                    return v
        except Exception:
            continue
    return None


def _parse_version(v: str) -> tuple:
    parts = []
    for token in str(v).split("."):
        try:
            parts.append(int(token))
        except Exception:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


# UpdateChecker

class UpdateChecker:
    def __init__(self):
        self._settings = QSettings("ICTAuthority", "AccessControl")

    # Preferences
    
    def is_auto_check_enabled(self) -> bool:
        return self._settings.value("auto_check_updates", True, type=bool)

    def set_auto_check_enabled(self, enabled: bool):
        self._settings.setValue("auto_check_updates", bool(enabled))

    def last_check_timestamp(self) -> int:
        return self._settings.value("last_update_check", 0, type=int)

    def _record_check_now(self):
        self._settings.setValue("last_update_check", int(time.time()))

    def should_auto_check_now(self) -> bool:
        if not self.is_auto_check_enabled():
            return False
        return (time.time() - self.last_check_timestamp()) > AUTO_CHECK_INTERVAL_SECONDS

    
    # Lookup
    
    def fetch_manifest(self) -> Optional[dict]:
        try:
            import httpx
        except Exception:
            logger.error("httpx not installed — cannot check for updates")
            return None
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as c:
                r = c.get(UPDATE_MANIFEST_URL)
            if r.status_code != 200:
                logger.info(f"Update manifest HTTP {r.status_code}")
                return None
            return json.loads(r.text)
        except Exception as e:
            logger.info(f"Update check skipped: {e}")
            return None

    def check_now(self) -> Optional[dict]:
        """
        Return a manifest dict if a newer version is available, else None.
        Never raises.
        """
        local = _read_local_version()
        if not local:
            logger.info("No local version.txt — skipping update check")
            return None

        manifest = self.fetch_manifest()
        self._record_check_now()
        if not manifest:
            return None

        remote = str(manifest.get("version", "0.0.0"))
        if _parse_version(remote) > _parse_version(local):
            manifest["_local_version"] = local
            logger.info(f"Update available: {local} -> {remote}")
            return manifest

        logger.info(f"Already up to date ({local})")
        return None