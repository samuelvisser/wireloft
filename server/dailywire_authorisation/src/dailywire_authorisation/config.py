from __future__ import annotations

from dataclasses import dataclass

from wireloft_config import get_settings


@dataclass(frozen=True)
class DeviceAuthConfig:
    issuer: str = get_settings().dw_oauth.issuer
    audience: str = get_settings().dw_oauth.audience
    client_id: str = get_settings().dw_oauth.client_id
    scope: str = get_settings().dw_oauth.scope