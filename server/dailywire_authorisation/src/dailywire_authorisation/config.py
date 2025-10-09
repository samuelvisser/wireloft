from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def get_default_config():
    """Lazily load config from wireloft_config """
    from wireloft_config import get_settings
    settings = get_settings()
    return {
        "issuer": settings.dw_oauth.issuer,
        "client_id": settings.dw_oauth.client_id,
        "scope": settings.dw_oauth.scope,
        "audience": settings.dw_oauth.audience,
    }


@dataclass(frozen=True)
class DeviceAuthConfig:
    issuer: str
    client_id: str
    scope: str
    audience: str

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