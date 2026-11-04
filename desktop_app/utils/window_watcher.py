# utils/window_watcher.py
"""
Opt-in Win32 window watcher for diagnosing window flicker and ghost
frames on Windows.

Usage
-----
Add `--watch-windows` to the command line. The watcher will run for 60
seconds and log every visible top-level window owned by this process,
along with its class, title, and geometry. It also enumerates child
windows (many styled QWidgets are promoted to native child HWNDs by Qt
on Windows).

This module is a no-op on non-Windows platforms.

The watcher is deliberately NOT started by default: it spawns a
background thread and writes verbose logs at CRITICAL level. Use it
only when diagnosing a specific flicker issue.
"""
import os
import sys
import threading
import time as _time_module
import logging

logger = logging.getLogger(__name__)


def start_window_watcher(
    logger_: logging.Logger,
    poll_seconds: float = 0.25,
    duration_seconds: float = 60.0,
) -> bool:
    """
    Start a background thread that enumerates visible top-level windows
    and their visible children, owned by this process.

    Returns True if the watcher was started, False otherwise (non-Windows
    or ctypes unavailable).
    """
    if sys.platform != "win32":
        logger_.info("WINDOW WATCHER | skipped (non-Windows platform)")
        return False

    try:
        import ctypes
        import ctypes.wintypes
    except Exception as e:
        logger_.error(f"WINDOW WATCHER | ctypes unavailable: {e}")
        return False

    try:
        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumChildWindows = user32.EnumChildWindows
        GetWindowTextW = user32.GetWindowTextW
        GetClassNameW = user32.GetClassNameW
        GetWindowRect = user32.GetWindowRect
        IsWindowVisible = user32.IsWindowVisible
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        GetParent = user32.GetParent
    except Exception as e:
        logger_.error(f"WINDOW WATCHER | user32 unavailable: {e}")
        return False

    our_pid = os.getpid()

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )

    def _describe(hwnd):
        cls = ctypes.create_unicode_buffer(512)
        GetClassNameW(hwnd, cls, 512)
        txt = ctypes.create_unicode_buffer(512)
        GetWindowTextW(hwnd, txt, 512)
        rect = ctypes.wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        return cls.value, txt.value, (rect.left, rect.top, w, h)

    def _log_all(stage: str):
        tops = []

        def _top_cb(hwnd, lparam):
            try:
                pid = ctypes.wintypes.DWORD()
                GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value != our_pid:
                    return True
                if not IsWindowVisible(hwnd):
                    return True
                tops.append(hwnd)
            except Exception:
                pass
            return True

        try:
            EnumWindows(WNDENUMPROC(_top_cb), 0)
        except Exception as e:
            logger_.error(f"WINDOW WATCHER | EnumWindows failed: {e}")
            return

        for hwnd in tops:
            cls, title, geom = _describe(hwnd)
            logger_.critical(
                f"WIN-TOP [{stage}] hwnd={hwnd} class={cls!r} "
                f"title={title!r} geom={geom}"
            )

            children = []

            def _child_cb(chwnd, lparam):
                try:
                    children.append(chwnd)
                except Exception:
                    pass
                return True

            try:
                EnumChildWindows(hwnd, WNDENUMPROC(_child_cb), 0)
            except Exception as e:
                logger_.error(
                    f"WINDOW WATCHER | EnumChildWindows failed: {e}"
                )
                continue

            for chwnd in children:
                try:
                    if not IsWindowVisible(chwnd):
                        continue
                    ccls, ctitle, cgeom = _describe(chwnd)
                    parent = GetParent(chwnd)
                    logger_.critical(
                        f"WIN-CHILD [{stage}] parent={parent} hwnd={chwnd} "
                        f"class={ccls!r} title={ctitle!r} geom={cgeom}"
                    )
                except Exception:
                    pass

        if not tops:
            logger_.critical(
                f"WIN [{stage}] no visible top-level windows for this process"
            )

    def _worker():
        started = _time_module.time()
        tick = 0
        while _time_module.time() - started < duration_seconds:
            tick += 1
            try:
                _log_all(f"t{tick:04d}")
            except Exception as e:
                logger_.error(f"WINDOW WATCHER | tick failed: {e}")
            _time_module.sleep(poll_seconds)
        logger_.critical("WINDOW WATCHER | stopped")

    t = threading.Thread(target=_worker, daemon=True,
                         name="Win32WindowWatcher")
    t.start()
    logger_.critical(
        f"WINDOW WATCHER | started (poll={poll_seconds}s, "
        f"duration={duration_seconds}s)"
    )
    return True