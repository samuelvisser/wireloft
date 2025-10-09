from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from wireloft_config import get_settings


@dataclass(frozen=True)
class DeviceAuthConfig:
    issuer: str = get_settings().dw_oauth.issuer
    client_id: str = get_settings().dw_oauth.client_id
    scope: str = get_settings().dw_oauth.scope
    audience: str = get_settings().dw_oauth.audience

    @property
    def device_authorization_endpoint(self) -> str:
        return f"{self.issuer}/oauth/device/code"

    @property
    def token_endpoint(self) -> str:
        return f"{self.issuer}/oauth/token"


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: Optional[str]
    token_type: str
    expires_at: float
    scope: Optional[str] = None