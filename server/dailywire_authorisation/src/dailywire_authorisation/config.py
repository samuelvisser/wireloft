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

    device_authorization_endpoint: str = f"{issuer}/oauth/device/code"
    token_endpoint: str = f"{issuer}/oauth/token"


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: Optional[str]
    token_type: str
    expires_at: float
    scope: Optional[str] = None