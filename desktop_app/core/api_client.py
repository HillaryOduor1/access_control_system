# core/api_client.py

from __future__ import annotations

import base64
import json as json_module
import logging
import os
import sys
import threading
import time
from typing import Any, Dict, Optional

import httpx
import keyring
from PySide6.QtCore import QObject, QSettings, QTimer, Signal

logger = logging.getLogger(__name__)

# Constants
APP_NAME = "ICTAuthority"
APP_SERVICE = "AccessControl"
TOKEN_KEY = "access_token"

# Deployed fallback URL used when the configured base URL is a localhost address and the local server is unreachable. This mirrors the production deployment of the access-control backend.
DEPLOYED_FALLBACK_URL = "https://icta-access-control-system.onrender.com"

# Health check cadence (seconds). Only used to throttle the timer that calls `_background_health_check()`.
HEALTH_CHECK_INTERVAL_MS = 15000

class CircuitBreaker:
    """
    Circuit breaker pattern to prevent repeated calls to failing services.
    States: CLOSED (working) -> OPEN (failing) -> HALF_OPEN (testing)
    """

    STATE_CLOSED = "CLOSED"
    STATE_OPEN = "OPEN"
    STATE_HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.state = self.STATE_CLOSED
        self.last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        with self._lock:
            if self.state == self.STATE_CLOSED:
                return True
            if self.state == self.STATE_OPEN:
                if (self.last_failure_time
                        and (time.time() - self.last_failure_time)
                        > self.timeout_seconds):
                    self.state = self.STATE_HALF_OPEN
                    logger.info("Circuit breaker: OPEN -> HALF_OPEN")
                    return True
                return False
            # HALF_OPEN: allow one probe through
            return True

    def record_success(self):
        with self._lock:
            self.failure_count = 0
            if self.state == self.STATE_HALF_OPEN:
                self.state = self.STATE_CLOSED
                logger.info("Circuit breaker: HALF_OPEN -> CLOSED")
            elif self.state == self.STATE_OPEN:
                self.state = self.STATE_CLOSED
                logger.info("Circuit breaker: OPEN -> CLOSED")

    def record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state == self.STATE_HALF_OPEN:
                self.state = self.STATE_OPEN
                logger.warning("Circuit breaker: HALF_OPEN -> OPEN")
            elif self.failure_count >= self.failure_threshold:
                self.state = self.STATE_OPEN
                logger.warning(
                    "Circuit breaker: CLOSED -> OPEN (threshold reached)"
                )

    def reset(self):
        with self._lock:
            self.failure_count = 0
            self.state = self.STATE_CLOSED
            self.last_failure_time = None


class APIClient(QObject):
    """
    Enterprise HTTP client.Thread-safety notes
    -------------------
    - `self._jwt` is read and written on the GUI thread AND on worker
      threads. It is only ever assigned atomically (single Python
      reference rebind), which is safe under the GIL.
    - `self._online` is a plain bool. Reads from worker threads see
      the most recently committed value; this is sufficient because
      a stale bool only causes an extra online/offline round trip,
      never a crash.
    - `self._health_suspended` is an integer counter mutated only on
      the GUI thread (from `suspend_health_checks` /
      `resume_health_checks`). Worker threads read it. Reads are
      atomic under the GIL.
    """

    connection_changed = Signal(bool)
    token_expiring = Signal(float)
    token_expired = Signal()

    # Construction

    def __init__(self, base_url: Optional[str] = None):
        super().__init__()
        self.settings = QSettings(APP_NAME, APP_SERVICE)
        self.base_url = base_url or self._load_base_url()
        self._setup_http_client()

        self._online: Optional[bool] = None
        self._jwt: Optional[str] = None
        self._is_shutting_down = False
        self._last_check = 0.0
        self._check_interval = 30  # seconds between non-forced checks
        self._token_expiry: Optional[float] = None
        self._health_suspended: int = 0

        # Re-entrancy guard for health probes. Both the background timer and worker-thread callers can race to call is_online();this flag ensures only one probe runs at a time.
        self._probe_lock = threading.Lock()
        self._probe_in_progress = False

        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3, timeout_seconds=30
        )

        self.load_token()

        # QTimer parented to `self` so it is destroyed with the client.
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._background_health_check)
        self._health_timer.start(HEALTH_CHECK_INTERVAL_MS)

        logger.info(
            f"APIClient initialized with base_url: {self.base_url}"
        )
    
    # Transition safety API
    
    def suspend_health_checks(self):
        """Increment the suspension counter. Health checks are skipped while the counter is non-zero."""
        self._health_suspended += 1
        logger.debug(
            f"Health checks suspended (depth={self._health_suspended})"
        )

    def resume_health_checks(self):
        """
        Decrement the suspension counter. When the counter reaches zero, schedule a background probe. The probe runs on the next event-loop turn, NOT synchronously, so the caller (which is
        typically `MainApp._end_transition` on the GUI thread) is never blocked.
        """
        self._health_suspended = max(0, self._health_suspended - 1)
        logger.debug(
            f"Health checks resumed (depth={self._health_suspended})"
        )

        if self._health_suspended == 0 and not self._is_shutting_down:
            # Defer the probe so the GUI thread is not blocked.
            QTimer.singleShot(0, self._resume_probe)

    def _resume_probe(self):
        """Scheduled probe that runs after resume_health_checks()."""
        if self._is_shutting_down or self.health_checks_suspended:
            return
        try:
            real_state = self.is_online(force_check=True)
            self.connection_changed.emit(real_state)
            logger.info(
                f"Health checks fully resumed; re-emitted online={real_state}"
            )
        except Exception as e:
            logger.debug(f"Failed to re-emit connection state: {e}")

    @property
    def health_checks_suspended(self) -> bool:
        return self._health_suspended > 0

    # HTTP client

    def _setup_http_client(self):
        try:
            transport = httpx.HTTPTransport(
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                    keepalive_expiry=30.0,
                )
            )
        except TypeError:
            logger.warning(
                "HTTPTransport doesn't support keepalive_expiry, "
                "using fallback"
            )
            transport = httpx.HTTPTransport()

        self.client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(
                connect=5.0,
                read=30.0,
                write=30.0,
                pool=5.0,
            ),
            follow_redirects=True,
            verify=True,
        )

    def _load_base_url(self) -> str:
        saved_url = self.settings.value("api_base_url")
        if saved_url:
            return saved_url

        if getattr(sys, "frozen", False):
            env_file = os.path.join(
                os.path.dirname(sys.executable), ".env"
            )
        else:
            env_file = ".env"

        if os.path.exists(env_file):
            try:
                with open(env_file, "r") as f:
                    for line in f:
                        if line.startswith("API_BASE_URL="):
                            return line.split("=", 1)[1].strip()
            except Exception:
                pass

        return "http://localhost:8000"

    def set_base_url(self, url: str):
        """
        Change the API base URL.The next health check is deferred so this method never blocks the caller. If health checks are suspended, no probe is scheduled at all — the resume path will handle it.
        """
        if url == self.base_url:
            return

        self.base_url = url
        self.settings.setValue("api_base_url", url)
        self._online = None
        self.circuit_breaker.reset()
        logger.info(f"Base URL changed to: {url}")

        if not self.health_checks_suspended and not self._is_shutting_down:
            QTimer.singleShot(0, self._background_health_check)

    # Token management

    def load_token(self):
        try:
            self._jwt = keyring.get_password(APP_NAME, TOKEN_KEY)
            if self._jwt:
                self._update_token_expiry()
        except Exception as e:
            logger.warning(f"Failed to load token from keyring: {e}")

    def save_token(self, token: str):
        self._jwt = token
        try:
            keyring.set_password(APP_NAME, TOKEN_KEY, token)
            self._update_token_expiry()
        except Exception as e:
            logger.error(f"Failed to save token to keyring: {e}")

    def clear_token(self):
        self._jwt = None
        self._token_expiry = None
        try:
            keyring.delete_password(APP_NAME, TOKEN_KEY)
        except Exception:
            pass

    def _update_token_expiry(self):
        if not self._jwt:
            return
        try:
            parts = self._jwt.split(".")
            if len(parts) >= 2:
                payload = parts[1]
                payload += "=" * (4 - len(payload) % 4)
                decoded = base64.urlsafe_b64decode(payload)
                data = json_module.loads(decoded)
                exp = data.get("exp")
                if exp:
                    self._token_expiry = exp
                    remaining = exp - time.time()
                    if remaining < 0:
                        self.token_expired.emit()
                    elif remaining < 300:
                        self.token_expiring.emit(remaining)
        except Exception as e:
            logger.debug(f"Failed to parse token expiry: {e}")

    def is_token_valid(self) -> bool:
        if not self._jwt:
            return False
        if self._token_expiry and self._token_expiry < time.time():
            return False
        return True

    def _get_headers(self, need_auth: bool = True) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": f"{APP_NAME}/{APP_SERVICE} (Python/httpx)",
        }
        if need_auth:
            if not self.is_token_valid():
                # Build a synthetic 401. httpx.HTTPStatusError requires a request/response pair; passing None for both is supported by httpx and keeps the message useful.
                raise httpx.HTTPStatusError(
                    "401 Unauthorized - Invalid or expired token",
                    request=None,
                    response=None,
                )
            headers["Authorization"] = f"Bearer {self._jwt}"
        return headers

    # Availability
    
    def is_online(self, force_check: bool = False) -> bool:
        """
        Blocking health check.Safe to call from a worker thread. On the GUI thread, prefer
        `is_online_cached()` unless you explicitly need a fresh probe.Re-entrancy: only one probe runs at a time. Concurrent callers that arrive while a probe is in flight receive the current
        cached value (or False if no probe has ever completed).
        """
        if self._is_shutting_down:
            return False
        if self.health_checks_suspended:
            return False

        current_time = time.time()

        # Serve from cache when a non-forced check is requested and the cached value is still fresh.
        if not force_check and self._online is not None:
            if (current_time - self._last_check) < self._check_interval:
                return self._online

        # Re-entrancy guard.
        if not self._probe_lock.acquire(blocking=False):
            return bool(self._online)

        self._probe_in_progress = True
        try:
            self._last_check = current_time
            online = False

            if not self.circuit_breaker.is_available():
                logger.debug(
                    "Circuit breaker is OPEN, skipping health check"
                )
                self._online = False
                return False

            # Primary probe against the configured base URL.
            try:
                resp = self.client.get(
                    f"{self.base_url}/health",
                    timeout=2.0,
                    headers={
                        "User-Agent": f"{APP_NAME}/{APP_SERVICE}"
                    },
                )
                if resp.status_code == 200:
                    online = True
                    self.circuit_breaker.record_success()
                else:
                    self.circuit_breaker.record_failure()
            except Exception as e:
                logger.debug(f"Health check failed: {e}")
                self.circuit_breaker.record_failure()

            # Fallback probe: only when the primary probe failed AND the configured URL is a localhost address. This avoids the double-probe latency on every offline cycle.
            if not online and "localhost" in self.base_url.lower():
                try:
                    resp = self.client.get(
                        f"{DEPLOYED_FALLBACK_URL}/health",
                        timeout=2.0,
                        headers={
                            "User-Agent": f"{APP_NAME}/{APP_SERVICE}"
                        },
                    )
                    if resp.status_code == 200:
                        online = True
                        self.base_url = DEPLOYED_FALLBACK_URL
                        self.settings.setValue(
                            "api_base_url", DEPLOYED_FALLBACK_URL
                        )
                        logger.info(
                            f"Switched to deployed URL: "
                            f"{DEPLOYED_FALLBACK_URL}"
                        )
                        self.circuit_breaker.record_success()
                except Exception as e:
                    logger.debug(
                        f"Deployed URL health check failed: {e}"
                    )
                    self.circuit_breaker.record_failure()

            if online != self._online:
                self._online = online
                self.connection_changed.emit(online)
                logger.info(
                    f"Connection status changed: "
                    f"{'ONLINE' if online else 'OFFLINE'}"
                )

            return bool(self._online)
        finally:
            self._probe_in_progress = False
            self._probe_lock.release()

    def is_online_cached(self) -> bool:
        """
        Non-blocking online check. Safe from any thread, including the GUI thread and worker threads. Never performs I/O.
        """
        if self._is_shutting_down:
            return False
        if self.health_checks_suspended:
            return False
        return bool(self._online)

    def _background_health_check(self):
        """
        Timer-driven health check. Runs on the GUI thread.The probe itself is short (2 s per endpoint) and only runs when the re-entrancy guard permits. If a previous probe is still in flight, this call returns immediately.
        """
        if self._is_shutting_down:
            return
        if self.health_checks_suspended:
            return
        if self._probe_in_progress:
            return
        self.is_online(force_check=True)

    # Request plumbing

    def _retry_request(
        self,
        method: str,
        url: str,
        max_retries: int = 3,
        **kwargs,
    ) -> httpx.Response:
        """
        Perform an HTTP request with retry/backoff.4xx responses (including 401/403) are returned to the caller WITHOUT retrying, because retrying an authorization failure never succeeds and wastes the user's time.
        """
        last_exception: Optional[Exception] = None
        timeout = kwargs.pop("timeout", 30.0)

        for attempt in range(max_retries):
            try:
                headers = kwargs.get("headers", {}) or {}
                headers["X-Retry-Count"] = str(attempt)
                kwargs["headers"] = headers

                response = self.client.request(
                    method,
                    url,
                    timeout=timeout,
                    **kwargs,
                )

                # Rate limit — respect Retry-After.
                if response.status_code == 429:
                    try:
                        retry_after = int(
                            response.headers.get("Retry-After", 5)
                        )
                    except (TypeError, ValueError):
                        retry_after = 5
                    logger.warning(
                        f"Rate limited. Retry after {retry_after}s"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(min(retry_after, 10))
                        continue
                    return response

                # 4xx other than 429: return to caller. The caller
                # (`request()`) will raise HTTPStatusError.
                if 400 <= response.status_code < 500:
                    self.circuit_breaker.record_success()
                    return response

                # 5xx: retry with backoff.
                if response.status_code >= 500:
                    logger.warning(
                        f"Server error {response.status_code} on "
                        f"attempt {attempt + 1}"
                    )
                    if attempt < max_retries - 1:
                        backoff = (2 ** attempt) + 1
                        time.sleep(backoff)
                        continue
                    # Final attempt failed with 5xx: return so the
                    # caller can raise and record the failure.
                    return response

                # 2xx / 3xx: success.
                self.circuit_breaker.record_success()
                return response

            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning(f"Timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    backoff = (2 ** attempt) + 1
                    time.sleep(backoff)
                    continue
                raise

            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                last_exception = e
                self.circuit_breaker.record_failure()
                self._online = False
                self.connection_changed.emit(False)
                logger.warning(
                    f"Connection error on attempt {attempt + 1}: {e}"
                )
                if attempt < max_retries - 1:
                    backoff = (2 ** attempt) + 1
                    time.sleep(backoff)
                    continue
                raise ConnectionError(
                    f"Failed to connect to server: {e}"
                )

            except Exception as e:
                last_exception = e
                logger.error(f"Request error: {e}")
                if attempt < max_retries - 1:
                    backoff = (2 ** attempt) + 1
                    time.sleep(backoff)
                    continue
                raise

        if last_exception is not None:
            raise last_exception

        # Should be unreachable, but the type checker wants a return.
        raise ConnectionError("Request failed after retries")

    def request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict] = None,
        need_auth: bool = True,
        params: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the API with retry logic.

        This method does NOT pre-check `is_online()`. Doing so would
        perform a blocking health probe before every single request,
        which freezes the GUI whenever a worker thread issues a
        request. Connectivity is determined by the request itself:
        httpx raises ConnectError if the server is unreachable, and
        the caller's error path handles it.
        """
        if self._is_shutting_down:
            raise ConnectionError("Client is shutting down")

        if not self.circuit_breaker.is_available():
            logger.warning(
                "Circuit breaker is OPEN, cannot make request"
            )
            raise ConnectionError(
                "Service unavailable (circuit breaker open)"
            )

        url = f"{self.base_url}{endpoint}"

        caller_supplied_auth = bool(
            headers and "Authorization" in headers
        )

        if caller_supplied_auth:
            merged = self._get_headers(need_auth=False)
            merged.update(headers)
        else:
            merged = self._get_headers(need_auth=need_auth)
            if headers:
                merged.update(headers)

        logger.debug(f"Request: {method} {url}")

        try:
            response = self._retry_request(
                method=method,
                url=url,
                json=json,
                params=params,
                headers=merged,
                timeout=timeout,
                max_retries=max_retries,
            )

            # Successful round-trip — mark online.
            self._online = True
            self.circuit_breaker.record_success()

            if response.status_code == 401:
                if not caller_supplied_auth:
                    self.clear_token()
                    self.token_expired.emit()
                raise httpx.HTTPStatusError(
                    "401 Unauthorized - Token expired",
                    request=response.request,
                    response=response,
                )

            if response.status_code == 403:
                raise httpx.HTTPStatusError(
                    "403 Forbidden - Insufficient permissions",
                    request=response.request,
                    response=response,
                )

            if response.status_code >= 400:
                # Extract the server's error detail so the caller can
                # surface it in a toast or dialog.
                detail = ""
                try:
                    body = response.json()
                    detail = (
                        body.get("detail")
                        or body.get("message")
                        or ""
                    )
                    if isinstance(detail, list):
                        parts = []
                        for item in detail:
                            loc = ".".join(
                                str(x) for x in item.get("loc", [])
                            )
                            msg = item.get("msg", "")
                            parts.append(
                                f"{loc}: {msg}" if loc else msg
                            )
                        detail = "; ".join(parts)
                except Exception:
                    detail = (response.text or "").strip()

                message = f"{response.status_code}"
                if detail:
                    message = f"{response.status_code}: {detail}"

                raise httpx.HTTPStatusError(
                    message,
                    request=response.request,
                    response=response,
                )

            try:
                return response.json()
            except json_module.JSONDecodeError:
                logger.error(f"Invalid JSON response from {url}")
                raise ValueError("Invalid JSON response from server")

        except httpx.HTTPStatusError:
            # 4xx: server is reachable; do NOT trip the breaker.
            logger.error(f"HTTP error from {url}")
            raise

        except ConnectionError:
            self._online = False
            self.connection_changed.emit(False)
            raise

        except Exception as e:
            logger.error(f"Request error: {e}")
            self.circuit_breaker.record_failure()
            raise

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        need_auth: bool = True,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        return self.request(
            "GET",
            endpoint,
            params=params,
            need_auth=need_auth,
            timeout=timeout,
        )

    def post(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        need_auth: bool = True,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        return self.request(
            "POST",
            endpoint,
            json=data,
            need_auth=need_auth,
            timeout=timeout,
        )

    def put(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        need_auth: bool = True,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        return self.request(
            "PUT",
            endpoint,
            json=data,
            need_auth=need_auth,
            timeout=timeout,
        )

    def delete(
        self,
        endpoint: str,
        need_auth: bool = True,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        return self.request(
            "DELETE",
            endpoint,
            need_auth=need_auth,
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self):
        """Idempotent. Safe to call multiple times."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        logger.info("Shutting down API client...")

        if getattr(self, "_health_timer", None) is not None:
            try:
                self._health_timer.stop()
                self._health_timer.deleteLater()
            except Exception:
                pass
            self._health_timer = None

        try:
            if getattr(self, "client", None) is not None:
                self.client.close()
        except Exception as e:
            logger.debug(f"Error closing HTTP client: {e}")

        logger.info("API client shutdown complete")
