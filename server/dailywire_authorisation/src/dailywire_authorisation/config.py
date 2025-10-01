from __future__ import annotations

from dataclasses import dataclass

from wireloft_config import get_settings

# Reasonable defaults to allow out-of-the-box usage. These can be overridden
# via CLI flags or environment variables.
DEFAULT_ISSUER = get_settings().dw_oauth.issuer
DEFAULT_AUDIENCE = get_settings().dw_oauth.audience
DEFAULT_CLIENT_ID = get_settings().dw_oauth.client_id
DEFAULT_SCOPE = get_settings().dw_oauth.scope


@dataclass(frozen=True)
class DeviceAuthConfig:
    issuer: str
    audience: str
    client_id: str
    scope: str = DEFAULT_SCOPE


def get_config(
    *,
    issuer: str | None = None,
    audience: str | None = None,
    client_id: str | None = None,
    scope: str | None = None,
) -> DeviceAuthConfig:
    """Load device authorization config from parameters, environment, or defaults.

    Resolution order (highest precedence first):
    1) Explicit function arguments
    2) Environment variables (DAILYWIRE_* first, then generic OAUTH_*):
       - DAILYWIRE_OAUTH_ISSUER or OAUTH_ISSUER
       - DAILYWIRE_OAUTH_AUDIENCE or OAUTH_AUDIENCE
       - DAILYWIRE_OAUTH_CLIENT_ID or OAUTH_CLIENT_ID
       - DAILYWIRE_OAUTH_SCOPE or OAUTH_SCOPE
    3) Built-in reasonable defaults (see constants above)
    """
    iss = (
        issuer
        or DEFAULT_ISSUER
    )
    aud = (
        audience
        or DEFAULT_AUDIENCE
    )
    cid = (
        client_id
        or DEFAULT_CLIENT_ID
    )
    scp = (
        scope
        or DEFAULT_SCOPE
    )

    # Normalize issuer to not end with a trailing slash
    iss = iss.rstrip("/")

    return DeviceAuthConfig(issuer=iss, audience=aud, client_id=cid, scope=scp)
