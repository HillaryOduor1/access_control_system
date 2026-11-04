# core/perf_monitor.py
"""
Periodic performance and resource sampler.

Samples the current process every N seconds and logs CPU, memory, thread
count, and disk I/O to the application log. Values are cheap to read
(two syscalls per sample), so the overhead is negligible.

Usage
-----
Start it once from main.py, after logging is configured:

    from core.perf_monitor import PerfMonitor
    monitor = PerfMonitor(interval_seconds=30)
    monitor.start()

Stop it during shutdown:

    monitor.stop()

Log format
----------
Each sample is one line at INFO level:

    PERF | cpu=2.1% | rss=118.4MB | vms=512.9MB | threads=14 |
           disk_read=0.1MB | disk_write=0.4MB | handles=310

If `psutil` is not installed, the monitor logs a single warning and
disables itself. It never raises and never blocks the GUI thread.

If you want a JSON dump for offline analysis, set env PERF_JSON=1 and
each sample is also written to logs/perf.jsonl as one line per sample.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)


class PerfMonitor(QObject):
    """
    QObject-based sampler. Uses a QTimer so it runs on the GUI thread
    with no extra worker thread and no locking. Each sample is a pair of
    syscalls (process.cpu_times, process.memory_info), fast enough that
    it never affects frame timing.
    """

    def __init__(self, interval_seconds: int = 30, parent=None):
        super().__init__(parent)
        self._interval = max(5, int(interval_seconds))
        self._timer: Optional[QTimer] = None
        self._proc = None
        self._available = False
        self._last_cpu_sample = None
        self._json_path: Optional[Path] = None

        try:
            import psutil  # noqa: F401
            self._psutil = psutil
            self._proc = psutil.Process(os.getpid())
            # Prime the CPU counter so the first delta is meaningful.
            self._proc.cpu_percent(interval=None)
            self._available = True
        except Exception as e:
            logger.warning(
                f"PerfMonitor disabled — psutil not available: {e}"
            )

        # Optional JSONL dump.
        if os.environ.get("PERF_JSON", "") == "1" and self._available:
            try:
                from logging.handlers import RotatingFileHandler
                log_dir = self._detect_log_dir()
                log_dir.mkdir(parents=True, exist_ok=True)
                self._json_path = log_dir / "perf.jsonl"
            except Exception:
                self._json_path = None

    # 

    @staticmethod
    def _detect_log_dir() -> Path:
        """
        Match main.py's LoggingConfig.get_log_dir() so perf.jsonl sits
        next to app_*.log.
        """
        if getattr(sys, "frozen", False):
            if sys.platform == "win32":
                base = Path(os.environ.get("APPDATA", "~"))
            elif sys.platform == "darwin":
                base = Path.home() / "Library" / "Application Support"
            else:
                base = Path.home() / ".local" / "share"
            return base / "ICTAuthority" / "AccessControl" / "logs"
        return Path(os.getcwd()) / "logs"

    # 

    def start(self):
        if not self._available:
            return
        if self._timer is not None:
            return

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._sample)
        self._timer.start(self._interval * 1000)
        # One immediate sample so we know the numbers early.
        self._sample()
        logger.info(
            f"PerfMonitor started (interval={self._interval}s, "
            f"json={'on' if self._json_path else 'off'})"
        )

    def stop(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
            logger.info("PerfMonitor stopped")

    # 

    def _sample(self):
        if not self._available or self._proc is None:
            return
        try:
            with self._proc.oneshot():
                cpu = self._proc.cpu_percent(interval=None)
                mem = self._proc.memory_info()
                num_threads = self._proc.num_threads()

                # Disk I/O counters are not available on all platforms.
                read_mb = write_mb = None
                try:
                    io = self._proc.io_counters()
                    read_mb = io.read_bytes / (1024 * 1024)
                    write_mb = io.write_bytes / (1024 * 1024)
                except Exception:
                    pass

                # Windows handles. Not available on Unix.
                handles = None
                if sys.platform == "win32":
                    try:
                        handles = self._proc.num_handles()
                    except Exception:
                        pass

            rss_mb = mem.rss / (1024 * 1024)
            vms_mb = mem.vms / (1024 * 1024)

            parts = [
                f"cpu={cpu:.1f}%",
                f"rss={rss_mb:.1f}MB",
                f"vms={vms_mb:.1f}MB",
                f"threads={num_threads}",
            ]
            if read_mb is not None:
                parts.append(f"disk_read={read_mb:.1f}MB")
            if write_mb is not None:
                parts.append(f"disk_write={write_mb:.1f}MB")
            if handles is not None:
                parts.append(f"handles={handles}")

            logger.info("PERF | " + " | ".join(parts))

            if self._json_path is not None:
                payload = {
                    "ts": time.time(),
                    "cpu_pct": round(cpu, 2),
                    "rss_mb": round(rss_mb, 2),
                    "vms_mb": round(vms_mb, 2),
                    "threads": num_threads,
                    "disk_read_mb": round(read_mb, 2) if read_mb is not None else None,
                    "disk_write_mb": round(write_mb, 2) if write_mb is not None else None,
                    "handles": handles,
                }
                try:
                    with open(self._json_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(payload) + "\n")
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"PerfMonitor sample failed: {e}")