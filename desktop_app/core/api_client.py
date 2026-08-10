# core/api_client.py
import httpx
from PySide6.QtCore import QObject, Signal
import keyring
import time

class APIClient(QObject):
    connection_changed = Signal(bool)
    
    def __init__(self, base_url="http://localhost:8000"):
        super().__init__()
        self.base_url = base_url
        self.client = httpx.Client(timeout=15.0)  # increased to 15 seconds
        self._online = None
        self._jwt = None
        self.load_token()
        
    def load_token(self):
        self._jwt = keyring.get_password("icta", "access_token")
        print(f"[DEBUG] load_token: {self._jwt[:20] if self._jwt else 'None'}...")
        
    def save_token(self, token):
        self._jwt = token
        keyring.set_password("icta", "access_token", token)
        print(f"[DEBUG] save_token: {token[:20]}...")
        
    def clear_token(self):
        self._jwt = None
        try:
            keyring.delete_password("icta", "access_token")
        except:
            pass
        print("[DEBUG] clear_token: token removed")
        
    def is_online(self, retries=2):
        """Check if backend is reachable with retries."""
        for attempt in range(retries):
            try:
                print(f"[DEBUG] is_online: checking {self.base_url}/health (attempt {attempt+1})")
                resp = self.client.get(f"{self.base_url}/health", timeout=10.0)  # increased to 10s
                online = resp.status_code == 200
                print(f"[DEBUG] is_online: response code {resp.status_code}, online={online}")
                if online:
                    break
            except Exception as e:
                print(f"[DEBUG] is_online: exception: {type(e).__name__}: {e}")
                if attempt < retries - 1:
                    time.sleep(0.5)
                    continue
                online = False
        if online != self._online:
            print(f"[DEBUG] is_online: status changed from {self._online} to {online}")
            self._online = online
            self.connection_changed.emit(online)
        print(f"[DEBUG] is_online: returning {self._online}")
        return self._online
    
    def request(self, method, endpoint, json=None, need_auth=True, params=None):
        print(f"[DEBUG] request: called with method={method}, endpoint={endpoint}, need_auth={need_auth}")
        if not self.is_online():
            print("[DEBUG] request: offline, raising ConnectionError")
            raise ConnectionError("Offline")
        print("[DEBUG] request: online, proceeding")
        headers = {}
        if need_auth:
            if not self._jwt:
                print("[DEBUG] request: no token, raising 401")
                raise httpx.HTTPStatusError("401 Unauthorized - No token", request=None, response=None)
            headers["Authorization"] = f"Bearer {self._jwt}"
            print(f"[DEBUG] request: using token: {self._jwt[:20]}...")
        
        url = f"{self.base_url}{endpoint}"
        print(f"[DEBUG] request: url={url}, params={params}")
        try:
            resp = self.client.request(method, url, json=json, headers=headers, params=params)
            print(f"[DEBUG] request: status={resp.status_code}")
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            print("[DEBUG] request: timeout")
            raise ConnectionError("Request timed out")
        except httpx.HTTPStatusError as e:
            print(f"[DEBUG] request: HTTP error {e.response.status_code}")
            raise


