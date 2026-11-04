# core/sync_manager.py
"""
sync manager with conflict resolution and exponential backoff.
"""
from PySide6.QtCore import QThread, Signal, QTimer, QObject
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import json

logger = logging.getLogger(__name__)


class SyncManager(QThread):
    """
    Enterprise sync manager with:
    - Automatic sync scheduling
    - Exponential backoff on failure
    - Conflict resolution
    - Non-blocking operations
    """

    sync_completed = Signal(bool, int)  # success, count
    sync_started = Signal()
    sync_progress = Signal(int, int)  # current, total

    def __init__(self, api_client, db_manager, interval_sec: int = 120):
        super().__init__()
        self.api = api_client
        self.db = db_manager
        self.interval = interval_sec
        self.running = True
        self._paused = False
        self._timer: Optional[QTimer] = None
        self._is_syncing = False
        self._sync_count = 0
        self._last_sync_time: Optional[datetime] = None
        self._backoff_seconds = 0
        self._max_backoff = 300  # 5 minutes max

        # Conflict resolution strategy
        self.conflict_resolution = "server_wins"  # or "client_wins", "manual"

        logger.info(f"SyncManager initialized with interval: {interval_sec}s")

    def run(self):
        """Main thread loop - uses QTimer for event-driven sync."""
        # Create timer with `self` as parent so it is deleted with the
        # thread object rather than leaking or being garbage-collected
        # out from under the event loop.
        self._timer = QTimer()
        self._timer.setParent(self)
        self._timer.timeout.connect(self._do_sync)
        self._timer.setInterval(self.interval * 1000)
        self._timer.start()

        logger.debug("SyncManager thread started")

        # Keep the thread event loop running
        self.exec()

        logger.debug("SyncManager thread stopped")

    def _do_sync(self):
        """Perform sync operation - called by timer."""
        if self._is_syncing or self._paused or not self.running:
            return

        # Check if backoff is active
        if self._backoff_seconds > 0:
            # Wait before retrying
            logger.debug(f"Sync backoff: waiting {self._backoff_seconds}s")
            return

        self._is_syncing = True
        self.sync_started.emit()

        try:
            if self.api.is_online_cached():
                pending = self.db.get_pending_operations()

                if not pending:
                    logger.debug("No pending operations to sync")
                    self.sync_completed.emit(True, 0)
                    self._is_syncing = False
                    # Reset backoff on success
                    self._backoff_seconds = 0
                    return

                self.sync_progress.emit(0, len(pending))
                logger.info(f"Syncing {len(pending)} pending operations")

                success, synced_count = self._sync_operations(pending)

                if success:
                    self.sync_completed.emit(True, synced_count)
                    self._sync_count += synced_count
                    self._last_sync_time = datetime.now()
                    # Reset backoff on success
                    self._backoff_seconds = 0
                    logger.info(f"Sync completed: {synced_count} operations synced")
                else:
                    self.sync_completed.emit(False, 0)
                    # Apply exponential backoff
                    self._apply_backoff()

            else:
                logger.debug("Skipping sync: offline")
                self.sync_completed.emit(False, 0)

        except Exception as e:
            logger.error(f"Sync error: {e}")
            self.sync_completed.emit(False, 0)
            self._apply_backoff()

        self._is_syncing = False

    def _sync_operations(self, pending: List[Dict]) -> tuple:
        """
        Sync pending operations with conflict resolution.

        Returns:
            (success, synced_count)
        """
        synced_ids = []
        failed_ids = []
        synced_count = 0

        for op in pending:
            try:
                # Prepare payload
                payload = {
                    "operation": op["operation"],
                    "collection": op["collection"],
                    "doc_id": op["doc_id"],
                    "data": op["data"]
                }

                # Send to server
                result = self.api.request("POST", "/sync", json=payload)

                if result.get("success"):
                    synced_ids.append(op["id"])
                    synced_count += 1
                    self.sync_progress.emit(synced_count, len(pending))
                else:
                    # Handle conflict
                    conflict = result.get("conflict")
                    if conflict:
                        resolved = self._resolve_conflict(op, conflict)
                        if resolved:
                            synced_ids.append(op["id"])
                            synced_count += 1
                        else:
                            failed_ids.append(op["id"])
                            logger.warning(f"Conflict unresolved for operation {op['id']}")
                    else:
                        failed_ids.append(op["id"])
                        logger.warning(f"Sync failed for operation {op['id']}: {result.get('error', 'Unknown error')}")

            except Exception as e:
                logger.error(f"Error syncing operation {op['id']}: {e}")
                failed_ids.append(op["id"])
                # Don't continue on critical errors
                if "401" in str(e) or "403" in str(e):
                    # Authentication error - stop syncing
                    return False, 0

        # Mark successful operations as synced
        if synced_ids:
            self.db.mark_synced(synced_ids)

        # Increment attempt count for failed operations
        if failed_ids:
            self.db.increment_sync_attempts(failed_ids)

        return True, synced_count

    def _resolve_conflict(self, operation: Dict, conflict: Dict) -> bool:
        """
        Resolve sync conflict based on strategy.

        Returns:
            True if resolved, False if needs manual intervention
        """
        if self.conflict_resolution == "server_wins":
            # Server version is authoritative
            return True

        elif self.conflict_resolution == "client_wins":
            # Client version is authoritative
            # Re-send with force flag
            try:
                payload = {
                    "operation": operation["operation"],
                    "collection": operation["collection"],
                    "doc_id": operation["doc_id"],
                    "data": operation["data"],
                    "force": True
                }
                result = self.api.request("POST", "/sync", json=payload)
                return result.get("success", False)
            except Exception:
                return False

        elif self.conflict_resolution == "manual":
            # Manual resolution - log and skip
            logger.warning(f"Manual conflict resolution required for operation {operation['id']}")
            return False

        return False

    def _apply_backoff(self):
        """Apply exponential backoff for retries."""
        if self._backoff_seconds == 0:
            self._backoff_seconds = 30  # Start with 30 seconds
        else:
            self._backoff_seconds = min(self._backoff_seconds * 2, self._max_backoff)

        # Schedule next sync attempt after backoff
        if self._timer:
            self._timer.setInterval(self._backoff_seconds * 1000)
            logger.debug(f"Sync backoff applied: {self._backoff_seconds}s")

    def stop(self):
        """Stop the sync manager - non-blocking."""
        self.running = False
        self._paused = True

        # Stop timer
        if self._timer:
            try:
                self._timer.stop()
            except Exception:
                pass
            self._timer.deleteLater()
            self._timer = None

        # Quit the thread event loop
        self.quit()

        # Wait for thread to finish (with timeout). If it doesn't stop
        # in time, log a warning and continue — do NOT call terminate()
        # because that can leave locks held and corrupt the DB.
        if not self.wait(2000):
            logger.warning(
                "SyncManager thread did not exit within 2s; "
                "continuing shutdown without terminate()."
            )

        logger.info("SyncManager stopped")

    def pause(self):
        """Pause sync operations."""
        self._paused = True
        logger.debug("SyncManager paused")

    def resume(self):
        """Resume sync operations."""
        self._paused = False
        self._backoff_seconds = 0  # Reset backoff on resume

        # Reset timer to normal interval
        if self._timer:
            self._timer.setInterval(self.interval * 1000)

        logger.debug("SyncManager resumed")

    def sync(self):
        """Manual sync trigger - immediate sync."""
        if self.running and not self._paused and not self._is_syncing:
            # Schedule sync immediately
            QTimer.singleShot(0, self._do_sync)
            logger.debug("Manual sync triggered")
        else:
            logger.debug("Manual sync skipped (not ready)")

    def sync_now(self):
        """Force sync immediately (blocking)."""
        if self.running and not self._is_syncing:
            self._do_sync()

    def get_status(self) -> Dict[str, Any]:
        """Get sync status."""
        return {
            "running": self.running,
            "paused": self._paused,
            "is_syncing": self._is_syncing,
            "last_sync": self._last_sync_time.isoformat() if self._last_sync_time else None,
            "sync_count": self._sync_count,
            "backoff_seconds": self._backoff_seconds,
            "pending_operations": len(self.db.get_pending_operations())
        }

