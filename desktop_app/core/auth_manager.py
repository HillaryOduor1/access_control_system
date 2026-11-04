# core/auth_manager.py
"""
Enterprise-grade authentication manager with JWT token handling and secure "remember me" session persistence.
"""
import time
import logging
from typing import Optional, Dict, Any, Set, List
from datetime import datetime, timedelta
from jose import jwt, JWTError
from cryptography.fernet import Fernet

from .api_client import APIClient
from config import Config, SecureConfig

logger = logging.getLogger(__name__)


# Keyring identifiers for secure refresh-token storage
KEYRING_SERVICE = "ICTAuthority"
KEYRING_REFRESH_TOKEN = "refresh_token"


class AuthError(Exception):
    """Base exception for authentication errors."""
    pass

class InvalidCredentialsError(AuthError):
    """Invalid username or password."""
    pass

class TokenExpiredError(AuthError):
    """Token has expired."""
    pass


class AuthManager:
    """
    Authentication manager with online/offline support.Handles JWT tokens, permissions, secure session persistence,
    and silent session restoration ("remember me").
    """

    TOKEN_REFRESH_BUFFER_SECONDS = 300  # refresh if <5 min remain

    def __init__(self, api_client: APIClient, db_manager):
        self.api = api_client
        self.db = db_manager
        self.secure_config = SecureConfig()
        self.current_user: Optional[Dict[str, Any]] = None
        self.permissions: Set[str] = set()
        self._token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expiry: Optional[float] = None
        self._failed_attempts: int = 0
        self._max_attempts = 5
        self._locked_until: Optional[float] = None

    # Public API

    def login(self, username: str, password: str, remember_me: bool = False) -> bool:
        """
        Authenticate a user.

        Args:
            username: Username or email
            password: Password
            remember_me: Persist a refresh token for silent re-login

        Returns:
            True if authentication successful

        Raises:
            InvalidCredentialsError: Invalid credentials
            AuthError: Other authentication errors
        """
        if self._is_locked_out():
            logger.warning(f"Login attempt for {username} - account locked")
            raise AuthError("Too many failed attempts. Please try again later.")

        logger.info(f"Login attempt for user: {username}")
        username = username.strip().lower()

        try:
            result = self._online_login(username, password, remember_me)
            if result:
                self._failed_attempts = 0
                self._locked_until = None
                logger.info(f"Login successful for user: {username}")
                return True
        except ConnectionError as e:
            logger.warning(f"Online login failed (offline mode): {e}")
            return self._offline_login(username, password)
        except InvalidCredentialsError:
            self._failed_attempts += 1
            logger.warning(f"Invalid credentials for user: {username}")
            raise
        except Exception as e:
            logger.error(f"Online login error: {e}")
            return self._offline_login(username, password)

        return False

    def try_restore_session(self) -> Optional[Dict[str, Any]]:
        """
        Attempt to silently restore a session using the stored refresh token.

        Returns:
            user_info dict on success, None otherwise
        """
        refresh_token = self._load_stored_refresh_token()
        if not refresh_token:
            logger.debug("No stored refresh token found")
            return None

        logger.info("Attempting silent session restore…")
        try:
            response = self.api.request(
                "POST",
                "/auth/refresh",
                need_auth=False,
                headers={"Authorization": f"Bearer {refresh_token}"},
                timeout=15.0,
            )
        except Exception as e:
            logger.warning(f"Session restore failed: {e}")
            self._clear_stored_refresh_token()
            return None

        access_token = response.get("access_token")
        new_refresh_token = response.get("refresh_token")

        if not access_token:
            logger.warning("Refresh response missing access_token")
            self._clear_stored_refresh_token()
            return None

        self._token = access_token
        self.api.save_token(access_token)

        # Rotate refresh token if server returned a new one
        if new_refresh_token:
            self._refresh_token = new_refresh_token
            self._store_refresh_token(new_refresh_token)

        try:
            payload = self._decode_and_validate_token(access_token)
        except JWTError as e:
            logger.error(f"JWT decode error during restore: {e}")
            self._clear_stored_refresh_token()
            return None

        user_info = self._extract_user_info(payload, payload.get("username", ""))
        self.current_user = user_info
        self.permissions = set(user_info.get("permissions", []))
        self._token_expiry = payload.get("exp", time.time() + 3600)

        self._cache_credentials(user_info.get("username", ""), access_token, user_info)

        logger.info(f"Session restored for {user_info.get('username', 'unknown')}")
        return user_info

    def has_persisted_session(self) -> bool:
        """Check if a refresh token is stored (without using it)."""
        return self._load_stored_refresh_token() is not None

    def logout(self):
        """Log out the current user and clear any persisted session."""
        logger.info("Logging out user")

        # Best-effort backend revocation so the refresh token can't be reused
        refresh_token = self._refresh_token or self._load_stored_refresh_token()
        if refresh_token:
            try:
                self.api.request(
                    "POST",
                    "/auth/logout",
                    need_auth=False,
                    headers={"Authorization": f"Bearer {refresh_token}"},
                    timeout=5.0,
                )
            except Exception as e:
                logger.debug(f"Backend logout failed (non-fatal): {e}")

        # Clear in-memory state
        self.current_user = None
        self.permissions = set()
        self._token = None
        self._refresh_token = None
        self._token_expiry = None

        # Clear secure storage
        self._clear_stored_refresh_token()
        try:
            self.api.clear_token()
        except Exception:
            pass

        # Clear offline credential cache
        if self.db:
            try:
                self.db.clear_user_credentials()
            except Exception as e:
                logger.error(f"Failed to clear cached credentials: {e}")

    # Login internals

    def _online_login(self, username: str, password: str, remember_me: bool) -> bool:
        try:
            response = self.api.request(
                "POST",
                "/auth/login",
                json={"username": username, "password": password},
                need_auth=False,
                timeout=30.0,
            )
        except Exception as e:
            logger.error(f"API request failed: {e}")
            raise ConnectionError(f"Failed to connect to server: {e}")

        access_token = response.get("access_token")
        refresh_token = response.get("refresh_token")

        if not access_token:
            logger.error("No access_token in response")
            raise InvalidCredentialsError("Invalid credentials")

        self._token = access_token
        self.api.save_token(access_token)

        # Store or clear the refresh token depending on the user's choice
        self._refresh_token = refresh_token
        if remember_me and refresh_token:
            self._store_refresh_token(refresh_token)
        elif not remember_me:
            self._clear_stored_refresh_token()

        try:
            payload = self._decode_and_validate_token(access_token)
        except JWTError as e:
            logger.error(f"JWT decode error: {e}")
            raise AuthError("Invalid authentication token")

        user_info = self._extract_user_info(payload, username)
        self.current_user = user_info
        self.permissions = set(user_info.get("permissions", []))
        self._token_expiry = payload.get("exp", time.time() + 3600)

        self._cache_credentials(username, access_token, user_info)

        logger.debug(f"Online login successful for {username}")
        return True

    def _decode_and_validate_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate a JWT.

        Note: In production you should verify the signature with the
        server's public key (RS256). This implementation decodes without
        verification for compatibility with the current backend.
        """
        try:
            payload = jwt.decode(token, key=None, options={"verify_signature": False})

            if "sub" not in payload:
                raise JWTError("Missing subject claim")
            if "exp" not in payload:
                raise JWTError("Missing expiration claim")
            if payload["exp"] < time.time():
                raise JWTError("Token has expired")

            return payload
        except JWTError:
            raise
        except Exception as e:
            raise JWTError(f"Invalid JWT: {e}")

    def _extract_user_info(self, payload: Dict[str, Any], username: str) -> Dict[str, Any]:
        """Extract user information from JWT payload."""
        return {
            "id": payload.get("sub", username),
            "username": payload.get("username", username),
            "full_name": payload.get("full_name", username),
            "email": payload.get("email", ""),
            "roles": payload.get("roles", []),
            "permissions": payload.get("permissions", []),
            "department": payload.get("department", ""),
            "title": payload.get("title", ""),
        }

    def _cache_credentials(self, username: str, token: str, user_info: Dict[str, Any]):
        """Cache credentials for offline use."""
        try:
            self.db.save_user_credentials(
                username,
                token,
                list(user_info.get("permissions", [])),
                user_info,
            )
        except Exception as e:
            logger.error(f"Failed to cache credentials: {e}")

    def _offline_login(self, username: str, password: str) -> bool:
        """Attempt offline authentication using cached credentials."""
        logger.debug(f"Attempting offline login for {username}")

        cached = self.db.get_cached_user(username)
        if not cached:
            logger.warning(f"No cached credentials for {username}")
            raise InvalidCredentialsError("Invalid credentials (offline)")

        token = cached.get("token")
        if not token:
            logger.warning(f"No cached token for {username}")
            raise InvalidCredentialsError("Invalid credentials (offline)")

        try:
            payload = self._decode_and_validate_token(token)
        except JWTError:
            logger.warning(f"Cached token for {username} is invalid")
            raise InvalidCredentialsError("Invalid credentials (offline)")

        user_info = cached.get("user_info", {})
        permissions = cached.get("permissions", [])

        self.current_user = user_info
        self.permissions = set(permissions)
        self._token = token
        self._token_expiry = payload.get("exp")

        logger.info(f"Offline login successful for {username}")
        return True

    def _is_locked_out(self) -> bool:
        """Check if the account is locked out."""
        if self._locked_until:
            if time.time() < self._locked_until:
                return True
            self._locked_until = None
            self._failed_attempts = 0
        return False

    # Token refresh

    def refresh_token(self) -> bool:
        """Refresh the access token using the stored refresh token."""
        refresh_token = self._refresh_token or self._load_stored_refresh_token()
        if not refresh_token:
            logger.debug("No token to refresh")
            return False

        if self._token_expiry:
            remaining = self._token_expiry - time.time()
            if remaining > self.TOKEN_REFRESH_BUFFER_SECONDS and self._token:
                return True

        logger.debug("Refreshing authentication token...")
        try:
            response = self.api.request(
                "POST",
                "/auth/refresh",
                need_auth=False,
                headers={"Authorization": f"Bearer {refresh_token}"},
                timeout=30.0,
            )
        except ConnectionError:
            logger.warning("Token refresh failed - offline")
            return False
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return False

        new_access = response.get("access_token")
        new_refresh = response.get("refresh_token")

        if not new_access:
            logger.warning("Token refresh failed - no new token")
            return False

        self._token = new_access
        self.api.save_token(new_access)

        if new_refresh:
            self._refresh_token = new_refresh
            self._store_refresh_token(new_refresh)

        try:
            payload = self._decode_and_validate_token(new_access)
            self._token_expiry = payload.get("exp")
        except JWTError:
            return False

        logger.debug("Token refreshed successfully")
        return True

    def is_token_valid(self) -> bool:
        """Check if the current token is valid."""
        if not self._token:
            return False

        if self._token_expiry and self._token_expiry < time.time():
            return self.refresh_token()

        return True

    # Permission helpers

    def has_permission(self, permission: str) -> bool:
        if not self.current_user:
            return False
        return permission in self.permissions

    def has_any_permission(self, *permissions: str) -> bool:
        return any(p in self.permissions for p in permissions)

    def has_all_permissions(self, *permissions: str) -> bool:
        return all(p in self.permissions for p in permissions)

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        return self.current_user

    def get_permissions(self) -> Set[str]:
        return self.permissions.copy()

    # Secure refresh-token storage (Windows Credential Manager via keyring)

    def _store_refresh_token(self, token: str) -> None:
        """Store the refresh token in the OS credential store."""
        try:
            import keyring
            keyring.set_password(KEYRING_SERVICE, KEYRING_REFRESH_TOKEN, token)
            logger.debug("Refresh token stored in OS credential manager")
        except Exception as e:
            logger.error(f"Failed to store refresh token: {e}")

    def _load_stored_refresh_token(self) -> Optional[str]:
        """Load the refresh token from the OS credential store."""
        try:
            import keyring
            return keyring.get_password(KEYRING_SERVICE, KEYRING_REFRESH_TOKEN)
        except Exception as e:
            logger.warning(f"Failed to load refresh token: {e}")
            return None

    def _clear_stored_refresh_token(self) -> None:
        """Remove the refresh token from the OS credential store."""
        try:
            import keyring
            keyring.delete_password(KEYRING_SERVICE, KEYRING_REFRESH_TOKEN)
            logger.debug("Refresh token removed from OS credential manager")
        except Exception:
            # keyring raises when the entry doesn't exist — ignore
            pass

    # Password change & reset

    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        if not self.current_user:
            raise AuthError("Not authenticated")

        try:
            response = self.api.request(
                "POST",
                "/auth/change-password",
                json={
                    "username": username,
                    "old_password": old_password,
                    "new_password": new_password,
                },
                need_auth=True,
                timeout=30.0,
            )

            if response.get("success"):
                logger.info(f"Password changed for user: {username}")
                self.db.clear_user_credentials()
                return True
            else:
                logger.warning(f"Password change failed for {username}")
                return False

        except ConnectionError:
            logger.warning("Password change failed - offline")
            raise AuthError("Cannot change password while offline")
        except Exception as e:
            logger.error(f"Password change error: {e}")
            raise AuthError(f"Password change failed: {e}")

    def request_password_reset(self, email: str) -> bool:
        try:
            response = self.api.request(
                "POST",
                "/auth/reset-password",
                json={"email": email},
                need_auth=False,
                timeout=30.0,
            )
            return response.get("success", False)
        except ConnectionError:
            raise AuthError("Cannot request password reset while offline")
        except Exception as e:
            logger.error(f"Password reset request error: {e}")
            return False
