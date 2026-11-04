# core/log_uploader.py
"""
Collect recent log files, redact obvious secrets, bundle them into a zip, and upload to the backend support endpoint.
"""
from __future__ import annotations

import io
import json
import logging
import os
import platform
import sys
import time
import uuid
import zipfile
from typing import Optional

from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)


# CONFIGURE THIS — the public URL of your log collection endpoint.
# Point it at the FastAPI backend route we add later:
#   POST /logs/upload

LOG_UPLOAD_URL = (
    "https://REPLACE-WITH-YOUR-HOST/logs/upload"
)

MAX_LOG_FILES = 15
MAX_PER_FILE_BYTES = 1_000_000  # 1 MB cap per file
MAX_BUNDLE_BYTES = 5_000_000    # 5 MB cap for the whole zip


# Redaction

_REDACT_NEEDLES = ("token=", "password=", "api_key=", "secret=", "Bearer ")


def _redact(text: str) -> str:
    for needle in _REDACT_NEEDLES:
        if needle not in text:
            continue
        lines = []
        for line in text.splitlines():
            idx = line.find(needle)
            if idx == -1:
                lines.append(line)
                continue
            end = idx + len(needle)
            j = end
            while j < len(line) and line[j] not in " \t\r\n\"',;":
                j += 1
            lines.append(line[:end] + "***" + line[j:])
        text = "\n".join(lines)
    return text


# Log discovery — must match LoggingConfig.get_log_dir() in main.py

def _log_dirs():
    # Frozen: %APPDATA%\ICTAuthority\AccessControl\logs
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            base = os.environ.get("APPDATA", "")
            if base:
                yield os.path.join(base, "ICTAuthority", "AccessControl", "logs")
        elif sys.platform == "darwin":
            yield os.path.join(
                os.path.expanduser("~"),
                "Library", "Application Support",
                "ICTAuthority", "AccessControl", "logs",
            )
        else:
            yield os.path.join(
                os.path.expanduser("~"),
                ".local", "share",
                "ICTAuthority", "AccessControl", "logs",
            )
    # Development: ./logs relative to the app
    here = os.path.dirname(os.path.abspath(__file__))
    yield os.path.join(here, "..", "logs")
    yield os.path.join(os.getcwd(), "logs")


def _find_log_files():
    seen = set()
    found = []
    for d in _log_dirs():
        d = os.path.abspath(d)
        if not os.path.isdir(d):
            continue
        try:
            names = sorted(os.listdir(d), reverse=True)
        except Exception:
            continue
        for name in names:
            p = os.path.join(d, name)
            if not os.path.isfile(p):
                continue
            if not (name.endswith(".log") or name.endswith(".txt")):
                continue
            if p in seen:
                continue
            seen.add(p)
            found.append(p)
    found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return found[:MAX_LOG_FILES]


def _read_version() -> str:
    for p in (
        os.path.join(os.path.dirname(sys.executable), "version.txt"),
        os.path.join(os.path.dirname(__file__), "..", "version.txt"),
        "version.txt",
    ):
        try:
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    v = f.read().strip()
                if v:
                    return v
        except Exception:
            pass
    return "unknown"


def _installation_id() -> str:
    s = QSettings("ICTAuthority", "AccessControl")
    iid = s.value("installation_id", "")
    if not iid:
        iid = uuid.uuid4().hex
        s.setValue("installation_id", iid)
    return iid


def _build_bundle(user_info: Optional[dict]) -> bytes:
    files = _find_log_files()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "app_version": _read_version(),
            "user": (user_info or {}).get("username", "unknown"),
            "full_name": (user_info or {}).get("full_name", ""),
            "os": platform.platform(),
            "python": sys.version,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "log_count": len(files),
            "installation_id": _installation_id(),
        }
        zf.writestr("meta.json", json.dumps(meta, indent=2))
        for p in files:
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(MAX_PER_FILE_BYTES)
                zf.writestr(f"logs/{os.path.basename(p)}", _redact(content))
            except Exception as e:
                zf.writestr(f"logs/{os.path.basename(p)}.error",
                            f"Could not read: {e}")

    data = buf.getvalue()
    if len(data) > MAX_BUNDLE_BYTES and len(files) > 1:
        # Retry with fewer files (newest only).
        trimmed = files[: max(1, len(files) // 2)]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in trimmed:
                try:
                    with open(p, "r", encoding="utf-8",
                              errors="replace") as f:
                        zf.writestr(
                            f"logs/{os.path.basename(p)}",
                            _redact(f.read(MAX_PER_FILE_BYTES)),
                        )
                except Exception:
                    pass
        data = buf.getvalue()
    return data


# Public API

class LogUploader:
    def collect_and_upload(self, user_info: Optional[dict] = None) -> dict:
        try:
            bundle = _build_bundle(user_info)
        except Exception as e:
            logger.exception("Failed to build log bundle")
            return {"ok": False, "error": f"could not build bundle: {e}"}

        if not bundle:
            return {"ok": False, "error": "no logs found"}

        try:
            import httpx
            files = {
                "bundle": ("logs.zip", bundle, "application/zip"),
                "meta": (
                    "meta.json",
                    json.dumps({"installation_id": _installation_id()}),
                    "application/json",
                ),
            }
            with httpx.Client(timeout=60.0, follow_redirects=True) as c:
                r = c.post(LOG_UPLOAD_URL, files=files)
            if r.status_code >= 400:
                return {"ok": False,
                        "error": f"HTTP {r.status_code}: {r.text[:200]}"}
            try:
                data = r.json()
            except Exception:
                data = {}
            return {"ok": True, "reference": data.get("reference", "—")}
        except Exception as e:
            logger.exception("Log upload failed")
            return {"ok": False, "error": str(e)}