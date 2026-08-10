# core/auth_manager.py
import time
from jose import jwt
from .api_client import APIClient

class AuthManager:
    def __init__(self, api_client: APIClient, db_manager):
        self.api = api_client
        self.db = db_manager
        self.current_user = None
        self.permissions = set()
        
    def login(self, username, password):
        # Try online first
        try:
            print("[DEBUG] login: sending request to /auth/login")
            # Nb: i need_auth=False because i don't have a token yet
            resp = self.api.request("POST", "/auth/login", json={"username": username, "password": password}, need_auth=False)
            access_token = resp.get("access_token")
            if not access_token:
                print("[DEBUG] login: no access_token in response")
                return False

            print("[DEBUG] login: got access_token, saving...")
            self.api.save_token(access_token)

            # Decode the JWT without verification
            payload = jwt.decode(access_token, key=None, options={"verify_signature": False})
            print(f"[DEBUG] login: Decoded JWT payload: {payload}")

            # Build user info from payload
            user_info = {
                "id": payload.get("sub"),
                "username": payload.get("username", username),
                "full_name": payload.get("full_name", username),
                "email": payload.get("email", ""),
                "roles": payload.get("roles", []),
                "permissions": payload.get("permissions", [])
            }
            print(f"[DEBUG] login: user_info = {user_info}")

            self.current_user = user_info
            self.permissions = set(user_info.get("permissions", []))
            print(f"[DEBUG] login: self.permissions set to {self.permissions}")

            # Cache user and permissions in SQLite for offline use
            self.db.save_user_credentials(
                username, 
                access_token, 
                list(self.permissions),
                user_info
            )
            print("[DEBUG] login: credentials cached")
            return True
            
        except ConnectionError:
            # Offline fallback: check if user exists and token not expired
            print("[DEBUG] login: offline fallback")
            cached = self.db.get_cached_user(username)
            if cached and self._is_token_valid(cached["token"]):
                self.current_user = cached.get("user_info", {})
                self.permissions = set(cached.get("permissions", []))
                print(f"[DEBUG] login: offline - self.permissions set to {self.permissions}")
                return True
            return False
            
    def _is_token_valid(self, token):
        try:
            payload = jwt.decode(token, key=None, options={"verify_signature": False})
            exp = payload.get("exp")
            return exp > time.time()
        except:
            return False
            
    def has_permission(self, permission):
        return permission in self.permissions
