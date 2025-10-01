from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Dict, Any
import requests

from .storage import TokenStore, TokenRecord

# NEW: settings import
from wireloft_config import get_settings  # type: ignore


@dataclass(frozen=True)
class DeviceAuthConfig:
    issuer: str  # e.g., "https://authorize.dailywire.com"
    client_id: str
    scope: str
    device_authorization_endpoint: str
    token_endpoint: str
    audience: Optional[str] = None  # Some IdPs require audience

    @staticmethod
    def from_wireloft() -> "DeviceAuthConfig":
        """
        Build config from wireloft_config.get_settings().dw_oauth and
        conventionally derive device & token endpoints.
        """
        s = get_settings()  # AppSettings
        o = s.dw_oauth      # _OAuthSettings
        issuer = o.issuer.rstrip("/")
        return DeviceAuthConfig(
            issuer=issuer,
            client_id=o.client_id,
            scope=o.scope,
            audience=o.audience,
            device_authorization_endpoint=f"{issuer}/oauth/device/code",
            token_endpoint=f"{issuer}/oauth/token",
        )


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: Optional[str]
    token_type: str
    expires_at: float
    scope: Optional[str] = None


class DeviceAuthClient:
    """
    RFC 8628-compliant device authorization grant.
    """

    def __init__(self, config: Optional[DeviceAuthConfig] = None,
                 store: Optional[TokenStore] = None,
                 session: Optional[requests.Session] = None):
        # Prefer explicit config; otherwise derive from wireloft settings
        self.config = config or DeviceAuthConfig.from_wireloft()
        self.store = store or TokenStore()
        self.session = session or requests.Session()
        self._store_key = self._make_store_key()

    def _make_store_key(self) -> str:
        a = self.config.audience or ""
        return f"{self.config.issuer}|{self.config.client_id}|{a}|{self.config.scope}"

    # ---------- Public API ----------

    def ensure_token(self) -> OAuthTokens:
        rec = self.store.load(self._store_key)
        if rec and rec.expires_at - time.time() > 60:
            return OAuthTokens(**rec.__dict__)

        if rec and rec.refresh_token:
            refreshed = self._refresh(rec.refresh_token)
            if refreshed:
                self.store.save(self._store_key, refreshed)
                return OAuthTokens(**refreshed.__dict__)

        rec = self._device_authorize_interactive()
        self.store.save(self._store_key, rec)
        return OAuthTokens(**rec.__dict__)

    def revoke(self) -> None:
        self.store.delete(self._store_key)

    def start_device_flow(self) -> Dict[str, Any]:
        return self._start_device_flow()

    def poll_until_authorized(self, device_code: str, interval: int, expires_in: int) -> OAuthTokens:
        rec = self._poll_for_token(device_code, interval, expires_in)
        self.store.save(self._store_key, rec)
        return OAuthTokens(**rec.__dict__)

    # ---------- Internals ----------

    def _start_device_flow(self) -> Dict[str, Any]:
        payload = {
            "client_id": self.config.client_id,
            "scope": self.config.scope,
        }
        if self.config.audience:
            payload["audience"] = self.config.audience

        r = self.session.post(self.config.device_authorization_endpoint, data=payload, timeout=30)
        r.raise_for_status()
        j = r.json()
        return {
            "device_code": j["device_code"],
            "user_code": j["user_code"],
            "verification_uri": j["verification_uri"],
            "verification_uri_complete": j.get("verification_uri_complete"),
            "expires_in": int(j["expires_in"]),
            "interval": int(j.get("interval", 5)),
        }

    def _poll_for_token(self, device_code: str, interval: int, expires_in: int) -> TokenRecord | None:
        import time as _t
        start = _t.time()
        current_interval = max(1, interval)
        while True:
            if _t.time() - start > expires_in:
                raise RuntimeError("Device code expired before authorization.")

            data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": self.config.client_id,
            }
            r = self.session.post(self.config.token_endpoint, data=data, timeout=30)
            if r.status_code == 200:
                j = r.json()
                return self._to_record(j)
            else:
                try:
                    e = r.json()
                except Exception:
                    r.raise_for_status()
                    raise

                err = e.get("error")
                if err == "authorization_pending":
                    _t.sleep(current_interval)
                    continue
                elif err == "slow_down":
                    current_interval += 5
                    _t.sleep(current_interval)
                    continue
                elif err == "access_denied":
                    raise PermissionError("User denied the request.")
                elif err == "expired_token":
                    raise RuntimeError("The device_code expired.")
                else:
                    raise RuntimeError(f"Token polling failed: {e}")

    def _device_authorize_interactive(self) -> TokenRecord:
        start = self._start_device_flow()
        print("To authorize, visit:", start["verification_uri"])
        if start.get("verification_uri_complete"):
            print("Or open:", start["verification_uri_complete"])
        print("Enter code:", start["user_code"])
        return self._poll_for_token(start["device_code"], start["interval"], start["expires_in"])

    def _refresh(self, refresh_token: str) -> Optional[TokenRecord]:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.config.client_id,
        }
        r = self.session.post(self.config.token_endpoint, data=data, timeout=30)
        if r.status_code != 200:
            return None
        return self._to_record(r.json(), existing_refresh=refresh_token)

    def _to_record(self, j: Dict[str, Any], existing_refresh: Optional[str] = None) -> TokenRecord:
        import time as _t
        expires_in = int(j.get("expires_in", 3600))
        refresh_token = j.get("refresh_token") or existing_refresh
        return TokenRecord(
            access_token=j["access_token"],
            refresh_token=refresh_token,
            token_type=j.get("token_type", "Bearer"),
            scope=j.get("scope"),
            expires_at=_t.time() + expires_in - 30,
        )
